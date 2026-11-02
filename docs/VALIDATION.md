# Validation

## Default Apps and file selection — 1 November 2026

The new Control Panel page passed eleven association-helper checks with real Gio
and `xdg-mime` queries in disposable homes. Coverage includes grouped browser and
media associations, individual MIME types, desktop-specific overrides, literal
folder paths, unrelated-setting preservation, stale-write rejection, atomic
failure recovery and Undo. Eight native Qt checks passed in all twelve design
and palette combinations. The complete panel found all 35 tool routes, including
Default Apps, with no navigation errors. The installed Binary Knife page was
visually inspected without changing the account's defaults during testing.

Fusion Files passed twenty native checks using mouse selection in all five
views, F2, Delete, copy/cut/paste, Undo, unknown-file and script menus, and Ark's
actual ZIP action. Numbered pastes preserve existing files, nested directories,
dotfiles, compound extensions and dangling symlinks. Separate private D-Bus
checks sent a real 64 MiB folder copy through Fusion's Binary Knife JobView UI:
progress, pause/resume, successful completion and cancellation all passed;
cancellation preserved the source files. The progress-specific native case is
skipped in the ordinary suite and run by these two dedicated checks.

The 33 installer checks, 15 Control Panel adapter checks, 10 desktop-menu checks,
seven screenshot-action checks, 23 transfer model/preferences checks and shared
scrollbar layout check passed. Native Hyprland configuration validation passed
before deployment; the live reload reported no errors and Super+E resolved to
the selected-file-manager helper. Installation used private backups and kept
unrelated local settings. Test screenshots, app inventories and default-app
history are excluded from the public changes.

## Fireball Minimize and window ordering — 31 October 2026

The native adapter was compiled against the pinned Hyprland 0.56.2 ABI and tested
in a disposable nested compositor with Cube and Burn loaded. Actual Qt Wayland
and XWayland minimize requests, virtual-pointer fireball clicks, repeated
minimize, external activation, column scrolling, groups, closing a minimized
app, disabling the effect, restore-all and plugin unload passed. Floating
geometry, maximized/fullscreen state and pins survived restoration. Removing
an output returned its minimized app before normal workspace migration.

A maximized viewer and a floating settings window reproduced the relevant
stacking arrangement. Front/Back changed the floating-over-fullscreen state,
and three workspace round-trips kept the chosen order. No VM was used or changed.
Reduced-motion recovery also passed. See `tests/check-minimize.py` for the
reproducible integration check.

Seven settings/UI/native-math checks, 33 updater checks, 31 installer/source
checks and the Burn controls suite passed. The socket lifecycle test needs an
environment that permits local Unix sockets. Full installed-profile
`Hyprland --verify-config` validation passed before activation.

## Pinned compositor and graphical Setup — 31 October 2026

The current release requires the development machine's Hyprland **0.56.2**,
commit `efb50993780079460b0cbed1363e2166a2de1d9f`. The official Arch
`0.56.2-4` package and signature matched the manifest checksums, and the
system Arch keyring accepted the package signature. The developer computer
already had this version; the new helper successfully installed and verified
its dedicated pacman hold, with a backup of the previous package configuration.

A complete separate profile built all native components with 32 available CPU
threads for the Control Panel, including both Cube and Burn, and passed native
Hyprland configuration validation. The installer, archive, compatibility and
runtime suites ran **49 checks: 46 passed and three optional 0.57 binary checks
were skipped**. All **33 updater tests passed**. Coverage includes checksum
rejection, hold preservation, signed-package recovery, same-revision compositor
repair, background mismatch detection without package writes, activation gates,
settings preservation, rollback, logout cleanup and unpublished developer
revisions without a false update badge.

The GTK installer also passed an isolated Xvfb interaction run covering welcome,
downgrade review, back/forward navigation, progress, cancellation, retry and
completion. Its welcome and review screens were visually inspected. These
checks did not replace the local compositor with 0.57 or perform a remote
downgrade on the recipient PC; that downgrade runs when its user opens Setup.

