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

On first login, HyperFusion initializes the account's standard folders with
`xdg-user-dirs-update` before starting Files. Accounts with an existing
`user-dirs.dirs` are left alone, including custom paths, unavailable mounts and
intentionally disabled folders. The user's `enabled=False` opt-out is respected.
Browsing another installed system's home does not create folders on that drive.

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

## Search files and contents

**Ctrl+F** opens a separate search area in the current tab and focuses its input.
The existing **Filter this folder…** field stays in the address row;
**Ctrl+Shift+F** returns to the folder view and focuses that filter. Filtering
only narrows the current listing. Searching includes subfolders by default and
does not inherit the folder filter.

Type a partial name or a wildcard and press **Enter**. Matching ignores case by
default. Examples: `*.jpg`, `par*ialname*png`, `image?.png`, or `*.png;*.jpg`.
`*.*` matches every name, including extensionless names; `*.` matches names
without an extension. Semicolon or `|` separates alternative patterns.
Searches use the current local or mounted folder; **Choose folder…** changes
the scope. From This PC or a KIO network URL, choose a local or mounted path.

Checking **Advanced** opens a dialog with:

- **Search text inside files**, with literal text or regular expressions,
  case sensitivity, whole words, and matching across lines.
- Filename patterns and common text/source/web/configuration/data file types.
  Selected types are combined, then intersected with the filename filter.
  The multiline, word-wrapped extension box shows `.txt, .html, .cpp` rather
  than wildcard syntax. Checking a group adds its extensions; unchecking it
  removes that group's extensions while retaining extensions shared with
  another checked group and unrelated custom entries. Edit this box directly
  to add or remove extensions. Plain `txt` and `*.txt` are also accepted and
  normalized to `.txt`; an empty box searches all file types.
- Excluded files/folders, recursive search, hidden files, optional symbolic-link
  traversal with loop detection, and optional binary-data searching.
- Minimum/maximum file size, modified-date range, and automatic Unicode or
  explicit UTF-8, UTF-16, and Windows-1252 decoding. Advanced searches start
  with a 64 MiB file-size limit; zero removes the limit.
- **Parallel workers**: Automatic uses up to four; choose 1–32 explicitly.
  Fewer workers can suit hard drives or mounted network folders.
- A result limit, initially 20,000 rows, adjustable up to 100,000.

The advanced dialog's **Presets** dropdown lists saved search setups. **Save…**
stores the current search folder, query, extensions and every advanced option
under a name; saving over an existing preset asks before replacing it.
Choose a preset and click **Load**, or use **Load file…** for a preset from
another location. Loading fills the form for review and does not start a search.
You can save an incomplete query or a folder that will be available later.

**Open folder** opens `~/.config/hypr/file_manager/state/search-presets/` for the
standard profile. Each preset is a separate JSON file. Renaming or deleting a
file updates the dropdown while the dialog is open; deleting the selected
preset leaves the current form intact. Files added externally also appear.
These private files survive desktop updates and are not shipped in releases.
Preset writes are atomic, and malformed or unsupported files report an error
without replacing the form's settings.

Rows show **name, size, line, match count, modified date, full path and matching
text**. Content searches produce one row per matching line; a multiline match
shows its starting line. Double-click a content row to preview the excerpt;
**Open file** uses the normal file-opening action, and **Show in folder** returns
to the containing folder with that file selected. Copy paths or result rows,
sort completed results, or export the displayed results as CSV. Excerpts are
bounded to 400 characters around the first match. Search results are read-only;
use Show in folder for renaming, moving or deleting files.

**Stop** retains results already received. **Escape** stops a running search;
press it again to close search. Starting another search, navigating away,
closing a tab or closing the window cancels its worker and child readers. Each
tab/window has an independent search. No indexing service is required.

Content search uses the installed **ripgrep** package with its default regex
engine (no look-around or backreferences). Files are searched as text; PDF,
Office and archive contents are not extracted. Unreadable files, binary files,
oversized result lines and reached result limits are reported. JSON result
lines larger than 2 MiB are skipped to keep memory bounded. Search runs as the
current user and does not change file contents.

## File actions

Local copy and move operations use Fusion's streaming transfer worker. Copying
starts immediately while a background scan counts files and bytes. The animated
transfer card uses your selected File Transfer style and supports pause, resume
and cancellation. Rename, Trash, restore and remote operations use KDE KIO.
Dragging into another
folder moves immediately; hold Ctrl to copy instead. The dragged icon shows a
bottom-left **+** while Ctrl is held, including when the key changes mid-drag.
Folder targets in the sidebar use the same behavior.

Local transfer conflicts and errors collect in a compact **Items needing
attention** popup while other files keep copying. Select unfinished rows to
**Retry**, **Skip item**, **Replace…**, or **Use administrator access…** for a
permission error. Administrator access lasts for that transfer; retries run
after the current pass. The similar-items checkbox applies a choice to matching
queued issues, and **Skip similar** also covers later matches in that transfer.
Matching directories merge; unrelated destination files are kept. Replacing a
file does not retain its old contents for Undo.

A successful retry immediately shows **Copied successfully** with a check mark.
The previous error remains under **Original issue** in its details and saved
report. Skipping another row leaves that copy intact. Actual filesystem sockets
are ignored automatically during copying: no popup, queue row or file-count
increment. Their originals stay in place. This uses the filesystem type, so a
regular file named `.sock`, a directory, or a symbolic link still transfers.
Named pipes, devices and genuine file errors remain visible for a choice.
**Review queue** reopens a hidden
popup, and **Save report…** includes every affected path, including automatic
skips; automatically ignored sockets are recorded separately for diagnostics.
Closing the popup during a transfer only hides it.

Folder attributes have their own progress count after copying. Same-drive moves
use an instant rename where possible; other moves verify copied data before
removing unchanged originals. **Copied; move pending** becomes **Moved
successfully** only after removal, or **Copied; original kept** when it remains.
The finished card shows the number actually copied and the skipped count, with
**Copy complete** or **Move complete** at the top. Skipped originals stay in place.

KIO confirmation questions are attached to their exact job, including when multiple transfers run
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

If a folder cannot be read because of Linux permissions, Files shows **This
folder is private** with an **Unlock folder…** button. Unlock opens the desktop's
administrator authentication prompt and browses that folder using KIO's `admin:`
worker. Use an administrator account on the **currently running system**, not
the password from another Linux installation on the mounted drive. Files does
not collect or save passwords, change ownership, or loosen folder permissions.
An **Administrator access** banner stays visible while using this mode;
**Use normal access** switches the tab back to ordinary access. System
authentication may remain cached briefly. Cancellation or a failed unlock
leaves a visible error with Retry and Back, without repeated prompts.

The authenticated folder supports browsing, creating folders, copying, moving,
renaming and opening files through KIO. The application chooser also uses KIO
for `admin:` files, so ordinary application launching is not handed an
unsupported URI. Administrator access does not decrypt encrypted volumes or
make a read-only mount writable. Search and file pickers still require paths
that their unprivileged workers or requesting applications can access.

A readable folder containing only hidden entries instead shows **This folder
contains hidden files** with **Show hidden files** (also **Ctrl+H**). This enables
the existing hidden-files option across tabs. A genuinely empty folder or a
folder with no filter matches is never described as private.

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
| Ctrl+F | Open and focus search |
| Ctrl+Shift+F | Focus the current-folder filter |
| Escape (in search) | Stop search, then close search |
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
