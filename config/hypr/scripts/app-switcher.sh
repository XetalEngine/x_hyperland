#!/usr/bin/env bash
exec env QT_QPA_PLATFORMTHEME= QT_STYLE_OVERRIDE=Fusion python3 "$HOME/.config/hypr/switcher/app.py" "$@"
