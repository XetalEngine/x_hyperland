# Window memory

`service.py` runs only for its Hyprland instance, follows the compositor event
socket and uses a per-instance lock. It observes windows already open at startup;
only newly mapped windows receive saved geometry. Normal windows and transient
dialogs have separate hashed identities. No titles, filenames, process IDs or
monitor serials are persisted. `state/` is private and preserved by updates.

All automatic geometry helpers share `runtime/window_types_native.hpp` and
`window_rules/window_types.py`. The native decision uses protocol roles: XWayland
override-redirect windows and EWMH menu, dropdown, popup, tooltip, combo, drag,
notification, splash, toolbar, dock and desktop surfaces keep their application's
geometry. Normal X11 windows (including legacy untyped windows), dialogs and
utilities remain eligible. On Wayland only xdg toplevels qualify; xdg popups do
not. No application names, dimensions or delay heuristics determine this.
See the [EWMH window types](https://specifications.freedesktop.org/wm/latest/ar01s05.html).

`xetal-windows` exposes `geometry_managed` and the same hexadecimal `stableId`
as `clients`. Python consumers require an explicit true decision and matching
stable IDs. Missing/old metadata suspends geometry handling instead of assuming
a main window. Reclassified surfaces lose pending restores and uncommitted
samples, including on close/shutdown. Menus cannot win an app's memory ownership
or consume a pending launcher request, even if class, role or launch tags match.
Workspace enforcement, title controls, title grips and Wobbly's final position
adjustment use the same native guard. Existing private state remains intact;
excluded surfaces no longer read or write it.

The exact-ABI native adapter supplies transient/role metadata and addressed
fullscreen changes without moving focus. Zero xdg-shell size limits mean
unspecified, not fixed. Rebuild it with `build.py` for the pinned runtime. Never
overwrite a native library already mapped by a running compositor. A tested
adapter update uses a new build path and a controlled plugin unload/load while
the memory watcher is stopped; existing windows are only observed on restart.

The adapter also aligns pointer hits and held-button motion with xdg window
geometry when clients include invisible decoration padding. This includes child
surfaces, such as Firefox's browser content, and their redraw coordinates. The
Minimize adapter crops the main surface and shifts its children to that same
origin before calculating clipping. Popup surfaces retain their own origin.
Main-surface partial damage also uses that visible origin: the adapter follows
the pinned core's buffer scale, transform and viewport normalization, then crops
and translates damage by the xdg geometry offset before the window-size clip.
This ordering preserves right/bottom updates until the final content clip.
Without this, typing can leave background-colored strips over text, while a
full repaint from screen capture makes the defect disappear.
First-map launcher fullscreen
rules are released back to ordinary client/compositor state synchronization,
so later native maximize/restore controls continue to work.

Numbered workspace overrides live in `workspaces/rules.json`. The adapter applies
forced tiling/floating before the first layout and to existing or incoming
windows. A native mode-change hook prevents conflicting app/launcher restores;
tiled drag gestures retain their temporary floating path and rejoin the layout
on release. The watcher skips app-mode restoration in forced workspaces. Force
floating still records and restores each app's normal floating size and position;
force tiled never restores pixel geometry or samples temporary floating drag
targets. Neither override replaces the app's ordinary remembered mode.

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
launches retain `launcher/floating.py`'s first-map placement, followed by the same
normal geometry memory used by other launch routes. Bar pins and launch hotkeys
retain their explicit shortcut mode preference.

Normal geometry memory applies to all managed floating application windows,
including Files, pickers, transient dialogs and windows with explicit launch
tags or matched rules. Fixed-size windows keep their application's size limits
and remember position. Layers/popups are not independent managed windows, and
minimized windows are not sampled. App and dialog identities remain separate.
Saved positions are relative to the destination monitor's usable desktop, so
negative origins, scaling, rotation and disconnected monitors cannot restore a
window onto a missing output. Geometry is fitted to that usable area.

The last normal rectangle survives maximizing, fullscreen, tiling, minimization
and service restarts. A sampled resize is retained even if maximizing or closing
happens before the write debounce. The last closed sibling supplies the next
window's default; simultaneous closes prefer the last focused sibling. Startup
only observes existing windows. Private state uses atomic writes and is flushed
on service shutdown. Version-1 records remain readable; old maximized/tiled sizes
are never treated as a normal floating size.

Fusion Files and picker launch rules still decide their mode. Ordinary Files
launches tile; external folder/reveal requests and pickers float. Generic mode
memory cannot override these choices, and their floating geometry is remembered
like other applications.

Run `python3 -m unittest discover -s config/hypr/runtime/window_memory` and the
real compositor check `tests/check-file-picker.py OUTPUT_DIR FILES_BUILD`.
Append `--memory-only` to check floating/maximized restoration and balanced
tiles when reopening two windows quickly or mixing applications.
The latter covers all three workspace modes, explicit launch tags, normal
position after maximized close, service restart and balanced tiles. The full
check also reopens real Chrome from a private profile. Both check the display
Primary checkbox using real Wayland mouse input through canvas repaints, since
a programmatic `click()` bypasses native mouse-grab bugs. They use private
settings, a private D-Bus and disabled XWayland; input never reaches the parent
desktop. `--primary-only` runs just the checkbox check.

`dbus-run-session -- python3 tests/check-firefox-geometry.py MEMORY_SO MINIMIZE_SO OUTPUT_DIR`
checks real Firefox with a temporary profile and local page. It covers frame
edges, clicks, held drags, partial redraws, native maximize/restore and dock
restore in tiled/floating modes at 100% and 125% scaling. It requires Firefox,
grim, Pillow and the Wayland C tools and never loads a plugin into the parent.

`python3 tests/check-text-damage.py MEMORY_SO MINIMIZE_SO OUTPUT_DIR` checks
main-surface text-height updates and right/bottom edges without screencopy or
forcing full repaints. It observes the real damage regions of a private
compositor, with padded/unpadded clients, buffer scales 1/2, output scales
1/1.25 and both Wayland damage coordinate spaces. Add
`--expect-bug` with the previous adapter to demonstrate the regression.
