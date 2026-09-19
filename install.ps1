<#
.SYNOPSIS
    Python Image Switcher - Windows Installer (PowerShell)

.DESCRIPTION
    Installs Python Image Switcher on Windows with NO extra tools required
    (no Inno Setup, no winget). Works on Windows PowerShell 5.1 (built into
    Windows) and PowerShell 7+.

    Where the app comes from (pick ONE, or none to auto-detect):

      Local build, onefile     :  -SourceExe .\dist\ImageSwitcher.exe
      Local build, onedir      :  -SourceDir .\dist\ImageSwitcher
      Download from the web    :  -ReleaseUrl "https://.../ImageSwitcher.exe"
      Latest GitHub release    :  -Release

    If you run this straight from a fresh PyInstaller build (repo root), it
    auto-detects dist\ImageSwitcher.exe or dist\ImageSwitcher\ and installs
    that, so after "python build_exe.py --onefile" a bare ".\install.ps1"
    just works.

    By default this is a PER-USER install into
      %LOCALAPPDATA%\Programs\Image Switcher
    which needs no admin rights. Use -MachineScope to install for all users
    into C:\Program Files (a UAC elevation prompt appears when needed).

    What the installer does:
      * verifies the source EXE (optional -Sha256, strongly recommended)
      * upgrades an existing install with a timestamped backup
      * copies the app into the install folder
      * creates Desktop + Start Menu shortcuts
      * registers an uninstall entry (visible in Settings > Apps)
      * writes Uninstall-ImageSwitcher.ps1 / .bat into the install folder
      * optionally registers file associations (-FileAssociations)
      * launches the app when finished (-NoLaunch to skip)

    Typical usage:

      powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
      powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -SourceExe .\dist\ImageSwitcher.exe -FileAssociations
      powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -ReleaseUrl "https://github.com/muhummadzarrar09-sudo/python-image-switcher/releases/download/v1.0.0/ImageSwitcher.exe" -Sha256 0123ABCD... -MachineScope

.PARAMETER SourceExe
    Path to a one-file PyInstaller build, e.g. .\dist\ImageSwitcher.exe

.PARAMETER SourceDir
    Path to a onedir PyInstaller build folder, e.g. .\dist\ImageSwitcher

.PARAMETER ReleaseUrl
    Direct URL of a prebuilt EXE to download and install (usually a GitHub
    release asset).

.PARAMETER Release
    Download the latest release EXE from the project's GitHub releases page.
    Requires a published release with an "ImageSwitcher.exe" asset.

.PARAMETER Sha256
    Expected SHA-256 checksum (hex) of the EXE. Verified for downloads AND
    local sources alike. The install is refused on a mismatch.

.PARAMETER InstallDir
    Custom install folder.
    Default: %LOCALAPPDATA%\Programs\Image Switcher
             (or %ProgramFiles%\Image Switcher with -MachineScope)

.PARAMETER MachineScope
    Install for all users into C:\Program Files. Prompts for admin rights.

.PARAMETER NoDesktopIcon
    Do not create a Desktop shortcut.

.PARAMETER NoStartMenu
    Do not create a Start Menu shortcut.

.PARAMETER NoLaunch
    Do not launch the app after installing.

.PARAMETER FileAssociations
    Register Image Switcher for common image extensions (PNG, JPG, WEBP, ...)
    so you can open image files with it via double-click / "Open with".

.PARAMETER NoBackup
    When upgrading, do not keep a backup copy of the previous install.

.PARAMETER Force
    No prompts. Overwrites an existing install without asking.

.PARAMETER Quiet
    For scripts / CI. Implies -Force, -NoLaunch and -NoBackup.

.PARAMETER Version
    Version string for the uninstall entry.
    Default: read from pyproject.toml, else 1.0.0.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1

.EXAMPLE
    .\install.ps1 -SourceDir .\dist\ImageSwitcher -FileAssociations -MachineScope

.NOTES
    Uninstall via Settings > Apps > Installed apps > Image Switcher > Uninstall,
    or run Uninstall-ImageSwitcher.bat from the install folder.
