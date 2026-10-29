# Validation

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
