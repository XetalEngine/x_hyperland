# Sourced by Fusion's Bash and Zsh terminals after the user's own rc file.
# Profile-only updates cannot install /usr/local/bin commands, and some login
# environments omit that directory. Keep the checker usable in either case.
if ! command -v fusion-check >/dev/null 2>&1; then
    function fusion-check {
        /bin/sh "$HOME/.config/hypr/bin/fusion-check" "$@"
    }
fi
