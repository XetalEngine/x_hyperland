#!/usr/bin/env bash
# This helper belongs only to the current Hyprland session.
set -euo pipefail
exec python3 "$HOME/.config/hypr/desktop_menu/app.py"
