# Windows 11 alpha updater. Run from a PowerShell terminal in the checkout:
# powershell -NoProfile -ExecutionPolicy Bypass -File .\update-alpha.ps1
# Creates .venv, verifies dependencies, builds the alpha and updates an existing
# installation in place (or launches first-time setup). Never rewrites photos or Git branches.
param([switch]$DependenciesOnly, [switch]$ProbeTest,
      [switch]$GpuReport, [string]$ReportPath)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

function Invoke-Checked($command, [string[]]$arguments) {
    Write-Host "+ $command $($arguments -join ' ')"
    & $command @arguments
    if ($LASTEXITCODE -ne 0) { throw "$command failed with exit code $LASTEXITCODE" }
}

function Test-Python311($command, [string[]]$prefix) {
    # Windows PowerShell 5.1 treats native stderr as a terminating error when
    # ErrorActionPreference=Stop, even for a harmless failed version probe.
    # Missing runtimes must return false, not abort the whole updater.
    $oldPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $command @prefix -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3,11) else 1)' 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $oldPreference
    }
}

function Find-Python311 {
    $plain = Get-Command python -ErrorAction SilentlyContinue
    if ($plain -and (Test-Python311 -command $plain.Source -prefix @())) { return @($plain.Source) }
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher -and (Test-Python311 -command $launcher.Source -prefix @('-3.11'))) {
        return @($launcher.Source, '-3.11')
    }
    $paths = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'),
        (Join-Path $env:ProgramFiles 'Python311\python.exe')
    )
    foreach ($candidate in $paths) {
        if ((Test-Path $candidate) -and (Test-Python311 -command $candidate -prefix @())) { return @($candidate) }
    }
    return @()
}