The older 0.57 results below describe the retained compatibility layer. They
do not override the current release's exact compositor requirement.

## Installer retries and CPU usage — 31 October 2026

The Control Panel no longer caps compilation at two jobs. Its builder used all
32 CPUs available to this process and completed an incremental native build.
The installer prints its source revision and validates the configuration before
compilation, retaining the final validation before activation. The 27 installer
and archive checks, 10 compatibility checks, and the 22 installer checks repeated
with the real Hyprland 0.57 executable passed. Invalid configurations stopped
both installation modes before compilation and preserved the existing profile.
The `5e4cea8` source ZIP was also extracted afresh: its unmodified installer
selected `hyprland.lua`, and the resulting profile passed native 0.57 validation.

## Hyprland 0.57 fresh installation — 31 October 2026

The fresh Arch failure `unexpected symbol near '#'` came from 0.57 parsing
the legacy `.conf` entry as Lua. The installer now selects the matching entry
point and validates the actual staged Lua reader as well as its settings.
The reader reports unsupported syntax rather than discarding it.

Validation used the official Arch Hyprland 0.57.0 executable, extracted into
a temporary directory without replacing the development desktop's 0.56.2.
A clean recipient profile completed all native component builds and full
configuration validation. Native libraries were built against this workstation's
installed headers; Burn/Cube remain gated to their existing 0.56.2 ABI and were
not loaded into 0.57.

The installer/archive and compatibility checks passed (36 tests). The 30 hotkey
and desktop-settings checks passed with both compositor versions. The 25 updater
checks and 18 floating-window checks passed. Lua regression coverage includes
complete sourced settings, candidate edits, rejection without writes, escaped
commands, capture submaps and verification without running startup/reload commands.

A disposable nested 0.57 session with a real Qt Wayland window also passed
workspace switching, capture submap entry/exit, option updates, named-rule batches,
floating launch rules, focus, move, resize, tags, silent workspace moves, close and
reload. A batch containing quoted semicolons retained its command arguments.
The test used a separate home/runtime directory, excluded DRM devices and disabled
systemd/D-Bus environment updates. All 133 recorded shared/KDE hashes and both
saved KVM profile hashes remained unchanged. No VM was launched.

## Taskbar crash recovery — 28 October 2026

A live Waybar 0.15.0 crash after `SIGUSR2` reload reached the media-player
callback in `libplayerctl` and crashed while notifying a GLib dispatcher. Restoring the Waybar
process restored all three monitor bars without restarting Hyprland or effects.
Avoid module hot reloads with this build; CSS and taskbar options already update
live. For module-configuration changes, restart the owned bar process instead.

`scripts/waybar-session.py` now owns the bar. A crash triggers a fresh process;
repeated failures back off from one to thirty seconds. A private per-instance
lock prevents duplicate supervisors. Closing Hyprland's event socket or stopping
the supervisor terminates only its owned bar, with no respawn after logout.

Five real-process regression checks cover crash/restart, repeated-failure
backoff, logout with stale socket files, duplicate owners, stopping a stubborn
child without touching an unrelated process, and session closure before launch.
They use private Unix sockets and fake bars, never the live desktop.

The follow-up passed **44 session-helper checks, 22 updater checks and 17
installer checks**. The update badge is empty while current/checking and stays
visible for an available, preparing or ready update, including actionable update
failures. A live capture verified the idle button disappears. Exactly one
supervised bar mapped on each of the three monitors; all 582 protected setting
hashes remained unchanged.

## Compiz Burn — 28 October 2026

The Burn port passed the **374-check desktop suite** and **15 installer checks**.
Two additional regression cases then passed for a damaged Burn configuration and
an unavailable optional adapter: the resulting suites contain **375 desktop
checks and 16 installer checks**. The compiled engine tests compare the original
particle-update math, RGBA channels, directions, constant-speed scaling, complete
particle cleanup and valid duration/timestep boundary combinations. Python tests
compare all defaults and ranges against the extracted Compiz metadata, exercise
atomic rollback and external-edit protection, and check that controls fit.

