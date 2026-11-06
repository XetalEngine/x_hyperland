#!/usr/bin/env bash
# Run as your desktop user. Only system operations request administrator access.
set -euo pipefail
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if (( EUID == 0 )); then
    echo 'Run Xetal Setup as your regular desktop user, without sudo. It requests administrator access when needed.' >&2
    exit 1
fi
setup_as_admin() {
    if command -v sudo >/dev/null 2>&1; then
        sudo "$@"
    elif command -v su >/dev/null 2>&1; then
        local setup_command
        printf -v setup_command '%q ' "$@"
        echo 'sudo is not installed. Authenticate with your system root password.' >&2
        su --login --shell /bin/bash --command "$setup_command" root
        export XETAL_SETUP_AUTH_SU=1
    else
        echo 'Setup needs sudo or su to install its missing prerequisites.' >&2
        return 1
    fi
}
if ! command -v python3 >/dev/null 2>&1; then
    if [[ ! -t 0 ]] && command -v kitty >/dev/null 2>&1; then
        exec kitty --title 'Xetal Setup prerequisites' bash "$repo_dir/x_hyperinstall.sh" "$@"
    fi
    if [[ -t 0 ]] && { command -v pacman >/dev/null 2>&1 || command -v dnf >/dev/null 2>&1 || command -v apt-get >/dev/null 2>&1; }; then
        setup_prompt='Install Python to open Xetal Setup? [Y/n] '
        if command -v pacman >/dev/null 2>&1; then
            setup_prompt='Install Python and upgrade Arch-family packages to open Setup? [Y/n] '
        fi
        read -r -p "$setup_prompt" setup_answer
        case "$setup_answer" in
            ''|[yY]|[yY][eE][sS])
                setup_as_admin /bin/bash "$repo_dir/installer/bootstrap_packages.sh" python ;;
            *) exit 1 ;;
        esac
    else
        echo 'Xetal Setup needs Python 3. Install python3, then run this installer again.' >&2
        exit 1
    fi
fi
if [[ -x /usr/bin/python3 ]]; then
    exec /usr/bin/python3 "$repo_dir/installer/launcher.py" "$@"
fi
exec python3 "$repo_dir/installer/launcher.py" "$@"