#>
[CmdletBinding()]
param(
    [string]$SourceExe,
    [string]$SourceDir,
    [string]$ReleaseUrl,
    [switch]$Release,
    [string]$Sha256,
    [string]$InstallDir,
    [switch]$MachineScope,
    [switch]$NoDesktopIcon,
    [switch]$NoStartMenu,
    [switch]$NoLaunch,
    [switch]$FileAssociations,
    [switch]$ContextMenu,
    [switch]$NoBackup,
    [switch]$Force,
    [switch]$Quiet,
    [string]$Version
)

$ErrorActionPreference = 'Stop'

# ================================================================ constants
$AppName        = 'Image Switcher'
$ExeName        = 'ImageSwitcher.exe'
$Publisher      = 'Image Switcher Team'
$RepoUrl        = 'https://github.com/muhummadzarrar09-sudo/python-image-switcher'
$UninstallKey   = "Software\Microsoft\Windows\CurrentVersion\Uninstall\PythonImageSwitcher"
$DefaultVersion = '1.0.0'
$ScriptRoot     = $PSScriptRoot
$AssocExts      = @('png','jpg','jpeg','webp','gif','bmp','tiff','tif','ico','avif','heif','heic','svg')

if (-not $ScriptRoot) { $ScriptRoot = (Get-Location).Path }
if ($Quiet) { $Force = $true; $NoLaunch = $true; $NoBackup = $true }

# $PSBoundParameters inside a function refers to the FUNCTION's own
# parameters, so snapshot the script-level ones for the elevation re-launch.
$script:BoundParams = $PSBoundParameters

