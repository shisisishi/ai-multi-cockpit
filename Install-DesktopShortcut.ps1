<#
.SYNOPSIS
    Creates a "AI Multi Cockpit" desktop shortcut (frameless desktop app mode, zero UAC).
#>
[CmdletBinding()]
param(
    [string]$ShortcutName = 'AI Multi Cockpit'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VbsPath = Join-Path $RepoRoot 'Launch-Cockpit.vbs'
$DesktopDir = [Environment]::GetFolderPath('Desktop')
$StartMenuDir = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
$Targets = @(
    (Join-Path $DesktopDir "$ShortcutName.lnk"),
    (Join-Path $StartMenuDir "$ShortcutName.lnk")
)

$icoPath = Join-Path $RepoRoot 'assets\cockpit.ico'
$edgeExe = "$env:ProgramFiles (x86)\Microsoft\Edge\Application\msedge.exe"
if (-not (Test-Path -LiteralPath $edgeExe)) { $edgeExe = "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe" }

$ws = New-Object -ComObject WScript.Shell
foreach ($LnkPath in $Targets) {
    $parent = Split-Path -Parent $LnkPath
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    $sc = $ws.CreateShortcut($LnkPath)
    $sc.TargetPath = "$env:SystemRoot\System32\wscript.exe"
    $sc.Arguments = "`"$VbsPath`""
    $sc.WorkingDirectory = $RepoRoot
    $sc.Description = 'AI Multi Cockpit - Antigravity & Codex Multi-Account Quota Dashboard'
    if (Test-Path -LiteralPath $icoPath) {
        $sc.IconLocation = "$icoPath,0"
    } elseif (Test-Path -LiteralPath $edgeExe) {
        $sc.IconLocation = "$edgeExe,0"
    }
    $sc.Save()
    Write-Host "[OK] Created shortcut: $LnkPath" -ForegroundColor Green
}
