# Desktop icons and context menu

Right-click the wallpaper and enable **Show Desktop icons**. The transparent
desktop surface displays files and folders directly from `~/Desktop`, beneath
application windows and panels. Turning icons off only hides them.

**Arrange icons** offers Columns (the default), Rows, and three icon sizes.
**Auto align** is on by default: drag an icon to any grid cell and it snaps there,
keeping gaps and other icons in place. Turn it off for placement between grid
cells. **Auto arrange** is a separate option, off by default, that keeps icons
packed together in the selected row or column order. **Align now** snaps the
current positions once; **Arrange now** packs them together once. Changing Rows
or Columns only rearranges existing icons while Auto arrange is enabled.

Positions are remembered per monitor; disconnecting
a display temporarily brings its icons onto the primary display, and reconnecting
it restores their placement. Reserved panel space is kept clear.

Double-click a folder to open a new floating Fusion Files window. Other files
open with their associated application. Desktop icons support multiple
selection, a selection rectangle, keyboard navigation, rename, trash, properties,
and drag and drop. Dropping onto another folder moves files; hold Ctrl to copy.
Fusion Files handles transfers and any conflict prompts. The desktop watches the
folder for changes, so files saved or renamed elsewhere appear automatically.

Preferences and positions live in `desktop_menu/icons.json`. This private file is
created only when a preference or layout changes, is excluded from Git, and is
preserved by updates. A fresh installation starts with icons hidden. The helper
belongs to the Hyprland session and exits at logout; it creates no persistent
service and changes no Plasma settings.

The desktop uses the session's native Fusion Files service through
`org.xetal.FusionFiles.Desktop1`. Folder launches use `--external --new-window`
and the existing `xetal-files-external` floating rule. Transfer handling stays in
the Files service so operations can continue when the icon surface refreshes.

Validation:

```sh
cd config/hypr/desktop_menu
python3 -m unittest test_icons test_menu
FUSION_DESKTOP_TEST_GUI=1 GDK_BACKEND=x11 GSETTINGS_BACKEND=memory \
  xvfb-run -a dbus-run-session -- python3 -m unittest test_icons
```

From the repository root, `python3 tests/check-desktop-icons.py OUTPUT FILES_BUILD`
runs actual input in an isolated nested Hyprland with a temporary Desktop, private
D-Bus and virtual input. `OUTPUT` must be a new directory; `FILES_BUILD` must
contain the built `xetal-files` executable. The check covers layout, persistence,
floating folder launches, drag transfers, hiding icons, and session shutdown.