# ================================================================ helpers
function Write-Step($msg)  { Write-Host "  >  $msg" -ForegroundColor Cyan }
function Write-Ok($msg)    { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn($msg)  { Write-Host "  [!!] $msg" -ForegroundColor Yellow }
function Write-Err($msg)   { Write-Host "  [XX] $msg" -ForegroundColor Red }

function Test-IsAdministrator {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($id)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# Re-runs this same script elevated (UAC) with all parameters preserved.
function Invoke-ElevatedRelaunch {
    $parts = @('-NoProfile','-ExecutionPolicy','Bypass','-File',"`"$PSCommandPath`"")
    foreach ($key in ($script:BoundParams.Keys | Sort-Object)) {
        $value = $script:BoundParams[$key]
        if ($value -is [System.Management.Automation.SwitchParameter]) {
            if ($value.IsPresent) { $parts += "-$key" }
        }
        elseif ($null -ne $value -and "$value" -ne '') {
            $escaped = "$value" -replace '"','\"'
            $parts += "-$key", "`"$escaped`""
        }
    }
    Write-Warn 'Machine-wide install needs admin rights - a UAC prompt will appear.'
    Start-Process -FilePath 'powershell.exe' -ArgumentList ($parts -join ' ') -Verb RunAs
    Write-Host '  Elevated installer started in a new window. This window can be closed.' -ForegroundColor DarkGray
    exit 0
}

# Ask y/n, honoring -Force (always answers the default).
function Read-Confirm([string]$Message, [bool]$DefaultYes = $true) {
    if ($Force) { return $DefaultYes }
    $suffix = if ($DefaultYes) { ' [Y/n] ' } else { ' [y/N] ' }
    $reply = ''
    try { $reply = Read-Host ($Message + $suffix) }
    catch { $reply = '' }   # non-interactive: take the default
    if ($reply -eq '') { return $DefaultYes }
    return ($reply -match '^[Yy]')
}

function Test-Checksum([string]$Path, [string]$Expected) {
    if (-not $Expected) { return }
    Write-Step "Verifying SHA-256 checksum of $(Split-Path $Path -Leaf)"
    $actual = (Get-FileHash -Path $Path -Algorithm SHA256).Hash
    if ($actual -ieq $Expected) {
        Write-Ok "Checksum verified ($actual)"
    }
    else {
        Write-Err 'Checksum MISMATCH - refusing to install an unverified file.'
        Write-Host "      expected: $Expected"
        Write-Host "      actual  : $actual"
        exit 1
    }
}

function Invoke-Download([string]$Uri, [string]$Dest) {
    [Net.ServicePointManager]::SecurityProtocol =
        [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    Write-Step "Downloading $Uri"
    try {
        Invoke-WebRequest -Uri $Uri -OutFile $Dest -UseBasicParsing
    }
    catch {
        Write-Err "Download failed: $($_.Exception.Message)"
        if ("$($_.Exception.Message)" -match '404|Not Found|NotFound') {
            Write-Host '      Check that a release with an "ImageSwitcher.exe" asset exists at that URL.'
        }
        exit 1
    }
    $sizeMb = [math]::Round((Get-Item $Dest).Length / 1MB, 1)
    Write-Ok "Downloaded ($sizeMb MB) -> $Dest"
}

function New-ShortcutFile([string]$LnkPath, [string]$Target, [string]$WorkDir, [string]$Icon) {
    $wsh = New-Object -ComObject WScript.Shell
    $lnk = $wsh.CreateShortcut($LnkPath)
    $lnk.TargetPath = $Target
    $lnk.WorkingDirectory = $WorkDir
    if ($Icon -and (Test-Path $Icon)) { $lnk.IconLocation = "$Icon,0" }
    $lnk.Description = "$AppName $Version - Universal Image Converter"
    $lnk.Save()
}

# ================================================================ banner + checks
function Show-Banner {
    Write-Host ''
    Write-Host '  ==============================================================' -ForegroundColor DarkGray
    Write-Host '    Python Image Switcher - Windows Installer' -ForegroundColor White
    $scope = if ($MachineScope) { 'machine-wide (all users)' } else { 'per-user (no admin needed)' }
    Write-Host ("    version {0}   |   {1}" -f $Version, $scope) -ForegroundColor DarkGray
    Write-Host '  ==============================================================' -ForegroundColor DarkGray
    Write-Host ''
}

# Top-level error handling
trap {
    Write-Host ''
    Write-Err "Installer failed: $($_.Exception.Message)"
    Write-Host '      The install has been stopped. Fix the issue above and re-run the installer.'
    exit 1
}

# 1) Platform checks
if ($env:OS -ne 'Windows_NT') {
    Write-Err 'This installer is for Windows only.'
    Write-Host '      On macOS / Linux, run the app directly with Python (see README.md).'
    exit 1
}
if ([IntPtr]::Size -ne 8) {
    Write-Warn '32-bit Windows detected. PyInstaller EXEs are normally built for 64-bit and may not run here.'
    if (-not (Read-Confirm 'Continue anyway?' $false)) { exit 0 }
}
$osv = [System.Environment]::OSVersion
if ($osv.Version.Major -lt 10) {
    Write-Warn "This installer targets Windows 10/11 (detected Windows build $($osv.Version.Build))."
    if (-not (Read-Confirm 'Continue anyway?' $false)) { exit 0 }
}

# 2) Version (explicit > pyproject.toml > default)
if (-not $Version) {
    $pyproject = Join-Path $ScriptRoot 'pyproject.toml'
    if (Test-Path $pyproject) {
        $m = [regex]::Match((Get-Content $pyproject -Raw -ErrorAction SilentlyContinue), '(?m)^version\s*=\s*"([^"]+)"')
        if ($m.Success) { $Version = $m.Groups[1].Value }
    }
}
if (-not $Version) { $Version = $DefaultVersion }

# 3) Install location
if (-not $InstallDir) {
    if ($MachineScope) {
        $InstallDir = Join-Path $env:ProgramFiles $AppName
    }
    else {
        $InstallDir = Join-Path (Join-Path $env:LOCALAPPDATA 'Programs') $AppName
    }
}
$InstallDir = $InstallDir.TrimEnd('\','/')
$TargetExe = Join-Path $InstallDir $ExeName

Show-Banner

# 4) Machine-wide needs admin -> relaunch elevated if required
if ($MachineScope -and -not (Test-IsAdministrator)) {
    Invoke-ElevatedRelaunch
}

# ================================================================ step 1: source
Write-Step "Step 1/7 - Preparing source"

$srcCount = @()
if ($ReleaseUrl) { $srcCount += 'ReleaseUrl' }
if ($Release)    { $srcCount += 'Release' }
if ($SourceExe)  { $srcCount += 'SourceExe' }
if ($SourceDir)  { $srcCount += 'SourceDir' }
if ($srcCount.Count -gt 1) {
    Write-Err "Only ONE of -ReleaseUrl / -Release / -SourceExe / -SourceDir may be used (got: $($srcCount -join ', '))."
    exit 1
}

$srcFile = $null     # single EXE to install (onefile or downloaded)
$srcFolder = $null   # folder to install (onedir build)
$removeAfter = $null # temp file to delete when done

if ($ReleaseUrl -or $Release) {
    if ($Release -and -not $ReleaseUrl) {
        $ReleaseUrl = "$RepoUrl/releases/latest/download/$ExeName"
    }
    $tmpExe = Join-Path $env:TEMP "ImageSwitcher-dl-$([guid]::NewGuid().ToString('N')).exe"
    Invoke-Download -Uri $ReleaseUrl -Dest $tmpExe
    Test-Checksum -Path $tmpExe -Expected $Sha256
    if (-not $Sha256) { Write-Warn 'No -Sha256 given - the download was NOT checksum-verified.' }
    $srcFile = $tmpExe
    $removeAfter = $tmpExe
}
elseif ($SourceExe) {
    if (-not (Test-Path $SourceExe)) {
        Write-Err "Source EXE not found: $SourceExe"
        Write-Host '      Build one first:  python build_exe.py --onefile'
        exit 1
    }
    Test-Checksum -Path $SourceExe -Expected $Sha256
    $srcFile = (Resolve-Path $SourceExe).Path
    Write-Ok "Using local build: $srcFile"
}
elseif ($SourceDir) {
    if (-not (Test-Path (Join-Path $SourceDir $ExeName))) {
        Write-Err "No $ExeName found in: $SourceDir"
        Write-Host '      Build one first:  python build_exe.py --onedir'
        exit 1
    }
    $srcFolder = (Resolve-Path $SourceDir).Path
    Write-Ok "Using local build folder: $srcFolder"
}
else {
    # Auto-detect a PyInstaller build next to this script (repo root)
    $candExe = Join-Path $ScriptRoot "dist\$ExeName"
    $candDir = Join-Path $ScriptRoot 'dist\ImageSwitcher'
    if (Test-Path $candExe) {
        $srcFile = $candExe
        Write-Ok "Auto-detected build: $candExe"
    }
    elseif (Test-Path (Join-Path $candDir $ExeName)) {
        $srcFolder = $candDir
        Write-Ok "Auto-detected build folder: $candDir"
    }
    else {
        Write-Err 'No build found to install.'
        Write-Host '      Build one first:'
        Write-Host '          python build_exe.py --onefile'
        Write-Host '      then re-run this script (or pass -SourceExe / -SourceDir / -ReleaseUrl).'
        exit 1
    }
}

# ================================================================ step 2: existing install / backup
Write-Step "Step 2/7 - Checking for an existing installation"

$regRoot = if ($MachineScope) { 'HKLM' } else { 'HKCU' }
$regKey = "${regRoot}:\$UninstallKey"
$existingInfo = $null
if (Test-Path $regKey) {
    $existingInfo = Get-ItemProperty $regKey
}
$installExists = Test-Path $TargetExe

if ($installExists -or $existingInfo) {
    $oldVer = 'unknown'
    if ($existingInfo -and $existingInfo.DisplayVersion) { $oldVer = $existingInfo.DisplayVersion }
    Write-Warn "Existing installation found (version $oldVer) at: $InstallDir"
    if (-not (Read-Confirm "Upgrade over it and keep a backup of the current files?" $true)) {
        Write-Host ''
        Write-Host '  Install cancelled.' -ForegroundColor Yellow
        exit 0
    }
}
else {
    Write-Ok 'No previous installation found - fresh install.'
}

# Close a running app so files are not locked
$running = Get-Process -Name 'ImageSwitcher' -ErrorAction SilentlyContinue
if ($running) {
    Write-Warn 'Image Switcher is still running - closing it now.'
    $running | Stop-Process -Force
    Start-Sleep -Seconds 1
}

# Backup of the old install
$backupPath = $null
if ($installExists -and -not $NoBackup) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $backupPath = "${InstallDir}-backup-$stamp"
    try {
        Move-Item -Path $InstallDir -Destination $backupPath -Force
        Write-Ok "Old install backed up to: $backupPath"
    }
    catch {
        Write-Err "Could not move the old install aside: $($_.Exception.Message)"
        Write-Host '      If Image Switcher is running, close it and re-run.'
        exit 1
    }
}

# ================================================================ step 3: copy files
Write-Step "Step 3/7 - Copying files to $InstallDir"

try {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}
catch {
    Write-Err "Cannot create install folder: $InstallDir"
    if (-not $MachineScope) {
        Write-Host '      That location needs admin rights. Re-run with -MachineScope,'
        Write-Host '      or pick another location with -InstallDir "C:\some\writable\folder".'
    }
    exit 1
}

try {
    if ($srcFile) {
        Copy-Item -Path $srcFile -Destination $TargetExe -Force
        # Ship license + readme alongside the EXE when available
        foreach ($extra in @('LICENSE.txt', 'README.md')) {
            $srcExtra = Join-Path $ScriptRoot $extra
            if (Test-Path $srcExtra) {
                Copy-Item -Path $srcExtra -Destination $InstallDir -Force
            }
        }
    }
    else {
        Copy-Item -Path (Join-Path $srcFolder '*') -Destination $InstallDir -Recurse -Force
    }
}
catch {
    Write-Err "Copy failed: $($_.Exception.Message)"
    exit 1
}

if (-not (Test-Path $TargetExe)) {
    Write-Err "Install incomplete - $TargetExe is missing after copy."
    exit 1
}
Write-Ok "Files copied."

# ================================================================ step 4: shortcuts
Write-Step "Step 4/7 - Creating shortcuts"

$desktopLnk = $null
$startMenuLnk = $null

if (-not $NoDesktopIcon) {
    $desktopFolder = if ($MachineScope) {
        [Environment]::GetFolderPath('CommonDesktop')
    }
    else {
        [Environment]::GetFolderPath('Desktop')
    }
    $desktopLnk = Join-Path $desktopFolder "$AppName.lnk"
    try {
        New-ShortcutFile -LnkPath $desktopLnk -Target $TargetExe -WorkDir $InstallDir -Icon $TargetExe
        Write-Ok "Desktop shortcut: $desktopLnk"
    }
    catch {
        Write-Warn "Could not create desktop shortcut: $($_.Exception.Message)"
        $desktopLnk = $null
    }
}

if (-not $NoStartMenu) {
    if ($MachineScope) {
        $startMenuFolder = Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs'
    }
    else {
        $startMenuFolder = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
    }
    $startMenuLnk = Join-Path $startMenuFolder "$AppName.lnk"
    try {
        if (-not (Test-Path $startMenuFolder)) {
            New-Item -ItemType Directory -Path $startMenuFolder -Force | Out-Null
        }
        New-ShortcutFile -LnkPath $startMenuLnk -Target $TargetExe -WorkDir $InstallDir -Icon $TargetExe
        Write-Ok "Start Menu shortcut: $startMenuLnk"
    }
    catch {
        Write-Warn "Could not create Start Menu shortcut: $($_.Exception.Message)"
        $startMenuLnk = $null
    }
}

# ================================================================ step 5: file associations + context menu (optional)
if ($FileAssociations -or $ContextMenu) {
    $cls = 'HKCU:\Software\Classes'
    if ($FileAssociations) {
        Write-Step "Step 5/7 - Registering file associations ($($AssocExts -join ', '))"
        try {
            New-Item -Path "$cls\ImageSwitcherFile" -Force | Out-Null
            Set-ItemProperty -Path "$cls\ImageSwitcherFile" -Name '(Default)' -Value 'Python Image Switcher image file'
            Set-ItemProperty -Path "$cls\ImageSwitcherFile" -Name 'DefaultIcon' -Value $TargetExe
            New-Item -Path "$cls\ImageSwitcherFile\shell" -Force | Out-Null
            New-Item -Path "$cls\ImageSwitcherFile\shell\open" -Force | Out-Null
            New-Item -Path "$cls\ImageSwitcherFile\shell\open\command" -Force | Out-Null
            Set-ItemProperty -Path "$cls\ImageSwitcherFile\shell\open\command" -Name '(Default)' -Value "`"$TargetExe`" `"%1`""
            foreach ($ext in $AssocExts) {
                New-Item -Path "$cls\.$ext" -Force | Out-Null
                Set-ItemProperty -Path "$cls\.$ext" -Name '(Default)' -Value 'ImageSwitcherFile'
            }
            Write-Ok "Image Switcher is now an option for $($AssocExts.Count) image extensions."
            Write-Host '      Note: if an extension already has a default app, that default stays.'
            Write-Host '      To switch: right-click an image > Open with > Choose another app > Image Switcher.'
        }
        catch {
            Write-Warn "File associations were not fully set up: $($_.Exception.Message)"
        }
    }

    if ($ContextMenu) {
        Write-Step "Step 5/7 - Adding Explorer context menu 'Convert with Image Switcher' (RHHHAAAAA)"
        try {
            # Image files context menu (SystemFileAssociations\image)
            $imgMenu = "$cls\SystemFileAssociations\image\shell\ImageSwitcher"
            New-Item -Path $imgMenu -Force | Out-Null
            Set-ItemProperty -Path $imgMenu -Name '(Default)' -Value "Convert with Image Switcher"
            Set-ItemProperty -Path $imgMenu -Name 'Icon' -Value $TargetExe
            New-Item -Path "$imgMenu\command" -Force | Out-Null
            Set-ItemProperty -Path "$imgMenu\command" -Name '(Default)' -Value "`"$TargetExe`" `"%1`""

            # Also for each specific extension for better coverage on older Windows
            foreach ($ext in $AssocExts) {
                $extMenu = "$cls\SystemFileAssociations\.$ext\shell\ImageSwitcher"
                try {
                    New-Item -Path $extMenu -Force | Out-Null
                    Set-ItemProperty -Path $extMenu -Name '(Default)' -Value "Convert with Image Switcher"
                    Set-ItemProperty -Path $extMenu -Name 'Icon' -Value $TargetExe
                    New-Item -Path "$extMenu\command" -Force | Out-Null
                    Set-ItemProperty -Path "$extMenu\command" -Name '(Default)' -Value "`"$TargetExe`" `"%1`""
                } catch {}
            }

            # Folder background - convert all images in folder (batch)
            $dirMenu = "$cls\Directory\shell\ImageSwitcherBatch"
            New-Item -Path $dirMenu -Force | Out-Null
            Set-ItemProperty -Path $dirMenu -Name '(Default)' -Value "Convert images in folder with Image Switcher"
            Set-ItemProperty -Path $dirMenu -Name 'Icon' -Value $TargetExe
            New-Item -Path "$dirMenu\command" -Force | Out-Null
            Set-ItemProperty -Path "$dirMenu\command" -Name '(Default)' -Value "`"$TargetExe`" `"%1`""

            # Directory background (right-click inside folder)
            $dirBgMenu = "$cls\Directory\Background\shell\ImageSwitcherBatch"
            New-Item -Path $dirBgMenu -Force | Out-Null
            Set-ItemProperty -Path $dirBgMenu -Name '(Default)' -Value "Convert images here with Image Switcher"
            Set-ItemProperty -Path $dirBgMenu -Name 'Icon' -Value $TargetExe
            New-Item -Path "$dirBgMenu\command" -Force | Out-Null
            Set-ItemProperty -Path "$dirBgMenu\command" -Name '(Default)' -Value "`"$TargetExe`" `"%V`""

            Write-Ok "Context menu installed: Right-click image -> Convert with Image Switcher"
            Write-Ok "Batch context: Right-click folder -> Convert images in folder"
        }
        catch {
            Write-Warn "Context menu setup failed: $($_.Exception.Message)"
        }
    }
}
else {
    Write-Step "Step 5/7 - Skipping file associations & context menu (use -FileAssociations -ContextMenu to enable)"
}

# ================================================================ step 6: uninstaller + registry entry
Write-Step "Step 6/7 - Installing the uninstaller and Windows registry entry"

$uninstallPs = Join-Path $InstallDir 'Uninstall-ImageSwitcher.ps1'
$uninstallBat = Join-Path $InstallDir 'Uninstall-ImageSwitcher.bat'

$uninstallTemplate = @'
<#
    Uninstaller for Image Switcher.
    Generated by install.ps1 - it knows exactly what the installer created.
    Usage:  powershell -NoProfile -ExecutionPolicy Bypass -File .\Uninstall-ImageSwitcher.ps1
            (add -Quiet to skip the confirmation prompt)
#>
[CmdletBinding()]
param([switch]$Quiet)

$ErrorActionPreference = 'Stop'

$AppName      = 'Image Switcher'
$AppVersion   = '__VERSION__'
$InstallDir   = '__INSTALLDIR__'
$RegBase      = '__REGBASE__'     # HKCU (per-user) or HKLM (machine-wide)
$UninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\PythonImageSwitcher'
$DesktopLnk   = '__DESKTOPLNK__'
$StartMenuLnk = '__STARTMENULNK__'
$AssocExts    = @('png','jpg','jpeg','webp','gif','bmp','tiff','tif','ico','avif','heif','heic','svg')

function Test-IsAdministrator {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# Machine-wide installs need admin rights to clean up the HKLM entry
if ($RegBase -eq 'HKLM' -and -not (Test-IsAdministrator)) {
    Write-Host '  Re-launching with admin rights (UAC prompt)...'
    $extra = ''
    if ($Quiet) { $extra = ' -Quiet' }
    Start-Process powershell.exe -Verb RunAs -ArgumentList ("-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" + $extra)
    exit 0
}

Write-Host ''
Write-Host "  Uninstall $AppName $AppVersion ?"
if (-not $Quiet) {
    $answer = Read-Host "  Remove $AppName $AppVersion [y/N]"
    if ($answer -notmatch '^[Yy]') {
        Write-Host '  Aborted - nothing was removed.'
        exit 0
    }
}

# 1) Close a running app
Get-Process -Name 'ImageSwitcher' -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 500

# 2) Shortcuts
foreach ($lnk in @($DesktopLnk, $StartMenuLnk)) {
    if ($lnk -ne '' -and (Test-Path $lnk)) {
        Remove-Item -Path $lnk -Force
        Write-Host "  Removed shortcut: $lnk"
    }
}

# 3) Registry uninstall entry
$reg = "${RegBase}:\$UninstallKey"
if (Test-Path $reg) {
    Remove-Item -Path $reg -Recurse -Force
    Write-Host '  Removed the Windows uninstall entry.'
}

# 4) File associations (only the ones we own)
$cls = 'HKCU:\Software\Classes'
foreach ($ext in $AssocExts) {
    $key = "$cls\.$ext"
    if (Test-Path $key) {
        $current = (Get-ItemProperty -Path $key).'(Default)'
        if ($current -eq 'ImageSwitcherFile') {
            Remove-Item -Path $key -Force -ErrorAction SilentlyContinue
            Write-Host "  Cleared .$ext association."
        }
    }
    # Clean context menu per-extension
    $extCtx = "$cls\SystemFileAssociations\.$ext\shell\ImageSwitcher"
    if (Test-Path $extCtx) {
        Remove-Item -Path $extCtx -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "  Removed context menu for .$ext"
    }
}
Remove-Item -Path "$cls\ImageSwitcherFile" -Recurse -Force -ErrorAction SilentlyContinue

# 4b) Context menu cleanup
$ctxPaths = @(
    "$cls\SystemFileAssociations\image\shell\ImageSwitcher",
    "$cls\Directory\shell\ImageSwitcherBatch",
    "$cls\Directory\Background\shell\ImageSwitcherBatch"
)
foreach ($ctx in $ctxPaths) {
    if (Test-Path $ctx) {
        Remove-Item -Path $ctx -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "  Removed context menu: $ctx"
    }
}

# 5) Install folder
if (Test-Path $InstallDir) {
    try {
        Remove-Item -Path $InstallDir -Recurse -Force
        Write-Host "  Removed install folder: $InstallDir"
    }
    catch {
        Write-Host "  [!] Could not fully remove $InstallDir (a file may be locked)."
        Write-Host '      Close Image Switcher, then delete the folder manually.'
    }
}

Write-Host ''
Write-Host "  $AppName $AppVersion has been uninstalled. Bye!"
Write-Host ''
'@

$content = $uninstallTemplate.Replace('__VERSION__', $Version)
$content = $content.Replace('__INSTALLDIR__', $InstallDir)
$content = $content.Replace('__REGBASE__', $regRoot)
$content = $content.Replace('__DESKTOPLNK__', $(if ($desktopLnk) { $desktopLnk } else { '' }))
$content = $content.Replace('__STARTMENULNK__', $(if ($startMenuLnk) { $startMenuLnk } else { '' }))

Set-Content -Path $uninstallPs -Value $content -Encoding ASCII

$batTemplate = @'
@echo off
rem Uninstaller for Image Switcher - generated by install.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Uninstall-ImageSwitcher.ps1" %*
'@
Set-Content -Path $uninstallBat -Value $batTemplate -Encoding ASCII

# Registry entry so the app shows up in Settings > Apps (Control Panel)
try {
    New-Item -Path $regKey -Force | Out-Null
    $sizeKb = 0
    Get-ChildItem -Path $InstallDir -Recurse -File | ForEach-Object {
        $sizeKb += [math]::Floor($_.Length / 1KB)
    }
    $registryProps = @{
        'DisplayName'     = $AppName
        'DisplayVersion'  = $Version
        'Publisher'       = $Publisher
        'InstallLocation' = $InstallDir
        'UninstallString' = "`"$uninstallBat`""
        'DisplayIcon'     = $TargetExe
        'URLInfoAbout'    = $RepoUrl
        'NoModify'        = 1
        'NoRepair'        = 1
        'InstallDate'     = (Get-Date -Format 'yyyyMMdd')
        'EstimatedSize'   = $sizeKb
    }
    foreach ($name in $registryProps.Keys) {
        Set-ItemProperty -Path $regKey -Name $name -Value $registryProps[$name]
    }
    Write-Ok "Uninstall entry registered under ${regRoot}:\$UninstallKey"
    Write-Ok "Uninstaller written to: $uninstallBat"
}
catch {
    Write-Warn "Registry entry could not be written: $($_.Exception.Message)"
    Write-Host '      The app still works; it just will not appear under Settings > Apps.'
}

# ================================================================ step 7: finish
Write-Step "Step 7/7 - Finishing up"

if ($removeAfter -and (Test-Path $removeAfter)) {
    Remove-Item -Path $removeAfter -Force -ErrorAction SilentlyContinue
}

Write-Host ''
Write-Host '  ==============================================================' -ForegroundColor Green
Write-Host '    Installation complete!' -ForegroundColor Green
Write-Host '  ==============================================================' -ForegroundColor Green
Write-Host ''
Write-Host ("     Install folder : {0}" -f $InstallDir)
Write-Host ("     Version        : {0}" -f $Version)
if ($desktopLnk)   { Write-Host ("     Desktop icon   : {0}" -f $desktopLnk) }
if ($startMenuLnk) { Write-Host ("     Start Menu     : {0}" -f $startMenuLnk) }
if ($backupPath)   { Write-Host ("     Previous build : backed up to {0}" -f $backupPath) }
Write-Host ''
Write-Host '     Uninstall: Settings > Apps > Installed apps > Image Switcher > Uninstall'
Write-Host ("               or run: {0}" -f $uninstallBat)
Write-Host ''

if (-not $NoLaunch) {
    Write-Step "Launching $AppName..."
    try {
        Start-Process -FilePath $TargetExe -WorkingDirectory $InstallDir
    }
    catch {
        Write-Warn "Could not launch automatically: $($_.Exception.Message)"
        Write-Host "      Start it manually from: $TargetExe"
    }
}

exit 0
