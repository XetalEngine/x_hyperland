# Window close button

Hold **Super** while pointing at a window to reveal a glowing × at its top-right
corner. Click it to send the application's normal close request. Unsaved-work
dialogs still work. Releasing the modifier hides the button; Super-drag elsewhere
continues to move windows. Moving or resizing a window hides the button until
the drag ends, including when Wobbly is disabled. It returns on release if the
modifier is still held and the pointer is over a window.

Configure or disable it in **Fusion Settings → Hotkeys → Window close…**:
enable switch, Super / Alt / Super+Shift, size, corner distance, and gentle pulse.
The accent follows `theme/current.colors`; theme application and rollback both
reload the renderer. These controls do not rewrite `keybindings.conf`.

Hyprland does not universally supply the title bars that another window manager
may have drawn. This adapter complements applications without a close button.
It does not replace application decorations or force unsupported decorations.

`model.py` validates `settings.conf`; `controller.py` checks for external edits,
saves atomically, activates the setting, and rolls back on failure. The updater
treats the file as a personal preference. Fresh installations enable the button.
`page.py` supplies the themed Hotkeys dialog. `scripts/session.sh` starts the
controller for this compositor session; there is no persistent system service.

`native/plugin.cpp` uses cancellable compositor input events and a render-pass
overlay. Only a left-button press on the visible button is intercepted; release
must still be over the same window with the modifier held. It uses weak window
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
