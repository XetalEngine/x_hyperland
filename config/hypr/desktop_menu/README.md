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
New folders appear at the right-click position. Paste uses the monitor and
pointer position at invocation; a context-menu Paste uses that menu's original
click. Incoming drops use the drop location. These positions survive dialogs,
long transfers, and later pointer movement. Auto align chooses nearby empty grid
cells; Auto arrange keeps incoming items packed on the chosen monitor. Replacing
an existing file preserves its icon position.

Double-click a folder to open a new floating Fusion Files window. Other files
open with their associated application. Desktop icons support multiple
selection, a selection rectangle, keyboard navigation, and drag and drop.
**Ctrl+C / Ctrl+X / Ctrl+V** copy, cut and paste, including files copied in Fusion
Files and other file managers. Cut icons fade until the clipboard changes. Paste
targets the Desktop folder; selecting a folder does not redirect it. **F2** edits
the name directly under the icon, selecting the filename without its extension.
Enter saves, Escape cancels, and a rename never replaces an existing file.
**Alt+Enter** and **Properties** open a floating Properties window. **Ctrl+Shift+N**
creates a folder. Links and desktop launchers have a small accent-colored arrow
badge at the bottom left of the icon; launchers display their own name and icon.

File actions load asynchronously from Fusion Files. The completed menu replaces
the loading popup at the original click, so Wayland can size it for all actions.
Dismissed or superseded requests cannot reopen an old menu. Keyboard invocation
uses the selected icon as its anchor.

**Show Trash** adds an optional, movable Trash icon without creating a file in
`~/Desktop`. It remembers its position, reflects whether Trash contains files,
and double-clicking opens Trash in a floating Fusion Files window. Delete,
**Move to Trash**, and dropping files onto Trash use Fusion Files' removal engine.
After successful removal, the icons follow the same animated flight into Trash
as in Files. Failed or cancelled removals do not animate. This respects Files'
**trashAnimation** preference and GTK's animation setting. With Trash hidden,
the flight ends near the source monitor's lower right corner. Hiding desktop
icons hides Trash too and preserves its preference.

Dropping onto another folder moves files. Hold **Ctrl** to copy, **Shift** to
move, or **Ctrl+Shift** to create shortcuts (symbolic links). This works within
the desktop and in both directions with Fusion Files, including multiple files
and folders. A desktop-to-desktop move on empty space still repositions icons.
The dragged image shows a plus at the bottom left for Copy, an arrow for
Shortcut, a faded icon for Move, or a red prohibited badge for a rejected target.
Copy and Shortcut cannot drop into Trash; neither operation silently moves files.
Fusion Files handles transfers and any conflict prompts. The desktop watches the
folder for changes, so files saved or renamed elsewhere appear automatically.

Directory refreshes update existing icon widgets in place. In particular, an
archive being written on the desktop must not destroy the source of an active
drag or an inline rename editor. Each drag retains the URLs selected at its
start. Removing its source, hiding icons, disconnecting its monitor or ending
the session explicitly cancels the drag before destroying its widget, releasing
the native input grab and the feedback timer. Compression and file transfers
remain outside the desktop event loop.

The cursor-probe runtime supplies accepted drag actions for the pinned Hyprland
compositor and keeps modifier feedback current across application focus changes.
Its Wayland negotiation applies only to Fusion's marked file drags. Drag feedback
queries are asynchronous, bounded, and stop when the drag ends.

Preferences and positions live in `desktop_menu/icons.json`. This private file is
created only when a preference or layout changes, is excluded from Git, and is
preserved by updates. A fresh installation starts with icons hidden. The helper
belongs to the Hyprland session and exits at logout; it creates no persistent
service and changes no Plasma settings.

The desktop uses the session's native Fusion Files service through
`org.xetal.FusionFiles.Desktop1`. Folder launches use `--external --new-window`
and the existing `xetal-files-external` floating rule. Transfer handling stays in
the Files service so operations can continue when the icon surface refreshes.
Desktop Properties and operation dialogs use that same floating application role.

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
floating folder/Properties launches, clipboard exchange with Qt, inline rename,
Trash opening and removal animations, drag transfers, hiding icons and session
shutdown. Use an output directory on the home filesystem to keep the fixture's
Trash inside its private HOME.
Use `--drag-actions-only` to check copy/move/shortcut transfers in both directions,
folder links, drag badges, and rejected My Computer/toolbar destinations.
Use `--drag-refresh-only` to write an archive during a two-file drag to an
external GTK target, then check URL delivery, Escape, source removal and clicks
in both applications. The target is a local upload-queue fixture; it never
contacts an external server. The unit suite also covers hidden icons, metadata
updates, rename editor preservation and opening archive submenus.
