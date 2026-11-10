# Text-safe floating header dragging

`scripts/floating-drag.py` provides an invisible grip from the visible upper
border through the first 32 logical pixels of a floating window. There is no
five-pixel inset at the top; the actual per-window border width is included.
The left/right button clusters remain outside the grip.
`scripts/drag_cursor.py` permits that gesture only with an
ordinary pointer. Text-selection, resize, link and unknown cursors stay with the
application. A press that starts over text remains excluded until mouse release,
even after leaving the field. An already started header drag continues normally.
Super-drag uses the existing compositor binding and is unaffected.

Hyprland's standard IPC does not expose the current cursor shape. This small
native adapter adds `hyprctl xetal-cursor`: the current shape, a snapshot
at left-button press, the button state and a gesture serial. `origin` records
the global press position, the window address and stable ID, and its border
width at the input event. Layers and popups cannot supply a drag origin. A named
arrow on the compositor-owned border is valid without client surface focus.
It reads the
compositor's cursor metadata and cursor-only CPU image cache. It never captures
window pixels or text, modifies cursor images, cancels input or patches functions.

After the Python helper validates both cursors and the movement threshold,
`xetaldrag:begin ADDRESS SERIAL` starts a native compositor drag. A matching held
left-button serial and the same mapped floating window with unchanged geometry
are required. The helper keeps that target when fast motion leaves the window
during the hold delay; it never substitutes the window beneath the new pointer
position. Motion accumulated during the delay is applied before native dragging
captures its offset, preserving the original grab point. Release or
`xetaldrag:end` ends only that grip's drag. Movement now follows native pointer
events instead of 16 ms IPC position changes. Wobbly recognizes it as normal
dragging, and the Super-hover close button stays hidden until the drag ends.
Older installed probes keep the addressed-movement fallback until updated.

Named Wayland shapes distinguish an arrow from `text` and `vertical-text`.
Clients using cursor images, including legacy Wayland and XWayland clients, are
allowed only when their bitmap exactly matches installed Xcursor arrow artwork.
The Python helper reads bounded cursor files from the private Fusion cursor
directory and standard icon paths, including animated frames and sizes. The
catalog refreshes when files change. Unknown, unavailable or custom unmatched
cursors deliberately keep the gesture with the application; Super-drag remains
available. No OCR, hotspot guessing or application-title exceptions are used.

The installer and updater compile this adapter with the existing pinned-runtime
development dependencies. The helper loads it once for its compositor session;
it rejects mismatched ABI versions. Each build has a unique hashed path and no
mapped library is overwritten. Missing probe information disables only the
automatic title grip. The helper exits with the Hyprland session and uses no
persistent service. Source updates to a loaded probe take effect at next login.

Checks:

```
python3 -m unittest discover -s config/hypr/scripts -p 'test_*drag*.py' -v
python3 tests/check-floating-text-drag.py /tmp/fusion-text-drag-check
```

The second command uses a new output directory, a private nested compositor with
XWayland disabled, a private D-Bus session and a frameless text-field fixture. It
tests real selection, leaving the field while holding the mouse, empty-header
dragging and Super-drag with both named and bitmap cursors. Test input goes only
to that nested compositor.
