# GRUB Boot Editor

Open **Control Panel → Files & recovery → GRUB Boot Editor**.

1. Select a drive by its model and capacity, then click **Detect bootable systems**. Authenticate when prompted. Mounted and unmounted disks are both listed; right-click **Properties…** to inspect the disk and all its partitions without authentication.
2. The editor finds its Windows or Linux bootloader and selects it. If the drive contains several systems, choose one from the list.
3. Keep the suggested name or enter the name you want in the menu, then click **Add to GRUB**.

The entry is saved for the next restart. No partition names, UUIDs, boot commands or mount paths need to be typed. The entry uses your existing GRUB theme, with a Windows or Linux icon where that theme provides one. Your default operating system stays selected. A hidden or zero-second menu becomes visible so you can choose the new entry.

**Rename**, **Remove from menu…**, and **Undo last change** manage entries created by this editor. Removing an entry keeps the operating system and its drive intact. Existing entries from your distribution or other tools remain in place.

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

This first version requires an existing GRUB installation with one configuration at `/boot/grub/grub.cfg` or `/boot/grub2/grub.cfg`. It adds existing bootable systems; it does not repair a missing bootloader, convert BIOS to UEFI, unlock encrypted volumes, or install GRUB. Secure Boot continues to enforce the firmware's trust policy; finding a valid EFI program does not certify that its signature is trusted. Unusual RAID, encrypted boot partitions and distribution-specific BIOS modules may need manual setup outside this tool.

## Saving and recovery

Drive inspection uses private read-only mounts, including options that suppress filesystem journal replay. There are no partition-table, target-drive or firmware-variable writes.

Changes are confined to:

- `/etc/grub.d/42_hyper_fusion`: the editor's own generator, included by future regular GRUB regeneration.
- The corresponding marked section in the current `grub.cfg`: everything outside this section is preserved.
- `/var/lib/hyper-fusion/grub-editor`: root-only entry records, transaction journals and timestamped backups.

The complete configuration passes `grub-script-check` before replacement. Saves use atomic file replacement, check for external changes, and retain the previous configuration. A failed save rolls back; an interrupted transaction is recovered the next time the authenticated editor opens. **Undo last change** refuses to overwrite intervening changes from a kernel update or another boot tool. Use **Remove from menu…** in that case to preserve those updates.

Opening the page only lists drives. Its authenticated helper belongs to the open panel, times out when idle and exits when its connection closes. The GUI itself runs as the desktop user.

## Development checks

`test_grub_editor.py` covers mounted/unmounted inventory, detection, shared EFI references, stale devices, duplicate UUIDs, literal menu names, configuration validation, external changes, rollback and recovery using temporary fixtures. Native `grub_editor_tests` cover properties, selection, naming, save responses and cancelled authentication. `check_grub_boot.py` explicitly boots disposable QEMU images to check UEFI chainloading, missing drives and Linux configuration handoff under UEFI and BIOS; it attaches no host disks. These checks do not replace testing a particular Windows/Linux installation on its intended hardware.

The boot methods follow GNU GRUB's [chainloading](https://www.gnu.org/software/grub/manual/grub/html_node/Chain_002dloading.html) and [configfile](https://www.gnu.org/software/grub/manual/grub/html_node/configfile.html) commands. Filesystem inspection follows the kernel's [ext4 mount guidance](https://docs.kernel.org/admin-guide/ext4.html) and the [NTFS-3G manual](https://github.com/tuxera/ntfs-3g/wiki/Manual).