Native tests ran in disposable nested Hyprland 0.56.2 sessions before live
activation. Captured frames were inspected for every direction, orange and custom
blue fire, Mystical Fire, smoke, 1.25× scaling and a rotated monitor. Tests also
covered Wayland and Xwayland clients, tiled and floating windows, the global
animations switch, disabling during a burn, 10000 particles, active plugin
unload/reload, dim-around bounds, display-mode changes and loader shutdown when
its compositor exits. Visual checks found and corrected both GL scissor-cache
restoration and the rotated-monitor particle transform.

All three themes render the new controls. The installed Control desk's actual
Preview Burn button opened a centered, floating **540×320** sample window; its
close animation completed and released its snapshot. The full live Hyprland
configuration validates. The audit of **582 existing protected paths** found
no KDE/shared-setting changes. The original Compiz texture was verified byte for
byte apart from the C++ array declaration (its extra string terminator is never
uploaded). A fresh source checkout contains no prebuilt native objects.

The initial package was checked on 26 October 2026 on the original Arch Linux desktop. Preparation and tests used disposable directories; the export did not replace or reload the running desktop's configuration.

## Automated checks

**175 tests passed**, including the subsequent hovered-app force-kill, grouped favorites, free tile placement and focus-dismissal fixes:

| Suite | Tests |
| --- | ---: |
| Installer | 13 |
| Control desk, hotkeys, audio and display settings | 46 |
| Application launcher, favorite groups, shortcut editing, pins and hotkeys | 59 |
| Theme, wallpaper and window controls | 14 |
| Application switcher | 2 |
| Screen-sharing picker | 10 |
| Workspace, screenshot and hovered-app force-kill helpers | 31 |

Installer coverage includes a different home directory, HDMI/eDP connectors, fractional scaling, offline automatic monitor configuration, the optional original monitor layout, disabled login animation, backup/restore, restoration after a failed activation, symlinked existing profiles, concurrent configuration edits, and asset checksums. Existing KDE settings and changes made after installing are retained in the install/restore tests.

GUI tests use Qt's offscreen backend. Tests do not log out, change live display modes, install packages, or replace the real user profile.

XWayland socket recovery follow-up: **29 session recovery/logging checks, 12 distribution checks and 33 installer checks passed**. The 13 new socket tests use disposable sockets outside the real X11 directory and cover read-only diagnosis, verified recovery, stale/wrong-process listeners, conflicting files/FIFOs/symlinks, concurrent replacement and compositor disconnect. In the affected live session, the canonical display pathname had disappeared while Hyprland's alternate listener remained alive. Its credentials matched the active compositor; the process that removed the pathname could not be established. VLC 3.0.24 opened with both automatic selection and explicit xcb in isolated settings, then opened normally through its installed desktop entry. The recovery helper was started without restarting XWayland, and the live Hyprland config verified successfully. Shared KDE/settings hashes remained unchanged.

Administrator display, file dragging, and close-button follow-up: **15 socket recovery, 7 administrator-launch, 16 shortcut, 4 close-settings, 17 hotkey, 36 theme, 11 log-guard, 5 session-logging, 2 session-UI, 33 installer, and 59 updater checks passed**. The administrator failure was reproduced even with temporary root display authorization: Linux returned EACCES when root followed the user-owned X11 symlink. A verified socket hard-link migration restored authenticated `xdpyinfo` and Taskman. Taskman opened again through the installed helper; the added root display grant disappeared when that launch exited. Its independent font-cache warning remains and did not prevent opening. These checks do not disable protected-symlink rules or grant permanent display access.

The new Files regression failed with dragging disabled before the fix, then passed across all five view modes and repeated mode switches. A real native Wayland drag sent a file containing spaces, accents, `#`, and `%` into a private Chromium upload page; the page received the exact filename and contents. Ctrl-drag copied the same file into a folder without removing its source. The disposable compositor used XWayland disabled, private files, a private browser profile, and a D-Bus daemon created with the private environment. No upload reached an external service.

