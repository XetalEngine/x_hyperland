# Workspace behavior

Right-click a numbered workspace in the taskbar. **Force window layout** offers
Individual (normal behavior), Force tiling, Force floating, and KDE mode. **Force modifier buttons**
offers Individual (existing app/window choices), On (always-visible shared
controls), and Off (no artificial controls, including while Super is held).
These choices belong to the clicked workspace and persist across logins.

Fresh installs start in **KDE mode on every numbered workspace**, including new
workspaces and Cube faces created later on any monitor. Choose another mode in
that workspace's menu to override the default. Updates preserve existing profiles'
defaults and saved choices; legacy profiles retain Individual for unset workspaces.

Between **Keys** and **Update**, each taskbar shows its active workspace's layout:
one window for Individual (layout forcing Off), four equal panes for Force tiling,
three overlapping windows for Force floating, and **KDE** text for KDE mode.
Left-click cycles **Individual → Force tiling → Force floating → KDE mode**;
hover shows the current mode and next choice. All four indicators use the same-sized
button and follow the bar's text color. Workspace
switches and saved mode changes update the indicator automatically, including
Cube's local face numbering. It can be hidden in the taskbar's Options menu.

KDE mode floats windows and adds a compact title bar above application content,
with gear, minimize, maximize/restore and close controls. The bar grows with the
chosen button size, reserves space when maximized and disappears in fullscreen.
Drag its title area without Super; double-click to maximize/restore. The gear
saves independent KDE app/window preferences. Uncheck **Add a title bar above the
app** to use the previous Automatic, Always, nearby, modifier-only or Off overlay
controls. Hold Super over a window to reveal its gear when those controls are hidden.
App choices persist across
logins; window-only choices last until that window closes. KDE mode temporarily
supersedes Force modifier buttons, preserving that setting for the other modes.

With the title bar disabled, Automatic detection uses per-surface Wayland decoration negotiation and X11
GTK/Motif frame hints. Those hints describe decoration ownership, not the actual
buttons: a frameless app can report that it draws its own frame. Use Always or Off
in its gear for such apps. No screenshots, accessibility scraping or application
name guesses are used. Automatic buttons hide during true fullscreen playback.

On uses a shared size, position and background. Hold Super over a window to open
its gear: the editor loads the workspace settings, previews changes across its
windows, and saves to that workspace. Reset previews global button defaults.
The submenu's **Settings…** opens that same shared editor directly, including for
an empty workspace or while controls are Individual/Off. Saving its size,
position and background preserves the visibility choice. Live desktop previews
are available when the workspace is On and contains a window.
Individual restores existing app/window preferences; workspace overrides never
delete them. Off can always be reversed from the taskbar menu. A stale editor
cannot bypass Off or save to a workspace its target has left. Native application
title-bar buttons are unaffected.

Layouts apply to existing, newly opened and incoming windows. Forced tiling joins
the normal shared layout; native maximize/restore remains usable within it.
Tiled drag gestures can float temporarily, then rejoin the destination layout.
Forced floating uses remembered dimensions and fits them to the output.
Force floating and KDE mode keep maximized windows in the same stacking order
as other floating windows: activating a window brings its drawing and input
to the front together. Menus retain their application's behavior and explicitly
pinned windows keep their always-on-top behavior.
Turning layout forcing Off leaves the current arrangement and permits normal mode changes.
The gear editor itself remains independently movable. Layer-shell and unmanaged
X11 surfaces are outside the managed window layout.

Fresh installs seed `rules.json` with `default_layout: "kde"` and no per-workspace
overrides. Missing files or legacy files without that field default to Individual.
Special workspaces, including minimized-window storage, keep native behavior.
The controller validates and locks the file,
merges the selected field, checks editor conflicts, activates both native readers
and rolls back unsuccessful updates. The updater preserves this preference.
The taskbar stores the actual workspace ID, including when Cube displays local
face numbers. `runtime/window_memory` applies layout policies before the first
frame and prevents contradictory mode changes; its watcher leaves normal app
mode memory intact. `effects/window_close` applies button precedence and bounded,
temporary workspace previews. Both builds hash the shared native policy header.
Cycling computes the next mode under the same lock as the save. Rapid repeated
presses are ignored until the pending change finishes; errors are surfaced and
the displayed mode is always read back from the saved policy.

Run `python3 -m unittest discover -s config/hypr/workspaces` for persistence tests.
`tests/check-window-buttons.py PLUGIN OUTPUT_DIR --workspaces-only` checks real
layouts, window transfers, drag/release, native controls, shared editor previews,
Off under Super, persistence and GTK menus in a private compositor and HOME.
Add `--kde-only` instead for Wayland/X11 decoration hints, real button actions,
KDE profile separation, stale editors, window lifetime and plugin reloads.
