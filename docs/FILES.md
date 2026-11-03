# Fusion Files

Fusion Files is Hyper Fusion's native Qt file manager. Fresh installations put
**My Computer** in Apps → Favorites. That shortcut opens **This PC**; **Fusion
Files** is also available in All apps. Apps → Files, the desktop's file-manager
action, and the default Super+E binding follow the file manager chosen in
**Control Panel → Default Apps**, initially Fusion Files. Dolphin remains
available as a separate application.

Normal Favorites/All apps launches and **Super+E** open tiled. **Ctrl-click** an
Apps icon, or enable its **Start this shortcut in a floating window** property,
to open centered and floating with the launcher's remembered floating size.
Chrome's **Show in folder**, other FileManager1 folder requests, screenshot
reveal actions and desktop folder associations open centered and floating from
their first frame, with a separate remembered size. They keep the requested
file selected. Open/save pickers also remain floating and remember their own
per-application sizes.

Files does not restore the old general Qt geometry/maximize record or let the
general window-memory helper change its main window after it appears. This
prevents a tiled → floating → resized sequence and keeps ordinary launches
independent from external requests. Files' child dialogs retain their normal
window memory.

## Navigation and layout

This PC has up to three sections separated by draggable horizontal dividers:
mounted internal drives, USB devices, and unmounted internal drives. The upper
section contains disks with at least one mounted partition. Every section has
one framed row per physical disk, with all its partitions side by side, largest
to smallest. A partially mounted disk stays together in the mounted section.
Long rows scroll horizontally without wrapping. USB devices appear together in
the middle, whether mounted or unmounted; USB SSDs are recognized by their
connection type even when their removable flag is unset. The lower section
contains wholly unmounted internal drives. Frames use the theme's accent;
frames and partition cards inherit its shared corner styling without a list
of theme names. Divider positions are remembered.
Empty sections and their extra dividers hide automatically and return when
matching drives appear. Mounted volumes
show available space; unmounted volumes show
capacity and filesystem. In the sidebar, mounted volumes appear below This PC;
the Unmounted drives group sits below Trash. Double-click a volume to open it,
mounting it first when needed. Right-click for Mount, Unmount, Force mount,
details, and safe removal of unmounted removable drives. Discovery never mounts
anything. Encrypted and unformatted volumes remain visible and can be managed
through Control Panel.

**Properties…** (or Alt+Enter on a selected volume) opens a themed storage
overview with a usage ring, used/free/capacity figures in readable units and
exact bytes, and filesystem, device, physical disk, mount location and access
details. Filesystem-reserved space is shown separately when present. Unmounted
volumes report usage as unavailable until mounted. Open dialogs update when a
volume is mounted, unmounted or disconnected; Copy details copies their text.
The compact 560-pixel properties window follows the desktop palette and includes
**System Cleaner**, which opens Control Panel directly to that page without
starting cleanup.

Quick access starts with the recipient's Home, Desktop, Documents, Downloads,
Pictures, Music and Videos locations. Right-click a folder to pin it. Sidebar
shortcuts can be renamed, removed and dragged to reorder. Dropping local folders
onto the Quick access heading or empty sidebar space pins them; dropping onto a
folder row transfers them there. This PC, Network and Trash are separate locations.
Expanded/collapsed states for This PC, Quick access and Unmounted drives are
saved immediately in private preferences, including across restarts and drive
disconnection/reconnection. Sidebar width and the main splitters are also saved.

The location bar has clickable breadcrumbs and an editable full address. Use
Ctrl+L, Alt+D or the blank part of the bar to type or copy it; Escape returns to
breadcrumbs. Paths containing spaces, Unicode, `#` and `%` retain their literal
names. Back, Forward and Up work across folder and This PC navigation. Network
locations accept URLs such as `smb://server/share` and `sftp://host/path`, using
the installed KIO protocol workers and their authentication dialogs.

The folder-view icon opens a menu of small, medium and large icons, a compact
list and details. It shows the current tab's selection and is disabled in This
PC, where the drive cards keep their own layout. Right-click the details header to choose columns; drag columns to
reorder and resize them. The folder filter matches names in the current folder.
The preview pane is enabled for fresh profiles and displays local images, text excerpts and metadata;
remote selections display metadata without downloading their full contents.
The small arrow above the new-tab (+) button hides or shows it and stays available when the pane is hidden.
Local picture thumbnails are enabled on file icons by default. Open **⋮ →
Configure Fusion Files…** to turn thumbnails, the preview pane, hidden files or
the Trash animation on or off. Saved choices survive reopening and updates;
the new defaults do not replace an existing preview preference. Remote folders
keep their file-type icons instead of downloading pictures for thumbnails.