The same native gesture check verified the close overlay, normal close requests that an application can refuse, accepted closes, release-to-hide, disabling, an alternate modifier, a live blue-to-red accent change, and unchanged Super-drag behavior outside the button. Native test captures were inspected. The live close plugin was activated and the live configuration verified successfully. New Files processes use the rebuilt binary; hidden Apps and Settings caches were refreshed. Workstation-specific Taskman paths were saved only in live shortcut overrides, outside the public tree. The recorded KDE and shared MIME-setting hashes remained unchanged. The developer guide documents all three changes.

Floating-header text-selection follow-up: **12 drag/cursor, 33 installer and 59 updater checks passed**. `tests/check-floating-text-drag.py` exercised actual pointer input in a disposable native Wayland compositor, with XWayland disabled and private HOME, runtime and D-Bus directories. A frameless editable address field occupied the same top strip as the automatic grip. Both named I-beam cursors and client-supplied cursor bitmaps allowed text selection without moving the window, including a held gesture leaving the text field. Empty-header dragging and Super-drag still moved the fixture. The cursor-image check uses Hyprland's existing CPU cache after SHM buffers have been released, including the pinned GL renderer's unset texture-format metadata. Unknown cursor images are not treated as permission to drag. The read-only cursor adapter and updated helper were installed in the live profile; configuration verification passed and the recorded shared KDE/MIME hashes remained unchanged. The installer builds the adapter, and updates preserve its compatible build cache.

Drive accent follow-up: the release and test builds completed, and the existing native view/screenshot check passed separately with BreakPoint and Binary Knife in private settings and private D-Bus sessions. Rendered drive cards show the bright theme accent, gradient and halo; the rebuilt Fusion Files window was also opened in the live session. The normal bar remains themed when selected; usage over 90% retains its warning color. These checks do not claim to resolve unrelated application, driver or portal failures.

Favorite-layout coverage includes migration without rewriting existing favorites, persistent group/order/size changes, four-small-to-one-medium packing, fixed columns across resizing, keyboard navigation, search, cancelled drags, and conflicting or malformed saved state. Native pointer tests in a private Xvfb display also verified tile reordering, moves between groups, dragging group headers between columns, and clicking small tiles. Dropping tiles did not launch applications. Dark and light layouts were rendered and visually checked.

The follow-up tile placement checks cover vertical stacks with empty adjacent cells, saved gaps, resizing occupied tiles, collision handling and invalid positions. A real pointer drag placed the second small tile directly below the first without filling the neighboring cell. Screenshot tests use fake capture tools to verify that Apps stays visible during selection/capture, with the guard released on success, cancellation, capture failure and clipboard failure. The notification broker cannot retain that guard.

After compacting the launcher header, the 55 launcher checks passed again. Rendered windows at 1140×723, 1140×600 and 740×480 were checked for overlapping controls, independent sidebar/tile scrolling and saved shorter heights. Existing favorite groups and positions remained unchanged.

Four focus-dismissal regressions cover an outside click during the opening delay, capture completion without a second focus event, editor protection, and returning focus before dismissal. Three reproduced failures passed after replacing the single check with a retry timer. A private Xvfb window-manager session also verified actual outside clicks and capture protection/release.

Floating-launch follow-up: **75 launcher tests passed**, including checks for Ctrl+click without changing saved launch preferences, normal clicks and keyboard activation, Ctrl+drag, centered first-launch defaults, persistent per-app sizes, current floating geometry, intentionally tall windows, ignoring tiled/maximized/fullscreen sizes, reused windows, slow launches, atomic storage, and session-bound helper cleanup. Native Wayland probes in an unopened test workspace verified default size, centered placement, manual resizing, restoration after closing/reopening and restarting the tracker, preserved full-height sizes, and reused-window placement. The probes used a temporary size store and did not change existing application windows. Temporary Xvfb tests from the earlier checks have been retired after a live XWayland socket failure; the newer checks use offscreen Qt or disposable native Wayland windows.

