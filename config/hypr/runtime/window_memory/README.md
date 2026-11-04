# Window memory

`service.py` runs only for its Hyprland instance, follows the compositor event
socket and uses a per-instance lock. It observes windows already open at startup;
only newly mapped windows receive saved geometry. Normal windows and transient
dialogs have separate hashed identities. No titles, filenames, process IDs or
monitor serials are persisted. `state/` is private and preserved by updates.

The exact-ABI native adapter supplies transient/role metadata and addressed
fullscreen changes without moving focus. Zero xdg-shell size limits mean
unspecified, not fixed. Rebuild it with `build.py` for the pinned runtime. Never
overwrite a native library already mapped by a running compositor. A tested
adapter update uses a new build path and a controlled plugin unload/load while
the memory watcher is stopped; existing windows are only observed on restart.

The adapter also aligns pointer hits and held-button motion with xdg window
geometry when clients include invisible decoration padding. The Minimize
adapter's render crop uses that same origin. First-map launcher fullscreen
rules are released back to ordinary client/compositor state synchronization,
so later native maximize/restore controls continue to work.

Numbered workspace overrides live in `workspaces/rules.json`. The adapter applies
forced tiling/floating before the first layout and to existing or incoming
windows. A native mode-change hook prevents conflicting app/launcher restores;
tiled drag gestures retain their temporary floating path and rejoin the layout
on release. The watcher skips app-mode restoration and sampling in forced
workspaces so those overrides do not replace an app's ordinary remembered mode.

Restoration separates mode, geometry and fullscreen into different compositor
frames; changing floating state replaces the layout target. Normal floating
size is preserved when maximizing. Tiled windows retain their remembered mode,
but their sizes belong to the current shared layout. Never restore a saved
tiled pixel size: it changes sibling splits and can squeeze a new window into
a narrow strip. Older tiled-size records remain readable and are ignored for
geometry restoration. Floating sizes stay within the current monitor and
application constraints. Layer-shell surfaces and unmapped/hidden
windows are not ordinary managed windows. Apps-menu launches explicitly choose
tiling; Ctrl-click chooses floating. Both carry first-map launch tags and bypass
later generic mode restoration, including stale maximized preferences. Floating
launches retain `launcher/floating.py`'s per-shortcut normal size and position,
fitted to the destination monitor. Saved floating geometry survives tiling and
maximizing. Bar pins and launch hotkeys retain their explicit shortcut preference.

Fusion pickers keep their more recent, synchronous actual-size record in
`file_manager/state/settings.ini`; the memory helper does not override it.
The picker class rule makes every open/save request floating from its first map.

Fusion Files main windows (`xetal-files` and `xetal-files-external`) also skip
generic restoration. Ordinary launches tile; explicit launcher floating requests
use their exec rules and per-shortcut size; external folder/reveal requests use
a floating/centered class rule and the Files `external/size` preference before
mapping. Files child dialogs still restore independently. This prevents older
generic or Qt maximize state from changing these launch modes after opening.

Run `python3 -m unittest discover -s config/hypr/runtime/window_memory` and the
real compositor check `tests/check-file-picker.py OUTPUT_DIR FILES_BUILD`.
Append `--memory-only` to check floating/maximized restoration and balanced
tiles when reopening two windows quickly or mixing applications.
The latter uses private settings, a private D-Bus and disabled XWayland; input
never reaches the parent desktop.