## File actions

Ordinary copy, move, drag-and-drop, rename, Trash, restore and undo use KDE KIO jobs.
Copies use the existing Fusion transfer-progress service, including the selected
File Transfer style, pause, resume and cancellation. Dragging into another
folder moves immediately; hold Ctrl to copy instead. The dragged icon shows a
bottom-left **+** while Ctrl is held, including when the key changes mid-drag.
Folder targets in the sidebar use the same behavior.

For existing destination files, **Replace or skip files** offers **Replace the
files in the destination**, **Skip these files**, and **Let me decide for each
file**. These choices expand downward inside the active animated transfer window,
using its selected File Transfer style, then collapse after the answer. Theme →
File Transfer's preview status menu includes the conflict, individual and duplicate
questions. Replace applies throughout that transfer. Skip keeps existing files and
still transfers new files, including new descendants inside matching folders.
Matching directories merge; unrelated destination files are kept. Individual
decisions offer Replace, Skip, Cancel, and an apply-to-all checkbox. Replacing a
file does not retain its old contents for Undo.

Questions are attached to their exact job, including when multiple transfers run
at once. Only that job's client can ask or receive its answer. Cancel or loss of the
question service never authorizes an overwrite. When Files is launched outside a
Fusion session without the progress service, standalone confirmation dialogs are
available as a fallback. Ark-owned extraction questions remain controlled by Ark.

Dropping into the source folder asks whether to copy the selection anyway.
Same-folder copies and pastes alone use names such as `photo_copy1.png`, then
`photo_copy2.png`. Folder names, dotfiles and compound extensions are preserved.
Each transfer remains one job with Undo for supported operations. Permission
and transfer failures still report errors. A filesystem that cannot
provide Trash reports the error; it never silently substitutes permanent deletion.
Permanent deletion always asks for confirmation. Pending tracked file jobs keep
the application process alive after its last browser window closes.

Protected copy and move operations, including drag-and-drop and protected
destinations, use KIO's `admin:` worker after an asynchronous, read-only access
check. `kio-admin` supplies the graphical PolicyKit prompt; the browser stays
unprivileged. The normal themed transfer window, cancellation, numbered names
and Undo remain available. Local moves use the same protocol at both ends to
preserve atomic renames and ownership when possible. Symlink targets are not
traversed by the access check. Permission failures appear in a visible dialog.

On a local removal permission failure, Fusion Files opens the desktop's
administrator authentication dialog for the selected action. The bounded
Python helper checks the selected
items' identities, refuses system roots and nested mounts, and does not follow
directory symlinks. Protected Trash moves retain original permissions and
standard Trash records; they never become permanent deletion. Restoring or
permanently removing protected top-level Trash items can authenticate too.
Restoration refuses to overwrite an existing destination. Cancelling
authentication leaves the remaining protected items in place. Successful
ordinary KIO operations retain their Undo integration; protected items can be
recovered through **Trash → Restore**. Existing account-owned Trash directories
with permissive modes such as 755 are secured to 700 before use; they no longer
cause a failure after successful authentication.

After a successful Trash move, the selected file icons curve and shrink toward
the sidebar's Trash icon with the current theme accent. Failed/cancelled moves
do not animate as successes. The effect is a non-interactive overlay and can be
disabled in Configure Fusion Files.

Executable files and shell scripts have **Execute** first. Double-click or Enter
runs a recognized local executable with executable permission, including shell
installers with a shebang. Shell scripts open in
a terminal with their output kept visible, using their declared interpreter (or
Bash for a `.sh` script without one). Non-executable scripts can still be run
through the explicit Execute action; permissions are not changed. The context
menu's **Open with [app]** always opens the associated app, even for an executable.
**Open with…** offers a searchable list of installed applications, a custom command/program and
the option to remember a file-type association, including for unknown file types.
Discovery uses the shared Gio application inventory and does not require a
Plasma application-menu definition. Recommended/default apps appear first,
and default saves reuse Control Panel's guarded MIME-association backend.
Cut, Copy and Paste are available
in file menus. In This PC, select a mounted volume and use Ctrl+V or **Paste into
drive** to paste into its root folder; copied and cut files retain their usual
copy/move behavior. **Copy** on a mounted volume copies its folder location.
Cut applies to files and folders inside a drive, rather than the mounted drive
itself. Pasting checks that the target is still mounted. Right-click blank
space in a drive grid for **Paste into…** with a list of mounted destinations.