Startup mascot follow-up: **12 companion tests and all 13 installer tests passed**. Coverage includes saved view selection in both directions, failed atomic saves, damaged preferences, fragmented mouse reports, drag/scroll/right-click filtering, Escape handling, image cleanup, missing artwork and bounded idle motion across terminal sizes. A disposable native Wayland Kitty instance on an unopened workspace verified ASCII → PNG → ASCII through mouse reports, transparent image rendering, idle movement, resizing from 1000×1000 to 720×680, and restoring the PNG choice after closing/reopening. Native screenshots were inspected at both sizes. The check used temporary preferences and closed its own windows. The shipped mascot's checksum matches the supplied PNG byte for byte.

The PNG mascot was subsequently made static at the user's request. Its placement now changes only with the window dimensions or view selection. The 12 companion checks passed again with the motion expectations updated; animated ASCII, click switching and saved selection remain supported.

The hover-kill tests cover a pointer target different from keyboard focus, empty desktop, floating/fullscreen/special workspaces, pinned windows, rotated/scaled displays, bars/overlays, invalid process identities and a target changing before dispatch. The dry-run path cannot send a signal.

A disposable Qt window in an unopened special workspace also verified the real compositor signal path. It ignored a normal close, survived the helper's dry-run, and was removed by the force-kill helper. That check supplied a synthetic pointer over the disposable window; it did not target existing applications.

Independent Start menu styles: **339 desktop checks and 15 installer checks passed**. Coverage includes both mixed combinations, the default following the desktop, persisted choices, per-menu transparency and artwork drafts, unchanged favorite positions, transaction rollback and invalid settings. The theme illustrations and both menu layouts were rendered and inspected. Both native Qt plugins rebuilt successfully; the palette regression was also run with the compiled Qt 6 plugin to verify that its live watcher respects the menu’s process-local style in Dark, Light and High contrast modes.

Immediate search focus adds three regressions: the first keystroke reaches search in either menu style, immediate Down-arrow navigation retains focus, and showing the menu again restores search focus. These reproduced the initial sidebar focus and delayed focus theft before the fix.

## Native build and configuration validation

Two complete `--prepare` builds succeeded: one with no compositor connection, exercising the automatic display fallback, and one reading the original desktop's three connected displays. Each built these components from the copied repository source:

- Qt 5 and Qt 6 platform theme plugins.
- Waybar draggable app pins and workspace controls modules.
- Wayland screen-sharing preview helper and protocol bindings.

The staged Python and JSON files parsed successfully, shell syntax checks passed, and `Hyprland --verify-config` accepted the complete staged configuration and its included files. No source files were borrowed from the live profile for that validation.

| Build component | Version used |
| --- | --- |
| Hyprland | 0.56.2 |
| Waybar | 0.15.0 |
| Kitty | 0.49.2 |
| Hyprpaper | 0.8.4 |
| Qt 5 | 5.15.19 |
| Qt 6 | 6.12.0 |

The bundled wallpaper's SHA-256 matches the original desktop image byte for byte. Wallpaper and font checksums are recorded in [`assets-manifest.json`](../assets-manifest.json).

## Reproduce

Startup project showcase (28 October 2026): **19 startup tests and 16 installer
tests passed**. Offscreen checks cover bundled icon checksums, safe project URLs,
keyboard activation, non-overlapping one/two/three-column layouts, animation
controls and migration from the mascot console. Rendered previews were inspected
in Raw, Modern and BreakPoint, including the full desktop panel size.

A disposable Wayland compositor verified all four panels map, Super+D toggles
reuse their existing windows, hidden cubes stop animating, Escape hides the
dashboard, and a 600×500 resize reflows the gallery. A real Qt mouse click ran the
navigation helper, hid the special workspace, and passed the exact Echo page URL
to a test browser stub. Tests did not launch a browser into the working session.


