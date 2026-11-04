# Workspace behavior

Right-click a numbered workspace in the taskbar. **Force window layout** offers
Off (normal behavior), Force tiled, and Force floating. **Force modifier buttons**
offers Individual (existing app/window choices), On (always-visible shared
controls), and Off (no artificial controls, including while Super is held).
These choices belong to the clicked workspace and persist across logins.

On uses a shared size, position and background. Hold Super over a window to open
its gear: the editor loads the workspace settings, previews changes across its
windows, and saves to that workspace. Reset previews global button defaults.
Individual restores existing app/window preferences; workspace overrides never
delete them. Off can always be reversed from the taskbar menu. A stale editor
cannot bypass Off or save to a workspace its target has left. Native application
title-bar buttons are unaffected.

Layouts apply to existing, newly opened and incoming windows. Forced tiling joins
the normal shared layout; native maximize/restore remains usable within it.
Tiled drag gestures can float temporarily, then rejoin the destination layout.
Forced floating uses remembered dimensions and fits them to the output. Turning
layout forcing Off leaves the current arrangement and permits normal mode changes.
The gear editor itself remains independently movable. Layer-shell and unmanaged
X11 surfaces are outside the managed window layout.

`rules.json` is created only when saving. The controller validates and locks it,
merges the selected field, checks editor conflicts, activates both native readers
and rolls back unsuccessful updates. The updater preserves this preference.
The taskbar stores the actual workspace ID, including when Cube displays local
face numbers. `runtime/window_memory` applies layout policies before the first
frame and prevents contradictory mode changes; its watcher leaves normal app
mode memory intact. `effects/window_close` applies button precedence and bounded,
temporary workspace previews. Both builds hash the shared native policy header.

Run `python3 -m unittest discover -s config/hypr/workspaces` for persistence tests.
`tests/check-window-buttons.py PLUGIN OUTPUT_DIR --workspaces-only` checks real
layouts, window transfers, drag/release, native controls, shared editor previews,
Off under Super, persistence and GTK menus in a private compositor and HOME.
