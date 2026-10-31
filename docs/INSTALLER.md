# Hyper Fusion Setup

Run `./x_hyperinstall.sh` from a complete checkout or extracted GitHub ZIP as your regular desktop user. It opens the GTK 3 wizard, using the same lightweight GTK approach as the Echo Linux installer. Welcome, setup choices, review, progress/details and completion all remain in one window. An existing registered Xetal desktop selects the settings-preserving update flow automatically. `--cli` opens the terminal flow; existing command-line options such as `--check`, `--prepare` and `--yes` retain their terminal behavior.

For an existing desktop, **Keep my existing desktop and startup preferences** starts checked. Uncheck it to install the current desktop and startup defaults instead. The Review page shows the selected behavior, and the existing profile is backed up before replacement in either case.

Dolphin Places are generated for the recipient: Home, existing standard XDG folders, Trash and Network. Drives are discovered on that computer. Developer bookmarks, history and Dolphin runtime data are excluded from both Git and installer copies. Updates keep the recipient's own Places; a fresh/default install generates a clean list.

Dolphin's bottom terminal opens by default and uses Konsole's embedded component, which Setup installs and checks. Kitty remains the standalone terminal, including Dolphin's external-terminal action. The embedded terminal uses a private profile whose colors follow the Hyprland Kitty theme when Dolphin is opened; shared KDE/Konsole preferences are not changed. F4 hides or shows the panel, and Dolphin remembers subsequent layout changes.

Fresh profiles show **Places** on the left and hide the redundant **Folders** tree. Existing saved layouts are preserved; F7 hides or shows Folders. The dashboard's taskbar entry reads **Welcome**, without icons for its four companion windows. Super+D continues to open or hide all four together.

During installation, the forward button is disabled, gray and labeled **Installing…**. It becomes **Finish** after success, or **Retry** if setup stops.

Python and GTK 3 can be bootstrapped from Arch, Fedora or Debian packages if missing. The wizard itself does not need PyQt or PyGObject before starting. On Debian 13, graphical Setup uses the desktop's administrator dialog through `pkexec` when available, with a root-password fallback for accounts without sudo access. Existing sudo-authorized users can use a separate password window through `sudo -A`. Passwords go only to the authentication tool and are never included in the installation log. Details are saved to `~/.local/state/xetal-hyprland/setup.log`.

## Tested compositor

`config/hypr/runtime/manifest.json` selects Hyprland **0.56.2**, commit `efb50993780079460b0cbed1363e2166a2de1d9f`, official Arch package **0.56.2-4** for x86-64. Setup compares both the version and commit. The unmodified package (51.3 MB / 48.9 MiB) and detached signature are included in `installer/packages/`, including GitHub ZIP downloads. Setup prefers this bundle, reuses verified pacman cache files, and falls back to the official Arch Linux Archive if needed. It verifies both recorded SHA-256 hashes and the package signature with the system Arch keyring. Other dependencies may still need downloads.