Cube background motion fix (28 October 2026): **9 Cube tests and 16 installer
tests passed**. The new `tests/check-cube-sky.py` probe failed against the previous
plugin because rotating with picture motion enabled left the background pixels
unchanged. The corrected build passed pixel comparisons for pictures and
panoramas with motion on/off, independent drift, two monitors, a full turn, and
a rotated output at 1.25 scale. Unrelated monitor backgrounds stayed unchanged.
The existing nested Wayland integration also passed real Ctrl+Alt drag/release,
Escape cancellation, workspace isolation, empty faces, 3D windows, Burn
coexistence, disabling, output removal and unload/reload. Native geometry tests
check aspect preservation, bounded sampling and continuity over complete turns.
Native settings checks cover all sky modes, switches, drift, malformed JSON,
invalid types/ranges, artwork paths and bounded input. The compositor reader now
uses json-c: unloading json-glib had left registered types behind and stalled a
live plugin update. The working session was recovered without restarting it;
the revised build passed an old-to-new replacement and three further replacements
at distinct paths in a disposable compositor.

```bash
python3 tests/check-cube-sky.py /path/to/xetal-cube.so /tmp/xetal-cube-sky-check
```

This probe creates and closes its own nested compositor with Xwayland disabled;
the output directory must be new. It does not load into the working compositor.

File picker previews (28 October 2026): **390 desktop tests and 16 installer
tests passed**. A complete prepare build compiled the GTK preview module,
both Qt platform themes, the bar modules, sharing helper, Burn and Cube, and
passed full Hyprland configuration validation. The 36 theme tests also passed
with the newly compiled Qt 6 plugin, including live palette updates.

Native Qt 5 and Qt 6 probes verified automatic panes, image aspect ratio,
text selection, all dialog modes, static picker acceptance, closing during
loading and reopening without duplicate panes. A private GTK Broadway display
verified the GTK module's image/text updates, open/save/folder modes, repeated
shows and preservation of an application's existing preview. Python regressions
cover bounded text/folder reads, special-file rejection, stale background
results, destruction during loading and filenames rendered as plain text.
All three desktop designs were rendered, including the close-header integration.
The pane scrolls independently of the dialog's acceptance buttons. Coverage
limits for custom and portal dialogs are documented in [FILE-PREVIEWS.md](FILE-PREVIEWS.md).

The native preview checks are reproducible with:

```bash
python3 tests/run-file-preview-checks.py
```

They build in temporary directories and use offscreen Qt plus a private local
Broadway socket for GTK. The GTK runtime probe reports a skip if `broadwayd` is
unavailable; the module build still runs. They never use or restart Xwayland.

Desktop Cube / 3D follow-up (28 October 2026): **383 desktop checks and 16
installer checks passed**. The complete prepare build compiled both Burn and
Cube from the copied source and passed full Hyprland configuration validation.
Cube coverage includes strict option/image validation, portable artwork,
transaction rollback, external edits, controls at reduced height, and compiled
workspace isolation, face selection, geometry and window-layer calculations.
The hotkey regression verifies the narrow Ctrl+Alt mouse exception, conflict
checks, and continued protection of application keyboard shortcuts.

A disposable nested Wayland Hyprland with two outputs and real virtual pointer/
keyboard events verified repeated Ctrl+Alt drags, release-to-select, Escape,
unchanged cursor position during rotation, per-output workspace selection, and
creating an empty face without taking another monitor's workspace. Visual checks
covered custom ceiling/floor artwork, panorama and fitted-image backgrounds,
three raised windows, and a rotated output at 1.25 scale. Mode changes and output
removal cancelled the scene. Disabling, unloading while active, and reloading
were checked. Burn was loaded alongside Cube and a disposable client was closed
while the cube was visible. The nested compositor exited normally; Xwayland was
disabled in this test session.

The controls were rendered with the BreakPoint theme; Apply/Discard remain
outside the scroll area. These checks target the documented Hyprland 0.56.2
OpenGL adapter; they do not establish compatibility with other compositor ABIs
or every GPU/color-management mode.

