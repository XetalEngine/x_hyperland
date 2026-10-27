#!/usr/bin/env bash
set -euo pipefail
pin_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
pin_output="$(mktemp "$pin_root/.pins-XXXXXX.so")"
trap 'rm -f -- "$pin_output"' EXIT
read -r -a pin_flags <<< "$(pkg-config --cflags --libs gtk+-3.0 json-glib-1.0)"
cc -std=c11 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -fPIC -shared \
    "$pin_root/pins.c" -o "$pin_output" "${pin_flags[@]}"
chmod 755 "$pin_output"
mv -f -- "$pin_output" "$pin_root/pins.so"