The **Ark** submenu uses Ark's own installed compression and extraction menu
plugins, including their format shortcuts and options dialog. Dragging selected
entries from an Ark ZIP or tar.gz window onto a folder or its background extracts
them there. Ark retains control of extraction, passwords, and archive conflicts;
the archive itself is kept. These actions are
enabled by default. **Customize context menu…** controls
action visibility, order, labels and icons. Custom actions accept `%f` / `%F` for
local files and `%u` / `%U` for URLs. Commands execute as argument lists, without
shell expansion; multiple-file placeholders must occupy a separate argument.

| Shortcut | Action |
| --- | --- |
| F2 | Rename selected item(s) |
| Ctrl+C / Ctrl+X / Ctrl+V | Copy / cut / paste |
| Delete / Shift+Delete | Trash / confirm permanent deletion |
| Ctrl+Z | Undo a supported file operation |
| Ctrl+Shift+N | New folder |
| Ctrl+A | Select all |
| Ctrl+L / Alt+D | Edit the complete location |
| Alt+Left / Alt+Right / Alt+Up | Back / forward / parent |
| F5 | Refresh |
| Alt+. / Ctrl+H | Show or hide hidden files |
| Alt+P | Toggle preview pane |
| Ctrl+F | Filter the current folder |
| Ctrl+Shift+C | Copy complete selected path(s) |
| Ctrl+T / Ctrl+W | New / close tab |
| Ctrl+Tab / Ctrl+Shift+Tab | Next / previous tab |
| Ctrl+N | New window |
| Alt+Enter | Properties |

## Theme, installation and private state

Appearance follows the active Fusion design and Dark, Light or High contrast
palette. An open window refreshes when the desktop's theme changes.

`installer/install.py` builds `file_manager/.build/xetal-files` and validates its
presence. Update preparation builds the same executable and includes it in the
activation transaction, excluding CMake files and test executables. The launcher
and desktop-entry paths are rendered for the recipient's installation.

Bookmarks, custom actions, column layout and window preferences live in
`file_manager/state/settings.ini`. This directory is ignored by Git, excluded
from installation payloads, and preserved during updates. Existing launcher
favorites remain the recipient's choices; updates make My Computer available
without replacing their favorite layout.

The native file-operation dependencies are Qt 6 and KDE Frameworks 6 KIO.
Setup installs KIO development files, KIO extras, `kio-admin`, Ark and UDisks on the supported
distributions. Normal mount and force-mount arguments are shared with Control
Panel in `control_panel/backend/volume_commands.h`; the file manager does not
perform filesystem repair or discard Windows hibernation files.

## Development checks

```bash
python3 config/hypr/file_manager/build.py
config/hypr/scripts/files.sh --this-pc
python3 config/hypr/file_manager/test.py
```

Native tests use a private D-Bus session and disposable configuration, files and
Trash. Checks click icons in all five views, exercise keyboard file operations,
numbered copy/move collisions, access routing, drag-and-drop, script/unknown-file menus and a real 64 MiB folder
copy through the themed JobView service with pause/resume. They do not mount
real drives. `--select /path/to/file` reveals a file in
its parent folder. `scripts/session.sh` starts a resident `--service` instance
before startup applications. It owns the standard `org.freedesktop.FileManager1`
interface throughout the Hyprland login, including while no Files windows are
open. Chrome's **Show in folder** portal (`OpenURI.OpenDirectory`) forwards to
this same interface. ShowItems and ShowFolders resolve the current Default Apps
handler through the folder launcher on every request; ShowItems retains selection
and forwards the request's activation token. The `--external` flag reaches Fusion
only; alternative file managers receive their usual arguments. Fusion assigns
the `xetal-files-external` application ID before creating its window, so the
Hyprland class rule floats and centers it on its first map. Its actual size is
saved under `external/size` in the private Files settings. The desktop entry's
`--from-desktop` flag distinguishes a supplied folder URI from an ordinary app
icon launch with no URI.

This explicit startup matters: the shared user bus does not inherit Hyprland's
profile-local D-Bus activation search path, so a service file alone can still
activate Dolphin. The resident service follows the compositor's event socket and
releases its name at logout. A per-instance lock prevents duplicate helpers. An
ordinary Fusion window yields its temporary registration to the resident service;
another manager that refuses replacement is left running, with Fusion queued
until it releases the name. No shared activation environment or KDE service
configuration is changed. `test_service.py` checks routing, changing defaults,
tokens, competing owners, duplicate startup and logout on a private bus with a
temporary handler and simulated compositor socket.
The separately gated `administratorTransfers` native check requires root,
`FUSION_FILES_ADMIN_CHECK=1`, a private D-Bus session and temporary XDG directories;
it exercises the installed administrator worker only on disposable fixtures.
