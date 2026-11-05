# GRUB Boot Editor

Open **Control Panel → Files & recovery → GRUB Boot Editor**.

## Current Grub

The first tab reads the installed boot menu, including distribution entries, firmware tools, submenus and entries added with Fusion. Select an entry and choose **Edit entry…** to change its name. Enable **Edit boot commands (advanced)** to edit that entry's commands. Submenus can be renamed; edit their individual entries to change boot commands.

**Remove from menu…** removes the selected entry, or a submenu and its children. It keeps the operating system and drive intact. The editor refuses to remove the last operating-system boot entry. **Undo last change** restores the previous saved menu when it has not changed since that save.

Fusion entries are also updated in the editor's generator, so their changes survive normal GRUB regeneration. **Changes to system-generated entries affect the current menu; regenerating GRUB, including during some system updates, can restore their original names, commands or entries.** The editor leaves the distribution's generator scripts intact and explains this distinction beside the selection and in the edit/remove dialogs.

The list parses literal `menuentry` and `submenu` declarations in the main configuration without executing it. Variable-generated titles are shown for reference; entries produced at boot by external scripts or configurations are not expanded. If the configuration requires administrator access to read, choose **Load current menu**.

## Add Entry

1. Select a drive by its model and capacity, then click **Detect bootable systems**. Authenticate when prompted. Mounted and unmounted disks are both listed; right-click **Properties…** to inspect the disk and all its partitions without authentication.
2. The editor finds its Windows or Linux bootloader and selects it. If the drive contains several systems, choose one from the list.
3. Keep the suggested name or enter the name you want in the menu, then click **Add to GRUB**.

The entry is saved for the next restart. No partition names, UUIDs, boot commands or mount paths need to be typed. The entry uses your existing GRUB theme, with a Windows or Linux icon where that theme provides one. Your default operating system stays selected. A hidden or zero-second menu becomes visible so you can choose the new entry.

After saving, the editor switches to **Current Grub** and selects the new entry. Adding an entry preserves the existing entries from your distribution and other tools.

## Automatic detection

| Current boot mode | Detected target | Boot method |
| --- | --- | --- |
| UEFI | Windows Boot Manager | Chainload its existing `bootmgfw.efi` |
| UEFI | Linux shim, GRUB or systemd-boot | Chainload its existing EFI program, preferring shim when available |
| UEFI | Unified Linux kernel image | Chainload the EFI image in `EFI/Linux` |
| UEFI | Linux with an existing compatible GRUB menu | Open that system's maintained GRUB configuration |
| Legacy BIOS | Linux with an existing GRUB menu | Open that system's maintained GRUB configuration |
| Legacy BIOS | Windows on an MBR disk | Chainload its existing partition boot sector; inspection requires `ntfs-3g` |

The editor searches the selected drive's partitions, including unmounted Linux filesystems and separate boot partitions. Reserved BIOS boot and Microsoft reserved areas are excluded. A named Linux installation's maintained GRUB menu is preferred to an unidentified fallback EFI loader. It also checks other EFI partitions when a Windows BCD or Linux GRUB configuration identifies the selected drive. This handles installations whose boot files live on another disk. A shared boot manager retains its own operating-system choices; it may show a second menu. That drive containing the boot files must remain connected.

Filesystem UUIDs identify entries even when Linux device names change. Cloned UUIDs, an incompatible EFI architecture, the current bootloader, and a disconnected or replaced drive are rejected. The boot files are checked again when saving.

The editor requires an existing GRUB installation with one configuration at `/boot/grub/grub.cfg` or `/boot/grub2/grub.cfg`. It does not repair a missing bootloader, convert BIOS to UEFI, unlock encrypted volumes, or install GRUB. Secure Boot continues to enforce the firmware's trust policy; finding a valid EFI program does not certify that its signature is trusted. Unusual RAID, encrypted boot partitions and distribution-specific BIOS modules may need manual setup outside this tool.

## Appearance

The third tab connects the repository's original Hyper Fusion boot theme to the
panel. It offers Hyper Fusion, Shadow Edge, Hollow Grove, Tidal Glass, Porcelain
Ink, Obsidian Forge, Candy Cloud, Breakpoint and Binary Knife. Any bundled picture
can be paired with any design, or choose a local picture or a solid color.

The page has no scrolling settings panels: Picture, Menu and Colors tabs keep
the controls beside the preview. Theme thumbnails use arrow buttons; short
windows switch to a compact theme picker.

The controls adjust picture dimming, menu shading, left/center/right placement,
heading, subtitle, menu text size, accent/text/shade colors and navigation hints.
The live preview uses the same artwork renderer as the saved design and shows
the current menu's top-level entries (sample entries before that menu is loaded).
The preview is a visual guide at 1920 × 1080; firmware resolution and GRUB's
bitmap font rendering can change text spacing. Scrolling still works in GRUB
when there are more entries than fit in the menu.

**Review & apply…** authenticates, validates the design and saves recovery
backups first. It opens a review that says **Take a picture of the screen. Here
are your backups.** Every file that will be replaced or removed is listed next
to its exact backup path. New files are identified separately, including the
complete list of theme assets. **Apply for next boot** in that review is the
confirmation that writes the boot files. Cancel keeps the backups and leaves
the boot configuration unchanged. Selecting a preset, editing controls or
browsing pictures only changes the preview. Custom artwork
is decoded as the desktop user and copied into a self-contained versioned theme
under the boot filesystem, so moving the original picture does not break boot.
The original picture remains untouched.

