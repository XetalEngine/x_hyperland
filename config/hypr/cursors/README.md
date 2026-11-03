# Cursors

Open **Theme → Cursors**, choose a style and size, then **Apply cursors**.
Pearl, Carbon, Neon Cyan, Orchid, Ember and Sumi Ink include matching pointer, link, text,
resize, drag/drop, zoom, help, unavailable and animated busy shapes.

Open **Theme → Window effects → Mouse effects** for the trail gallery and an
interactive preview. **Follow desktop theme** is the fresh-install default:

| Desktop preset | Mouse effect |
| --- | --- |
| Xetal Raw | Plasma weave — twisting electric ribbons and nodes |
| Xetal Modern | Orbital bloom — expanding rings and satellite pearls |
| BreakPoint | Faultline — tumbling shards and sparks |
| Binary Knife | Data stream — circuit traces and drifting binary digits |
| Tidal Glass | Bioluminescence — rising bubbles and plankton |
| Porcelain Ink | Living ink — tapered ink strokes and vermilion petals |
| Obsidian Forge | Cinder wake — cooling molten fissures and rising embers |

Every effect can be selected with any desktop theme. Follow uses the effect's
own palette; selecting a particular effect also allows a custom accent.
Uncheck **Enable mouse trail**, or select **Off**, then apply to disable the trail.
Opacity, lifetime and optional click ripples are independent of cursor artwork
and size. The **General effects** gallery contains the original **Comet**,
**Soft glow** and **Stardust** effects, independent of every theme.
The Cursors, Mouse effects and **Theme → Mix & match** pages share one validated preference store;
conflicting drafts must be reloaded before applying. Theme snapshots include
these choices in their Cursors component. Built-in presets select Follow while
preserving personal timing and opacity.

`art.py` contains original vector artwork. `build.py` generates both Hyprcursor
and XCursor formats in the profile's ignored `.build/data/icons` directory. Its
uniquely named `Xetal-Cursor-*` links in `~/.local/share/icons` make these private
assets discoverable by a compositor that has already cached its search paths.
Existing themes are never replaced, and no other desktop's selection is changed. Setup
installs `hyprcursor-util`, `xcursorgen` and Qt SVG support, and builds the collection.
No shared cursor theme, KDE preference, GSettings value or system icon directory
is changed. Newly launched Hyprland applications receive the private XCursor path;
applications that cache their own cursors can require reopening.

The session's native Cube adapter applies cursors without GSettings synchronization
and draws optional pointer effects even when Cube itself is off. It requires the
same tested Hyprland 0.56.2/OpenGL ABI. Effects do not intercept clicks, do not draw
on the lock screen or captured/constrained input, and stop requesting frames when idle.
Mouse movement samples a bounded, distance-spaced path. Three geometry batches
render each output's trail at its own presentation cadence; there is no 60 Hz
polling timer. Age is based on monotonic time, so mixed refresh rates do not
change its lifetime. Monitor layout changes discard stale points.

Tests: `QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s config/hypr/cursors`.
The disposable native regressions are `tests/check-cube-workspaces.py` and
`tests/check-wobbly.py` (all themed trails, theme following, mixing, disabling and idle).
