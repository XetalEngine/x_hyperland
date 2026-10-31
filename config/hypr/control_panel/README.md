# Hyper Fusion Control Panel

Native floating Qt/C++ panel, opened from Apps above Fusion Settings. See the [feature map and integration guide](../../../docs/CONTROL-PANEL.md).

- `backend/`: complete CachyOsTools source/resources at the revision in `UPSTREAM.json`, with desktop integration changes. The original checkout remains independent.
- `native.*`, `main.cpp`, `tools.json`: icon navigation, responsive layout and shared appearance.
- `bridge.py`, `shell_adapter.h`, `aliases.py`: shell settings and the existing Apps shortcut editor.
- `startup.py`, `terminal.py`: Hyprland startup applications/environment and Kitty integration.
- `disk_visualizer.*`, `disk_layout.h`: lazy disk tree, breadcrumbs and squarified treemap in System Cleaner.
- `disk_scan.py`: pipe-owned sudo metadata scanner, disposable SQLite index and ID-based deletion; `test_disk_scan.py` exercises isolated fixtures.
- `ram_cleaner.*`: manual file/metadata cache reclamation, live memory readings and observed before/after results. The Python helper authenticates only on cleanup; it never closes apps, deletes files or changes swap.
- `backend/iso/`: original ISO builder and installer payloads, embedded in the executable.
- `backend/drive_tree.*`: expandable disks and partitions with a compact minimum-size filter; refresh preserves expansion and selection. Device actions use stored paths and types, including mounted descendants hidden by the filter.
- `window_sizing.h`: 1650 × 910 starting size for tool windows, bounded to the screen; small confirmation prompts retain their content size.
- `build.py`: local native build. `.build/` and `state/` are not committed.
- `test_adapters.py`: isolated adapter, coverage and ISO-resource checks.

License: GPLv3; see `LICENSE`. Original source attribution and documentation are retained.
