# Hyper Fusion Setup

Run `./x_hyperinstall.sh` from a complete checkout or extracted GitHub ZIP as your regular desktop user. It opens the GTK 3 wizard, using the same lightweight GTK approach as the Echo Linux installer. Welcome, setup choices, review, progress/details and completion all remain in one window. An existing registered Xetal desktop selects the settings-preserving update flow automatically. `--cli` opens the terminal flow; existing command-line options such as `--check`, `--prepare` and `--yes` retain their terminal behavior.

Python and GTK 3 can be bootstrapped from Arch packages if missing. The wizard itself does not need PyQt or PyGObject before starting. Package authentication uses a separate password window through `sudo -A`; passwords are passed only to sudo and are never included in the installation log. Details are saved to `~/.local/state/xetal-hyprland/setup.log`.

## Tested compositor

`config/hypr/runtime/manifest.json` selects Hyprland **0.56.2**, commit `efb50993780079460b0cbed1363e2166a2de1d9f`, official Arch package **0.56.2-4** for x86-64. Setup compares both the version and commit. When necessary, it downloads the package and detached signature from the official Arch Linux Archive, verifies their recorded SHA-256 hashes and verifies the signature with the system Arch keyring. Files already present in the pacman cache can be reused after verification.

The package operation retains pacman's dependency and conflict checks. It never forces a dependency-incompatible downgrade. Its dedicated `/etc/pacman.d/xetal-hyprland.conf` supplies `IgnorePkg = hyprland`, included in the options section of `/etc/pacman.conf`; existing repository configuration and other holds remain intact. This uses pacman's documented [IgnorePkg and Include settings](https://man.archlinux.org/man/pacman.conf.5.en).

Only Hyprland is held. Other desktop/build dependencies use the distribution package manager normally. Setup builds the included native sources on the recipient computer, using all available CPU threads for the Control Panel. Cube and Burn builds are required, and the complete configuration is checked before and after compilation. KVM runtime binaries remain separate downloads inside KVM Settings.

## Cancellation and recovery

Before replacing an installed compositor, Setup preserves its signed package for recovery. Package/configuration backups live under `/var/lib/xetal-hyprland/runtime/`. The existing Hyprland profile is backed up under `~/.local/state/xetal-hyprland/backups/` before replacement.

**Stop after this step** waits for the current package transaction or build command to finish, then stops before installing the desktop profile. If the compositor changed, Setup restores the prior package and hold on cancellation or failure. Dependencies already installed remain available for a retry. A successful install leaves the matching compositor held and the profile ready for the next login. The current graphical session is never forcibly restarted.

For a manual compositor recovery, the recorded root-owned backup can be passed to `sudo python3 installer/system_runtime.py --restore /var/lib/xetal-hyprland/runtime/RECORD`. It verifies the saved package and refuses to overwrite a compositor changed by another operation. Restore the associated desktop profile using the installer backup command printed at completion. Profile restoration refuses a declared compositor mismatch.

## Future version changes

Update the runtime manifest only after validating the new compositor, native effect adapters and complete desktop together. Keep the package/signature hashes and commit in agreement. The updater compares the incoming requirement before building and again before activation. A system package change goes through foreground Setup; ordinary background updates continue without sudo. A compositor upgrade or downgrade therefore carries the matching profile and rebuilt plugins with it.

Arch-based x86-64 is the automatic compositor installation target. Other distributions must install the exact required compositor themselves before using the remaining dependency recipes. Pinning Hyprland does not pin the complete operating system; dependency checks and native builds remain necessary on every recipient machine.
