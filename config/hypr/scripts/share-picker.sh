#!/usr/bin/env bash
set -euo pipefail
# The portal can predate the current Qt theme; our local picker styles itself.
unset QT_QPA_PLATFORMTHEME
export QT_STYLE_OVERRIDE=Fusion
exec python3 "$HOME/.config/hypr/share-picker/app.py" "$@"
