#!/usr/bin/env bash
set -euo pipefail
options_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
options_output="$(mktemp "$options_root/.options-XXXXXX.so")"
trap 'rm -f -- "$options_output"' EXIT
read -r -a options_flags <<< "$(pkg-config --cflags --libs gtk+-3.0 json-glib-1.0)"
cc -std=c11 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -fPIC -shared \
    "$options_root/options.c" -o "$options_output" "${options_flags[@]}"
chmod 755 "$options_output"
mv -f -- "$options_output" "$options_root/options.so"
