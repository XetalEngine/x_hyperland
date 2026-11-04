# Fusion Files

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
