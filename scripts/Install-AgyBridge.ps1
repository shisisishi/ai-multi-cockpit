<#
.SYNOPSIS
    Installs or updates the official Antigravity sidecar plugin (ai-multi-cockpit-bridge)
    for the current user and all configured AntigravityMulti sub-accounts (zero UAC).
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$PluginSrc = Join-Path $RepoRoot 'plugins\ai-multi-cockpit-bridge'
$AgyMultiRoot = Join-Path $env:PROGRAMDATA 'AntigravityMulti'

if (-not (Test-Path -LiteralPath $PluginSrc)) {
    throw "Bridge plugin source not found at $PluginSrc"
}

function Copy-PluginToDir([string]$DestDir) {
    if (-not (Test-Path -LiteralPath $DestDir)) {
        New-Item -ItemType Directory -Path $DestDir -Force | Out-Null
    }
    & robocopy $PluginSrc $DestDir /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
    $rc = $LASTEXITCODE
    $global:LASTEXITCODE = 0
    if ($rc -ge 8) {
        throw "Failed to deploy bridge plugin to $DestDir (robocopy exit code $rc)"
    }
}

# 1. Install for current (Main) Antigravity account
$mainDest = Join-Path $env:USERPROFILE '.gemini\config\plugins\ai-multi-cockpit-bridge'
Copy-PluginToDir $mainDest
Write-Host "[OK] Deployed bridge plugin to Main account: $mainDest" -ForegroundColor Green

# 2. If AntigravityMulti is present, stage plugin into sync_pool and deploy into each sub-account via DPAPI cred
$poolStage = Join-Path $AgyMultiRoot 'sync_pool\plugins_stage\ai-multi-cockpit-bridge'
$credsDir = Join-Path $env:LOCALAPPDATA 'AntigravityMulti\creds'
$teleDir = Join-Path $AgyMultiRoot 'sync_pool\telemetry'

if ((Test-Path -LiteralPath (Join-Path $AgyMultiRoot 'sync_pool')) -and (Test-Path -LiteralPath $credsDir)) {
    Copy-PluginToDir $poolStage
    if (-not (Test-Path -LiteralPath $teleDir)) {
        New-Item -ItemType Directory -Path $teleDir -Force | Out-Null
    }

    $psExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $subScript = Join-Path $AgyMultiRoot 'sync_pool\plugins_stage\deploy_sub.ps1'
    $subBody = @"
param([string]`$StageDir)
`$ErrorActionPreference = 'Stop'
`$dest = Join-Path `$env:USERPROFILE '.gemini\config\plugins\ai-multi-cockpit-bridge'
if (-not (Test-Path -LiteralPath `$dest)) { New-Item -ItemType Directory -Path `$dest -Force | Out-Null }
& robocopy `$StageDir `$dest /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
if (`$LASTEXITCODE -ge 8) { exit `$LASTEXITCODE }
exit 0
"@
    $utf8Bom = New-Object System.Text.UTF8Encoding($true)
    [System.IO.File]::WriteAllText($subScript, $subBody, $utf8Bom)

    $credFiles = @(Get-ChildItem -LiteralPath $credsDir -Filter '*.xml' -ErrorAction SilentlyContinue)
    foreach ($cf in $credFiles) {
        $accName = $cf.BaseName
        try {
            $cred = Import-Clixml -LiteralPath $cf.FullName
            $argStr = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$subScript`" -StageDir `"$poolStage`""
            $proc = Start-Process -FilePath $psExe -ArgumentList $argStr -Credential $cred -WorkingDirectory $AgyMultiRoot -WindowStyle Hidden -PassThru
            $proc.WaitForExit(30000) | Out-Null
            Write-Host "[OK] Deployed bridge plugin to sub-account: $accName" -ForegroundColor Green
        } catch {
            Write-Host "[WARN] Skipped sub-account ${accName}: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
}
