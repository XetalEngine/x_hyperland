# Cursors

Open **Theme → Cursors**, choose a style and size, then **Apply cursors**.
Pearl, Carbon, Neon Cyan, Orchid and Ember include matching pointer, link, text,
resize, drag/drop, zoom, help, unavailable and animated busy shapes.

Trails (Comet, Soft glow, Stardust) and click ripples are independent and off by
default. Color, opacity and lifetime are adjustable; move and click inside the
preview to try them. Custom theme presets save these settings as their own component.

`art.py` contains original vector artwork. `build.py` generates both Hyprcursor
and XCursor formats in the profile's ignored `.build/data/icons` directory. Setup
installs `hyprcursor-util`, `xcursorgen` and Qt SVG support, and builds the collection.
No shared cursor theme, KDE preference, GSettings value or system icon directory
is changed. Newly launched Hyprland applications receive the private XCursor path;
applications that cache their own cursors can require reopening.

The session's native Cube adapter applies cursors without GSettings synchronization
and draws optional pointer effects even when Cube itself is off. It requires the
same tested Hyprland 0.56.2/OpenGL ABI. Effects do not intercept clicks, do not draw
on the lock screen or captured/constrained input, and stop requesting frames when idle.

Tests: `QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s config/hypr/cursors`.
The disposable native regression is `tests/check-cube-workspaces.py`.
