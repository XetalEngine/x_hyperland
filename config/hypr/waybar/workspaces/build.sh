#!/usr/bin/env bash
set -euo pipefail
workspace_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
workspace_output="$(mktemp "$workspace_root/.button-XXXXXX.so")"
trap 'rm -f -- "$workspace_output"' EXIT
read -r -a workspace_flags <<< "$(pkg-config --cflags --libs gtk+-3.0 gtk-layer-shell-0)"
cc -std=c11 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -fPIC -shared \
    "$workspace_root/button.c" -o "$workspace_output" "${workspace_flags[@]}"
chmod 755 "$workspace_output"
mv -f -- "$workspace_output" "$workspace_root/controls.so"
read -r -a workspace_flags <<< "$(pkg-config --cflags --libs gtk+-3.0 json-glib-1.0)"
cc -std=c11 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -fPIC -shared \
    "$workspace_root/mode.c" -o "$workspace_output" "${workspace_flags[@]}"
chmod 755 "$workspace_output"
mv -f -- "$workspace_output" "$workspace_root/mode.so"
