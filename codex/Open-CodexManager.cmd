@echo off
chcp 65001 >nul
setlocal
set "SCRIPT_DIR=%~dp0"
echo ====================================================
echo   Codex Side-by-Side Multi-Account Manager (CLI)
echo ====================================================
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%Codex-Multi.ps1" -Action List
echo.
echo Commands:
echo   [1] Create new isolated Codex profile
echo   [2] Launch Codex Desktop for a profile
echo   [3] Launch Codex CLI for a profile
echo   [4] Sign in (codex login) for a profile
echo   [5] Create desktop shortcut for a profile
echo   [6] Sync shared config/skills/AGENTS.md to all profiles
echo   [Q] Quit
echo.
set /p "CHOICE=Select option: "
if /i "%CHOICE%"=="Q" exit /b 0
if "%CHOICE%"=="1" (
    set /p "PNAME=Profile name (e.g. acc2, work): "
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%Codex-Multi.ps1" -Action Create -Name "%PNAME%"
    pause
    exit /b 0
)
if "%CHOICE%"=="2" (
    set /p "PNAME=Profile name (default / acc2 / ...): "
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%Codex-Multi.ps1" -Action LaunchDesktop -Name "%PNAME%"
    pause
    exit /b 0
)
if "%CHOICE%"=="3" (
    set /p "PNAME=Profile name (default / acc2 / ...): "
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%Codex-Multi.ps1" -Action LaunchCli -Name "%PNAME%"
    pause
    exit /b 0
)
if "%CHOICE%"=="4" (
    set /p "PNAME=Profile name (default / acc2 / ...): "
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%Codex-Multi.ps1" -Action Login -Name "%PNAME%"
    pause
    exit /b 0
)
if "%CHOICE%"=="5" (
    set /p "PNAME=Profile name (default / acc2 / ...): "
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%Codex-Multi.ps1" -Action CreateShortcut -Name "%PNAME%"
    pause
    exit /b 0
)
if "%CHOICE%"=="6" (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%Codex-Multi.ps1" -Action SyncShared -Name all
    pause
    exit /b 0
)
exit /b 0
