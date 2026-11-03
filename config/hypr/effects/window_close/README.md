# Window buttons

Hold **Super** while pointing at a window to reveal minimize, maximize/restore,
and close buttons at its top-right corner. Minimize uses Fusion's existing
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

Releasing the modifier hides the buttons; Super-drag elsewhere continues to
move windows. Moving or resizing hides the buttons until the drag and its final
wobble/geometry animation have settled, including native motion blur. They then
return at the final corner if the modifier is still held and the pointer is over
that window. This follows the window's live animation state, with no fixed delay;
unrelated settling windows do not hide the hovered window's controls.

Configure or disable them in **Fusion Settings → Hotkeys → Window buttons…**:
enable switch, Super / Alt / Super+Shift, size, corner distance, and gentle pulse.
The accent follows `theme/current.colors`; theme application and rollback both
reload the renderer. These controls do not rewrite `keybindings.conf`.

Hyprland does not universally supply the title bars that another window manager
may have drawn. This adapter complements applications without window controls.
It does not replace application decorations or force unsupported decorations.

`model.py` validates `settings.conf`; `controller.py` checks for external edits,
saves atomically, activates the setting, and rolls back on failure. The updater
treats the file as a personal preference. Fresh installations enable the button.
`page.py` supplies the themed Hotkeys dialog. `scripts/session.sh` starts the
controller for this compositor session; there is no persistent system service.

`native/plugin.cpp` uses cancellable compositor input events and a render-pass
overlay. Only a left-button press on a visible button is intercepted; release
must still be over the same button and window with the modifier held. It uses weak window
references, hides during locking, input capture and file drags, and sends
`CWindow::sendClose()` rather than terminating a process. Its timer sleeps when
the modifier is released. No Hyprland function hooks are patched.

The native adapter currently supports x86-64 **Hyprland 0.56.2**, commit
`efb50993780079460b0cbed1363e2166a2de1d9f`, and OpenGL. A mismatched compositor,
headers, or renderer is rejected. Builds require the existing compositor
development dependencies plus Cairo headers/library; each source/ABI build gets
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
