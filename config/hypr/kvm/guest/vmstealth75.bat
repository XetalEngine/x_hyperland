@echo off
setlocal DisableDelayedExpansion
REM Windows guest helper: run manually after Windows reaches the desktop.
REM KVM Settings downloads, decrypts and loads the matching modules BEFORE VM boot.
REM This helper verifies the loaded modules and enables native CPUID after boot.
REM A running VM cannot have its KVM modules replaced. System KVM is unsupported.
REM KVM Settings Copy fills your Linux login, local SSH port and selected VM paths.
set "HOST_LOGIN=YOUR_LINUX_USER@YOUR_LINUX_HOST"
set "HOST_PORT=2222"
REM These are the standard KVM Settings paths in the SSH user's Linux home.
REM Enable local SSH in KVM Settings before running the copied script.
set "HOST_HELPER=.config/hypr/kvm/guest/vmstealth75.sh"
set "QMP_SOCKET=.local/share/xetal-kvm/run/qmp.sock"
set "GUEST_NAME=win10"
REM Run with "on" before rebooting Windows inside this VM; default is "off".
set "CPUID_MODE=off"
if /I "%~1"=="on" set "CPUID_MODE=on"
if not "%~1"=="" if /I not "%~1"=="on" if /I not "%~1"=="off" (
    echo Usage: %~nx0 [on or off]
    exit /b 2
)

if "%HOST_LOGIN%"=="YOUR_LINUX_USER@YOUR_LINUX_HOST" (
    echo Edit HOST_LOGIN in this file before running it.
    echo Use your Linux username and the host address, separated by @.
    pause
    exit /b 2
)
where ssh.exe >nul 2>&1
if errorlevel 1 (
    echo Install the Windows OpenSSH Client optional feature, then retry.
    pause
    exit /b 2
)
echo Use your Linux password for SSH and for the sudo administrator prompt.
REM Keep SSH host-key checking enabled. Allocate a terminal for the sudo prompt.
ssh.exe -tt -o ConnectTimeout=15 -p "%HOST_PORT%" "%HOST_LOGIN%" "bash '%HOST_HELPER%' --qmp '%QMP_SOCKET%' --domain '%GUEST_NAME%' --cpuid '%CPUID_MODE%'"
set "Result=%errorlevel%"
if not "%Result%"=="0" (
    echo.
    echo Guest helper failed. Read the message above before retrying.
)
pause
exit /b %Result%
