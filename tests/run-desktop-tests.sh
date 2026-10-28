#!/usr/bin/env bash
set -euo pipefail
test_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export QT_QPA_PLATFORM=offscreen
export GSETTINGS_BACKEND=memory
export NO_AT_BRIDGE=1
for test_component in control_center launcher desktop_menu media theme switcher share-picker scripts startup waybar/options image_viewer file_jobs effects/burn; do
    (
        cd "$test_root/config/hypr/$test_component"
        python3 -m unittest discover -p 'test_*.py' -v
    )
done
