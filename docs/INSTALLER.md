# Hyper Fusion Setup

Run `./x_hyperinstall.sh` from a complete checkout or extracted GitHub ZIP as your regular desktop user. It opens the GTK 3 wizard, using the same lightweight GTK approach as the Echo Linux installer. Welcome, setup choices, review, progress/details and completion all remain in one window. An existing registered Xetal desktop selects the settings-preserving update flow automatically. `--cli` opens the terminal flow; existing command-line options such as `--check`, `--prepare` and `--yes` retain their terminal behavior.

For an existing desktop, **Keep my existing desktop and startup preferences** starts checked. Uncheck it to install the current desktop and startup defaults instead. The Review page shows the selected behavior, and the existing profile is backed up before replacement in either case.

Fresh installs and resets use the **Binary Knife** preset in dark mode, with its
matching wallpapers. Updates keep the existing theme and wallpaper choices.
Fresh installs always open Welcome at login, including its live `fusion-check`
panel. Disable **Show this dashboard at login** in Welcome after signing in if
desired. Fresh Start menus show the desktop wallpaper across all themes. Window
defaults are 10 px corners, 2 px borders, `5 5 5 5` inner/outer gaps, border-drag
resizing off, animations/blur/shadows on, and focused/unfocused opacity at 1.00.

Dolphin Places are generated for the recipient: Home, existing standard XDG folders, Trash and Network. Drives are discovered on that computer. Developer bookmarks, history and Dolphin runtime data are excluded from both Git and installer copies. Updates keep the recipient's own Places; a fresh/default install generates a clean list.

