# Hyper Fusion Control Panel

Native floating Qt/C++ panel, opened from Apps above Fusion Settings. See the [feature map and integration guide](../../../docs/CONTROL-PANEL.md).

System Overview's legacy language selector and restart callback are commented
out. Sensors & Power links to **System Tweaks → Performance** between the power
controls and Fan control. Users & Groups shows the signed-in account's shared
Hyper Fusion profile image, including animated GIFs in its account card; other
accounts retain their own account images. **Change Icon** for the current account
opens the shared appearance settings.

**Window Inspector** automatically uses Hyprland's window and layer inventory,
with `xetal-inspector-surfaces` adding popup menus and child surfaces after the
updated native adapter loads at login. Untitled/classless surfaces are included
by default. Geometry, owner, process path, workspace, monitor and raw properties
come from the compositor and local process information. Controls are limited to
ordinary managed windows; popup/layer/child-surface inspection is read-only.
See [backend coverage](backend/docs/WINDOW_ENUM.md) for details and checks.

**RDP** provides native remote desktop sessions with saved PCs and system-wallet
passwords, a shared home folder, clipboard text/images, audio, microphone,
printer redirection, resizing, reconnect, and a hiding session toolbar. See
[`rdp/README.md`](rdp/README.md) for defaults, controls, dependencies, and checks.

**Install .deb is available again as an experimental compatibility tool.**
Choose a trusted Debian application in **Install .deb → Install or update from .deb**.
**Check dependencies only** reads the package and the existing pacman databases
without installing tools, downloading packages or changing the system.
Each visit warns if **neither Yay nor Paru** is installed. Either helper is
sufficient; the warning does not start an installation and stays silent during
background preloading.

For an update, download the newer `.deb` from the same publisher and use the same
button. Conversion and validation run again, then `pacman -U` upgrades the matching
installed package and tracks the new files. A same-version file is a reinstall;
pacman displays its transaction before confirmation. Matching is by the converted
package name, so changing edition, vendor, or packaging source is not necessarily
an upgrade. Dependencies and file conflicts remain checked. This page does not
poll vendors or automatically download application updates; registration with
pacman alone does not provide an update feed. App-owned data/settings in the home
directory are outside the converted system payload.

The page has a theme-aware **Experimental** banner and a responsive app grid
below the installation buttons. `deb_apps.json` is the compatibility catalog:
**Google Chrome** is reported working on **November 7, 2026**, and **Discord
1.0.168** and **Visual Studio Code 1.145.2** on **November 8, 2026**.
Clicking an app opens its official download page; it does not download or install a package.
Test dates describe a reported result, not support for all future versions.
Keep new entries untested until an installation and launch have been checked;
record a `tested_on` ISO date (`YYYY-MM-DD`) and explain the result in `note`.
Use `status: "launch_tested"` for an automated installation, GUI startup and
removal check after reviewing the captured screenshot. This displays **Launch
tested**, separately from human-reported **Tested working** results. It does not
claim account, application-feature, GPU or Wayland compatibility. Obsidian
1.15.0, Bitwarden 2026.9.1, Insomnia 13.4.0, Signal 8.34.0, Sublime Text
4215, Opera 139.0.6053.38, 1Password 8.12.44 and AnyDesk 8.1.0 passed this
check on November 8, 2026. The reusable isolated runner is documented in
[`tests/deb_lab/README.md`](../../../tests/deb_lab/README.md).
The bundled Papirus icons are fallbacks for fresh installations.

**Send feedback** opens a local form for the app name, optional version, original
`.deb` download URL, result and error/test details. Copying requires a name, an
HTTP(S) URL and details. **Copy & open Echo/Discord** copies the report and opens
chat in the browser; the user pastes and sends it. Nothing is uploaded, sent or
saved automatically. The report adds only the OS name, architecture and date;
it does not collect logs, usernames or hardware identifiers. Echo's existing
contact is `xetal`, and the confirmed Discord username is also `xetal`. The form
shows add-friend instructions for both. Discord opens its Friends/direct-message
area, since a username alone does not supply a numeric profile URL. Contact
destinations and instructions live in the catalog's `feedback` section.

`deb_page.*` owns this presentation and forwards the original install, check-only
and helper-install actions. Native interaction checks are available with
`-DBUILD_DEB_PAGE_TESTS=ON` and `ctest -R '^deb_page$'`. They intercept browser
opens and use temporary state; they do not install packages or send reports.

