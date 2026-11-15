#!/usr/bin/env bash
exec env QT_QPA_PLATFORMTHEME= QT_STYLE_OVERRIDE=Fusion /usr/bin/python3 "$HOME/.config/hypr/clipboard/launch.py" "$@"
