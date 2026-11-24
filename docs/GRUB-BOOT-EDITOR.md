# GRUB Boot Editor

Open **Control Panel → Files & recovery → GRUB Boot Editor**.

The editor requests administrator authentication when you enter it, then loads
your current menu automatically. Cancelling authentication keeps the page open;
**Load current menu** retries. The desktop UI itself stays unprivileged.

Every new privileged operation opens a fresh administrator prompt, including
entry edits, ordering, boot preferences, undo, appearance and UEFI registration.
Loading the menu does not authorize later changes. A reviewed appearance or
firmware operation uses one prompt when starting its review; its confirmation
or cancellation completes that same operation, then the helper exits. Recovery
reviews expire after five minutes. Passwords are handled by the system's
authentication agent, not stored by the editor.

## Current Grub

The first tab reads the installed boot menu, including distribution entries, firmware tools, submenus and entries added with Fusion. Select an entry and choose **Edit entry…** to change its name. Enable **Edit boot commands (advanced)** to edit that entry's commands. Submenus can be renamed; edit their individual entries to change boot commands.

**Remove from menu…** removes the selected entry, or a submenu and its children. It keeps the operating system and drive intact. The editor refuses to remove the last operating-system boot entry. **Undo last change** restores the previous saved menu when it has not changed since that save.

**Move up / Move down** changes the selected entry's position. Submenu children
stay inside their submenu. Moving across generator boundaries asks to move the
complete source groups together, preserving each system's setup commands.
Entries separated by executable setup code or conditions cannot be split apart.
Undo also restores ordering. System-generated ordering can be restored by a
later GRUB regeneration; ordering within Fusion's own group is saved in its generator.

Fusion entries are also updated in the editor's generator, so their changes survive normal GRUB regeneration. **Changes to system-generated entries affect the current menu; regenerating GRUB, including during some system updates, can restore their original names, commands or entries.** The editor leaves the distribution's generator scripts intact and explains this distinction beside the selection and in the edit/remove dialogs.

The list parses literal `menuentry` and `submenu` declarations in the main configuration without executing it. Variable-generated titles are shown for reference; entries produced at boot by external scripts or configurations are not expanded.

## Boot preferences

Choose the default entry (including entries inside submenus), remember the last
selected operating system, set a timeout, and choose a visible, countdown or
hidden menu. **Apply boot preferences** validates and backs up the changes.
**Undo preferences** restores the previous settings and menu if no other tool
has changed them since. Zero seconds boots immediately; -1 waits for a choice.

The editor updates only the selection/timeout keys in `/etc/default/grub` and a
dedicated final generator. It also applies these preferences to the current menu
without regenerating it, preserving entry edits, kernel commands and the theme.
Remembering a selection respects one-time `grub-reboot` choices. It requires an
existing usable GRUB environment block on a supported boot filesystem. The UI
explains when this is unavailable (for example, a Btrfs boot volume without an
already configured reserved environment block). It does not create raw disk
environment blocks or enable unsupported LVM/RAID writes.

## UEFI boot option

Use this when Linux can start through another GRUB menu but has no boot option
of its own in the motherboard firmware:

1. Start that Linux installation **on the physical computer in UEFI mode**.
   Inside a VM, registration affects only that VM's firmware.
2. Open **UEFI boot option**, select this installation's mounted EFI System
   Partition, and choose its firmware label (for example, **Hyper Fusion**).
3. Leave **Make this the first firmware boot choice** unchecked to preserve
   existing priority. The new entry is appended to BootOrder.
4. Choose **Review registration…**. Review the exact partition, loader path,
   filesystem UUID, GRUB menu and backup directory, then **Register current system**.
5. Select the named entry in this computer's UEFI boot menu at the next boot.

The editor builds a separate x86-64 GRUB EFI image under
`EFI/HyperFusion-<installation-id>/grubx64.efi`. Its embedded configuration finds
this installation's GRUB menu by filesystem UUID, including a separate `/boot`
or a Btrfs subvolume. It leaves other vendors' loaders and `EFI/BOOT` intact.
If this installation lacks `/boot/grub/x86_64-efi` (for example, BIOS GRUB was
installed in the VM), the review includes installing the missing EFI support
directory. An existing directory must match the installed GRUB tools; the
editor refuses to overwrite a different or incomplete installation.
Refreshing an existing registration reuses its firmware entry. This does not
convert a disk's partition table, repair a missing GRUB menu, enable Secure Boot
or prepare an encrypted/LVM/RAID boot filesystem. Secure Boot must be disabled
for this unsigned loader; signed bootloader installations need their distribution tools.

Preparation writes only private backups, support-file staging and a candidate image. Confirmation
rechecks the menu, mounted partition, old loader, image hash and firmware state.
Normal Arch `grub-install` output is accepted: its missing, empty `fdt.lst`
build index is not treated as a module mismatch. Real module and runtime-index
differences remain checked, including changes between review and confirmation.
Failed writes attempt to restore the previous loader and boot order and remove
only the newly created firmware entry and support directory. Backups, the reviewed plan, transaction
result and **RECOVERY.txt** are kept under
`/var/lib/hyper-fusion/grub-editor/firmware/backups/`. If power is lost or the
helper is killed during registration, inspect that directory before retrying;
firmware recovery is not an automatic replay of old NVRAM variables.

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

The editor requires an existing GRUB installation with one configuration at `/boot/grub/grub.cfg` or `/boot/grub2/grub.cfg`. Add Entry discovers existing bootloaders; the separate UEFI boot option creates a dedicated EFI loader for the current installation. It does not convert BIOS to UEFI or unlock encrypted volumes. Secure Boot continues to enforce the firmware's trust policy; finding a valid EFI program does not certify that its signature is trusted. Unusual RAID, encrypted boot partitions and distribution-specific BIOS modules may need manual setup outside this tool.

