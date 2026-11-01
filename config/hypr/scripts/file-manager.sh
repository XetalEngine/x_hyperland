#!/usr/bin/env bash
# Follow the user's Default Apps choice; Fusion Files remains the fresh default.
set -euo pipefail
profile="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "$profile/control_panel/default_apps.py" open-folder "$@"
