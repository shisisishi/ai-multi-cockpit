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
$LnkPath = Join-Path $DesktopDir "$ShortcutName.lnk"

$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut($LnkPath)
$sc.TargetPath = "$env:SystemRoot\System32\wscript.exe"
$sc.Arguments = "`"$VbsPath`""
$sc.WorkingDirectory = $RepoRoot
$sc.Description = 'AI Multi Cockpit - Antigravity & Codex Multi-Account Quota Dashboard'

$edgeExe = "$env:ProgramFiles (x86)\Microsoft\Edge\Application\msedge.exe"
if (-not (Test-Path -LiteralPath $edgeExe)) { $edgeExe = "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe" }
if (Test-Path -LiteralPath $edgeExe) {
    $sc.IconLocation = "$edgeExe,0"
}
$sc.Save()

Write-Host "[OK] Created desktop shortcut: $LnkPath" -ForegroundColor Green
