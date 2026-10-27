#!/usr/bin/env bash
# A separate Dolphin profile: no KDE preferences or service menus are written.
set -euo pipefail
[[ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]] || exit 1
base="$HOME/.config/hypr/dolphin"
export XDG_CONFIG_HOME="$base/config"
export XDG_DATA_HOME="$base/data"
export XDG_STATE_HOME="$base/state"
export XDG_CACHE_HOME="$base/cache"
export XDG_DATA_DIRS="$HOME/.local/share:/usr/local/share:/usr/share"
export XDG_CURRENT_DESKTOP=Hyprland
export XDG_SESSION_DESKTOP=Hyprland
# --new-window prevents a light instance from swallowing this launch.
exec python3 "$HOME/.config/hypr/theme/run.py" dolphin --new-window "$@"