The same page shows whether **Yay** and **Paru** are installed and offers an
install button for either missing helper. One is sufficient. They use the same
detector and install actions as the dedicated Yay/Paru pages. When bootstrapping
without another helper, build tools are prepared with `pacman -Syu`, AUR build
files are shown for review, and `makepkg -si` runs as the desktop user. Passwords
are entered into sudo in the terminal, never embedded in a shell command.

`deb_dependencies.py` reads `Depends` and `Pre-Depends` from the original control
archive. Explicit ABI-aware mappings translate common desktop libraries to Arch
packages. Exact names already available in Arch also work. It chooses one usable
member of each `A | B` group, preferring a sufficiently recent installed member,
then an official repository package. If neither satisfies it, exact mapped names
are checked using the AUR metadata API. An installed Yay or Paru builds those
dependencies after the application's converted payload and metadata pass checks.
Its normal build review remains enabled. Pacman verifies the resulting installed
versions before the application transaction. A declined build cannot count as
success. AUR network failures are reported separately from missing packages.
It compares upstream minimum versions, keeping Arch's epoch separate from
Debian's epoch and packaging revision. For example, `libnspr4 (>= 2:4.9-2~)` becomes
`nspr>=4.9`, not `nspr4.9-2~`. Pre-release minimums conservatively require the
upstream final release. Debian-specific revision requirements cannot be proved
on Arch. Exact/upper/strict bounds, unknown ABI names, unavailable packages and
foreign architectures stop with a list of unresolved requirements. Required
dependencies are never silently dropped or installed with `--nodeps`. Unknown
dependencies are not guessed, downloaded from Debian, or built from arbitrary AUR
search matches; extending support requires an explicit mapping or recipe.

GCC runtime mappings follow Arch's [split runtime packages](https://archlinux.org/todo/gcc-libs-deprecation/):

| Debian dependency | Arch package | Shared library ABI |
| --- | --- | --- |
| `libatomic1` | `libatomic` | `libatomic.so.1` |
| `libgcc-s1` | `libgcc` | `libgcc_s.so.1` |
| `libstdc++6` | `libstdc++` | `libstdc++.so.6` |
| `libgomp1` | `libgomp` | `libgomp.so.1` |
| `libquadmath0` | `libquadmath` | `libquadmath.so.0` |
| `libgfortran5` | `libgfortran` | `libgfortran.so.5` |

