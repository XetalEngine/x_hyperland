# AI theme creation — Hyper Fusion

Read this before adding or extending a Hyper Fusion theme, even if you have no
conversation context. A complete theme is a coordinated desktop design, not
just a palette or a mockup. **Every new theme must include three distinct,
finished wallpapers.** Keep this document current when the architecture changes.

## Start in the correct tree

- The distributable source is `config/hypr/` inside this repository. The installed
  profile is normally `~/.config/hypr/`. Editing one does not update the other.
- Read applicable `AGENTS.md` files and the repository's `IA_START_HERE.html`.
  Inspect `git status` and preserve unrelated edits. Work as the desktop user.
- Read a recent complete design, such as `theme/midnighttransit.py` and
  `theme/MIDNIGHT_TRANSIT.md`. Search for its stable ID across the profile; several
  consumers have separate catalogs. Do not blindly replace every occurrence.
- Choose a permanent lowercase ID (for example `midnighttransit`) and one display
  name. Saved presets use IDs. Never rename existing IDs or reorder numeric
  native effect IDs to insert a new theme.
- Adding a design must not select it, reset the user's choices, change monitor
  layout, or replace startup settings. Provide it through the existing chooser.
- Keep KDE/Plasma, shared GTK/Qt settings, GSettings, shell profiles and login
  manager configuration untouched. All styles and helper processes belong to
  this Hyprland profile. Never use broad `pkill`/`killall` to refresh it.

All paths in the following sections are relative to `config/hypr/`, unless a
path explicitly starts with `tools/`, `tests/`, or another repository root file.

## Design the entire visual language

Define materials, shape, borders, typography, accent, selection, hover, focus,
disabled controls, destructive actions and animations. Follow the user's concept
without copying screenshot text or painting a fake UI over the wallpaper.
Use existing semantic palette roles rather than scattered hardcoded colors.

| Surface | Files and responsibilities |
| --- | --- |
| Catalog and modes | `theme/designs.py`: names, descriptions, defaults and style dispatch. `theme/palettes.json`: complete **dark, light and contrast** palettes. Use the same role set as existing designs; keep readable text and selection contrast. |
| Qt controls and dialogs | New `theme/<id>.py`: reusable material painters plus Qt, Waybar and notification styles. Style buttons, inputs, menus, combo popups, checkboxes, tabs, trees, tables, sliders, progress, tooltips, disabled/focused states and `QMessageBox`. Avoid transparent dialogs with unreadable text. |
| Window chrome and typography | `theme/window_chrome.py`, `theme/runtime.py`, `theme/platformtheme.cpp`, `theme/layouts.py`. Cover title bars and close/minimize/maximize buttons. A font change in the native platform plugin requires rebuilding **Qt 5 and Qt 6** integrations. Use bundled/licensed fonts. |
| Settings and presets | `theme/page.py`, `theme/gallery.py`, `theme/design_preview.py`, `theme/identity.py`, `theme/presets.py`. Register labels, search/story text, material painting and genuine previews. Keep selected components independent and preserve external-edit detection and rollback. |
| Launcher | `theme/launcher_surfaces.py`, `launcher/app.py`, the preview and identity painters. Cover main surface, groups, tiles, sidebar, search/results, selection, hover, backgrounds and opacity controls. Wallpaper backgrounds and custom account pictures must still work. |
| Taskbar | `theme/bar_styles.py`, theme assets and the design's GTK CSS. Cover **Full, Partial and Centered** variants, horizontal and vertical placements, workspace states, app pins, tooltips and context menus. Preserve module commands, user order, Stash help, audio/network controls and update status. |
| Notifications | `theme/designs.py` notification dispatch and the design's `notification_style()`, consumed by `theme/backend.py` into `swaync/style.css`. Test popup and control center, media controls, actions, DND, clear and empty state. The center needs its own readable background; do not rely on the wallpaper being dark. |
| Fusion Files and file pickers | `file_manager/appearance.py` plus the design's `files_style()`. Cover toolbar, Places/file tree, This PC drive cards, selection, tabs, breadcrumbs, filters, context menus, previews, status and Open/Save actions. Keep the left navigation available in every instance, including application pickers. Theme code must not alter navigation or drag/drop behavior. |
| Control Panel | `control_panel/bridge.py`: register custom material/shape overrides. Confirm real cards, tables and dialogs inherit the theme. |
| File transfers | `file_jobs/preferences.py`, `file_jobs/window.py`, `file_jobs/artwork.py`: register style, animation handler, surface and track geometry. Provide an original transfer illustration and satisfy **Transfer animations must loop seamlessly** below. Exercise copy/move/archive/extract, pause, cancellation, errors and completion; labels, buttons and progress must remain legible at compact sizes. |
| Minimize container | `effects/minimize/model.py`, `native/settings.hpp`, `native/dock_shader.hpp`, `artwork.py`. Add a distinct tray and slot material, **append** a native ID, and match the Qt preview to actual shader rendering. Preserve hover, restore, auto-hide/burn-away, monitor edges, overflow/scroll, independent style selection and palette following. Building a pretty preview alone is not sufficient. |
| Other desktop effects | `theme/backend.py`, `theme/effect_colors.py`, `switcher/` and existing effect preferences. Check compositor border/rounding/shadow, task switcher, Burn/Cube/Wobbly color following and reduced-motion choices. Do not reset effect enable switches, personal timing or hardware options. |
| Terminal and lock screen | Existing backend generates Kitty palette, lock-screen and startup styles. Verify them with the new palette, including selection and muted text. Do not replace the user's shell or terminal content. |
| Greeter and GRUB | `login/model.py`, `control_panel/grub_appearance.py`: register the display name and palette. Their editors should offer the new design and three wallpapers. Adding a theme does **not** authorize installing a greeter or rewriting `/etc/default/grub`. |