```bash
./x_hyperinstall.sh --check
python3 -m unittest discover -s tests -v
./tests/run-desktop-tests.sh
./x_hyperinstall.sh --skip-packages --prepare /tmp/xetal-build-check
# Exercise the live Qt palette watcher with the freshly built plugin as well.
(cd config/hypr/theme && XETAL_TEST_PLUGIN_PATH=/tmp/xetal-build-check/theme/qt6 QT_QPA_PLATFORM=offscreen python3 -m unittest test_theme -v)
```

Use a new destination for each prepare run. These checks cover packaging, native compilation and automated behavior; they are not a full login test on every distribution or GPU. Fedora and Debian/Ubuntu dependency recipes are included but have not been executed here. Their package versions must still pass the same checks before installation.


Hyper Fusion updater and presentation (28 October 2026): **419 desktop checks
and 17 installer checks passed**. The 20 updater checks include real disposable
Git histories, a private session socket, a network worker with a detached child,
logout cleanup, killed-process transaction recovery, completed-journal recovery,
rollback conflict protection, settings merges, exact source verification, rate
limits and GTK badge CSS in all nine palette combinations.

A disposable recipient profile completed source preparation, native builds, full
Hyprland configuration validation, login activation and rollback. Personal theme
choices, hotkeys, an unmanaged file and a separate KDE guard remained intact.
The live profile received only the reviewed updater files and taskbar integration,
with a backup and complete config validation before reload. README screenshots
were captured from real widgets in a temporary copy of the profile; the file
progress card uses a sample job. No tests close the user's real applications.


## KVM captured baseline and binary updates — 2026-10-30

- Compared both captured profiles against the master's current vmstart_2 sessions, allowing relocated paths and first-run metadata. Included SMBIOS/template, 12 AML tables, two GPU ROMs, Windows/Mac NVRAM and public TPM identity properties. A fresh offline install resolved all managed runtime paths, verified asset hashes, and opened the configured Mac boot image.
- Seventeen focused package, boot-edit, activity and setup checks passed. Eleven publisher/server checks passed, including a real localhost HTTP round trip and rejection of signed source inventories. OpenCore draft restoration preserved boot-image and NVRAM hashes.
- The broader backend checks passed 140 cases initially; two wizard-progress assertions were updated for the Downloads step and passed on rerun. One existing upstream narrow-window test still expects 1100 pixels although the toolbar has a 1153-pixel minimum; the same failure was reproduced from the preceding commit.
- On Hyprland, the main KVM window maximized, a child dialog remained 307×150, restore returned to 1720×1000, and close saved immediately without a confirmation. Full config verification passed, and all 133 recorded protected settings remained unchanged.
- Published binary-only release 1.0.4, verified its signed public feed, and downloaded/installed OVMF from the public server into a disposable directory. No live guest boot, GPU handoff, kernel-module load or bootloader change was performed during these checks.

## KVM launch audit, bridge setup and terminal emblem — 2026-10-30

- **445 backend checks passed** across Single, Virtual and Dual GPU configuration, lifecycle, disks, passthrough validation, Windows/Mac profiles, OpenCore, memory and firmware handling. The initial run passed 444 and skipped the firmware/display combination; rerunning that case with the matching downloaded OVMF passed too. Disposable diskless QEMU guests used software emulation and localhost sockets, including a verified 1600×900 UEFI display, clean viewer disconnect and immediate restart.
- **30 setup and bridge checks passed**, covering missing-bridge NAT fallback, bridge selection, running-guest guards and failed NetworkManager transaction rollback. Generated bridge/port profiles also passed real libNM validation; a read-only system-bus check recognized the workstation's existing bridge. The host network was not reconfigured.
- The SMBIOS row buttons were measured and clicked in eight design/light-dark combinations. Each changed only its selected guest field, with the original template value preserved. Existing navigation tests were corrected for the toolbar-only wizard and the actual toolbar minimum width.
- **18 installer checks and three terminal checks passed**. The theme-colored Arch SVG rendered through Qt SVG and was inspected in a real Kitty window using scrolling Unicode image placements. ASCII and narrow-terminal fallbacks remain available.
- Generated Single GPU shell scripts were executed against inert hooks and disposable process/sysfs fixtures for success, failed preparation, failed QEMU, termination and restoration of an unbound AMD device. No physical GPU was detached, no real guest disk was opened, and no kernel module, bootloader or host network settings were changed by these tests. Physical handoff and guest operating-system startup still require testing on the target PC.

