<#
.SYNOPSIS
    Side-by-side multi-account manager for OpenAI Codex Desktop & Codex CLI on Windows.
.DESCRIPTION
    Uses official CODEX_HOME environment variable and Chromium --user-data-dir isolation
    so multiple Codex Desktop windows and Codex CLI sessions can run concurrently with
    independent ChatGPT / OpenAI accounts (zero UAC, zero extra Windows users required).
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('List', 'Create', 'LaunchDesktop', 'LaunchCli', 'Login', 'SyncShared', 'CreateShortcut', 'Remove', 'Info')]
    [string]$Action = 'List',

    [string]$Name = 'default',
    [string]$Workspace = '',
    [string]$Proxy = '',
    [string]$Label = '',
    [switch]$NoShareConfig,
    [switch]$NoShareSkills,
    [switch]$NoShareAgentsMd,
    [switch]$Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppDataRoot = Join-Path $env:LOCALAPPDATA 'AIMultiCockpit'
$ProfilesRoot = Join-Path $AppDataRoot 'codex-profiles'
$DefaultCodexHome = Join-Path $env:USERPROFILE '.codex'
$MetaFile = Join-Path $AppDataRoot 'codex-profiles.json'

function Ensure-Directory([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Test-ValidProfileName([string]$ProfileName) {
    if ([string]::IsNullOrWhiteSpace($ProfileName)) { return $false }
    return ($ProfileName -match '^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$')
}

function Load-Meta {
    if (Test-Path -LiteralPath $MetaFile) {
        try {
            $raw = Get-Content -LiteralPath $MetaFile -Raw -Encoding UTF8
            $obj = $raw | ConvertFrom-Json
            if ($null -ne $obj) { return $obj }
        } catch {}
    }
    return [PSCustomObject]@{ profiles = [PSCustomObject]@{} }
}

function Save-Meta($MetaObj) {
    Ensure-Directory $AppDataRoot
    $jsonText = $MetaObj | ConvertTo-Json -Depth 6
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($MetaFile, $jsonText, $utf8NoBom)
}

function Get-ProfileMeta([string]$ProfileName) {
    $meta = Load-Meta
    $prop = $meta.profiles.PSObject.Properties[$ProfileName]
    if ($null -ne $prop) { return $prop.Value }
    return $null
}

function Set-ProfileMeta([string]$ProfileName, [hashtable]$Data) {
    $meta = Load-Meta
    $existing = Get-ProfileMeta $ProfileName
    $merged = @{}
    if ($null -ne $existing) {
        foreach ($p in $existing.PSObject.Properties) { $merged[$p.Name] = $p.Value }
    }
    foreach ($k in $Data.Keys) { $merged[$k] = $Data[$k] }
    $meta.profiles | Add-Member -MemberType NoteProperty -Name $ProfileName -Value ([PSCustomObject]$merged) -Force
    Save-Meta $meta
}

function Remove-ProfileMeta([string]$ProfileName) {
    $meta = Load-Meta
    if ($null -ne $meta.profiles.PSObject.Properties[$ProfileName]) {
        $meta.profiles.PSObject.Properties.Remove($ProfileName)
        Save-Meta $meta
    }
}

function Find-CodexCliExe {
    # 1. Official OpenAI Codex Desktop bundled/managed CLI under %LOCALAPPDATA%\OpenAI\Codex\bin
    $localBin = Join-Path $env:LOCALAPPDATA 'OpenAI\Codex\bin'
    if (Test-Path -LiteralPath $localBin) {
        $candidates = @(Get-ChildItem -LiteralPath $localBin -Recurse -Filter 'codex.exe' -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending)
        if ($candidates.Count -gt 0) { return $candidates[0].FullName }
    }
    # 2. Appx bundled resources\codex.exe
    $appx = Get-AppxPackage -Name 'OpenAI.Codex' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($appx -and $appx.InstallLocation) {
        $bundled = Join-Path $appx.InstallLocation 'app\resources\codex.exe'
        if (Test-Path -LiteralPath $bundled) { return $bundled }
    }
    # 3. PATH lookup
    $cmd = Get-Command 'codex' -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

function Find-CodexDesktopExe {
    $appx = Get-AppxPackage -Name 'OpenAI.Codex' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($appx -and $appx.InstallLocation) {
        $exe = Join-Path $appx.InstallLocation 'app\ChatGPT.exe'
        if (Test-Path -LiteralPath $exe) { return $exe }
        $alt = Join-Path $appx.InstallLocation 'app\Codex.exe'
        if (Test-Path -LiteralPath $alt) { return $alt }
    }
    return $null
}

function Get-ProfilePaths([string]$ProfileName) {
    if ($ProfileName -eq 'default') {
        return @{
            Name       = 'default'
            Mode       = 'default'
            Root       = $DefaultCodexHome
            CodexHome  = $DefaultCodexHome
            UserData   = ''
            AuthExists = (Test-Path -LiteralPath (Join-Path $DefaultCodexHome 'auth.json'))
        }
    }
    $root = Join-Path $ProfilesRoot $ProfileName
    $codexHome = Join-Path $root 'codex_home'
    $userData = Join-Path $root 'user_data'
    return @{
        Name       = $ProfileName
        Mode       = 'isolated'
        Root       = $root
        CodexHome  = $codexHome
        UserData   = $userData
        AuthExists = (Test-Path -LiteralPath (Join-Path $codexHome 'auth.json'))
    }
}

function Sync-SharedFiles([string]$TargetCodexHome, [bool]$CopyConfig, [bool]$CopySkills, [bool]$CopyAgents) {
    Ensure-Directory $TargetCodexHome
    if (-not (Test-Path -LiteralPath $DefaultCodexHome)) { return }

    if ($CopyConfig) {
        $srcCfg = Join-Path $DefaultCodexHome 'config.toml'
        $dstCfg = Join-Path $TargetCodexHome 'config.toml'
        if (Test-Path -LiteralPath $srcCfg) {
            Copy-Item -LiteralPath $srcCfg -Destination $dstCfg -Force
        }
    }
    if ($CopyAgents) {
        $srcAg = Join-Path $DefaultCodexHome 'AGENTS.md'
        $dstAg = Join-Path $TargetCodexHome 'AGENTS.md'
        if (Test-Path -LiteralPath $srcAg) {
            Copy-Item -LiteralPath $srcAg -Destination $dstAg -Force
        }
    }
    if ($CopySkills) {
        $srcSk = Join-Path $DefaultCodexHome 'skills'
        $dstSk = Join-Path $TargetCodexHome 'skills'
        if (Test-Path -LiteralPath $srcSk) {
            Ensure-Directory $dstSk
            & robocopy $srcSk $dstSk /E /NFL /NDL /NJH /NJS /NP | Out-Null
            $rc = $LASTEXITCODE
            $global:LASTEXITCODE = 0
            if ($rc -ge 8) {
                throw "Failed to sync Codex skills directory (robocopy exit code $rc)"
            }
        }
    }
}

function Get-AllProfiles {
    $list = @()
    $def = Get-ProfilePaths 'default'
    $defMeta = Get-ProfileMeta 'default'
    $list += [PSCustomObject]@{
        name       = 'default'
        label      = if ($defMeta -and $defMeta.label) { $defMeta.label } else { 'Default (~/.codex)' }
        mode       = 'default'
        codexHome  = $def.CodexHome
        userData   = ''
        authExists = $def.AuthExists
        proxy      = if ($defMeta -and $defMeta.proxy) { $defMeta.proxy } else { '' }
    }

    if (Test-Path -LiteralPath $ProfilesRoot) {
        $dirs = @(Get-ChildItem -LiteralPath $ProfilesRoot -Directory | Sort-Object Name)
        foreach ($d in $dirs) {
            $p = Get-ProfilePaths $d.Name
            $m = Get-ProfileMeta $d.Name
            $list += [PSCustomObject]@{
                name       = $d.Name
                label      = if ($m -and $m.label) { $m.label } else { "Codex - $($d.Name)" }
                mode       = 'isolated'
                codexHome  = $p.CodexHome
                userData   = $p.UserData
                authExists = $p.AuthExists
                proxy      = if ($m -and $m.proxy) { $m.proxy } else { '' }
            }
        }
    }
    return $list
}

function Apply-ProxyEnv([string]$ProfileName, [string]$OverrideProxy) {
    $proxyUrl = $OverrideProxy
    if ([string]::IsNullOrWhiteSpace($proxyUrl)) {
        $m = Get-ProfileMeta $ProfileName
        if ($m -and $m.proxy) { $proxyUrl = $m.proxy }
    }
    if (-not [string]::IsNullOrWhiteSpace($proxyUrl)) {
        $env:HTTP_PROXY = $proxyUrl
        $env:HTTPS_PROXY = $proxyUrl
        $env:ALL_PROXY = $proxyUrl
    }
    return $proxyUrl
}

switch ($Action) {
    'Info' {
        $info = [PSCustomObject]@{
            codexCliExe     = Find-CodexCliExe
            codexDesktopExe = Find-CodexDesktopExe
            profilesRoot    = $ProfilesRoot
            defaultHome     = $DefaultCodexHome
        }
        if ($Json) { $info | ConvertTo-Json -Depth 4 } else { $info | Format-List }
    }

    'List' {
        $profiles = @(Get-AllProfiles)
        if ($Json) {
            $profiles | ConvertTo-Json -Depth 4
        } else {
            $profiles | Select-Object name, label, mode, authExists, proxy | Format-Table -AutoSize
        }
    }

    'Create' {
        if ($Name -eq 'default') { throw "Profile name 'default' is reserved." }
        if (-not (Test-ValidProfileName $Name)) {
            throw "Invalid profile name '$Name'. Use 1-32 alphanumeric, '.', '_', or '-' characters."
        }
        $p = Get-ProfilePaths $Name
        Ensure-Directory $p.CodexHome
        Ensure-Directory $p.UserData
        Sync-SharedFiles -TargetCodexHome $p.CodexHome -CopyConfig:(-not $NoShareConfig) -CopySkills:(-not $NoShareSkills) -CopyAgents:(-not $NoShareAgentsMd)
        $displayLabel = if ([string]::IsNullOrWhiteSpace($Label)) { "Codex - $Name" } else { $Label }
        Set-ProfileMeta $Name @{
            label         = $displayLabel
            proxy         = $Proxy
            shareConfig   = (-not $NoShareConfig)
            shareSkills   = (-not $NoShareSkills)
            shareAgentsMd = (-not $NoShareAgentsMd)
            createdAt     = (Get-Date).ToString('o')
        }
        $res = [PSCustomObject]@{ ok = $true; name = $Name; label = $displayLabel; codexHome = $p.CodexHome; userData = $p.UserData }
        if ($Json) { $res | ConvertTo-Json -Depth 4 } else { Write-Host "[OK] Created Codex profile '$Name' at $($p.Root)" -ForegroundColor Green }
    }

    'SyncShared' {
        $targets = @()
        if ($Name -eq 'all' -or $Name -eq 'default') {
            $targets = @(Get-AllProfiles | Where-Object { $_.mode -eq 'isolated' })
        } else {
            $p = Get-ProfilePaths $Name
            if (-not (Test-Path -LiteralPath $p.CodexHome)) { throw "Profile '$Name' does not exist." }
            $targets = @([PSCustomObject]@{ name = $Name; codexHome = $p.CodexHome })
        }
        $synced = @()
        foreach ($t in $targets) {
            Sync-SharedFiles -TargetCodexHome $t.codexHome -CopyConfig:(-not $NoShareConfig) -CopySkills:(-not $NoShareSkills) -CopyAgents:(-not $NoShareAgentsMd)
            $synced += $t.name
        }
        $res = [PSCustomObject]@{ ok = $true; synced = $synced }
        if ($Json) { $res | ConvertTo-Json -Depth 4 } else { Write-Host "[OK] Synced shared config/skills/AGENTS.md to: $($synced -join ', ')" -ForegroundColor Green }
    }

    'LaunchDesktop' {
        $desktopExe = Find-CodexDesktopExe
        if (-not $desktopExe) {
            throw "OpenAI Codex Desktop app (Appx OpenAI.Codex) was not found on this machine."
        }
        $p = Get-ProfilePaths $Name
        if ($p.Mode -eq 'isolated' -and -not (Test-Path -LiteralPath $p.CodexHome)) {
            throw "Profile '$Name' does not exist. Create it first."
        }
        $appliedProxy = Apply-ProxyEnv $Name $Proxy
        $env:CODEX_HOME = $p.CodexHome

        $argsList = @()
        if ($p.Mode -eq 'isolated') {
            Ensure-Directory $p.UserData
            $argsList += "--user-data-dir=`"$($p.UserData)`""
        }
        if (-not [string]::IsNullOrWhiteSpace($appliedProxy)) {
            $argsList += "--proxy-server=`"$appliedProxy`""
        }
        if (-not [string]::IsNullOrWhiteSpace($Workspace) -and (Test-Path -LiteralPath $Workspace)) {
            $argsList += "`"$Workspace`""
        }

        $startParams = @{ FilePath = $desktopExe; PassThru = $true }
        if ($argsList.Count -gt 0) { $startParams['ArgumentList'] = ($argsList -join ' ') }
        if (-not [string]::IsNullOrWhiteSpace($Workspace) -and (Test-Path -LiteralPath $Workspace)) {
            $startParams['WorkingDirectory'] = $Workspace
        }
        $proc = Start-Process @startParams
        $res = [PSCustomObject]@{ ok = $true; name = $Name; mode = 'desktop'; pid = $proc.Id; codexHome = $p.CodexHome }
        if ($Json) { $res | ConvertTo-Json -Depth 4 } else { Write-Host "[OK] Launched Codex Desktop [$Name] (PID $($proc.Id))" -ForegroundColor Green }
    }

    'LaunchCli' {
        $cliExe = Find-CodexCliExe
        if (-not $cliExe) { throw "Codex CLI (codex.exe) was not found." }
        $p = Get-ProfilePaths $Name
        if ($p.Mode -eq 'isolated' -and -not (Test-Path -LiteralPath $p.CodexHome)) {
            throw "Profile '$Name' does not exist. Create it first."
        }
        $appliedProxy = Apply-ProxyEnv $Name $Proxy
        $workDir = if (-not [string]::IsNullOrWhiteSpace($Workspace) -and (Test-Path -LiteralPath $Workspace)) { $Workspace } else { $env:USERPROFILE }

        $title = "Codex CLI - $Name"
        $escapedHome = $p.CodexHome.Replace("'", "''")
        $escapedExe = $cliExe.Replace("'", "''")
        $proxyLines = if ($appliedProxy) {
            $ep = $appliedProxy.Replace("'", "''")
            "`$env:HTTP_PROXY='$ep'; `$env:HTTPS_PROXY='$ep'; "
        } else { '' }
        $cmdBody = "`$Host.UI.RawUI.WindowTitle='$title'; `$env:CODEX_HOME='$escapedHome'; $proxyLines& '$escapedExe'"
        $proc = Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoExit', '-NoProfile', '-Command', $cmdBody) -WorkingDirectory $workDir -PassThru
        $res = [PSCustomObject]@{ ok = $true; name = $Name; mode = 'cli'; pid = $proc.Id; codexHome = $p.CodexHome }
        if ($Json) { $res | ConvertTo-Json -Depth 4 } else { Write-Host "[OK] Launched Codex CLI [$Name] (PID $($proc.Id))" -ForegroundColor Green }
    }

    'Login' {
        $cliExe = Find-CodexCliExe
        if (-not $cliExe) { throw "Codex CLI (codex.exe) was not found." }
        $p = Get-ProfilePaths $Name
        if ($p.Mode -eq 'isolated' -and -not (Test-Path -LiteralPath $p.CodexHome)) {
            throw "Profile '$Name' does not exist. Create it first."
        }
        $appliedProxy = Apply-ProxyEnv $Name $Proxy
        $title = "Codex Login - $Name"
        $escapedHome = $p.CodexHome.Replace("'", "''")
        $escapedExe = $cliExe.Replace("'", "''")
        $proxyLines = if ($appliedProxy) {
            $ep = $appliedProxy.Replace("'", "''")
            "`$env:HTTP_PROXY='$ep'; `$env:HTTPS_PROXY='$ep'; "
        } else { '' }
        $cmdBody = "`$Host.UI.RawUI.WindowTitle='$title'; `$env:CODEX_HOME='$escapedHome'; $proxyLinesWrite-Host '=== Codex Sign-In for profile: $Name ===' -ForegroundColor Cyan; Write-Host 'CODEX_HOME = $escapedHome' -ForegroundColor DarkGray; & '$escapedExe' login"
        $proc = Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoExit', '-NoProfile', '-Command', $cmdBody) -PassThru
        $res = [PSCustomObject]@{ ok = $true; name = $Name; mode = 'login'; pid = $proc.Id }
        if ($Json) { $res | ConvertTo-Json -Depth 4 } else { Write-Host "[OK] Opened interactive Codex login terminal for '$Name' (PID $($proc.Id))" -ForegroundColor Green }
    }

    'CreateShortcut' {
        if ($Name -ne 'default') {
            $p = Get-ProfilePaths $Name
            if (-not (Test-Path -LiteralPath $p.CodexHome)) { throw "Profile '$Name' does not exist." }
        }
        $vbsPath = Join-Path $ScriptDir 'SilentLaunchCodex.vbs'
        $desktopDir = [Environment]::GetFolderPath('Desktop')
        $m = Get-ProfileMeta $Name
        $shortcutName = if ($m -and $m.label) { $m.label } else { "Codex - $Name" }
        $safeShortcutName = ($shortcutName -replace '[\\/:*?"<>|]', '_')
        $lnkPath = Join-Path $desktopDir "$safeShortcutName.lnk"

        $ws = New-Object -ComObject WScript.Shell
        $sc = $ws.CreateShortcut($lnkPath)
        $sc.TargetPath = "$env:SystemRoot\System32\wscript.exe"
        $sc.Arguments = "`"$vbsPath`" `"$Name`""
        $sc.WorkingDirectory = $ScriptDir
        $sc.Description = "Launch Codex Desktop ($Name) side-by-side"
        $desktopExe = Find-CodexDesktopExe
        if ($desktopExe) { $sc.IconLocation = "$desktopExe,0" }
        $sc.Save()

        $res = [PSCustomObject]@{ ok = $true; name = $Name; shortcut = $lnkPath }
        if ($Json) { $res | ConvertTo-Json -Depth 4 } else { Write-Host "[OK] Created shortcut: $lnkPath" -ForegroundColor Green }
    }

    'Remove' {
        if ($Name -eq 'default') { throw "Refusing to delete the default (~/.codex) profile." }
        if (-not (Test-ValidProfileName $Name)) { throw "Invalid profile name '$Name'." }
        $p = Get-ProfilePaths $Name
        if (Test-Path -LiteralPath $p.Root) {
            Remove-Item -LiteralPath $p.Root -Recurse -Force
        }
        Remove-ProfileMeta $Name
        $res = [PSCustomObject]@{ ok = $true; name = $Name; removed = $true }
        if ($Json) { $res | ConvertTo-Json -Depth 4 } else { Write-Host "[OK] Removed isolated Codex profile '$Name'" -ForegroundColor Yellow }
    }
}
