#!/usr/bin/env bash
# Invoked from Windows over SSH after the guest has reached the desktop.
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if (( EUID != 0 )); then
    exec sudo -- /usr/bin/python3 "$root/guest_timing.py" "$@"
fi
exec /usr/bin/python3 "$root/guest_timing.py" "$@"
