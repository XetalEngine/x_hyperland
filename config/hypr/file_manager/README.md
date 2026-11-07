# Fusion Files

## Navigation tree

Every Fusion Files window keeps the left navigation tree visible: This PC,
folders, windows opened by other applications, and Open, Save, and folder
pickers. Its width is adjustable, but dragging the divider cannot collapse it
completely. Previously saved collapsed layouts recover automatically when the
window opens. Valid saved widths and other preferences are preserved.

Pickers remember their panel widths separately for each application and
operation, alongside their existing window size and last-folder settings.
Closing a picker does not change the main Files window's panel layout.

## Dragging files

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

Run `python3 test.py` for the native Files, picker, Auto mount, service routing,
and transfer-prompt checks. Auto mount tests use temporary preferences, synthetic
drive inventories and mock mount commands; they never mount real drives.
