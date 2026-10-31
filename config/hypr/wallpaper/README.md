# Wallpaper browser

Press **Super+W** to open or close the wallpaper ribbon. Scroll, drag, or use
Left/Right to browse. Click any image or press Enter to select it. Search and
collection filters help find a picture; **Slideshow** previews images without
changing your desktop until you choose one.

All bundled theme wallpapers appear by default. **Add / remove folders** adds
personal folders, including their subfolders, or hides the bundled collection.
Removing a folder only removes it from this browser; it never deletes images.
Folder preferences stay private in `wallpaper/state/browser.json`.

With one display, selecting a picture applies it immediately. With multiple
displays, choose a screen from a preview of the actual layout, including portrait
screens, scaling and offsets. Hover a display to preview your choice. Cancel
returns to browsing without changing any wallpaper. Selections are shared with
Fusion Settings and saved per monitor and theme.

Choose **Bloom**, **Crossfade**, **Silk sweep** or **Instant**. Animations run
behind applications on the selected display. Disabling compositor animations
also disables wallpaper transitions and carousel motion.

## Implementation and checks

The Qt browser scans folders and decodes bounded thumbnails in worker threads.
Workers finish before Qt shuts down, including when Super+W quickly closes it.
A session-local socket handles the toggle; the browser exits with Hyprland.

The short-lived native transition helper uses GTK layer-shell and OpenGL 3.3.
It draws above hyprpaper and below applications, accepts no keyboard or pointer
input, and exits after handoff. If the helper is unavailable, applying the
wallpaper still works. The existing wallpaper backend owns saving, conflict
checks, cache copies and rollback. No extra persistent wallpaper daemon runs.

Build requirements: `gtk+-3.0`, `gtk-layer-shell-0`, `epoxy`, a C compiler and
`pkg-config`. Setup installs the corresponding development packages and builds
the helper. The browser uses the same PyQt6 and profile theme as Fusion Settings.

```sh
python3 config/hypr/wallpaper/build.py
QT_QPA_PLATFORM=offscreen python3 config/hypr/wallpaper/test_browser.py
python3 tests/check-wallpaper.py /tmp/new-wallpaper-check
```

The integration check uses a separate compositor, hyprpaper instance and saved
preferences. It checks real intermediate animation frames, one/two-display
selection, cancel, disconnect handling and repeated launcher toggles.
