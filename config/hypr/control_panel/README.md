# Hyper Fusion Control Panel

Native floating Qt/C++ panel, opened from Apps above Fusion Settings. See the [feature map and integration guide](../../../docs/CONTROL-PANEL.md).

**Install .deb is available again as an experimental compatibility tool.**
Choose a trusted Debian application in **Install .deb → Choose .deb and install**.
**Check dependencies only** reads the package and the existing pacman databases
without installing tools, downloading packages or changing the system.

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
script is not used for Chrome. All other converted install scripts must pass
`bash -n` before packaging; unsupported scripts stop for a dedicated recipe.
Syntax checking does not execute the script or prove its runtime behavior.
Chrome's replacement hook also repairs root-owned `0700` directories left by the
previous converter, but only when that exact directory is a public `0755`
directory in the checked Chrome payload. It never recursively changes modes,
follows symlinks or changes ownership. Reinstalling replaces damaged file modes;
the hook handles directories that pacman otherwise retains. Verification still
runs as the desktop user, so inaccessible application files remain an error.

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
