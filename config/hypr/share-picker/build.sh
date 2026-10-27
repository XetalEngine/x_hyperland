#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$(readlink -f -- "$0")")"
mkdir -p build
for name in hyprland-toplevel-export-v1 wlr-foreign-toplevel-management-unstable-v1; do
    wayland-scanner client-header "protocols/$name.xml" "build/$name-client.h"
    wayland-scanner private-code "protocols/$name.xml" "build/$name-protocol.c"
    cc -O2 -fPIC -c "build/$name-protocol.c" -o "build/$name.o" $(pkg-config --cflags wayland-client)
done
c++ -std=c++20 -O2 -fPIC -Wall -Wextra -Ibuild window-preview.cpp build/*.o \
    $(pkg-config --cflags --libs Qt6Gui wayland-client) -o build/window-preview.new
mv build/window-preview.new window-preview
