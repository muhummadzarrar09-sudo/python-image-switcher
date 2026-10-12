# Windows 11 alpha updater. Run from a PowerShell terminal in the checkout:
# powershell -NoProfile -ExecutionPolicy Bypass -File .\update-alpha.ps1
# Creates .venv, installs Python dependencies, tests, builds and launches
# the unsigned alpha installer. It never rewrites source photos or Git branches.
param([switch]$DependenciesOnly, [switch]$ProbeTest)
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
            } finally {
                $env:LOCALAPPDATA = $oldLocalAppData
                if (Test-Path $probeRoot) { Remove-Item -LiteralPath $probeRoot -Recurse -Force }
            }
        }
        Write-Host 'Missing-runtime and per-user compiler probes handled safely.'
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
        Write-Host 'Dependencies and tests are ready. Skipped packaging and desktop installation (-DependenciesOnly).'
        return
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
    $setup = Join-Path $root 'dist\ImageSwitcher-Setup-0.2.0-alpha.1.exe'
    if (-not (Test-Path $setup)) { throw "Alpha installer was not produced: $setup" }
    Write-Warning 'The alpha installer is UNSIGNED and not validated on a clean Windows 11 machine. Continue only if you trust this checkout.'
    $process = Start-Process -FilePath $setup -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Installer exited with status $($process.ExitCode)" }
    Write-Host 'Alpha installer completed. Open Image Switcher from the Start menu.'
} finally {
    Pop-Location
}
