#!/usr/bin/env bash
set -euo pipefail
exec python3 "$HOME/.config/hypr/theme/run.py" python3 "$HOME/.config/hypr/control_center/logout.py" "$@"
