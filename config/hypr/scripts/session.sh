#!/usr/bin/env bash
# Own only the processes started here. Stop them when this Hyprland instance ends.
# Never change KDE, shared GTK/Qt settings, D-Bus activation variables or user services.
set -euo pipefail
umask 077

[[ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" && -n "${XDG_RUNTIME_DIR:-}" ]] || exit 1
instance_dir="$XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE"
[[ -S "$instance_dir/.socket.sock" ]] || exit 1

exec 9>"$instance_dir/isolated-helpers.lock"
flock -n 9 || exit 0
config_dir="$HOME/.config/hypr"

# Prepared updates activate before any session helper or native effect is loaded.
# A replaced launcher is re-executed; applications are never logged out by updates.
if [[ "${XETAL_UPDATE_ACTIVATED:-}" != 1 ]]; then
    update_result=0
    python3 "$config_dir/updates/service.py" --activate >"$instance_dir/update-activation.log" 2>&1 || update_result=$?
    if [[ "$update_result" == 20 ]]; then
        hyprctl reload >>"$instance_dir/update-activation.log" 2>&1 || true
        exec 9>&-
        export XETAL_UPDATE_ACTIVATED=1
        exec bash "$config_dir/scripts/session.sh"
    fi
fi
unset XETAL_UPDATE_ACTIVATED
children=()

cleanup() {
    trap - EXIT
    for child in "${children[@]}"; do
        kill "$child" 2>/dev/null || true
    done
    wait || true
}
trap cleanup EXIT
trap 'exit 0' INT TERM HUP

export XDG_CURRENT_DESKTOP=Hyprland
export XDG_SESSION_DESKTOP=Hyprland
export XDG_SESSION_TYPE=wayland

# Opt-in sign-in artwork is a public copy; private home settings stay private.
python3 "$config_dir/login/profile.py" >"$instance_dir/sign-in-artwork.log" 2>&1 || true

python3 "$config_dir/updates/service.py" --serve >"$instance_dir/desktop-updates.log" 2>&1 9>&- &
children+=("$!")

# Rebuild the profile-local palette plugins if the installed Qt version changed.
if ! python3 "$config_dir/theme/build.py" >"$instance_dir/theme-build.log" 2>&1; then
    printf '%s\n' 'Theme plugin rebuild failed; see theme-build.log. Session tools will still start.' >&2
fi

# Optional native effects are private to this compositor. Unsupported versions
# keep the normal close animation; building never delays the rest of the shell.
python3 "$config_dir/effects/burn/controller.py" --session >"$instance_dir/burn.log" 2>&1 9>&- &
children+=("$!")

# Each output has its own optional cube; this loader exits with the compositor.
python3 "$config_dir/effects/cube/controller.py" --session >"$instance_dir/cube.log" 2>&1 9>&- &
children+=("$!")

# Native minimize requests and fireballs belong to this compositor only.
python3 "$config_dir/effects/minimize/controller.py" --session >"$instance_dir/minimize.log" 2>&1 9>&- &
children+=("$!")

# User-configured startup applications belong to this Hyprland session.
python3 "$config_dir/control_panel/startup.py" --session >"$instance_dir/panel-startup.log" 2>&1 9>&- &
children+=("$!")

# Preload Apps, Fusion Settings/Theme and Control Panel without mapping windows.
python3 "$config_dir/session_ui/preload.py" >"$instance_dir/session-ui-preload.log" 2>&1 9>&- &
children+=("$!")

# A resident switcher receives ordered key events, including a very quick Super release.
"$config_dir/scripts/app-switcher.sh" >"$instance_dir/switcher.log" 2>&1 9>&- &
children+=("$!")

# Plain left-drag near the top of floating windows; idle between click events.
python3 "$config_dir/scripts/floating-drag.py" >"$instance_dir/floating-drag.log" 2>&1 9>&- &
children+=("$!")

# File-operation progress uses the standard job interface and ends with this session.
"$config_dir/scripts/file-progress.sh" >"$instance_dir/file-progress.log" 2>&1 9>&- &
children+=("$!")

# Recover a crashed bar inside this session; logout stops the owner and its bar.
python3 "$config_dir/scripts/waybar-session.py" \
    >"$instance_dir/waybar-supervisor.log" 2>&1 9>&- &
children+=("$!")

# Wallpaper renderer belongs to this session and reads only the Hyprland profile.
if ! pgrep -u "$UID" -x hyprpaper >/dev/null; then
    hyprpaper --config "$config_dir/wallpaper/hyprpaper.conf" \
        >"$instance_dir/hyprpaper.log" 2>&1 9>&- &
    children+=("$!")
fi

# Native right-click menus receive input only on the uncovered wallpaper.
"$config_dir/scripts/desktop-menu.sh" >"$instance_dir/desktop-menu.log" 2>&1 9>&- &
children+=("$!")

# A real tray network applet, owned by this Hyprland session only.
if ! pgrep -u "$UID" -x nm-applet >/dev/null; then
    XDG_CONFIG_HOME="$config_dir/apps" GSETTINGS_BACKEND=keyfile GTK_THEME="${GTK_THEME:-Adwaita:dark}" nm-applet --indicator \
        >"$instance_dir/network-applet.log" 2>&1 9>&- &
    children+=("$!")
fi

# Respect an existing notification server, including one belonging to another desktop.
owner=$(gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus \
    --method org.freedesktop.DBus.NameHasOwner org.freedesktop.Notifications) || owner=unknown
if [[ "$owner" == '(false,)' ]]; then
    swaync --config "$config_dir/swaync/config.json" --style "$config_dir/swaync/style.css" \
        >"$instance_dir/swaync.log" 2>&1 9>&- &
    children+=("$!")
fi

# Do not replace an authentication agent that is already running.
if ! pgrep -u "$UID" -f '^/usr/(lib|libexec)/(polkit-gnome/polkit-gnome-authentication-agent-1|polkit-gnome-authentication-agent-1|policykit-1-gnome/polkit-gnome-authentication-agent-1|polkit-kde-authentication-agent-1|kf6/polkit-kde-authentication-agent-1|hyprpolkitagent)( |$)' >/dev/null; then
    for agent in /usr/lib/polkit-gnome/polkit-gnome-authentication-agent-1 \
                 /usr/libexec/polkit-gnome-authentication-agent-1 \
                 /usr/lib/policykit-1-gnome/polkit-gnome-authentication-agent-1 \
                 /usr/libexec/hyprpolkitagent; do
        if [[ -x "$agent" ]]; then
            "$agent" >"$instance_dir/polkit-agent.log" 2>&1 9>&- &
            children+=("$!")
            break
        fi
    done
fi

# A live IPC connection also closes if Hyprland crashes and leaves stale socket files.
# This prevents our helpers from surviving into a later KDE session.
python3 - "$instance_dir/.socket2.sock" 9>&- <<'PY' &
import socket
import sys

with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
    stream.connect(sys.argv[1])
    while stream.recv(65536):
        pass
PY
watcher=$!
children+=("$watcher")
wait "$watcher"
