#!/usr/bin/env bash
# Styling and settings apply only to this process; no KDE settings are changed.
set -euo pipefail
exec python3 "$HOME/.config/hypr/theme/run.py" python3 "$HOME/.config/hypr/control_center/app.py" "$@"
