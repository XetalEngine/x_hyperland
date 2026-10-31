#!/usr/bin/env bash
# Run as your desktop user. Only distribution package installation uses sudo.
set -euo pipefail
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
    if [[ ! -t 0 ]] && command -v kitty >/dev/null 2>&1; then
        exec kitty --title 'Xetal Setup prerequisites' bash "$repo_dir/x_hyperinstall.sh" "$@"
    fi
    if [[ -t 0 ]] && { command -v pacman >/dev/null 2>&1 || command -v dnf >/dev/null 2>&1; }; then
        read -r -p 'Install Python to open Xetal Setup? [Y/n] ' setup_answer
        case "$setup_answer" in
            ''|[yY]|[yY][eE][sS])
                if command -v pacman >/dev/null 2>&1; then sudo pacman -S --needed python
                else sudo dnf install python3; fi ;;
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
