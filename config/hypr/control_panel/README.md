# Hyper Fusion Control Panel

Native floating Qt/C++ panel, opened from Apps above Fusion Settings. See the [feature map and integration guide](../../../docs/CONTROL-PANEL.md).

- `backend/`: complete CachyOsTools source/resources at the revision in `UPSTREAM.json`, with desktop integration changes. The original checkout remains independent.
- `native.*`, `main.cpp`, `tools.json`: icon navigation, responsive layout and shared appearance.
- `bridge.py`, `shell_adapter.h`, `aliases.py`: shell settings and the existing Apps shortcut editor.
- `startup.py`, `terminal.py`: Hyprland startup applications/environment and Kitty integration.
- `disk_visualizer.*`, `disk_layout.h`: lazy disk tree, breadcrumbs and squarified treemap in System Cleaner.
- `disk_scan.py`: pipe-owned sudo metadata scanner, disposable SQLite index and ID-based deletion; `test_disk_scan.py` exercises isolated fixtures.
- `backend/iso/`: original ISO builder and installer payloads, embedded in the executable.
- `build.py`: local native build. `.build/` and `state/` are not committed.
- `test_adapters.py`: isolated adapter, coverage and ISO-resource checks.

License: GPLv3; see `LICENSE`. Original source attribution and documentation are retained.