The editor adds a guarded appearance section to the existing menu and its own
`/etc/grub.d/99_hyper_fusion_appearance` generator for future ordinary GRUB updates.
It validates the full candidate with `grub-script-check`, retains a backup and
checks for concurrent changes. It preserves the existing boot entries, kernel
arguments, selected default, timeout, `/etc/default/grub`, firmware variables and
bootloader binary. No `grub-install` or `grub-mkconfig` is run when applying a design.
Forwarding configurations without a local boot menu are rejected.

**Undo appearance** restores the last appearance transaction if the menu has not
changed elsewhere. **Use system appearance** removes this editor's override,
revealing the previous appearance; this action can also be undone. Appearance
recovery is separate from entry editing, under `/var/lib/hyper-fusion/grub-appearance`.
Use system appearance and Undo appearance use the same backup review before
confirmation. Each review expires after five minutes and its approval is used
once. A changed configuration, permissions, undo history or damaged backup
blocks saving and requires a new review. Versioned assets are retained because
earlier backups may still refer to them.
Installing or updating the desktop ships these controls and assets without
changing the machine's boot appearance.

### Appearance recovery instructions

Each timestamped directory in `/var/lib/hyper-fusion/grub-appearance/backups/`
contains the original `config`, `generator` and `entries` files when they existed,
plus `undo-history.json` when there was an earlier undo record. `record.json`
records original permissions and SHA-256 checksums. `RECOVERY.txt` lists the full
paths and exact commands for that particular backup; `restore.sh` verifies all
backup checksums before restoring any files and restores the original modes.
These files are private to root. The review offers **Copy all details** and
**Save instructions…** so the user can keep the instructions on another device.

The normal recovery command is `sudo sh -- /exact/backup/path/restore.sh`.
For live USB recovery, mount the installed Linux root at `/mnt`, including the
correct root subvolume where applicable. Mount any separate `/boot` filesystem
at `/mnt/boot` and other boot submounts in their usual locations. Run the exact
command from the review: `sudo sh -- /mnt/exact/backup/path/restore.sh /mnt`.
Then restart. Do not regenerate GRUB after restoring the complete saved menu.
The script removes configuration files that did not exist before the change;
it leaves unused new theme assets in place. It does not reinstall a bootloader.

## Saving and recovery

Drive inspection uses private read-only mounts, including options that suppress filesystem journal replay. There are no partition-table, target-drive or firmware-variable writes.

Changes are confined to:

- `/etc/grub.d/42_hyper_fusion`: the editor's own generator, included by future regular GRUB regeneration; updated only for Fusion entries.
- The current `grub.cfg`: Fusion changes replace its marked section; other current-menu edits replace only the selected title, command body or entry. Surrounding configuration is preserved.
- `/var/lib/hyper-fusion/grub-editor`: root-only entry records, transaction journals and timestamped backups.

The complete configuration passes `grub-script-check` before replacement. Saves use atomic file replacement, check for external changes, and retain the previous configuration. Syntax validation does not prove that manually edited boot commands will start the intended system. A failed save rolls back; an interrupted transaction is recovered the next time the authenticated editor opens. **Undo last change** refuses to overwrite intervening changes from a kernel update or another boot tool. Reload the menu before making a new edit in that case.

Opening the page reads the current menu and lists drives without writing or requesting authentication. Saving, undoing and inspecting unmounted boot files use the authenticated helper. It belongs to the open panel, times out when idle and exits when its connection closes. The GUI itself runs as the desktop user.

## Development checks

`test_grub_editor.py` covers mounted/unmounted inventory, detection, shared EFI references, stale devices, duplicate UUIDs, nested current-menu parsing, name/command editing, removal, the last-OS guard, configuration validation, external changes, rollback and recovery using temporary fixtures. Native `grub_editor_tests` cover all three tabs, properties, selection, advanced editing, removal, save responses, cancelled authentication and preview-only appearance edits. `test_grub_appearance.py` exercises every preset, custom text, layout, sizes, stale pictures, menu preservation, generator output, pre-confirmation backups, cancellation, expired/replayed confirmations, backup integrity, recovery scripts on installed/live USB roots, restore, undo, rollback and interrupted transactions. `check_grub_boot.py` boots disposable QEMU images to check UEFI chainloading, missing drives, Linux configuration handoff, and edited current menus under UEFI and BIOS; it attaches no host disks. `check_grub_appearance.py OUTPUT_DIRECTORY` additionally boots the actual graphical theme under UEFI and BIOS and checks fallback without theme assets. These checks do not replace testing a particular Windows/Linux installation on its intended hardware.

The boot methods follow GNU GRUB's [chainloading](https://www.gnu.org/software/grub/manual/grub/html_node/Chain_002dloading.html) and [configfile](https://www.gnu.org/software/grub/manual/grub/html_node/configfile.html) commands. Filesystem inspection follows the kernel's [ext4 mount guidance](https://docs.kernel.org/admin-guide/ext4.html) and the [NTFS-3G manual](https://github.com/tuxera/ntfs-3g/wiki/Manual).
The appearance renderer follows GNU GRUB's [theme file format](https://www.gnu.org/software/grub/manual/grub/html_node/Theme-file-format.html).