Dolphin starts with Hyper Fusion's dark colors on a fresh install. Its private `dolphinrc` explicitly selects the bundled `HyperFusion` scheme, so KDE's color-scheme manager cannot fall back to a light theme outside Plasma. That scheme follows the selected Hyper Fusion palette when Dolphin opens; choosing a different scheme in Dolphin remains respected. The standard Dolphin launcher in the Hyprland application directory also uses this private profile. Shared KDE/Plasma settings are untouched. [KDE color-scheme manager behavior](https://api.kde.org/kcolorschememanager.html).

The launcher starts with My Computer, Kitty and the bundled Calculator as its supplied favorites. My Computer opens Fusion Files at This PC. Setup generates clean favorites, shortcut overrides and taskbar pins even if its source checkout has been used as a desktop. Saved favorite layouts, floating sizes and imported shortcut icons are excluded from the payload. The recipient's KDE favorites remain available through read-only discovery. Updates preserve existing launcher choices instead of applying these fresh-install defaults again.

The programmer calculator ships as Python source and SVG assets under `calculator/`, using the PyQt6 dependency already installed for the desktop. Its Hyprland-only application entry has no dependency on CachyOsTools aliases, a developer home path or a separate calculator installation. It opens floating and centered; DEC/HEX and live-result preferences stay in `calculator/state/preferences.ini`, which is excluded from release payloads and updates.

Dolphin's bottom terminal opens by default and uses Konsole's embedded component, which Setup installs and checks. Kitty remains the standalone terminal, including Dolphin's external-terminal action. The embedded terminal uses a private profile whose colors follow the Hyprland Kitty theme when Dolphin is opened; shared KDE/Konsole preferences are not changed. F4 hides or shows the panel, and Dolphin remembers subsequent layout changes.

Fresh profiles show **Places** on the left and hide the redundant **Folders** tree. Existing saved layouts are preserved; F7 hides or shows Folders. The dashboard's taskbar entry reads **Welcome**, without icons for its four companion windows. Super+D continues to open or hide all four together.

During installation, the forward button is disabled, gray and labeled **Installing…**. It becomes **Finish** after success, or **Retry** if setup stops.

Run `fusion-check` inside Hyprland to see which native plugins loaded and respond.
Foreground Setup installs and verifies `/usr/local/bin/fusion-check`. Fusion's
Bash, Zsh and Fish terminals also provide the command from the installed profile
when no command with that name is available, including after a background update
or when the shell omits `/usr/local/bin` from its search path. Existing user aliases
and commands take precedence. This does not change `PATH`, Hyprland environment
directives, or the user's shell startup files. Already-open terminals can run
`/usr/bin/python3 "$HOME/.config/hypr/runtime/plugin_health.py"` directly.

Python and GTK 3 can be bootstrapped from Arch, Fedora or Debian packages if missing. The wizard itself does not need PyQt or PyGObject before starting. On Debian 13, graphical Setup uses the desktop's administrator dialog through `pkexec` when available, with a root-password fallback for accounts without sudo access. Existing sudo-authorized users can use a separate password window through `sudo -A`. Passwords go only to the authentication tool and are never included in the installation log. Details are saved to `~/.local/state/xetal-hyprland/setup.log`.

Minimal installations do not need sudo preinstalled: Setup can use an existing graphical `pkexec` agent or normal `su` authentication with the system root password. It keeps that working authentication method through installation and recovery, even after the sudo package arrives. The Python bootstrap also supports `su`. On Arch-family systems the prerequisite prompt explicitly includes a full package upgrade; signing keys are refreshed first, preventing a partial Python/GTK library upgrade on an older base. A locked root account still needs an authorized administrator authentication method; Setup never resets passwords or disables authentication.

## Tested compositor

`config/hypr/runtime/manifest.json` selects Hyprland **0.56.2**, commit `efb50993780079460b0cbed1363e2166a2de1d9f`, official Arch package **0.56.2-4** for x86-64. Setup compares both the version and commit. The unmodified package (51.3 MB / 48.9 MiB) and detached signature are included in `installer/packages/`, including GitHub ZIP downloads. Setup prefers this bundle, reuses verified pacman cache files, and falls back to the official Arch Linux Archive if needed. It verifies both recorded SHA-256 hashes and the package signature with the system Arch keyring. Other dependencies may still need downloads.

The package operation retains pacman's dependency and conflict checks. It never forces a dependency-incompatible downgrade. The [Arch runtime manifest](../config/hypr/runtime/arch.json) adds eleven signed matching library/companion packages (about 2.8 MB) alongside Hyprland. A temporary local repository makes pacman select that complete runtime and fetch all remaining desktop dependencies from the user's configured distro repositories. It performs a coordinated full system upgrade, including on older installations. The temporary repository is not enabled in the user's persistent configuration.

Setup refreshes the installed distro signing-key packages before the main transaction, so an old keyring does not reject today's valid package signatures. Verification stays enabled. If that upgrade changes Python's major/minor version, the worker restarts with the new interpreter while preserving its arguments and runtime recovery record.

On Arch, `/etc/pacman.d/xetal-hyprland.conf` holds all twelve matching runtime packages through pacman's documented [IgnorePkg and Include settings](https://man.archlinux.org/man/pacman.conf.5.en). Other repository settings and holds are preserved. Setup builds the included native sources on the recipient computer, using all available CPU threads for the Control Panel. Cube, Burn and Minimize builds are required, and the complete configuration is checked before and after compilation. KVM runtime binaries remain separate downloads inside KVM Settings.

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
reset or bypass authentication. Terminal Setup uses sudo when available, with a
root-password fallback when sudo is absent.
Authentication denial or cancellation is reported separately from package
repository failures.

After installation, Setup verifies Hyprland's version and source commit as the
authenticated desktop user. This works with sudo, [PolicyKit's invoking-user identity](https://www.freedesktop.org/software/polkit/docs/latest/pkexec.1.html#pkexec-security-notes),
and the Debian root-password fallback. A failed version command reports its
actual diagnostic instead of labelling an installed compositor as missing.

Setup also includes installed system-tool directories in its own command search
path. Debian desktop sessions can omit `/usr/sbin`, which otherwise makes
installed tools such as `dmidecode`, `fsck.fat`, `losetup` and `modinfo` appear
missing. The same lookup applies to Hyprland's launched desktop tools, including
KVM Settings. Existing command overrides keep priority; this does not edit shell
profiles or shared desktop settings.

The bundle combines documented local Debian 13 backports with unmodified trixie-backports packages. These local builds are not official Debian binary releases. Setup verifies the trusted release manifest's SHA-256 hashes, archive contents and DEB identities before passing root-owned copies to APT. Ordinary dependencies still come from configured Debian repositories with normal APT authentication. No testing/backports repository is enabled on the recipient's machine.

Foreground installation and runtime updates prepare Debian's package sources
and refresh its lists before resolving dependencies. On DVD-only installations,
Setup disables active CD-ROM entries in both `.list` and `.sources` files and
adds the [official Debian 13 online repositories](https://www.debian.org/releases/trixie/release-notes/upgrading.en.html#adding-apt-internet-sources)
for `trixie`, `trixie-updates` and `trixie-security`, using the Debian archive
keyring. Existing base mirrors, third-party sources and disabled entries are
preserved. If a security or updates mirror already exists, it is not duplicated.

Setup first verifies the proposed sources with an authenticated APT refresh.
Network or repository errors stop setup without changing the original source
files or any packages. Successful changes are saved after backing up the original
files under `/var/lib/xetal-hyprland/apt-sources/`; the backup's `record.json`
identifies new files and records original permissions. Repeating Setup does not
add duplicate repositories. An Internet connection is required for downloads.
The [DVD-only regression test](../tests/debian_sources_container.py) reproduces
the installation-media error and verifies repair, dependency resolution, retries
and failed-refresh behavior with real APT in a disposable Debian container.

Setup resolves the full transaction without removing existing applications, saves exact previous packages and downloads dependencies before installation. It records recovery under `/var/lib/xetal-hyprland/debian-runtime/`. Dedicated version pins in `/etc/apt/preferences.d/xetal-hyprland` keep the compositor and its native libraries/headers together. Other preferences and package holds are preserved. If a previous package is unavailable for recovery, installation stops before changes.

Recovery restores replaced versions and the old pins. It removes newly introduced runtime packages and their newly introduced dependants when needed, while retaining ordinary dependencies such as system services. It refuses to remove pre-existing applications or overwrite externally changed package versions or pins. Manual recovery uses `sudo python3 installer/system_debian_runtime.py --restore RECORD`.

The native runtime has passed installation from a clean Debian root using standard repositories, a complete desktop build with all three effects, full configuration validation, rollback that preserves pre-existing packages, and recovery from a forced failure after a real compositor installation. The existing QEMU binary starts unchanged with the bundled SDL3 backport; EDK II firmware remains unchanged. Graphical VM login, VM launches and GPU passthrough require separate testing. The Debian CI job repeats native installation, builds and recovery on a fresh container.

## Cancellation and recovery

Before replacing installed Arch runtime packages, Setup preserves each changed package at its exact version and architecture, including CachyOS `x86_64_v3` / `x86_64_v4` builds. It checks package caches, matching repository URLs/signatures, configured mirrors and the official archive. It never substitutes a different recovery version or bypasses signatures. If an exact previous runtime package is unavailable, Setup stops before replacing it. Root-owned records under `/var/lib/xetal-hyprland/arch-runtime/` contain `pacman.conf`, the previous hold file, signed previous packages and `record.json` with package versions and hashes. The path is printed before installation. The existing Hyprland profile is separately backed up under `~/.local/state/xetal-hyprland/backups/` before replacement.

**Stop after this step** waits for the current package transaction or build command to finish, then stops before installing the desktop profile. Arch recovery restores changed compositor/library packages together, with dependency checks and protection against later external edits. Ordinary dependency installs and system upgrades remain; this is runtime recovery, not an operating-system snapshot. If the upgraded system can no longer satisfy an older package's dependencies, recovery reports the conflict instead of forcing broken packages. Debian recovery also removes newly introduced dependants when restoring its native runtime. A successful install leaves the matching runtime held and the profile ready for the next login. The current graphical session is never forcibly restarted.

For manual Arch runtime recovery, use `sudo python3 installer/system_arch_runtime.py --restore /var/lib/xetal-hyprland/arch-runtime/RECORD`, replacing `RECORD` with the printed backup name. Older compositor-only records still use `installer/system_runtime.py --restore /var/lib/xetal-hyprland/runtime/RECORD`. Both verify saved packages and refuse to overwrite packages changed by another operation. Restore the associated desktop profile using the installer backup command printed at completion. Profile restoration refuses a declared compositor mismatch.

## Future version changes

Update the runtime manifest only after validating the new compositor, native effect adapters and complete desktop together. Keep the package/signature hashes and commit in agreement. The updater compares the incoming requirement before building and again before activation. A system package change goes through foreground Setup; ordinary background updates continue without sudo. A compositor upgrade or downgrade therefore carries the matching profile and rebuilt plugins with it.

Arch-based x86-64, mutable Fedora 44 x86-64 and Debian 13 amd64 have automatic compositor installation paths. Other distributions must install the exact required native compositor themselves before using their remaining dependency recipes. Pinning Hyprland does not pin the complete operating system; dependency checks and native builds remain necessary on every recipient machine.
## Optional Fusion sign-in

The **Use Fusion sign-in at boot instead of my current login screen** checkbox is off by default on a new install. Leaving it off does not change system login services, PAM, SDDM, GDM or LightDM. Updates keep the existing choice. Welcome's own startup preference is independent.

An always-visible note above the checkbox states **Tested on Arch with SDDM only**, including before the option is selected.

When selected, Setup shows a warning **below that checkbox**, including the changed paths, backup directory, recovery command and a request to **take a picture of the screen for safety**. The options page scrolls so the entire warning is accessible on small displays.

Fusion runs its sign-in UI in a dedicated, unprivileged Hyprland greeter session. `greetd` authenticates the selected account with the distribution's PAM stack and then starts that account's selected desktop. The user's desktop, startup applications and optional Welcome dashboard do not run before authentication. There is no automatic login into a person's desktop behind the password field. Passwords are sent only to greetd's Unix socket and are never written to disk or logs.

Installed sessions are discovered from `/usr/share/wayland-sessions/*.desktop` and `/usr/share/xsessions/*.desktop`. Hyprland, KDE Plasma, XFCE and other installed desktops retain their own session commands. Wayland sessions start directly; X11 sessions use `startx` on the authenticated user's console. The greeter remembers the selected desktop separately for each account. PAM also unlocks GNOME Keyring and an installed KDE Wallet PAM module with the login password.

**Power** at the top right offers **Restart…** and **Shut down…**, each with a
confirmation whose default is Cancel. The greeter asks logind asynchronously and
keeps sign-in usable if the request fails. Other sessions and shutdown inhibitors
remain subject to system policy; there are no forced shutdowns or passwordless
shell commands. Design previews never send power requests. A dedicated polkit
rule permits only the two ordinary power actions for the local, active
`fusion-greeter` account.

The dedicated login compositor uses the same ABI-checked startup-notice adapter
as the pinned Hyprland desktop. Setup installs its own root-owned copy and
validates the greeter configuration before enabling it. The supported `.conf`
migration reminder and optional `hyprland-guiutils` reminder are handled at
startup; configuration errors and unrelated warnings remain visible.

The four themes, Dark/Light/High contrast modes, and GIF/PNG/JPG account images come from each person's Fusion profile. Public copies of account artwork are kept in `/var/lib/xetal-fusion-login/profiles/<uid>/`; the greeter does not need access to private home directories. Applying a Fusion theme refreshes those copies without administrator access.

Before changing settings, Setup creates a dated, root-only backup under **`/var/lib/xetal-fusion-login/backups/`**. The backup records original contents, modes, owners, symbolic links and paths that did not previously exist. Relevant paths are:

- `/etc/xetal-fusion-login/greetd.toml` and `hyprland.conf`.
- `/etc/pam.d/greetd` and existing `/etc/greetd/config.toml`.
- `/etc/polkit-1/rules.d/49-xetal-fusion-login.rules` (the scoped power-action rule).
- `/etc/X11/default-display-manager`, if supplied by the distribution.
- `/etc/systemd/system/xetal-fusion-login.service`, `display-manager.service`, `default.target`, and affected service enablement links.
- `/usr/local/lib/xetal-fusion-login/` (the system-owned greeter code).
- When migrating the earlier VM setup: `/etc/systemd/system/getty@tty1.service.d/99-xetal-autologin.conf` and the marked Fusion autostart block in the installing user's `~/.zprofile`.
- A temporary `/run/systemd/system/greetd.service` installation guard, restored immediately after package installation.

Only opting in installs the additional greetd/keyring/X11 helpers and creates the `fusion-greeter` system account. It enables `xetal-fusion-login.service` for the **next boot**, sets `graphical.target`, and disables the previous login manager without stopping the current session. A setup failure restores the backed-up configuration automatically. Installed packages and the dedicated system account remain available after recovery.

If sign-in fails after reboot, press **Ctrl+Alt+F2**, log in normally and run:

```bash
sudo /usr/local/lib/xetal-fusion-login/system_setup.py --restore original
sudo systemctl reboot
```

The original backup remains available across later Fusion sign-in updates. A specific dated backup can also be supplied to `--restore`. Unchecking the option in a later foreground Setup restores the original login configuration. Neither choosing another desktop nor disabling the Welcome dashboard changes this opt-in setting.

To update an already-installed Fusion greeter, run foreground Setup again with
**Use Fusion sign-in at boot** selected. Updating only the desktop profile cannot
replace the root-owned greeter. The update creates a new backup and takes effect
at the next sign-in; it does not restart the current desktop.
