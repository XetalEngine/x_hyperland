#!/usr/bin/env bash
set -euo pipefail
test_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export QT_QPA_PLATFORM=offscreen
export GSETTINGS_BACKEND=memory
export NO_AT_BRIDGE=1
for test_component in recording control_panel control_center launcher desktop_menu media theme switcher wallpaper share-picker scripts startup waybar/options image_viewer file_jobs file_manager quick_panel terminal_fetch session_ui login effects/burn effects/cube effects/minimize effects/wobbly updates kvm; do
    (
        cd "$test_root/config/hypr/$test_component"
        python3 -m unittest discover -p 'test_*.py' -v
    )
done