## Transfer animations must loop seamlessly

**A visible reset, backward jump, disappearing group or pause at the loop boundary
is a bug. Do not mark a theme complete until its animation passes these checks.**
A still screenshot cannot establish that an animation works.

`file_jobs/window.py` → `ProgressWindow.tick()` supplies a repeating **0–1 phase**
to the artwork renderer. It is a complete cycle, not elapsed seconds. The previous
HyperFusion Blue, Midnight Transit and Blackwood bug used `phase * .18` or
`phase * .22` for travel. When the clock wrapped, the objects jumped back after
covering only 18–22% of their route. **Do not copy that pattern.**

- Make each item complete its route using `(phase + index / count) % 1`.
  Fade the item **and its trail/glow** to invisible before it wraps from the
  destination back to the source, then fade it in. Do not teleport a visible item.
- Keep the existing animation-speed control. Do not slow a scene by multiplying
  the already wrapped phase by a fractional speed. If different timing is needed,
  implement a complete cycle at the clock level and test its wrap explicitly.
- Make secondary motion periodic too: water, bobbing, wheels, lights, particles
  and trails must match at phase 0 and phase 1. For a repeating oscillation use
  `sin(phase * math.tau + offset)` (or an integer number of full turns), not
  `sin(phase)` or `sin(phase * 1.7)`. Moving items also have their own wrap points;
  hiding only the overall cycle boundary is insufficient.
- Preserve pause/resume, hidden-window timer suspension, disabled animation and
  completion/error behavior. Resuming an existing job must not reset its scene
  to the beginning. Do not change file-operation behavior to fix artwork.

Required verification for **every new or changed transfer scene**:

1. Add its stable ID to **every applicable style list** in
   `file_jobs/test_artwork.py`; the current tests name their covered styles
   explicitly. Passing tests that never render the new style does not count.
   Compare rendered frames immediately before/after the 1→0 boundary and each
   individual item's wrap. Also verify that the scene keeps moving throughout
   the cycle, so a frozen image cannot pass as a seamless animation.