The package operation retains pacman's dependency and conflict checks. It never forces a dependency-incompatible downgrade. Its dedicated `/etc/pacman.d/xetal-hyprland.conf` supplies `IgnorePkg = hyprland`, included in the options section of `/etc/pacman.conf`; existing repository configuration and other holds remain intact. This uses pacman's documented [IgnorePkg and Include settings](https://man.archlinux.org/man/pacman.conf.5.en).

On Arch, only Hyprland is held. Other desktop/build dependencies use the distribution package manager normally. Setup builds the included native sources on the recipient computer, using all available CPU threads for the Control Panel. Cube, Burn and Minimize builds are required, and the complete configuration is checked before and after compilation. KVM runtime binaries remain separate downloads inside KVM Settings.

## Fedora 44

Mutable **Fedora 44 x86-64**, including KDE and Workstation installations, has a native RPM path selected from `/etc/os-release`. It uses the exact same Hyprland source commit as Arch. Other Fedora releases, derivatives and immutable OSTree variants are not covered by this bundle.

[`runtime/fedora-44.json`](../config/hypr/runtime/fedora-44.json) pins 19 unmodified signed packages from **giperborey/Hyprland on Fedora COPR**. The runtime totals **55,923,257 bytes (55.9 MB)**. Matching Hyprland and Hyprlang source RPMs add 55.4 MB separately for the bundled LGPL components. Every individual file is below GitHub's 100 MB limit; actual RPMs, not LFS pointers, are included in Download ZIP. Other desktop/build dependencies still download from the recipient's configured Fedora repositories. [Bundle provenance, key and licenses](../installer/packages/fedora-44/README.md).

Setup checks SHA-256 hashes, RPM identities, and signatures against an isolated key database containing only the pinned COPR key. It then imports that verified public key into RPM's trust database and uses normal DNF signature/dependency checks. No COPR repository is added or enabled. A read-only DNF resolution precedes package changes. The privileged helper stores and checks the resolved transaction before replay, including copies of the verified local RPMs; it does not use `--allowerasing`, `--nodeps`, or `--nogpgcheck`.

The bundle's compositor, libraries, tools and headers receive exact version/architecture locks in a marked section of `/etc/dnf/versionlock.toml`. Unrelated locks are preserved; overlapping user-owned locks require review. This keeps native effects paired with their libraries. Standard desktop packages remain managed normally. Fedora's package recipe includes PyQt6, the dark Papirus icons, shader/input development headers and its authentication agent. The session launches the agent as an owned child process; it does not enable its systemd service. Fedora's stock Kitty 0.47.1 is accepted after testing the three animated dashboard terminals.

Before replacing a bundled component, Setup saves its exact signed installed RPM from the package cache, an earlier Setup record, or configured repositories. If it cannot obtain that exact recovery RPM, it stops before replacing packages. On failure or cancellation it restores the old bundled components and locks, or removes the bundle if none was previously installed. Standard dependency packages remain installed. Recovery refuses external runtime changes and any resolved removal of unrelated applications. Records live in `/var/lib/xetal-hyprland/fedora-runtime/`; manual recovery uses `sudo python3 installer/system_fedora_runtime.py --restore RECORD`.

A disposable Fedora 44 test environment completed package signature/dependency checks, the complete native desktop build, configuration validation, Kitty dashboard rendering, successful runtime rollback, a real 0.57 → 0.56.2 downgrade with exact 0.57 recovery, DNF lock-file rewrites, and recovery from an injected post-install failure. The Fedora CI job repeats installation, builds and recovery. These checks do not replace a graphical VM login or tests of each GPU/driver combination.

## Debian 13

**Debian 13 (trixie) amd64** has a native DEB path selected from `/etc/os-release`. The [runtime ZIP](../installer/packages/debian-13/README.md) contains 52 packages totaling **22.3 MB**: Hyprland 0.56.2, matching headers/libraries, Waybar 0.15, Kitty 0.48.2 and SDL3 3.4.18. Corresponding sources and a rebuild helper are included separately; every individual archive is below 100 MB. Ubuntu, Debian 12/14 and derivatives are not accepted by this bundle.

Debian installations can have a separate root account and a desktop user without
sudo access. Graphical Setup uses the existing desktop authentication agent via
[`pkexec`](https://www.freedesktop.org/software/polkit/docs/latest/pkexec.1.html)
for package operations, recovery and account setup. Authenticate using the account
named in that dialog; it may require the root password. A desktop user's password
alone cannot authorize administrative changes if that account lacks permission.

After dependencies are ready, foreground Setup automatically adds the installing
local desktop user to Debian's standard `sudo` group if needed, preserving all
existing groups. The privileged helper identifies the user from the authentication
tool, and verifies the membership after changing it. Setup continues immediately
using administrator authentication; other applications pick up the group at the
next sign-in. Existing members are left unchanged. This persistent account setup
is limited to Debian 13; checks, review-only builds, `--skip-packages` and background
updates do not enroll accounts. It is retained if a later desktop build fails,
just like ordinary dependency packages. No sudoers or PolicyKit rules are changed,
and no passwordless access is granted. See
[Debian's account and group instructions](https://www.debian.org/doc/manuals/debian-reference/ch01.en.html#_permissions_for_groups_of_users_group).

Keep running Setup as the desktop user; only system operations run as root.
If `pkexec` is missing, sessions with active Debian `sudo` membership use their
user password. For a user without sudo access, graphical Setup instead opens a clearly
labeled **root password** dialog before the first APT operation. It submits that
password to Debian's normal [`su`/PAM authentication](https://manpages.debian.org/trixie/util-linux/su.1.en.html)
through a private terminal with password echo disabled. The password is never
passed in a command argument, environment variable, file or installation log.
Cancelling stops the operation, and a wrong password cannot run the command.
The same authentication path remains available through package installation,
account setup and recovery, even if those packages install `pkexec` during Setup.
This requires the root password chosen during Debian installation; it does not
reset or bypass authentication. Terminal Setup continues to use sudo.
Authentication denial or cancellation is reported separately from package
repository failures.

The bundle combines documented local Debian 13 backports with unmodified trixie-backports packages. These local builds are not official Debian binary releases. Setup verifies the trusted release manifest's SHA-256 hashes, archive contents and DEB identities before passing root-owned copies to APT. Ordinary dependencies still come from configured Debian repositories with normal APT authentication. No testing/backports repository is enabled on the recipient's machine.

Foreground installation and runtime updates refresh Debian's package lists
before resolving dependencies. A failed refresh stops setup before any package
changes and shows APT's repository/network error. An enabled Debian 13 network
mirror is required; a DVD-only source list cannot supply all dependencies.
Setup preserves the existing repository configuration. The empty-package-list
case is covered by the disposable Debian test.

Setup resolves the full transaction without removing existing applications, saves exact previous packages and downloads dependencies before installation. It records recovery under `/var/lib/xetal-hyprland/debian-runtime/`. Dedicated version pins in `/etc/apt/preferences.d/xetal-hyprland` keep the compositor and its native libraries/headers together. Other preferences and package holds are preserved. If a previous package is unavailable for recovery, installation stops before changes.

Recovery restores replaced versions and the old pins. It removes newly introduced runtime packages and their newly introduced dependants when needed, while retaining ordinary dependencies such as system services. It refuses to remove pre-existing applications or overwrite externally changed package versions or pins. Manual recovery uses `sudo python3 installer/system_debian_runtime.py --restore RECORD`.

The native runtime has passed installation from a clean Debian root using standard repositories, a complete desktop build with all three effects, full configuration validation, rollback that preserves pre-existing packages, and recovery from a forced failure after a real compositor installation. The existing QEMU binary starts unchanged with the bundled SDL3 backport; EDK II firmware remains unchanged. Graphical VM login, VM launches and GPU passthrough require separate testing. The Debian CI job repeats native installation, builds and recovery on a fresh container.

## Cancellation and recovery

Before replacing an installed compositor, Setup preserves its signed package for recovery. It uses the exact installed version and architecture, including CachyOS `x86_64_v3` / `x86_64_v4` builds. It checks the configured package caches, asks pacman for the matching repository URL and signature, and tries the configured mirrors before the Arch archive fallback. It never substitutes a different version for recovery or bypasses signature verification. If the exact package is unavailable, Setup stops before changing the compositor and explains the recovery-package failure. Package/configuration backups live under `/var/lib/xetal-hyprland/runtime/`. The existing Hyprland profile is backed up under `~/.local/state/xetal-hyprland/backups/` before replacement.

**Stop after this step** waits for the current package transaction or build command to finish, then stops before installing the desktop profile. If the compositor changed, Setup restores the prior package and hold on cancellation or failure. Ordinary dependencies already installed may remain available for a retry; Debian recovery also removes newly introduced dependants when restoring its native runtime. A successful install leaves the matching compositor held and the profile ready for the next login. The current graphical session is never forcibly restarted.

For a manual compositor recovery, the recorded root-owned backup can be passed to `sudo python3 installer/system_runtime.py --restore /var/lib/xetal-hyprland/runtime/RECORD`. It verifies the saved package and refuses to overwrite a compositor changed by another operation. Restore the associated desktop profile using the installer backup command printed at completion. Profile restoration refuses a declared compositor mismatch.

## Future version changes

Update the runtime manifest only after validating the new compositor, native effect adapters and complete desktop together. Keep the package/signature hashes and commit in agreement. The updater compares the incoming requirement before building and again before activation. A system package change goes through foreground Setup; ordinary background updates continue without sudo. A compositor upgrade or downgrade therefore carries the matching profile and rebuilt plugins with it.

Arch-based x86-64, mutable Fedora 44 x86-64 and Debian 13 amd64 have automatic compositor installation paths. Other distributions must install the exact required native compositor themselves before using their remaining dependency recipes. Pinning Hyprland does not pin the complete operating system; dependency checks and native builds remain necessary on every recipient machine.
