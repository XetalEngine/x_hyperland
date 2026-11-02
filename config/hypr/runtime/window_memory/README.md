# Window memory

`service.py` runs only for its Hyprland instance, follows the compositor event
socket and uses a per-instance lock. It observes windows already open at startup;
only newly mapped windows receive saved geometry. Normal windows and transient
dialogs have separate hashed identities. No titles, filenames, process IDs or
monitor serials are persisted. `state/` is private and preserved by updates.

The exact-ABI native adapter supplies transient/role metadata and addressed
fullscreen changes without moving focus. Zero xdg-shell size limits mean
unspecified, not fixed. Rebuild it with `build.py` for the pinned runtime. Never
overwrite or unload a native library already mapped by a running compositor.

Restoration separates mode, geometry and fullscreen into different compositor
frames; changing floating state replaces the layout target. Normal floating
size is preserved when maximizing. Tiled sizes scale to the current work area
and remain subject to the tiling layout. Floating sizes stay within the current
monitor and application constraints. Layer-shell surfaces and unmapped/hidden
windows are not ordinary managed windows. Explicit launcher floating requests
retain `launcher/floating.py`'s per-shortcut memory.

Fusion pickers keep their more recent, synchronous actual-size record in
`file_manager/state/settings.ini`; the memory helper does not override it.
The picker class rule makes every open/save request floating from its first map.

Run `python3 -m unittest discover -s config/hypr/runtime/window_memory` and the
real compositor check `tests/check-file-picker.py OUTPUT_DIR FILES_BUILD`.
The latter uses private settings, a private D-Bus and disabled XWayland; input
never reaches the parent desktop.
