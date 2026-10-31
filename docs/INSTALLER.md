# Hyper Fusion Setup

Run `./x_hyperinstall.sh` from a complete checkout or extracted GitHub ZIP as your regular desktop user. It opens the GTK 3 wizard, using the same lightweight GTK approach as the Echo Linux installer. Welcome, setup choices, review, progress/details and completion all remain in one window. An existing registered Xetal desktop selects the settings-preserving update flow automatically. `--cli` opens the terminal flow; existing command-line options such as `--check`, `--prepare` and `--yes` retain their terminal behavior.

For an existing desktop, **Keep my existing desktop and startup preferences** starts checked. Uncheck it to install the current desktop and startup defaults instead. The Review page shows the selected behavior, and the existing profile is backed up before replacement in either case.

Dolphin Places are generated for the recipient: Home, existing standard XDG folders, Trash and Network. Drives are discovered on that computer. Developer bookmarks, history and Dolphin runtime data are excluded from both Git and installer copies. Updates keep the recipient's own Places; a fresh/default install generates a clean list.

Dolphin's bottom terminal opens by default and uses Konsole's embedded component, which Setup installs and checks. Kitty remains the standalone terminal, including Dolphin's external-terminal action. The embedded terminal uses a private profile whose colors follow the Hyprland Kitty theme when Dolphin is opened; shared KDE/Konsole preferences are not changed. F4 hides or shows the panel, and Dolphin remembers subsequent layout changes.

Fresh profiles show **Places** on the left and hide the redundant **Folders** tree. Existing saved layouts are preserved; F7 hides or shows Folders. The dashboard's taskbar entry reads **Welcome**, without icons for its four companion windows. Super+D continues to open or hide all four together.

During installation, the forward button is disabled, gray and labeled **Installing…**. It becomes **Finish** after success, or **Retry** if setup stops.

Python and GTK 3 can be bootstrapped from Arch packages if missing. The wizard itself does not need PyQt or PyGObject before starting. Package authentication uses a separate password window through `sudo -A`; passwords are passed only to sudo and are never included in the installation log. Details are saved to `~/.local/state/xetal-hyprland/setup.log`.

## Tested compositor

`config/hypr/runtime/manifest.json` selects Hyprland **0.56.2**, commit `efb50993780079460b0cbed1363e2166a2de1d9f`, official Arch package **0.56.2-4** for x86-64. Setup compares both the version and commit. The unmodified package (51.3 MB / 48.9 MiB) and detached signature are included in `installer/packages/`, including GitHub ZIP downloads. Setup prefers this bundle, reuses verified pacman cache files, and falls back to the official Arch Linux Archive if needed. It verifies both recorded SHA-256 hashes and the package signature with the system Arch keyring. Other dependencies may still need downloads.

The package operation retains pacman's dependency and conflict checks. It never forces a dependency-incompatible downgrade. Its dedicated `/etc/pacman.d/xetal-hyprland.conf` supplies `IgnorePkg = hyprland`, included in the options section of `/etc/pacman.conf`; existing repository configuration and other holds remain intact. This uses pacman's documented [IgnorePkg and Include settings](https://man.archlinux.org/man/pacman.conf.5.en).

Only Hyprland is held. Other desktop/build dependencies use the distribution package manager normally. Setup builds the included native sources on the recipient computer, using all available CPU threads for the Control Panel. Cube and Burn builds are required, and the complete configuration is checked before and after compilation. KVM runtime binaries remain separate downloads inside KVM Settings.

## Cancellation and recovery

Before replacing an installed compositor, Setup preserves its signed package for recovery. It uses the exact installed version and architecture, including CachyOS `x86_64_v3` / `x86_64_v4` builds. It checks the configured package caches, asks pacman for the matching repository URL and signature, and tries the configured mirrors before the Arch archive fallback. It never substitutes a different version for recovery or bypasses signature verification. If the exact package is unavailable, Setup stops before changing the compositor and explains the recovery-package failure. Package/configuration backups live under `/var/lib/xetal-hyprland/runtime/`. The existing Hyprland profile is backed up under `~/.local/state/xetal-hyprland/backups/` before replacement.

**Stop after this step** waits for the current package transaction or build command to finish, then stops before installing the desktop profile. If the compositor changed, Setup restores the prior package and hold on cancellation or failure. Dependencies already installed remain available for a retry. A successful install leaves the matching compositor held and the profile ready for the next login. The current graphical session is never forcibly restarted.

For a manual compositor recovery, the recorded root-owned backup can be passed to `sudo python3 installer/system_runtime.py --restore /var/lib/xetal-hyprland/runtime/RECORD`. It verifies the saved package and refuses to overwrite a compositor changed by another operation. Restore the associated desktop profile using the installer backup command printed at completion. Profile restoration refuses a declared compositor mismatch.

## Future version changes

Update the runtime manifest only after validating the new compositor, native effect adapters and complete desktop together. Keep the package/signature hashes and commit in agreement. The updater compares the incoming requirement before building and again before activation. A system package change goes through foreground Setup; ordinary background updates continue without sudo. A compositor upgrade or downgrade therefore carries the matching profile and rebuilt plugins with it.

Arch-based x86-64 is the automatic compositor installation target. Other distributions must install the exact required compositor themselves before using the remaining dependency recipes. Pinning Hyprland does not pin the complete operating system; dependency checks and native builds remain necessary on every recipient machine.
