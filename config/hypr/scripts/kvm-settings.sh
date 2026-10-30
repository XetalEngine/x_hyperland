#!/usr/bin/env bash
set -euo pipefail
exec python3 "$HOME/.config/hypr/session_ui/client.py" kvm "$@"
