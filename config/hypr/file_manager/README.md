# Fusion Files

## Local applications and installers

AppImages and `.sh` / `.run` files show **Execute** first even without an execute
bit. AppImages open through `execute.py` on double-click; scripts do so once
executable. The shared helper inspects AppImage ELF headers without running them,
offers missing FUSE packages/interpreters and executable permissions, and opens
a terminal only after confirmation. Only package installation, `modprobe` and
`chmod +x` use sudo. The selected program always runs as the normal user, with
filenames passed as separate arguments. Cancellation, changed files and failed
setup stop execution. Existing ready AppImages launch directly; shell output
remains visible in the terminal. Bundled Qt applications do not inherit host Qt
plugin paths.

Legacy AppImages may need [FUSE 2](https://docs.appimage.org/user-guide/troubleshooting/fuse.html).
The [current static runtime](https://github.com/AppImage/type2-runtime) includes
libfuse, so it only needs a usable mount helper and kernel support.

For `.deb` files, **Install .deb…** is first and double-click opens Control Panel's
installer page with that file selected. It does not start installation. The same
rules apply to desktop file actions; remote and Trash URLs are never executed.

Run `python3 test_execute.py` for setup/launch checks and the CMake
`execution-tests` target for native file recognition and menu policy checks.

## Private folders

Permission-denied local folders show **This folder is private → Unlock folder…**.
KIO's `admin:` worker uses the running system's PolicyKit administrator prompt;
the GUI stays unprivileged and never stores credentials or changes permissions.
An administrator banner provides **Use normal access**. Failed authentication
can be retried or left without a prompt loop. File opening also routes `admin:`
URLs through KIO, including the application chooser and custom commands.

Readable folders containing only hidden entries instead offer **Show hidden
files**, synchronized with the existing **Ctrl+H** option. Empty folders, name
filter misses and ordinary I/O errors do not request administrator credentials.
See [the Files guide](../../../docs/FILES.md) for mounted-drive access details.

## Search

**Ctrl+F** opens and focuses a recursive search. **Ctrl+Shift+F** focuses the
existing **Filter this folder…** field. Search accepts partial names and
wildcards such as `*.jpg`, `par*ialname*png`, `*.png;*.jpg`, and `*.` for names
without an extension. `*.*` also includes extensionless names.

Check **Advanced** for text/regex content searches, common file-type presets,
name and folder exclusions, hidden files, size/date limits, encodings, and
1–32 parallel workers (Automatic uses up to four). Results include filename,
size, line, match count, modification time, full path and a text excerpt.
Preview matching text, open files, reveal them in their folder, copy paths or
rows, and export CSV. Stop keeps the results already found; Escape stops a
search and then closes it. Tabs and windows can search independently.

Common file-type checkboxes populate an editable, word-wrapped extension list
such as `.txt, .html, .cpp`. The list is the filter; custom extensions are
supported, and clearing it searches all types. Shared extensions remain when
another checked group still includes them.

The advanced dialog has **Save…**, **Load**, **Load file…** and a **Presets**
dropdown. Presets include the folder, query and all advanced settings. Each
lives in a private JSON file under `file_manager/state/search-presets/`.
**Open folder** lets users rename or delete them; the dropdown watches the
filesystem and updates automatically, without clearing the current form.
`search_presets.cpp` validates and atomically saves presets, normalizes extension
filters, and watches the preset directory. Loading does not launch a search.

`search.cpp` provides the native interface and `search_worker.py` scans local
or mounted folders in a separate process group. Content searches require
**ripgrep**; the installer supplies it. Workers and result counts are bounded,
and cancellation stops child readers. No persistent index is created.
See [the Files guide](../../../docs/FILES.md#search-files-and-contents) for
pattern rules, limits and supported formats.

## Configure menus

Open **Configure Fusion Files…** from the toolbar's three-dot menu. The
**Browsing** tab holds the existing display and file-action preferences.
**Files menu** and **Desktop menu** let you separately reorder, hide, rename,
add or remove right-click actions for Files and desktop files/folders.

Default menus place 7-Zip before Cut/Copy/Paste and end with Delete, Rename,
and Properties. Old saved layouts migrate to this order while keeping custom
commands, labels and visibility; later reordering remains supported. New appears
only on the background and contains Folder, Text document, custom templates, and
Template Options. `new_items.cpp` shares the same creation and template settings
with desktop icons. Entries support UTF-8 starter text or copying an existing
file without overwriting destinations. Settings in `file_manager/state/templates.json`
are atomic, guarded against concurrent edits, and retained by updates.

Paste accepts file clipboard formats, including KDE/GNOME cut selections. Plain
text and web links never create files through Paste. A selected folder's context
Paste targets that folder; keyboard Paste targets the current directory.

Existing customizations are preserved. **Save** applies all tabs; **Cancel**
discards the edits. Menu customization shortcuts no longer appear in either
right-click menu. Desktop icon visibility and arrangement remain in the
desktop's right-click menu.

## Navigation tree

The address is always a textbox, including with old breadcrumb preferences.
Ctrl+L and Alt+D select it; Escape restores the address without hiding it.
This PC keeps data partitions full-width and uses compact cards for boot and
helper partitions identified from their role or mount point.

Every Fusion Files window keeps the left navigation tree visible: This PC,
folders, windows opened by other applications, and Open, Save, and folder
pickers. Its width is adjustable, but dragging the divider cannot collapse it
completely. Previously saved collapsed layouts recover automatically when the
window opens. Valid saved widths and other preferences are preserved.

Pickers remember their panel widths separately for each application and
operation, alongside their existing window size and last-folder settings.
Closing a picker does not change the main Files window's panel layout.

Preview starts enabled on fresh installs. Its divider cannot collapse it to
zero width; old collapsed layouts recover to a usable width when opened or
when Preview is enabled. Normal custom widths and an intentional Preview-off
choice are preserved. The divider has a six-pixel grab area. This applies to
folders, This PC, external windows, and every upload/save picker.


## Dragging files

Local copy and move operations use Fusion's streaming worker. The first files
start immediately; a low-priority source scan counts bytes and files alongside
the copy. The transfer card shows the current file, completed/total files,
skipped files, bytes and speed. Until enumeration finishes it says **Counting
total…**, and 100% is reserved for successful completion. Progress comes from
the worker, not repeated scans of the destination. Updates are batched, and
neither file sizes nor transfer sizes have an application-imposed ceiling.

Local transfer errors and name conflicts collect in an **attention panel that
unfolds below the animated transfer card**. It is part of the same window and
keeps the card's width, artwork and controls in place. The panel starts at three
card heights and scrolls when needed to fit the display; its animation follows
the File Transfer animation setting. Ordinary files keep copying while the
panel is open or collapsed. The table shows Item, Status and Result / issue;
full source/destination paths, stage and original errors appear in the selected
row's details. Filtering also searches those paths. Select one or more rows
to **Retry**, **Skip**, **Replace** a conflicting file, or **Use administrator
access** for a permission error. The similar-items checkbox applies a choice
to matching queued issues; Skip also applies to later issues of that same
type for this job only. Filesystem sockets are ignored automatically while
copying, without a queue row or authentication prompt. Both the worker and its
background counter exclude them from file and byte totals; they do not count
as user-skipped files. Detection uses the actual no-follow filesystem type,
not a `.sock` extension or an error code. Ordinary files, directories and
symbolic links (including links to sockets) still transfer normally. Named
pipes, devices, unknown file types and access/I/O failures still need a choice.
Their rows explain **Skip** and disable actions that cannot resolve the issue.
Skip only affects unresolved items; successful
copies remain successful even when selected alongside a skipped row.

Retries run after the current copy pass. A successful retry immediately shows
**Copied successfully** with a check mark; its old error moves into **Original
issue** in the details and report. Directory traversal reports **Folder
processed**, and a move reports **Copied; move pending** until verification and
original removal finish. Failed retries return to the queue with **Retry failed**.
Progress says **Waiting for your choice** while queued items need an answer;
saving folder attributes and move verification can still follow that answer.
**Review queue** expands it again; **Collapse**, **Hide queue** and Escape fold
the panel away without canceling the transfer. The card's Cancel/Close controls
retain their normal meaning. Completed queue results remain available until the
card is closed. A searchable table and **Save report** retain details of
resolved and skipped rows. The journal also stores those decisions on disk;
this is an audit trail, not automatic resume after a process exit. Skipped
items finish with an explicit skipped count and the number actually copied.
Folder attributes have their own progress count, and the finished card says
**Copy complete** or **Move complete** instead of leaving **Finishing…** visible.
Later automatic skips are summarized with a count so choosing Skip similar on
a large tree does not flood the panel with millions of rows. **Save report**
streams every affected path from a read-only journal snapshot, including those
automatic skips, without loading the whole report into memory.
Automatically ignored sockets have separate diagnostic records in the journal
and optional report, outside the attention queue and transfer totals. Moves
that copy data retain those sockets at their sources; instant same-filesystem
renames retain their normal filesystem behavior.

Queue updates and decisions use the exact job's owner-checked D-Bus channel;
multiple transfers cannot answer each other's items. Decisions keep the worker's
item versions, including while a replacement confirmation is open. The original
standalone queue remains a fallback when the progress service is unavailable or
too old to provide an embedded panel. The file-operation worker is unchanged.

Same-filesystem moves use an atomic rename where the destination is free.
Cross-filesystem moves and folder merges copy the selected contents first,
compare copied file contents, flush the destination, and then remove only
unchanged, verified originals. Queued copy or verification failures must be
resolved before cleanup starts. Skipping one keeps its original while allowing
other verified files to finish moving. Skipped conflicts stay at their source. If cancellation or
an error happens during cleanup, the already verified copies remain available;
the remaining originals are retained. Active files can still change outside
the worker's control; this is not a filesystem snapshot or an all-or-nothing
transaction across drives.

Regular files are copied to exclusive temporary names before an atomic publish.
Reflinks and `copy_file_range` accelerate supported filesystems; the fallback
uses bounded buffers and preserves sparse holes. Symlinks stay symlinks.
Permissions, timestamps and supported extended attributes are retained;
cross-filesystem moves preserve ownership. Copies of hard-linked files are
independent files. Unsupported filesystem metadata is reported in **Details**.

When actual access fails, that item joins the queue while accessible items
continue. Choosing **Use administrator access** requests authentication
immediately, while the copy pass continues, using the normal PolicyKit dialog
to authorize a small helper for that transfer's selected paths. The queue
shows **Awaiting authorization**, then **Retry queued**; canceling or failing
authentication returns those rows to **Needs a choice**. Already-authorized
access is explicitly shown and reused without another prompt. The system may
also reuse a valid PolicyKit authorization. The worker continues using the same helper
for subsequent protected items, and socket EOF ends its lifetime. Passwords
are never collected or stored by Fusion Files, and the browser remains an
ordinary user process. Directory symlinks are not followed by privileged
operations. Read-only media, exhausted space and other I/O errors are reported
with their source, destination and transfer phase rather than silently skipped.

The disk-backed transfer journal supports **Undo** without keeping every file
record in GUI memory. Native transfers and KIO's rename/Trash actions share
command ordering. Undo checks that copied files have not changed before
removing them; it never recursively removes unrecorded files. Remote protocols
and shortcut creation retain their existing backends. The shared **7-Zip** menu
opens the [bundled Fusion archive manager](../archive_manager/README.md), which
stages and verifies archive work before publishing it through the native transfer
worker. Administrator access is scoped to each transfer, including Undo.

Hold **Ctrl** while dragging to copy, **Shift** to move, or **Ctrl+Shift** to
create shortcuts. Shortcuts are symbolic links to the original files or folders;
they use the existing transfer engine, conflict prompts and Undo. These gestures
also work between Files and desktop icons in either direction. Without a modifier,
folder drops move; a source that only allows copying is copied instead.

The drag image has a bottom-left plus for Copy, an arrow for Shortcut, and a
red prohibited badge over a target that cannot accept the operation. Move fades
the drag image like a cut item. My Computer's drive overview and non-drop areas
do not accept file transfers. An explicit Shift-move never becomes a copy when
the source only allows copying.

Wayland carries shortcut URLs as a non-destructive Copy action; the destination
performs the link operation. Fusion's cursor-probe runtime reports accepted drag
actions and modifiers across GTK/Qt focus changes, so badges remain accurate.

## Auto mount

The **Auto mount** checkbox in a physical drive's header becomes available after
at least one of its volumes has been mounted successfully. The current system
drive is excluded. This applies to internal disks and USB/removable drives.

Enabling the checkbox remembers the eligible volumes already mounted successfully
on that drive, using their filesystem UUIDs. Partitions that have never mounted
successfully remain excluded. If another partition qualifies later, the checkbox
shows a mixed state until the user chooses to include it. Disabling Auto mount
leaves currently mounted volumes alone.

The existing `xetal-files --service` process checks for opted-in drives at sign-in
and every five seconds, even with all Files windows closed. It belongs to the
Hyprland login and exits on logout. UDisks performs normal user-authorized mounts,
using the session's authorization dialog if required (for example, for internal
data disks). This never forces a mount, stores a password or unlocks an encrypted
volume. A failed or canceled mount can still be attempted manually in Files.

Manual unmount is respected until the drive reconnects, the next login, or the
user switches Auto mount off and back on. Failed automatic attempts follow the
same rule, avoiding repeated authentication prompts or mount loops. Files uses
the kernel disk sequence to distinguish quick USB reconnects.

Personal choices and successful-mount history live in `file_manager/automount.json`
inside this Hyprland profile, protected from updates and saved atomically under a
lock. Per-login attempts live in the compositor's runtime directory. No `/etc/fstab`,
KDE settings, passwords, or persistent system services are changed.

## Checks

Run `python3 test.py` for the native Files, search, picker, Auto mount, service routing,
and transfer-prompt checks. Auto mount tests use temporary preferences, synthetic
drive inventories and mock mount commands; they never mount real drives.
`python3 test_search_worker.py` runs the standalone search-engine checks.
`python3 test_transfer_worker.py` tests streaming, sparse files, links, Undo,
failed writes, cancellation and changed sources/destinations using disposable
files. `sudo -n env FUSION_TRANSFER_PRIVILEGED_TEST=1 python3
test_transfer_privileged.py` additionally checks real protected files and an
actual `/tmp` → `/dev/shm` move; it never changes the host's authorization policy.
`FUSION_FILES_BUILD` can reuse a build directory. The native test profile stays
on the home filesystem so the real Trash and mounted-volume checks work.
