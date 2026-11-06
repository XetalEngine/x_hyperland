#!/usr/bin/env bash
# Minimal prerequisites, before Python/GTK can run the normal Setup worker.
set -euo pipefail
if (( EUID != 0 )); then
    echo 'Launch this prerequisite step through Xetal Setup.' >&2
    exit 1
fi
case "${1:-}" in
    python|gtk3) setup_prerequisite=$1 ;;
    *) echo 'Unknown Setup prerequisite.' >&2; exit 1 ;;
esac
if command -v pacman >/dev/null 2>&1; then
    setup_keyrings=()
    for setup_keyring in archlinux-keyring manjaro-keyring cachyos-keyring endeavouros-keyring; do
        if pacman -Q "$setup_keyring" >/dev/null 2>&1; then
            setup_keyrings+=("$setup_keyring")
        fi
    done
    if (( ${#setup_keyrings[@]} == 0 )); then
        echo 'A trusted distribution signing keyring is required.' >&2
        exit 1
    fi
    pacman -Sy --noconfirm --needed "${setup_keyrings[@]}"
    # An old bootstrap must not mix a new Python/GTK with old system libraries.
    pacman -Syu --noconfirm --needed "$setup_prerequisite"
elif command -v dnf >/dev/null 2>&1; then
    [[ $setup_prerequisite != python ]] || setup_prerequisite=python3
    dnf install -y "$setup_prerequisite"
elif command -v apt-get >/dev/null 2>&1; then
    if [[ $setup_prerequisite == python ]]; then
        setup_prerequisite=python3
    else
        setup_prerequisite=libgtk-3-0t64
    fi
    apt-get update
    apt-get install -y "$setup_prerequisite"
else
    echo 'No supported package manager is available for Setup prerequisites.' >&2
    exit 1
fi