2. Run this focused regression from the repository root, then the full
   `file_jobs` suite listed below:

   ```bash
   QT_QPA_PLATFORM=offscreen QT_QPA_PLATFORMTHEME= QT_PLUGIN_PATH= python3 -m unittest discover -s config/hypr/file_jobs -p 'test_artwork.py'
   ```

3. Watch **at least three complete loops** in the Settings preview and a transfer
   window. Check normal, slow and fast animation speeds; densities 1, 3 and 7;
   forward and extraction travel; trails on/off; and dark, light and contrast
   modes. Inspect the departure/arrival points and secondary motion as well as
   the middle of the route. Record what was actually inspected; do not substitute
   one rendered frame or a source-code assertion for motion verification.

## Three wallpapers, every time

1. Create **three different, finished wide compositions** that share the theme's
   mood. A crop, recolor, duplicate or empty placeholder does not count.
2. Put them in `wallpaper/<id>/` with stable descriptive filenames. Keep artwork
   free of fake windows, taskbars, captions and baked-in desktop icons. Leave room
   for real desktop content. Inspect all three at full size before shipping.
3. Add all three relative paths, in intentional display order, to
   `wallpaper/sets.json`; add the name to `wallpaper/library.py`. Confirm gallery
   thumbnails, one-monitor selection and three-monitor assignment. Existing
   custom wallpapers and per-theme saved selections must survive switching.
4. Record title, provenance, actual dimensions and exact generation prompts (if
   generated) in `wallpaper/<id>/prompts.json` or a nearby README. Use the available
   image-generation skill for original bitmap artwork; use code/SVG for native
   vector assets. Do not claim a resolution the output does not have.
5. Include asset hashes in `assets-manifest.json` where applicable. Keep originals
   and licenses needed to reproduce/distribute the theme, not caches or personal
   photographs. No asset may depend on an absolute path to the author's Desktop.

When the user requests more wallpapers for an existing theme, append them to
that theme's catalog. Preserve the original first three: these remain the
default monitor set. Additional images are selectable individually and saved
per monitor. The preset reveal uses two columns for up to six wallpapers and
three for nine, widening on hover/focus to keep the thumbnails readable;
verify every thumbnail is visible and existing selections survive switching.

## Icons are a complete pack

- Extend `icon_themes/art.py` (`STYLES`, descriptions and SVG dispatch), using a
  dedicated renderer when the theme needs its own silhouettes and materials.
  Render every `CATALOG` entry and alias: folders, Home, Computer, Trash, devices,
  application categories, file types and actions. Inspect both small and large
  sizes. Do not use one identical generic icon for everything.
- Keep the three application identities unmistakable at launcher size:
  **Control Panel** (`xetal-control-panel`) uses a gear, **Fusion Settings**
  (`xetal-fusion-settings`) uses sliders, and **KVM** (`xetal-kvm-settings`)
  uses a CPU/chip with visible pins, never a computer/monitor. Check all three
  with both built-in packs and **Use Other Icons → Papirus-Dark/Light**.
  Use `theme/icons.py`'s `fusion-settings` and `chip` helpers when a selected
  external pack lacks our app icons: they draw distinct symbols in the theme's
  accent color. Preserve explicit individual icon overrides. Do not make Fusion
  Settings fall back to Control Panel's icon or KVM fall back to `computer`.
- Generate and ship `icon_themes/packs/Xetal-System-<id>/index.theme` and all its
  `scalable/*.svg` files. From repository root:

  ```bash
  PYTHONPATH=config/hypr python3 -m icon_themes.art
  ```

- `icon_themes/model.py` builds profile-local overlays and fallbacks. If changing
  existing artwork, review `art.VERSION` so cached overlays cannot retain stale
  assets. Preserve user overrides and Other Icons choices.
- Icon lookups and editor refreshes must stay read-only. Prepare overlays during
  installation/startup or an explicit Apply, never from `info()` or a file-watch
  callback. After adding a theme, older resident applications still have the
  previous catalog in memory; rebuilding on reads makes old and new processes
  repeatedly overwrite `theme/icons.json` and freeze interfaces with refreshes.
  Keep the old/new catalog regression tests in `icon_themes/test_icons.py`.
