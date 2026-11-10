# Window buttons

Hold **Super** while pointing at a window to reveal a gear, minimize,
maximize/restore, and close buttons at its top-right corner. Minimize uses Fusion's existing
Minimize effect and its restore icons. Close sends the application's normal
close request, so unsaved-work dialogs still work.

The middle button floats a tiled window, maximizes a normal floating window,
and restores a maximized window. Restore uses Hyprland's remembered floating
size, clamps it to the current display's usable area, and keeps the whole window
inside it. Without a useful remembered size it chooses a smaller rectangle.
This reuses the compositor's per-window memory. A newly tiled application's
initial size is not mistaken for an actual previous floating size. The existing
per-application window-memory service and launcher's per-shortcut memory remain
in charge of restoring geometry across launches.

By default, releasing the modifier hides the buttons; Super-drag elsewhere continues to
move windows. Moving or resizing hides the buttons until the drag and its final
wobble/geometry animation have settled, including native motion blur. They then
return at the final corner when the window's chosen visibility mode calls for
them. This follows the window's live animation state, with no fixed delay;
unrelated settling windows do not hide the hovered window's controls.

The **gear** opens an editor populated from this window's effective settings.
**All windows of this app · remembered** is the initial Apply-to destination;
changing that destination keeps the values being edited. Applying an app choice
also removes the edited window's old override so its saved result matches the
preview; explicit overrides on other windows remain independent.
Choose the modifier, always-visible, nearby-pointer, or Off display mode; adjust
button size, six corner/edge positions, insets and nearby distance with sliders
and optional exact pixel values. While the editor is open, all four buttons stay
visible **on the actual target window**, even with Super released or Off selected.
The preview follows changes without saving them. Apply saves; Close discards
unapplied changes. **Reset this window to defaults** previews the global defaults
for this window only, and Apply keeps that reset. Outside the editor, the gear
appears **only with Super held**, even in Off mode. An individual window
override lasts until it closes; application choices persist across launches and
logins. Window overrides take priority over app choices, then global settings.
**Use inherited settings**, followed by Apply, removes the selected override. App matching uses the
exact initial application class; live windows use compositor lifetime IDs, so
closing one cannot transfer its override to a replacement window.

Workspace choices take precedence over these individual settings. Right-click
a numbered taskbar workspace → **Force modifier buttons**: Individual keeps the
existing behavior; On shows shared controls on every window and makes its gear
edit one workspace layout with live previews; Off hides every artificial control,
including the gear and Super-triggered buttons. On can override the global enable
switch for that workspace. Switching back to Individual preserves app/window
choices. The gear editor's reset affects the workspace only while editing On.
In a forced-tiled workspace, maximize/restore stays within the tiled layout;
the Tile control is hidden where floating is forced. See `workspaces/README.md`.

**KDE mode** uses its own Automatic/Always/nearby/modifier/Off settings, with a
four-button row: gear, minimize, maximize/restore and close. The gear stays visible
with the fallback controls; Super reveals it when controls are hidden. Persistent
app choices live in `kde-rules.json`, and window-only choices in the session's
`xetal-windowbuttons-kde-rules.json`. Standard app/title rules and workspace
On/Off settings are preserved for the other modes. Previews and saves carry their
profile identity, so changing modes cannot apply a stale editor to another profile.

Automatic mode uses the pinned compositor's Wayland decoration requests and
nonblocking X11 GTK/Motif property replies. It reads protocol state without
changing client decoration negotiation. These are frame-ownership hints, not a
universal list of visible buttons; frameless clients may need an Always override.
Without Wayland decoration negotiation the client owns its frame. X11 properties
are refreshed while evaluating controls; pending queries are discarded on window
close or unload. No synchronous X11 round trips run in the rendering path.

**Button background** defaults to **Auto**, which matches the predominant color
of the window directly beneath the controls. A continuous opaque backing covers
native icons and text in the gaps as well as under the buttons; the glow still
pulses above it. **Manual** provides a color dialog and **Pick from screen…**
eyedropper. Both preview on the actual window before Apply. Cancelling a color
dialog restores its previous draft color; Escape cancels a screen pick without
changing it. Background choices follow the same app/window scope, inheritance,
reset and save rules as position and size. Existing six-field rules automatically
gain Auto without changing their other choices or rewriting their files on load.
Screen picking uses `hyprpicker` when available, with the existing `slurp`/`grim`
tools as a fallback. It does not copy colors to the clipboard or save screenshots.

Configure or disable them in **Fusion Settings → Hotkeys → Window buttons…**:
enable switch, Super / Alt / Super+Shift, size, corner distance, and gentle pulse.
The accent follows `theme/current.colors`; theme application and rollback both
reload the renderer. These controls do not rewrite `keybindings.conf`.

Hyprland does not universally supply the title bars that another window manager
may have drawn. This adapter complements applications without window controls.
It does not replace application decorations or force unsupported decorations.

