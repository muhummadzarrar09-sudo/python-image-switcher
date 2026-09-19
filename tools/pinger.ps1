<#
.SYNOPSIS
    Image Switcher - Main Branch Pinger (PowerShell Edition)
    Checks GitHub main for updates and notifies you.

.DESCRIPTION
    PowerShell version of the pinger for Windows users who live in PS.
    Shows toast notification when main has new commits.

    Usage:
        powershell -File tools/pinger.ps1
        powershell -File tools/pinger.ps1 -Watch -Interval 60
        powershell -File tools/pinger.ps1 -Json

.NOTES
    No extra modules required - uses built-in .NET
#>
param(
    [switch]$Watch,
    [int]$Interval = 60,
    [switch]$Json,
    [switch]$Notify
)

$Repo = "muhummadzarrar09-sudo/python-image-switcher"
$ApiMain = "https://api.github.com/repos/$Repo/commits/main"
$ApiReleases = "https://api.github.com/repos/$Repo/releases/latest"

function Get-LocalInfo {
    $root = (Resolve-Path "$PSScriptRoot\..").Path
    $branch = "unknown"
    $sha = "unknown"
    $originMain = $null
    try {
        $branch = (git -C $root rev-parse --abbrev-ref HEAD 2>$null).Trim()
        $sha = (git -C $root rev-parse HEAD 2>$null).Trim()
        $originMain = (git -C $root rev-parse origin/main 2>$null).Trim()
        if (-not $originMain) {
            git -C $root fetch origin main --quiet 2>$null | Out-Null
            $originMain = (git -C $root rev-parse origin/main 2>$null).Trim()
        }
    } catch {}
    return @{
        branch = $branch
        local_sha = $sha
        origin_main = $originMain
        root = $root
    }
}

function Get-GitHubJson($Url) {
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $r = Invoke-RestMethod -Uri $Url -Headers @{ "User-Agent" = "ImageSwitcher-Pinger-PS/1.0" } -TimeoutSec 15
        return $r
    } catch {
        return @{ error = $_.Exception.Message }
    }
}

function Show-Toast($Title, $Message) {
    try {
        # Try BurntToast if available, else MsgBox
        if (Get-Module -ListAvailable -Name BurntToast) {
            Import-Module BurntToast
            New-BurntToastNotification -Text $Title, $Message -AppLogo "$PSScriptRoot\..\assets\icon.png" -ErrorAction SilentlyContinue
        } else {
            # Fallback to Windows Forms balloon or WScript
            Add-Type -AssemblyName System.Windows.Forms -ErrorAction SilentlyContinue
            $notify = New-Object System.Windows.Forms.NotifyIcon
            $notify.Icon = [System.Drawing.SystemIcons]::Information
            $notify.BalloonTipTitle = $Title
            $notify.BalloonTipText = $Message
            $notify.Visible = $true
            $notify.ShowBalloonTip(5000)
            Start-Sleep -Seconds 6
            $notify.Dispose()
        }
    } catch {
        Write-Host "🔔 $Title - $Message" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "🔔 Image Switcher - Main Pinger (PowerShell)" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor DarkGray

$local = Get-LocalInfo
Write-Host "📁 $($local.root)" -ForegroundColor Gray
Write-Host "🌿 Branch: $($local.branch) | HEAD: $($local.local_sha.Substring(0,12))" -ForegroundColor White
if ($local.origin_main) { Write-Host "📌 origin/main: $($local.origin_main.Substring(0,12))" -ForegroundColor DarkGray }

Write-Host ""
Write-Host "🌐 Checking GitHub..." -ForegroundColor Cyan
$remote = Get-GitHubJson $ApiMain

if ($remote.PSObject.Properties.Name -contains "sha") {
    $rSha = $remote.sha
    $rMsg = $remote.commit.message.Split("`n")[0]
    $rDate = $remote.commit.committer.date
    Write-Host "☁️  Remote main: $($rSha.Substring(0,12))" -ForegroundColor Green
    Write-Host "💬 $rMsg" -ForegroundColor White
    Write-Host "📅 $rDate" -ForegroundColor Gray

    if ($local.local_sha -eq $rSha) {
        Write-Host ""
        Write-Host "✅ UP TO DATE with main!" -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "🚨 UPDATE AVAILABLE!" -ForegroundColor Red
        Write-Host "   Local:  $($local.local_sha.Substring(0,12))" -ForegroundColor Yellow
        Write-Host "   Remote: $($rSha.Substring(0,12))" -ForegroundColor Green
        Write-Host "   Run: git fetch origin && git merge origin/main" -ForegroundColor Cyan
        if ($Notify) { Show-Toast "Image Switcher Update!" "New commits on main: $($rSha.Substring(0,8)) - $rMsg" }
    }
} else {
    Write-Host "❌ Failed: $($remote.error)" -ForegroundColor Red
}

Write-Host ""
Write-Host "🏷️  Latest release:" -ForegroundColor Cyan
$rel = Get-GitHubJson $ApiReleases
if ($rel.tag_name) {
    Write-Host "🎉 $($rel.tag_name) - $($rel.name)" -ForegroundColor Green
    Write-Host "🔗 $($rel.html_url)" -ForegroundColor Gray
} else {
    Write-Host "ℹ️  No releases yet" -ForegroundColor DarkGray
}

if ($Json) {
    $out = @{
        checked_at = (Get-Date).ToUniversalTime().ToString("o")
        local = $local
        remote = $remote
        release = $rel
    }
    Write-Host ""
    Write-Host ($out | ConvertTo-Json -Depth 5)
}

if ($Watch) {
    Write-Host ""
    Write-Host "👀 Watching every $Interval sec - Ctrl+C to stop" -ForegroundColor Yellow
    $last = $remote.sha
    while ($true) {
        Start-Sleep -Seconds $Interval
        $cur = Get-GitHubJson $ApiMain
        if ($cur.sha -and $cur.sha -ne $last) {
            Write-Host ""
            Write-Host "🔔🔔🔔 NEW UPDATE! $($cur.sha.Substring(0,12)) - $($cur.commit.message.Split("`n")[0])" -ForegroundColor Green -BackgroundColor Black
            Show-Toast "Image Switcher - New Update!" "$($cur.sha.Substring(0,8)): $($cur.commit.message.Split("`n")[0])"
            $last = $cur.sha
        } else {
            Write-Host "." -NoNewline -ForegroundColor DarkGray
        }
    }
}