- Live theme watchers must coalesce saves, handle atomic and in-place writes,
  and ignore unrelated build files or unchanged settings. Never reassign an
  identical Qt stylesheet: that repolishes every widget, including hidden
  Settings pages. Keep `theme/test_live_refresh.py` and the live menu palette
  tests passing when extending the watched theme inputs.
- Fresh installs keep **Use Other Icons → Papirus-Dark**. The **Icons** checkbox
  in Apply preset stays **unchecked by default**. A user can opt into the new
  original icon pack without changing that policy.
- `theme/icons.json` can acquire a generated `resolved` cache during tests.
  Do not commit local cache paths or replace the portable defaults with it.

## Cursor artwork and pointer effects

- Add original artwork to `cursors/art.py` for a new family: normal pointer,
  links, text/I-beam, move, all resize directions, crosshair, busy animation,
  help, unavailable, drag-copy/move/link and every existing alias. Check hotspot
  coordinates, contrast, small sizes and animation frames.
- Update the native style allowlist in `effects/cube/native/cursors.hpp` for a
  new family. Otherwise the UI can offer a cursor that the compositor rejects.
  Build both Hyprcursor and XCursor formats with `cursors/build.py`.
- Set the builtin preset's artwork and accent in `theme/presets.py`. Preserve
  cursor size, trail duration/intensity and optional click feedback. Reusing a
  colored general glow/sparkle is supported. Use an explicit general trail if
  there is no dedicated native trail; `follow` falls back for unregistered IDs.
- A genuinely new trail also requires `cursors/effects.py`, native Cube mouse-art
  resolution/rendering and matching previews/tests. Do not register a name alone.
- `cursors/build.py --register` registers only uniquely named `Xetal-Cursor-*`
  links. Never change another desktop's cursor selection or system directories.
- Rebuild and activate the Cube adapter when its source changes; Python source
  and generated cursor assets cannot update a library already loaded in memory.

## Sounds

Register `sounds/model.py` and add an original score/voice to the repository's
`tools/generate_sound_packs.py`. Generate the pack by ID and include its catalog
metadata plus all eight cues (startup, shutdown, error, warning, information,
question, success and notification). Use bounded volume, short duration, fades and no abrupt
clipping. Existing event enable switches, volume and selected sound pack must be
preserved unless the user selects Sounds in Apply preset.

## Builds and verification

From repository root, with the project's documented dependencies installed:

```bash
python3 config/hypr/theme/build.py
python3 config/hypr/cursors/build.py
python3 config/hypr/effects/cube/build.py
python3 config/hypr/effects/minimize/build.py
python3 tools/generate_sound_packs.py YOUR_THEME_ID
```

Only rebuild affected native components. Do not bypass the pinned compositor
ABI checks. Build outputs and runtime caches are ignored files, not distributable
source. Setup builds them for the recipient's installed libraries.

Run the relevant existing suites, with headless Qt selected **for that process**:

```bash
QT_QPA_PLATFORM=offscreen QT_QPA_PLATFORMTHEME= QT_PLUGIN_PATH= python3 -m unittest discover -s config/hypr/theme
QT_QPA_PLATFORM=offscreen QT_QPA_PLATFORMTHEME= QT_PLUGIN_PATH= python3 -m unittest discover -s config/hypr/icon_themes
QT_QPA_PLATFORM=offscreen QT_QPA_PLATFORMTHEME= QT_PLUGIN_PATH= python3 -m unittest discover -s config/hypr/cursors
QT_QPA_PLATFORM=offscreen QT_QPA_PLATFORMTHEME= QT_PLUGIN_PATH= python3 -m unittest discover -s config/hypr/file_jobs
QT_QPA_PLATFORM=offscreen QT_QPA_PLATFORMTHEME= QT_PLUGIN_PATH= python3 -m unittest discover -s config/hypr/effects/minimize
python3 -m unittest discover -s config/hypr/sounds
```