`model.py` validates `settings.conf`; `controller.py` checks for external edits,
saves atomically, activates the setting, and rolls back on failure. The updater
treats it, `rules.json` and `kde-rules.json` as personal preferences. Fresh installations enable the controls.
`page.py` supplies the themed Hotkeys dialog. `scripts/session.sh` starts the
controller for this compositor session; there is no persistent system service.
`window_settings.py` supplies the gear editor; `rules.py` and `native/policies.hpp`
validate its overrides. Window-only overrides live under the compositor's runtime
directory. Saves check for external edits and roll back if the native reload fails.
Live previews exist only in compositor memory. They end when the editor or target
closes; a bounded heartbeat lease also removes them if the editor crashes or stops
responding. Preview updates are asynchronous and coalesce slider changes. Their
buttons still respect window stacking, locking, dragging and Wobbly settlement.

The **Floating title drag · all windows** section appears in both window-control
editors. A normal click passes straight through to the application. A no-Super
drag starts only after the left button has been held for 120 ms and moved at least
2 logical pixels. The two sliders adjust these global thresholds; **Apply drag
settings** saves them in `drag-settings.json` for the next gesture. The updater
preserves this preference. Text selection, native title-bar dragging, Super-drag,
and per-monitor Wobbly timing keep their existing paths.

`native/background.hpp` samples before drawing the controls, in their owning
window's render stack. It downsamples only the backing rectangle to 40×12 pixels,
at most four times per second when stationary. Fenced pixel buffers are read only
after completion, with zero-wait polling; no synchronous desktop screenshots or
GPU wait are used for Auto. A quantized histogram groups similar background
shades and rejects minority text/icon colors. Sampling accounts for output scale,
rotation and the working framebuffer's color description. Temporary GL state is
restored, caches are bounded and closing windows/unloading releases their buffers.

`native/plugin.cpp` uses cancellable compositor input events and a render-pass
element inserted in the owning window's stack, so other windows and panels cover
its controls naturally. Only a left-button press on a visible button is intercepted;
release must still be over the same visible button and window. It uses weak window
references, hides during locking, input capture and file drags, and sends
`CWindow::sendClose()` rather than terminating a process. Its timer sleeps when
there are no visible controls or settling windows to follow. No Hyprland function hooks are patched.

The native adapter currently supports x86-64 **Hyprland 0.56.2**, commit
`efb50993780079460b0cbed1363e2166a2de1d9f`, and OpenGL. A mismatched compositor,
headers, or renderer is rejected. Builds require the existing compositor
development dependencies plus Cairo and json-c headers/libraries; each source/ABI build gets
a unique `.so` path so loaded libraries are never overwritten. Updating a loaded
native adapter takes effect on the next login; settings apply immediately.

Run `python3 test_window_close.py` for preference/rollback checks. From the
repository root, `python3 tests/check-file-drag-and-close.py OUTPUT_DIR FILES_BUILD`
tests real pointer/keyboard input, browser uploads, folder drops, ignored/accepted
close requests, disabling, changing the modifier, and preserving Super-drag.
It creates its own compositor, D-Bus session, browser profile and file fixtures,
with XWayland disabled. It never targets the parent compositor with test input.

`tests/check-window-buttons.py PLUGIN OUTPUT_DIR` checks tiled/floating restore,
maximization, screen fitting, addressed minimize/restore, cancelled clicks, and
normal close requests in a disposable compositor. The native geometry unit
checks include negative output coordinates, portrait work areas and size limits.
Add `--workspaces-only` to check workspace layout enforcement, native drag/release,
shared settings/previews, Off under Super, Individual restoration and GTK menus.
Add `--rules-only` to exercise the real gear editor, all display modes, app/window
inheritance, no-modifier actions, bounds, reload and window lifetime. Add
`--preview-only` to exercise the real editor's sliders, current-value loading,
app Apply, window-only reset, discard, crash recovery and preview expiry. Add
`--native-only` to exercise Chrome's own maximize/restore button and title-bar
double-click repeatedly without a minimize reset. All browser/toolkit preferences
are isolated beneath the test's `/tmp` directory.
Add `--background-only` for real rendering and eyedropper checks: a contrasting
toolbar/content fixture, bright native marks, changing dominant colors, covering
gaps, preview/Apply/discard, picker cancellation and saved-color reload.

Run `QT_QPA_PLATFORM=offscreen python3 config/hypr/effects/window_close/test_drag_settings.py`
from the repository root for threshold persistence and slider checks.
`tests/check-floating-text-drag.py` also checks stationary clicks, 1-pixel slips,
fast moving taps, text selection, deliberate header drags, and both Wobbly switches.
Add `--files-only` to `tests/check-file-drag-and-close.py` for file transfers,
changing Ctrl mid-drag, replacement confirmation, view menus and real Ark ZIP/tar.gz
extraction. Its host-facing input devices are disabled only in the private test
compositor so ordinary desktop pointer movement cannot interfere with the checks.
