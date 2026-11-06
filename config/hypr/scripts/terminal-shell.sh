#!/bin/sh
# Only this Kitty profile uses the Fusion welcome. User aliases remain in their original rc file.
set -eu
fusion_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export XETAL_FUSION_TERMINAL=1
fusion_shell=${SHELL:-/bin/sh}
# Kitty cannot identify a shell behind this wrapper, so retain its normal
# prompt/CWD integration explicitly in the profile-local startup files.
if [ -n "${KITTY_INSTALLATION_DIR:-}" ]; then
    export KITTY_SHELL_INTEGRATION=${KITTY_SHELL_INTEGRATION:-no-cursor}
fi
case "${fusion_shell##*/}" in
    zsh)
        export XETAL_USER_ZDOTDIR=${ZDOTDIR:-$HOME}
        export ZDOTDIR="$fusion_root/terminal_fetch/zsh"
        exec "$fusion_shell" -i "$@" ;;
    bash)
        exec "$fusion_shell" --rcfile "$fusion_root/terminal_fetch/bashrc" -i "$@" ;;
    fish)
        export XETAL_FUSION_FETCH="$fusion_root/terminal_fetch/model.py"
        export XETAL_FUSION_COMMANDS="$fusion_root/terminal_fetch/commands.fish"
        exec "$fusion_shell" -i -C 'source "$XETAL_FUSION_COMMANDS"; set --erase XETAL_FUSION_COMMANDS; if test -n "$KITTY_INSTALLATION_DIR"; and test "$KITTY_SHELL_INTEGRATION" != disabled; and test -r "$KITTY_INSTALLATION_DIR/shell-integration/fish/vendor_conf.d/kitty-shell-integration.fish"; source "$KITTY_INSTALLATION_DIR/shell-integration/fish/vendor_conf.d/kitty-shell-integration.fish"; end; python3 "$XETAL_FUSION_FETCH"' "$@" ;;
    *)
        python3 "$fusion_root/terminal_fetch/model.py" || true
        exec "$fusion_shell" -i "$@" ;;
esac