Inspect actual Qt screenshots in **dark, light and high contrast**: menus,
dialogs, focus/disabled controls, Files and picker tree, transfer card and dock
preview. Parse actual Waybar/SwayNC CSS with GTK; stylesheet text tests cannot
catch every runtime parser failure. Inspect the three wallpapers and SVG packs.
Check native Files and Control Panel header buttons separately from Python
dialogs: `theme/window_chrome.hpp` gives native controls a local transparent
background. A global dark close-button glyph intended for a bright background
can become invisible there. Verify normal, hover and disabled contrast on the
actual native header rather than relying on the Python preview.

Native dock or cursor changes also need a **disposable nested compositor** on
the supported Hyprland version. Existing entry points:

```bash
python3 tests/check-minimize.py /absolute/new/xetal-minimize.so /tmp/unique-minimize-test
python3 tests/check-wobbly.py /absolute/xetal-wobbly.so /tmp/unique-cursor-test --cursors-only
```

These tests use their own profiles and restore/close their own windows. The
second checks native cursor loading, glow rendering, idle suspension and effect
coexistence. Omit `--cursors-only` for the complete Wobbly/trails suite. Test
directories must not already exist. Record failures and actual verification
limits; do not call an offscreen preview a live desktop test.

## Install and ship without disturbing personal settings

1. Back up changed live files and record hashes of shared KDE/GTK/Qt settings.
   Copy only reviewed source/assets into the live profile when installation is
   within the request. Preserve all settings JSON/conf files, user presets,
   wallpaper selections, icon choices, autostart and keybindings.
2. Build or copy matching content-addressed native outputs to the live profile.
   Use atomic replacement for Qt integration libraries; never truncate a mapped
   `.so`. Keep old native outputs available for recovery.
3. Validate the **complete** live config with
   `Hyprland --verify-config --config ~/.config/hypr/hyprland.conf` before reload.
   Use scoped component controllers and session state. Restore minimized windows
   before changing their plugin; never unload a plugin by guessing its path.
   Reopen Settings to discover new catalogs. Applications that cache Qt styles
   may need reopening. Do not forcibly close the user's applications.
4. Compare shared-setting hashes afterward and check that current theme, icons,
   cursors, sounds and effect preferences are unchanged. Installing a design and
   applying that design are separate operations.
5. If an ISO update is requested, update the bundled source/assets in both
   **online and offline** profiles, rebuild both through their documented
   pipeline, and inspect the resulting images. Editing this checkout does not
   retroactively change an existing ISO. Keep the offline package set frozen
   unless dependency changes are part of the request.
6. Add a short theme guide, genuine preview and README entry; report what was
   changed, tested and installed. Commit/push or publish only within the task's
   authorization. Do not silently include local caches or unrelated work.

## Completion checklist

- [ ] Stable ID registered in every relevant catalog and all three palette modes.
- [ ] Original materials for launcher, taskbar, windows, controls and notifications.
- [ ] Fusion Files, every file picker, desktop menus and transfer window covered.
      Keep both the navigation tree and enabled preview pane usable after
      restoring old splitter layouts; neither may collapse to an unreachable sliver.
- [ ] Transfer animation watched for at least three complete loops with no visible
      resets; the new style is included in rendered-frame boundary tests, and
      both focused animation and full File Transfer tests pass.
- [ ] Distinct minimize container implemented in both native shader and preview.
- [ ] Complete icons and cursor assets, including aliases, hotspots and busy shapes.
- [ ] Pointer effects, terminal, lock screen, other effects, greeter/GRUB previews checked.
- [ ] Eight matching sounds with valid metadata and preserved user preferences.
- [ ] **Exactly three distinct finished wallpapers**, registered and visually inspected.
- [ ] Selective Apply preset behavior intact; Icons still unchecked by default.
- [ ] Native builds, relevant regressions and real rendering checks pass.
- [ ] Source/live installation distinction, backups and remaining limitations reported.
