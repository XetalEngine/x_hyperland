#!/usr/bin/env bash
# Run as your desktop user. Only distribution package installation uses sudo.
set -euo pipefail
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -x /usr/bin/python3 ]]; then
    exec /usr/bin/python3 "$repo_dir/installer/install.py" "$@"
fi
exec python3 "$repo_dir/installer/install.py" "$@"