These shared mappings apply to every `.deb`, including Discord 1.0.168's
`libatomic1` requirement. The [Debian file list](https://packages.debian.org/trixie/amd64/libatomic1/filelist)
and [Arch file list](https://archlinux.org/packages/core/x86_64/libatomic/files/)
identify the same library ABI. Version minimums remain enforced, and unsupported
ABI generations still stop resolution. For future mappings, verify the actual
library and package ownership in both distributions and add a dependency fixture
with missing/insufficient-version cases. The Discord fixture checks dependency
resolution only; installation and launch reports are recorded separately in the catalog.

Visual Studio Code 1.145.2's `libxkbfile1 (>= 1:1.1.0)` requirement maps to
`libxkbfile>=1.1.0`. Arch's [libxkbfile package](https://archlinux.org/packages/extra/x86_64/libxkbfile/files/)
provides `libxkbfile.so.1`. This mapping also applies to other `.deb` apps, with
the same minimum-version checks. Its regression fixture covers Microsoft's full
dependency list, and missing, outdated or unsupported library ABIs still stop
resolution. Passing the dependency check does not mark VS Code tested working.

Spotify's dependency preflight also exposed two shared mappings:
`libxshmfence1` → `libxshmfence` and `libayatana-appindicator3-1` →
`libayatana-appindicator`. The [Debian Xshmfence files](https://packages.debian.org/trixie/amd64/libxshmfence1/filelist)
and [Arch Xshmfence files](https://archlinux.org/packages/extra/x86_64/libxshmfence/files/)
identify `libxshmfence.so.1`; the [Debian Ayatana files](https://packages.debian.org/trixie/amd64/libayatana-appindicator3-1/filelist)
and [Arch Ayatana files](https://archlinux.org/packages/extra/x86_64/libayatana-appindicator/files/)
identify `libayatana-appindicator3.so.1`. Minimum versions still apply. GTK 2,
other ABI generations and the old `libappindicator3-1` name are not substituted
with the GTK 3 Ayatana library. The Spotify metadata fixture checks that these
requirements resolve through official Arch packages without an AUR lookup.

The helper prepares missing conversion tools (including `pactree` from
`pacman-contrib`) and repairs incomplete debtap/pkgfile databases before converting.
It verifies database contents even when `debtap -u` claims success, and installs
only after successful conversion. The checked dependencies replace Debtap's
guesses in a temporary script **before** `.MTREE` is generated. The installed
Debtap script is unchanged, and an unknown script layout is rejected. Conversion
uses `-Q` because dependency metadata is supplied automatically. Additional native
library dependencies identified by namcap are retained; a failed scanner stops
conversion instead of being hidden by its output-filtering pipeline. The resulting
package must contain exactly the reviewed and scanned requirements, and `pacman -Up` must
resolve the complete transaction before privileged installation is offered.
Pacman then fetches missing native dependencies through its normal `-U`
transaction. Dependency, update, conversion and pacman
failures stop the operation with the failed command visible in the terminal.
Package installation keeps pacman's normal confirmation and authentication.
Before installing, the helper checks that conversion preserved the original
application executables, `/opt` files and Apps launchers, allowing debtap's
normal Arch executable-directory moves. After the pacman transaction, it checks
the installed package name/version, runs `pacman -Qk` and verifies application
files and launcher paths exist. The final installation success message appears
only after these checks pass; debtap's earlier "Package successfully created!"
message marks conversion. These checks do not launch the application or prove
that all of its runtime features or Debian maintainer scripts are compatible
with Arch. Missing or empty repository indexes, which can occur after an offline
installation, are detected before package availability is assessed. The normal
install action offers `sudo pacman -Syu` with pacman's usual transaction review,
then repeats the dependency check. Check-only and convert-only modes report the
missing indexes without updating the system. A standalone `-Sy` followed by new
packages is avoided because Arch does not support partial upgrades. A stale
repository cache or unavailable mirror remains a visible package-manager error.

Conversion uses a child-local `022` umask for generated directories and tells GNU
tar to preserve the source archive's modes. This keeps public executables usable,
private files private, and setuid helpers intact. The desktop's umask and the
private temporary parent are unchanged. A libarchive metadata pass compares
source and converted permissions, including parent directories, before installation.

`deb_recipes.py` supplies an explicit **Google Chrome Stable** adaptation. It
packages the browser icons under `usr/share/icons/hicolor`, keeps the browser,
launcher and original logos, and removes only Google's two Debian cron-updater
paths. Native pacman hooks replace Debian setup scripts; consequently Chrome's
packaging-only `dpkg` prerequisite is not installed. This follows the layout in
the [maintained Chrome Arch recipe](https://aur.archlinux.org/cgit/aur.git/tree/PKGBUILD?h=google-chrome).
Debtap corrupts the vendor script's heredocs and conditionals, so its generated
script is not used for Chrome. Other converted install scripts must pass
`bash -n` before packaging; unsupported scripts stop for a dedicated recipe.
Syntax checking does not execute the script or prove its runtime behavior.
Chrome's replacement hook also repairs root-owned `0700` directories left by the
previous converter, but only when that exact directory is a public `0755`
directory in the checked Chrome payload. It never recursively changes modes,
follows symlinks or changes ownership. Reinstalling replaces damaged file modes;
the hook handles directories that pacman otherwise retains. Verification still
runs as the desktop user, so inaccessible application files remain an error.

The **VS Code Stable** (`code`) recipe checks Microsoft's product identity and
the reviewed application layout before replacing Debtap's broken `.INSTALL`.
The `/usr/bin/code` symlink and hicolor icon become package-owned files. Native
desktop/icon/MIME hooks handle installation, upgrades and removal; their packages
are explicit dependencies. The editor, CLI, desktop entries, workspace MIME
definition, sandbox permissions and remaining payload are retained. File-loss
checks include `/usr/share/code`, where this app stores its executable/runtime.
APT repository/key setup, Debian editor alternatives and debconf prompts are
replaced by that native integration. The optional shared `/usr/bin/copilot`
command is left unclaimed; Microsoft's shim remains under
`/usr/share/code/bin/copilot-shim/copilot`. Existing editor preferences are kept.
Other apps' broken scripts still stop; this is a named recipe, not a syntax-check
bypass. A package layout or product identity change requires another review.

Three more named recipes replace the vendors' Debian setup scripts with native
package integration. All added launchers, icons, policies and units belong to the
converted pacman package; dependency, conflict and file ownership checks remain
enabled. The original binaries stay unchanged.

- **Opera Stable** keeps its vendor launcher and private library directory.
  Only the reviewed `apt-transport-https` and `debconf` setup groups are removed;
  unknown alternatives and architecture constraints still stop for review. Qt 5
  requirements resolve to `qt5-base`. Its specific `opera_sandbox` receives the
  vendor-required root/setuid mode, checked before packaging and after install.
  The recipe does not change the default browser or configure an APT repository.
- **1Password** packages its launchers, Polkit policy, browser defaults and a
  small native setup helper. On install/upgrade, that helper creates the vendor's
  protected `onepassword` and `onepassword-mcp` groups, sets the helper permissions
  and fills the policy with users from the target system. It never adds users to
  those groups. `/etc/1password/custom_allowed_browsers` is a pacman backup file.
  The Chromium sandbox retains the vendor-required root/setuid mode. A separate
  post-install check rejects incomplete group, permission or policy setup even
  if pacman returned success. APT/debsig configuration is not executed.
- **AnyDesk** installs its unit in `/usr/lib/systemd/system` as a package-owned
  file. Its native `libevdev` dependency supplies `libevdev.so.2`, required by
  the 8.1.0 ELF binary but omitted from its Debian control file. Unattended
  access is opt-in; installation prints the service command
  without enabling it. Upgrades refresh an already-running service and removal
  stops it. GUI startup testing does not certify remote connections.

These adaptations were reviewed against the vendor `.deb` contents and native
packaging: [Opera's archived Arch recipe](https://gitlab.archlinux.org/archlinux/packaging/packages/opera),
[1Password](https://aur.archlinux.org/cgit/aur.git/tree/PKGBUILD?h=1password), and
[AnyDesk](https://aur.archlinux.org/cgit/aur.git/tree/PKGBUILD?h=anydesk-bin).
The exact vendor versions, archive hashes and recipe snapshots are retained in
the lab reports. Changed layouts, unexpected symlinks and invalid scripts fail
before installation. Permission exceptions are restricted to the two named
sandbox files, specifically `0755` → `4755`; other original permissions remain
subject to the existing preservation check.

Shared mappings also cover `libxcb-shape0`, `libxcb-shm0`, `libxcb-xfixes0`
(`libxcb`), `libqt5core5a`, `libqt5gui5`, `libqt5widgets5` (`qt5-base`), the legacy
`libgcc1` name (`libgcc`), and `gnupg2` (`gnupg`). These match the components in
the Debian and Arch file lists and keep minimum version checks. They do not
guess other ABI generations or substitute Qt 5 for Qt 6/GLES packages.

Command-line checks (run as the desktop user):

```sh
python3 deb_install.py --check /path/to/application.deb
python3 deb_install.py --convert-only /path/to/output /path/to/application.deb
python3 -m unittest discover -s . -p 'test_deb*.py'
python3 -m unittest discover -s . -p 'test_aur_helper_install.py'
```

`--convert-only` prepares any missing conversion tools and saves a checked Arch
package without installing the application. It refuses to overwrite an existing
output. Tests include Chrome's failing version/alternative requirements, archive
inspection, metadata insertion before hashing, dependency dry runs, cancellations,
skipped pacman transactions and missing installed files.

Debtap 3.6.3's numbered-cache check rejects current pkgfile databases. For that
known check, conversion uses a temporary copy that asks `pkgfile -l pacman`
whether the database is usable. Older numbered caches remain supported, missing
or corrupt databases still stop conversion, and the installed debtap script is
unchanged. See the [upstream cache check](https://github.com/helixarch/debtap/blob/3.6.3/debtap)
and [pkgfile's cache naming](https://github.com/falconindy/pkgfile/blob/master/src/repo.cc).

System ISO rechecks missing tools when an individual-install or Install All
terminal closes, including after a cancelled or failed install. It removes only
dependencies that are now present, without requiring the page or panel to reopen.

The header has built-in minimize, maximize/restore and close buttons on the home
screen and every tool page. Minimize sends Qt's native minimize request, keeping
the panel available through Fusion's Minimize effect; it no longer merely hides
the window. The middle button tracks changes from keyboard shortcuts as well as
clicks. Double-clicking empty header space also maximizes/restores. Close still
honors the application's running-job and unsaved-work checks.

`../theme/window_chrome.hpp` supplies the same native controls to Fusion Files.
The Python counterpart supplies Fusion Settings, Theme, KVM Settings, Images,
Media, Desktop Updates and Projects. These buttons belong to the app's layout
and send ordinary Qt window requests. Calculator already has a native set;
launch menus, overlays and confirmation dialogs retain their contextual controls.
`tests/check-window-buttons.py PLUGIN OUTPUT_DIR --builtin-only` exercises real
clicks on Files, Control Panel, Settings, Theme and KVM in a private compositor,
including repeated maximize/restore and minimize without closing the process.

- `backend/`: complete CachyOsTools source/resources at the revision in `UPSTREAM.json`, with desktop integration changes. The original checkout remains independent.
- `native.*`, `main.cpp`, `tools.json`: icon navigation, responsive layout and shared appearance.
- `bridge.py`, `shell_adapter.h`, `aliases.py`: shell settings and the existing Apps shortcut editor.
- `startup.py`, `terminal.py`: Hyprland startup applications/environment and Kitty integration.
- `disk_visualizer.*`, `disk_layout.h`: lazy disk tree, breadcrumbs and squarified treemap in System Cleaner.
- `disk_scan.py`: pipe-owned sudo metadata scanner, disposable SQLite index and ID-based deletion; `test_disk_scan.py` exercises isolated fixtures.
- `ram_cleaner.*`: manual file/metadata cache reclamation, live memory readings and observed before/after results. The Python helper authenticates only on cleanup; it never closes apps, deletes files or changes swap.
- `default_apps.*`: themed app cards, an installed-app chooser, and searchable file types/links. The helper saves standard account-level MIME associations, keeps isolated profile fallbacks consistent, preserves unrelated preferences and supports Undo. Super+E and desktop folder actions use `scripts/file-manager.sh` to follow the chosen file manager. Inventory and previews are read-only.
- `runtime_log_guard.*`: System Tweaks → Hyprland controls for the default-enabled, session-owned `scripts/runtime-log-guard.py`. Oversized Hyprland and Hyper Fusion logs are cleared in place every minute. An independent **Disable session logs to file** checkbox applies on the next login through `scripts/session_logging.py`; existing logs are retained and helper output goes to `/dev/null`. Both choices are preserved under `control_panel/state`.
- `grub_editor.*`, `grub_appearance.*`: native boot-entry editor and Appearance tab, read-only automatic bootloader detection, design previews and a pipe-owned authenticated helper. Nine Fusion designs, bundled/custom pictures, menu placement, text and colors can be mixed before an explicit apply. Picture/Menu/Colors tabs fit beside the preview without nested scrolling. Private GRUB menus can be loaded with administrator authentication directly from Appearance, preserving the current draft. Before Apply, a recovery review creates backups, lists exact paths and new files, and offers copy/save instructions for Linux or a live USB. Confirmation uses that reviewed backup once and refuses stale or damaged backups. Validated changes preserve boot entries; appearance has its own restore/undo history. See the [GRUB Boot Editor guide](../../../docs/GRUB-BOOT-EDITOR.md). Python fixtures, native Qt tests and disposable UEFI/BIOS boot checks accompany it.
- `backend/iso/`: original ISO builder and installer payloads, embedded in the executable.
- `backend/drive_tree.*`: expandable disks and partitions with a compact minimum-size filter; refresh preserves expansion and selection. Device actions use stored paths and types, including mounted descendants hidden by the filter.
- `window_sizing.h`: 1650 × 910 starting size for tool windows, bounded to the screen; small confirmation prompts retain their content size.
- `build.py`: local native build. `.build/` and `state/` are not committed.
- `test_adapters.py`: isolated adapter, coverage and ISO-resource checks.

License: GPLv3; see `LICENSE`. Original source attribution and documentation are retained.
