# Windows 11 alpha updater. Run from a PowerShell terminal in the checkout:
# powershell -NoProfile -ExecutionPolicy Bypass -File .\update-alpha.ps1
# Creates .venv, installs Python dependencies, tests, builds and launches
# the unsigned alpha installer. It never rewrites source photos or Git branches.
param([switch]$DependenciesOnly)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

function Invoke-Checked($command, [string[]]$arguments) {
    Write-Host "+ $command $($arguments -join ' ')"
    & $command @arguments
    if ($LASTEXITCODE -ne 0) { throw "$command failed with exit code $LASTEXITCODE" }
}

function Find-Python311 {
    $plain = Get-Command python -ErrorAction SilentlyContinue
    if ($plain) {
        & $plain.Source -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3,11) else 1)' 2>$null
        if ($LASTEXITCODE -eq 0) { return @($plain.Source) }
    }
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        & $launcher.Source -3.11 -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3,11) else 1)' 2>$null
        if ($LASTEXITCODE -eq 0) { return @($launcher.Source, '-3.11') }
    }
    $paths = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'),
        (Join-Path $env:ProgramFiles 'Python311\python.exe')
    )
    foreach ($candidate in $paths) {
        if (Test-Path $candidate) { return @($candidate) }
    }
    return @()
}

function Find-InnoCompiler {
    $iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($iscc) { return $iscc.Source }
    $paths = @(
        (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
        (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe')
    )
    foreach ($candidate in $paths) { if (Test-Path $candidate) { return $candidate } }
    return $null
}

Push-Location $root
try {
    $python = @(Find-Python311)
    if ($python.Count -eq 0) {
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
            throw 'Python 3.11 is missing. Install it from the official Python installer, reopen PowerShell, then rerun. winget is unavailable.'
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
        if (-not $compiler) { throw 'Inno Setup was installed but ISCC.exe was not found. Reopen PowerShell and rerun.' }
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