function Find-InnoCompiler {
    $iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($iscc -and (Test-Path $iscc.Source)) { return $iscc.Source }

    # winget may install Inno Setup per-user with /CURRENTUSER; that puts it
    # under LocalAppData\Programs, not Program Files. Do not rely on a refreshed
    # PATH in the same shell immediately after installing it.
    $folders = @()
    if ($env:LOCALAPPDATA) {
        $folders += (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6')
        $folders += (Join-Path $env:LOCALAPPDATA 'Inno Setup 6')
    }
    if (${env:ProgramFiles(x86)}) { $folders += (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6') }
    if ($env:ProgramFiles) { $folders += (Join-Path $env:ProgramFiles 'Inno Setup 6') }

    # Inno's own uninstall registration records the installation directory;
    # use it for customized paths and either per-user or machine installations.
    $uninstallKeys = @(
        'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1',
        'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1',
        'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1'
    )
    foreach ($key in $uninstallKeys) {
        $entry = Get-ItemProperty -Path $key -ErrorAction SilentlyContinue
        if ($entry -and $entry.InstallLocation) { $folders += $entry.InstallLocation }
    }
    foreach ($folder in $folders) {
        $candidate = Join-Path $folder 'ISCC.exe'
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    return $null
}

function Find-InstalledEditor {
    # Prefer the user's existing installation. The Inno AppId below must stay
    # stable; its uninstall registration also supports a custom install path.
    $folders = @()
    if ($env:LOCALAPPDATA) { $folders += (Join-Path $env:LOCALAPPDATA 'Programs\Image Switcher') }
    $appId = '{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}_is1'
    $roots = @(
        'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall',
        'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall',
        'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'
    )
    foreach ($rootKey in $roots) {
        $entry = Get-ItemProperty -Path (Join-Path $rootKey $appId) -ErrorAction SilentlyContinue
        if ($entry -and $entry.InstallLocation) { $folders += $entry.InstallLocation }
    }
    foreach ($folder in $folders) {
        $candidate = Join-Path $folder 'ImageSwitcherEditor.exe'
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    return $null
}

function Backup-InstalledProjects([string]$editorPath, [string]$backupRoot) {
    # Only files *inside the existing installed application directory* are at
    # risk during setup. User-selected folders elsewhere are never scanned or
    # moved. Backups live outside the install tree and are never overwritten.
    $installDirectory = Split-Path -Parent $editorPath
    $installFull = [IO.Path]::GetFullPath($installDirectory).TrimEnd([char[]]@('\', '/'))
    $backupFull = [IO.Path]::GetFullPath($backupRoot).TrimEnd([char[]]@('\', '/'))
    if ($backupFull.Equals($installFull, [StringComparison]::OrdinalIgnoreCase) -or
        $backupFull.StartsWith($installFull + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Update stopped: backup destination must be outside the installed application folder.'
    }
    $files = @(Get-ChildItem -LiteralPath $installDirectory -Recurse -File -ErrorAction Stop |
               Where-Object { $_.Extension -in @('.isphoto', '.isbatch') })
    if ($files.Count -eq 0) {
        Write-Host 'No .isphoto/.isbatch files inside the installation; no in-place backup needed.'
        return $null
    }
    $snapshot = Join-Path $backupRoot ("pre-update-{0}-{1}" -f (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ'), [guid]::NewGuid().ToString('N'))
    try {
        foreach ($file in $files) {
            if (($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Cannot safely snapshot a linked project: $($file.FullName)"
            }
            $relative = $file.FullName.Substring($installDirectory.Length).TrimStart([char[]]@('\', '/'))
            $target = Join-Path $snapshot $relative
            New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
            Copy-Item -LiteralPath $file.FullName -Destination $target -ErrorAction Stop
            if ((Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash -ne
                (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash) {
                throw "Backup verification failed for $($file.FullName)"
            }
        }
    } catch {
        if (Test-Path -LiteralPath $snapshot) {
            try { Remove-Item -LiteralPath $snapshot -Recurse -Force } catch { Write-Warning "Incomplete backup at $snapshot needs manual review." }
        }
        throw "Update stopped before setup because the project/session backup failed: $($_.Exception.Message)"
    }
    Write-Host "Snapshot of $($files.Count) installed project/session file(s): $snapshot"
    return $snapshot
}

if ($GpuReport) {
    # Resolve the installed app by its actual location (including custom Inno
    # install paths), not a hardcoded LocalAppData guess. No build or install.
    $installed = Find-InstalledEditor
    if (-not $installed) {
        $built = Join-Path $root 'dist\ImageSwitcherEditor\ImageSwitcherEditor.exe'
        $hint = if (Test-Path -LiteralPath $built -PathType Leaf) {
            "A packaged build exists at $built, but it is NOT an installed app."
        } else { 'No local packaged build was found either.' }
        throw "Installed Image Switcher Editor not found. $hint Run .\update-alpha.ps1 without -DependenciesOnly, finish the first-time installer wizard, and check its final output."
    }
    $destination = if ($ReportPath) {
        $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($ReportPath)
    } else { Join-Path $root 'ui-captures\installed-gpu-report.json' }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
    Write-Host "Checking installed editor: $installed"
    $process = Start-Process -FilePath $installed -ArgumentList @('--gpu-report', ('"{0}"' -f $destination)) -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Installed GPU diagnostic failed with exit code $($process.ExitCode)" }
    if (-not (Test-Path -LiteralPath $destination -PathType Leaf)) {
        throw "Installed editor exited successfully but did not write $destination"
    }
    Write-Host "Installed GPU diagnostic: $destination"
    Get-Content -LiteralPath $destination
    $global:LASTEXITCODE = 0
    return
}

if ($ProbeTest) {
    # CI regression: a launcher writing to stderr and exiting nonzero must be
    # treated as unavailable, not terminate the updater's version search.
    try {
        $available = Get-Command python -ErrorAction Stop
        $errorCode = 'import sys; sys.stderr.write("No matching runtime"); sys.exit(103)'
        if (Test-Python311 -command $available.Source -prefix @('-c', $errorCode)) {
            throw 'Probe incorrectly accepted a missing runtime'
        }
        # Exercise the per-user winget installation path on Windows before
        # Inno Setup is installed by CI. No real compiler is executed here.
        if (-not (Get-Command ISCC.exe -ErrorAction SilentlyContinue)) {
            $oldLocalAppData = $env:LOCALAPPDATA
            $probeRoot = Join-Path $env:TEMP ('image-switcher-inno-probe-' + [guid]::NewGuid().ToString('N'))
            try {
                $env:LOCALAPPDATA = $probeRoot
                $probeFolder = Join-Path $probeRoot 'Programs\Inno Setup 6'
                New-Item -ItemType Directory -Path $probeFolder -Force | Out-Null
                $probeCompiler = Join-Path $probeFolder 'ISCC.exe'
                Set-Content -LiteralPath $probeCompiler -Value 'probe file'
                if ((Find-InnoCompiler) -ne $probeCompiler) {
                    throw 'Per-user Inno Setup compiler was not discovered'
                }
                $installedFolder = Join-Path $probeRoot 'Programs\Image Switcher'
                New-Item -ItemType Directory -Path $installedFolder -Force | Out-Null
                $installedEditor = Join-Path $installedFolder 'ImageSwitcherEditor.exe'
                Set-Content -LiteralPath $installedEditor -Value 'probe file'
                if ((Find-InstalledEditor) -ne $installedEditor) {
                    throw 'Existing per-user editor installation was not discovered'
                }
            } finally {
                $env:LOCALAPPDATA = $oldLocalAppData
                if (Test-Path $probeRoot) { Remove-Item -LiteralPath $probeRoot -Recurse -Force }
            }
        }
        # Test the backup routine without an installer or private user data.
        $probeRoot = Join-Path $env:TEMP ('image-switcher-backup-probe-' + [guid]::NewGuid().ToString('N'))
        try {
            $fakeInstall = Join-Path $probeRoot 'installed'
            $nested = Join-Path $fakeInstall 'my-edits'
            New-Item -ItemType Directory -Path $nested -Force | Out-Null
            $fakeEditor = Join-Path $fakeInstall 'ImageSwitcherEditor.exe'
            Set-Content -LiteralPath $fakeEditor -Value 'fake binary'
            Set-Content -LiteralPath (Join-Path $nested 'test.isphoto') -Value 'project bytes'
            Set-Content -LiteralPath (Join-Path $fakeInstall 'test.isbatch') -Value 'session bytes'
            Set-Content -LiteralPath (Join-Path $fakeInstall 'ordinary.txt') -Value 'unrelated'
            $snapshot = Backup-InstalledProjects -editorPath $fakeEditor -backupRoot (Join-Path $probeRoot 'backups')
            if (-not (Test-Path -LiteralPath (Join-Path $snapshot 'my-edits\test.isphoto'))) {
                $found = @(Get-ChildItem -LiteralPath $snapshot -Recurse -File | ForEach-Object { $_.FullName })
                throw "Nested project missing from backup. Found: $($found -join '; ')"
            }
            if ((Get-Content -LiteralPath (Join-Path $snapshot 'my-edits\test.isphoto') -Raw) -ne
                (Get-Content -LiteralPath (Join-Path $nested 'test.isphoto') -Raw)) {
                throw 'Project snapshot bytes differ'
            }
            if ((Get-Content -LiteralPath (Join-Path $snapshot 'test.isbatch') -Raw) -ne
                (Get-Content -LiteralPath (Join-Path $fakeInstall 'test.isbatch') -Raw)) {
                throw 'Session snapshot bytes differ'
            }
            if (Test-Path -LiteralPath (Join-Path $snapshot 'ordinary.txt')) {
                throw 'Unrelated installation file was backed up'
            }
            try {
                Backup-InstalledProjects -editorPath $fakeEditor -backupRoot (Join-Path $fakeInstall 'backups') | Out-Null
                throw 'Backup unexpectedly allowed inside the installation folder'
            } catch {
                if ($_.Exception.Message -notmatch 'outside the installed application') { throw }
            }
        } finally {
            if (Test-Path -LiteralPath $probeRoot) { Remove-Item -LiteralPath $probeRoot -Recurse -Force }
        }
        Write-Host 'Missing-runtime, per-user compiler and scoped project-backup probes passed.'
        # Actions' PowerShell wrapper exits with LASTEXITCODE even if a failed
        # native probe was intentional and this script returned normally.
        $global:LASTEXITCODE = 0
        return
    } catch {
        Write-Host "::error file=update-alpha.ps1,line=59::$($_.Exception.Message)"
        throw
    }
}

Push-Location $root
try {
    $python = @(Find-Python311)
    if ($python.Count -eq 0) {
        $launcher = Get-Command py -ErrorAction SilentlyContinue
        if ($launcher) {
            # The newer Python install manager recommends exactly this command
            # when `py -3.11` has no runtime. Legacy launchers may reject it.
            try {
                Write-Host 'Installing Python 3.11 via the Python launcher...'
                Invoke-Checked $launcher.Source @('install', '3.11')
            } catch {
                Write-Warning "Python launcher install was unavailable: $($_.Exception.Message)"
            }
            $python = @(Find-Python311)
        }
    }
    if ($python.Count -eq 0) {
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
            throw 'Python 3.11 is missing. Run py install 3.11 or install Python 3.11 from python.org, reopen PowerShell, then rerun. winget is unavailable.'
        }
        Write-Host 'Installing Python 3.11 for this Windows user via winget...'
        Invoke-Checked 'winget' @('install', '-e', '--id', 'Python.Python.3.11', '--scope', 'user', '--silent', '--accept-package-agreements', '--accept-source-agreements')
        $python = @(Find-Python311)
        if ($python.Count -eq 0) { throw 'Python was installed but not discoverable yet. Reopen PowerShell and rerun this script.' }
    }
    $pythonExe = $python[0]
    $pythonPrefix = @($python | Select-Object -Skip 1)
    Invoke-Checked $pythonExe ($pythonPrefix + @('scripts/update_alpha.py'))
    if ($DependenciesOnly) {
        Write-Host 'Dependencies and tests are ready. Skipped packaging and desktop setup (-DependenciesOnly).'
        return
    }

    $installedBefore = Find-InstalledEditor
    if ($installedBefore) {
        if (Get-Process -Name 'ImageSwitcherEditor' -ErrorAction SilentlyContinue) {
            throw 'Close Image Switcher Editor before updating it, then run this script again. Your projects are not affected.'
        }
        Write-Host "Existing editor found at $installedBefore. Preparing an in-place UPDATE..."
    } else {
        Write-Host 'No existing editor installation found. Preparing first-time setup...'
    }

    $venvPython = Join-Path $root '.venv\Scripts\python.exe'
    Invoke-Checked $venvPython @('build_editor.py')  # windowed, no console
    $editor = Join-Path $root 'dist\ImageSwitcherEditor\ImageSwitcherEditor.exe'
    $smoke = Start-Process -FilePath $editor -ArgumentList '--editor-self-test' -Wait -PassThru
    if ($smoke.ExitCode -ne 0) { throw "Packaged editor smoke test failed: $($smoke.ExitCode)" }
    $compiler = Find-InnoCompiler
    if (-not $compiler) {
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
            throw 'Inno Setup 6 is needed to build the installer. Install it, then rerun (winget is unavailable).'
        }
        Write-Host 'Installing Inno Setup 6 via winget...'
        Invoke-Checked 'winget' @('install', '-e', '--id', 'JRSoftware.InnoSetup', '--silent', '--accept-package-agreements', '--accept-source-agreements')
        $compiler = Find-InnoCompiler
        if (-not $compiler) { throw 'Inno Setup installed, but ISCC.exe could not be located in per-user/system program folders or uninstall registration. Locate ISCC.exe and share its full path; do not reinstall Inno repeatedly.' }
    }
    Invoke-Checked $compiler @('installer.iss')
    $setup = Join-Path $root 'dist\ImageSwitcher-Setup-0.2.0-alpha.7.exe'
    if (-not (Test-Path $setup)) { throw "Alpha setup was not produced: $setup" }
    if ($installedBefore) {
        # Snapshot user-created projects/sessions *under the installed app* to
        # a separate user-data directory; abort before running setup on any
        # read/copy/checksum failure. External exports stay where the user put
        # them and are not needlessly duplicated.
        $snapshot = Backup-InstalledProjects -editorPath $installedBefore -backupRoot (Join-Path $env:LOCALAPPDATA 'Image Switcher\UpdateBackups')
        # The stable Inno AppId reuses the prior directory/uninstaller. /SILENT
        # shows progress but avoids a second first-install wizard.
        Write-Host 'Updating your existing Image Switcher Alpha in place...'
        $process = Start-Process -FilePath $setup -ArgumentList @('/SILENT', '/NORESTART', '/SUPPRESSMSGBOXES') -Wait -PassThru
        if ($process.ExitCode -ne 0) { throw "Update failed with status $($process.ExitCode)" }
        $installedAfter = Find-InstalledEditor
        if (-not $installedAfter -or $installedAfter -ne $installedBefore) {
            throw 'Update finished but the existing installation could not be verified at its previous path.'
        }
        $smoke = Start-Process -FilePath $installedAfter -ArgumentList '--editor-self-test' -Wait -PassThru
        if ($smoke.ExitCode -ne 0) { throw "Updated editor verification failed: $($smoke.ExitCode)" }
        Write-Host "UPDATED in place to 0.2.0-alpha.7: $installedAfter"
        if ($snapshot) { Write-Host "Verified pre-update project/session backup: $snapshot" }
        Write-Host 'Your originals and files stored outside the installation were not touched.'
    } else {
        Write-Warning 'The alpha setup is UNSIGNED and not validated on a clean Windows 11 machine. Continue only if you trust this checkout.'
        $process = Start-Process -FilePath $setup -Wait -PassThru
        if ($process.ExitCode -ne 0) { throw "First-time setup exited with status $($process.ExitCode)" }
        $installedAfter = Find-InstalledEditor
        if (-not $installedAfter) {
            throw 'Setup exited, but no installed ImageSwitcherEditor.exe was found. Check whether the installer wizard completed; the packaged build in dist is NOT the installed app.'
        }
        $smoke = Start-Process -FilePath $installedAfter -ArgumentList '--editor-self-test' -Wait -PassThru
        if ($smoke.ExitCode -ne 0) { throw "Installed editor verification failed: $($smoke.ExitCode)" }
        Write-Host "INSTALLED 0.2.0-alpha.7 at $installedAfter. Open Image Switcher from the Start menu."
    }
} finally {
    Pop-Location
}
