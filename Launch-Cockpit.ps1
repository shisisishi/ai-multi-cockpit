<#
.SYNOPSIS
    Launches AI Multi Cockpit local server and opens it in a standalone Edge/Chrome --app desktop window.
#>
[CmdletBinding()]
param(
    [int]$Port = 19420,
    [switch]$ServerOnly,
    [switch]$BrowserTab
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ServerPy = Join-Path $RepoRoot 'cockpit\server.py'
$AppDataRoot = Join-Path $env:LOCALAPPDATA 'AIMultiCockpit'
$AppShellDir = Join-Path $AppDataRoot 'app-shell'
$BaseUrl = "http://127.0.0.1:$Port"

function Test-CockpitAlive([string]$Url) {
    try {
        $resp = Invoke-RestMethod -Uri "$Url/api/health" -TimeoutSec 2 -ErrorAction Stop
        return ($resp.ok -eq $true -and $resp.app -eq 'ai-multi-cockpit')
    } catch {
        return $false
    }
}

function Find-PythonExe {
    foreach ($name in @('pythonw.exe', 'python.exe', 'py.exe')) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }
    throw "Python 3 was not found in PATH. Please install Python 3.10+ to run AI Multi Cockpit."
}

function Find-AppBrowser {
    $candidates = @(
        "$env:ProgramFiles (x86)\Microsoft\Edge\Application\msedge.exe",
        "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "$env:ProgramFiles (x86)\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path -LiteralPath $c) { return $c }
    }
    return $null
}

if (-not (Test-CockpitAlive $BaseUrl)) {
    $pyExe = Find-PythonExe
    $argList = if ($pyExe -match 'py\.exe$') {
        @('-3', $ServerPy, '--port', "$Port")
    } else {
        @($ServerPy, '--port', "$Port")
    }
    Start-Process -FilePath $pyExe -ArgumentList $argList -WorkingDirectory $RepoRoot -WindowStyle Hidden | Out-Null

    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 250
        if (Test-CockpitAlive $BaseUrl) { $ready = $true; break }
    }
    if (-not $ready) {
        throw "AI Multi Cockpit backend failed to start on $BaseUrl."
    }
}

if ($ServerOnly) {
    Write-Host "[OK] AI Multi Cockpit backend running at $BaseUrl" -ForegroundColor Green
    exit 0
}

if (-not $BrowserTab) {
    $browser = Find-AppBrowser
    if ($browser) {
        if (-not (Test-Path -LiteralPath $AppShellDir)) {
            New-Item -ItemType Directory -Path $AppShellDir -Force | Out-Null
        }
        $appArgs = @(
            "--app=$BaseUrl",
            "--window-size=1280,860",
            "--user-data-dir=`"$AppShellDir`"",
            "--no-first-run",
            "--no-default-browser-check"
        )
        Start-Process -FilePath $browser -ArgumentList ($appArgs -join ' ') | Out-Null
        exit 0
    }
}

Start-Process $BaseUrl | Out-Null