## Appearance

The third tab connects the repository's original Hyper Fusion boot theme to the
panel. It offers Hyper Fusion, Shadow Edge, Hollow Grove, Tidal Glass, Porcelain
Ink, Obsidian Forge, Candy Cloud, Breakpoint and Binary Knife. Any bundled picture
can be paired with any design, or choose a local picture or a solid color.

**Killer Instinct · One More Credit** is a dedicated preset for the purple-lit
arcade cabinet wallpaper. It keeps the menu on the left so the cabinet stays
visible, with matching purple accents and adjustable picture/menu shading.
Select it from the theme thumbnails, then use **Review & apply…** to save it.

Published design folders are readable by the desktop and writable only by root,
even when authentication uses a private file-creation mask. Loading the editor
repairs older Fusion design folders created with mode `0700`, so their saved
pictures can be previewed and edited again. This changes only public theme
directory permissions; boot configuration contents and private backups stay intact.

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

GRUB's text console uses the same wallpaper, aligned to the full screen. Pressing
Enter to skip the countdown, editing with E, and opening the console with C no
longer draw a centered black rectangle. Boot messages and errors remain visible.
Existing installations need one **Review & apply…** of their current design to
write this presentation update, with the same backup review as any other apply.

If the installed GRUB menu is private, Appearance shows **Load GRUB menu…**.
Click it and authenticate to replace the sample entries with your actual menu.
Your chosen theme, picture and text stay in the preview. Loading does not apply a
design. The button then becomes **Review & apply…**, including when a theme was
already applied. Cancelling authentication keeps the draft and lets you retry.
A missing or unsupported GRUB installation keeps its diagnostic visible.

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

Drive inspection uses private read-only mounts, including options that suppress filesystem journal replay. It does not write to discovered systems. The separate, explicitly confirmed UEFI registration writes only its reviewed loader and firmware entry/priority; no partition-table edits are performed.

Changes are confined to:

- `/etc/grub.d/42_hyper_fusion`: the editor's own generator, included by future regular GRUB regeneration; updated only for Fusion entries.
- The current `grub.cfg`: Fusion changes replace its marked section; other current-menu edits replace only the selected title, command body or entry. Surrounding configuration is preserved.
- `/var/lib/hyper-fusion/grub-editor`: root-only entry records, transaction journals and timestamped backups.
- `/etc/default/grub`, `/etc/grub.d/99_zz_hyper_fusion_boot_options`, and `/var/lib/hyper-fusion/grub-preferences`: boot selection preferences, their generator and separate undo history.
- The reviewed EFI image and firmware entry/BootOrder, only when confirming UEFI registration.

The complete configuration passes `grub-script-check` before replacement. Saves use atomic file replacement, check for external changes, and retain the previous configuration. Syntax validation does not prove that manually edited boot commands will start the intended system. A failed save rolls back; an interrupted transaction is recovered the next time the authenticated editor opens. **Undo last change** refuses to overwrite intervening changes from a kernel update or another boot tool. Reload the menu before making a new edit in that case.

Opening the page authenticates and reads the current menu and drives. Saving, undoing and inspecting unmounted boot files reuse that helper. It belongs to the open panel, times out when idle and exits when its connection closes. The GUI itself runs as the desktop user.

## Development checks

`test_grub_editor.py` covers mounted/unmounted inventory, detection, shared EFI references, stale devices, duplicate UUIDs, nested current-menu parsing, name/command editing, removal, the last-OS guard, configuration validation, external changes, rollback and recovery using temporary fixtures. Native `grub_editor_tests` cover all five tabs, properties, selection, advanced editing, removal, save responses, cancelled authentication and preview-only appearance edits. `test_grub_appearance.py` exercises every preset, custom text, layout, sizes, stale pictures, menu preservation, generator output, pre-confirmation backups, cancellation, expired/replayed confirmations, backup integrity, recovery scripts on installed/live USB roots, restore, undo, rollback and interrupted transactions. `check_grub_boot.py` boots disposable QEMU images to check UEFI chainloading, missing drives, Linux configuration handoff, and edited current menus under UEFI and BIOS; it attaches no host disks. `check_grub_appearance.py OUTPUT_DIRECTORY` additionally boots the actual graphical theme under UEFI and BIOS and checks fallback without theme assets. These checks do not replace testing a particular Windows/Linux installation on its intended hardware.

The boot methods follow GNU GRUB's [chainloading](https://www.gnu.org/software/grub/manual/grub/html_node/Chain_002dloading.html) and [configfile](https://www.gnu.org/software/grub/manual/grub/html_node/configfile.html) commands. Filesystem inspection follows the kernel's [ext4 mount guidance](https://docs.kernel.org/admin-guide/ext4.html) and the [NTFS-3G manual](https://github.com/tuxera/ntfs-3g/wiki/Manual).
The appearance renderer follows GNU GRUB's [theme file format](https://www.gnu.org/software/grub/manual/grub/html_node/Theme-file-format.html).

`test_grub_options_firmware.py` additionally covers selection preferences,
generated groups, rollback, stale data, duplicate UUIDs, EFI image ownership,
review cancellation, idempotent registration and simulated NVRAM failures.
The native tests cover all five tabs and explicit firmware confirmation.
The disposable boot check also exercises the current-installation EFI handoff
and two successive boots using a saved selection. Set `FUSION_GRUB_QEMU`,
`FUSION_GRUB_QEMU_DATA`, `FUSION_GRUB_OVMF_CODE`, `FUSION_GRUB_OVMF_VARS` when
using a private QEMU/firmware installation; `FUSION_GRUB_TEST_OUTPUT` keeps its
disposable images and logs in a new directory for inspection.