## Fusion Files — 2026-11-01

Fusion Files and Control Panel compiled successfully with the shared volume
command helper. The native file manager suite passed 11 checks in a private
D-Bus session with disposable files, configuration and Trash. Coverage includes
F2 rename, copy and cut/paste, Trash and undo, cancelling overwrite and permanent
deletion, literal paths, address-bar navigation, tabs, view and column settings,
private bookmarks, and mount arguments exercised against mock executables.
LUKS and BitLocker volumes remain visible without offering direct mount.

All 33 installer checks and 59 updater checks passed. The launcher suite passed
120 checks initially; its two favorite-default expectations were updated for
My Computer and passed on rerun. Ten desktop-menu and seven screenshot-action
checks passed. Native Qt 5, Qt 6 and GTK preview probes still passed after the
shared preview pane gained a generic parent-widget constructor. Appearance
checks cover every Fusion design in dark, light and high contrast.

The broader root suite ran 188 checks with three skips and one existing failure:
the legacy Hyprland 0.57 Lua converter rejects the packaged `layerrule` setting.
The same error was reproduced using the unchanged baseline configuration; this
does not affect the pinned 0.56.2 configuration or the file manager checks.

The local development preview opened on Hyprland with the active BreakPoint
palette and discovered mounted and unmounted volumes. Both desktop entries
passed validation, and My Computer was added without replacing existing
favorites. No real volume was mounted, unmounted or repaired during validation;
live network-share authentication and file operations remain untested. Fedora
and Debian package recipes were reviewed but not installed on those systems.

The This PC follow-up passed **16 native checks** plus all design/palette
combinations. Mounted internal partitions group by their physical disk; mounted
and unmounted USB volumes occupy the middle section, including USB SSDs with
`RM=0`. Checks cover sidebar placement, divider dragging and persistence,
selection and scrolling during refresh, mount-state transitions, drive properties
and Alt+Enter. Property figures distinguish used, available and filesystem-reserved
space, and unmounted/disconnected volumes never report fabricated free space.

Real copy and cut/paste jobs into disposable directories were initiated from the
This PC USB cards and the drive context menu. Stale/unmounted targets rejected
paste. The file menu displayed a private fixture's default application name,
Open with, Cut, Copy and Paste. Ark's installed plugin supplied the archive
options and created a ZIP through its menu action; Python read back the archive
and verified its contents. These checks use a private D-Bus session and desktop
configuration; they do not mount or alter physical drives. The updated local
preview and penguin artwork were installed with a private backup.

The compact properties/sidebar follow-up passed **18 native checks**, the
**33 installer checks**, all design/palette appearance combinations and both
session UI routing checks. New interaction coverage reopens windows after
collapsing sidebar sections, disconnects/reconnects the drive inventory, and
clicks System Cleaner against a private command fixture to verify the exact
Control Panel section arguments. Copy/cut/paste, Ark archive creation and the
existing drive interactions remain covered by the same native run.

The updated dialog was inspected on the live desktop at 560 × 624 pixels with
the active theme. The System Cleaner route opened the correct Control Panel
page without running a scan or cleanup. The live Hyprland configuration passed
validation and reloaded without errors; the active Super+E binding points at
`scripts/files.sh` and the directory MIME default reports `xetal-files.desktop`.
The installer checks verify that fresh profiles retain these defaults and the
file-manager service entry. Development backups and screenshots stay outside
the repository.

The tab strip also suppresses Qt's document-mode baseline, which drew a stray
line at a different height beneath the new-tab corner button. The targeted
native view check passed and its current-theme capture shows a clean tab edge.
