#!/usr/bin/env bash
# Hyprland-only capture; independent of Spectacle and shared desktop settings.
set -euo pipefail
umask 077

[[ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" && -n "${WAYLAND_DISPLAY:-}" ]] || {
    printf 'Run this screenshot helper inside Hyprland.\n' >&2
    exit 1
}

# Hold the menu open before slurp takes keyboard focus. Children close this fd
# so a clipboard owner or notification broker cannot retain the capture guard.
exec {screenshot_guard_fd}>"$XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE/screenshot-active.lock"
flock --exclusive --nonblock "$screenshot_guard_fd" || exit 0

capture_args=()
case "${1:-area}" in
    area)
        region=$(slurp {screenshot_guard_fd}>&-) || exit 0
        [[ -n "$region" ]] || exit 0
        capture_args=(-g "$region")
        ;;
    screen) ;;
    *) printf 'Usage: %s [area|screen]\n' "$0" >&2; exit 2 ;;
esac

pictures=$(xdg-user-dir PICTURES 2>/dev/null) || pictures="$HOME/Pictures"
directory="${pictures:-$HOME/Pictures}/Screenshots"
mkdir -p -- "$directory"
file=$(mktemp --tmpdir="$directory" --suffix=.png "Screenshot-$(date +%F_%H-%M-%S)-XXXXXX")
if ! grim "${capture_args[@]}" "$file" {screenshot_guard_fd}>&-; then
    rm -f -- "$file"
    notify-send -a 'Hyprland Screenshot' 'Screenshot failed' 'The screen could not be captured.' || true
    exit 1
fi

if wl-copy --type image/png < "$file" {screenshot_guard_fd}>&-; then
    summary='Screenshot saved and copied'
else
    summary='Screenshot saved (clipboard unavailable)'
fi
flock --unlock "$screenshot_guard_fd"
exec {screenshot_guard_fd}>&-
python3 "$HOME/.config/hypr/scripts/screenshot-notify.py" "$file" "$summary" \
    </dev/null >"$XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE/screenshot-notify.log" 2>&1 &
printf '%s\n' "$file"
