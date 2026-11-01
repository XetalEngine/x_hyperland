# Hyper Fusion GRUB theme

This is an optional boot menu theme matching Hyper Fusion's **Modern dark** palette
and wallpaper. It changes only the graphical menu. It does not change boot entries,
kernel arguments, the default entry, timeout, or the installed GRUB EFI binary.

`hyper-fusion/` contains the ready-to-copy theme. To rebuild its PNG and PF2 assets
from the repository sources, run `python3 config/hypr/grub/build.py` with Pillow and
`grub-mkfont` installed. The source wallpaper and Inter font are already in the repo.
`preview.png` is an illustration with sample entries; GRUB renders the actual entries.

## Applying on this inspected machine only

The root GRUB configuration here is a hand-written single-entry file. The
`apply-this-machine.py` script is deliberately specific to its current UUID,
kernel, initramfs, default entry, and timeout. It refuses to run if any of those
change. It leaves `/etc/default/grub` and the EFI binary untouched. It copies the
theme, inserts a guarded graphical setup before the existing menu entry, checks
the candidate with `grub-script-check`, and saves the original config next to it.
Run it **manually**, in a normal terminal outside the Codex sandbox:

```sh
sudo python3 /home/xetal/Desktop/x_hyperland/config/hypr/grub/apply-this-machine.py
```

The script prints the backup path and a one-command rollback. x_hyperland's
installer and updater omit this folder from their payload.

## Applying on another installed system

First inspect the **actual** `/boot/grub/grub.cfg` as root and confirm whether it is
a generated menu or a small forwarding file. Some installations use a forwarding
file; replacing it with `grub-mkconfig` output can break the boot arrangement.
Check that `/boot` is mounted read-write and that this GRUB installation loads
themes from that partition. Back up `/etc/default/grub` and the actual `grub.cfg`.

Copy `hyper-fusion/` to `/boot/grub/themes/hyper-fusion/`, then set
`GRUB_THEME="/boot/grub/themes/hyper-fusion/theme.txt"` in `/etc/default/grub`.
Generate a *temporary* GRUB config, run `grub-script-check` on it, and compare its
menu entries, default, timeout, and kernel command lines with the current config.
Only replace the live config after that review. The theme files must be readable by
GRUB at boot, and a graphics mode supported by the firmware is required.

To roll back, restore the backed-up `/etc/default/grub` and `grub.cfg`. A missing or
unloadable theme should leave the GRUB menu functional, but the appearance and
screen resolution may fall back to defaults. Keep the normal GRUB command line and
firmware boot entry available for recovery.
