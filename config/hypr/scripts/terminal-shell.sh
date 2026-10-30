#!/bin/sh
# Only this Kitty profile uses the Fusion welcome. User aliases remain in their original rc file.
set -eu
fusion_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export XETAL_FUSION_TERMINAL=1
fusion_shell=${SHELL:-/bin/sh}
case "${fusion_shell##*/}" in
    zsh)
        export XETAL_USER_ZDOTDIR=${ZDOTDIR:-$HOME}
        export ZDOTDIR="$fusion_root/terminal_fetch/zsh"
        exec "$fusion_shell" -i "$@" ;;
    bash)
        exec "$fusion_shell" --rcfile "$fusion_root/terminal_fetch/bashrc" -i "$@" ;;
    fish)
        export XETAL_FUSION_FETCH="$fusion_root/terminal_fetch/model.py"
        exec "$fusion_shell" -i -C 'python3 "$XETAL_FUSION_FETCH"' "$@" ;;
    *)
        python3 "$fusion_root/terminal_fetch/model.py" || true
        exec "$fusion_shell" -i "$@" ;;
esac
