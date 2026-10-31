@echo off
setlocal DisableDelayedExpansion
REM Windows guest helper: run manually after Windows reaches the desktop.
REM The matching custom AMD KVM module must already be loaded on the Linux host.
REM This script does not install or load a module and is not needed for system KVM.
REM Set your SSH login below; use an address reachable from inside the guest.
set "HOST_LOGIN=YOUR_LINUX_USER@YOUR_LINUX_HOST"
set "HOST_PORT=22"
REM These are the standard KVM Settings paths in the SSH user's Linux home.
REM If you changed the workspace or VM name, adjust these three settings too.
set "HOST_HELPER=~/.local/share/xetal-kvm/components/kvm-amd/current/vmstealth75.sh"
set "QMP_SOCKET=~/.local/share/xetal-kvm/run/qmp.sock"
set "GUEST_NAME=win10"

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
REM Keep SSH host-key checking enabled. The host helper verifies module and VM state.
ssh.exe -o ConnectTimeout=15 -p "%HOST_PORT%" "%HOST_LOGIN%" "bash %HOST_HELPER% --qmp %QMP_SOCKET% --domain %GUEST_NAME%"
set "Result=%errorlevel%"
if not "%Result%"=="0" (
    echo.
    echo Guest helper failed. Read the message above before retrying.
)
pause
exit /b %Result%
