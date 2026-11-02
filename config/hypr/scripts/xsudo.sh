#!/usr/bin/env bash
# Hyprland-only graphical elevation, with temporary display authorization.
exec python3 "$(dirname -- "$(readlink -f -- "$0")")/gui-admin.py" "$@"
