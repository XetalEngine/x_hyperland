# Xetal / Hyprland

The complete Xetal desktop: our application menu, Control desk, themes, animated startup, workspace bar, screen-sharing picker, and the original wallpaper. All custom components are included as source and built on the computer where you install them.

![Included Xetal wallpaper](config/hypr/wallpaper/images/85547d33a30386a6b954d3a9.png)

## Install

Use a recent Hyprland installation, open a terminal **as your regular desktop user**, and run:

```bash
git clone https://github.com/XetalEngine/x_hyperland.git
cd x_hyperland
./x_hyperinstall.sh
```

The installer checks dependencies, offers the appropriate distribution packages, builds all native components, and validates the complete configuration. It then asks to install the prepared desktop and backs up your existing `~/.config/hypr` before replacing it. **Log out and select Hyprland again** to start the complete desktop, including the portal picker.

Current requirements: **Hyprland 0.56+, Waybar 0.15+, Kitty 0.49+, Hyprpaper 0.8+, Python 3.11+**, Qt 5/6 development headers, and the Hyprland desktop portal. These minimums preserve the actual features in this desktop, including Kitty's draggable scrollbar and the native workspace taskbar. Older distribution packages need upgrading first; the installer stops before replacing your configuration if requirements are unmet.

Arch/CachyOS is the tested build environment. Package recipes are also provided for Fedora and Debian/Ubuntu; their installed versions still have to pass the same checks. Other distributions can install the [listed dependencies](docs/DEPENDENCIES.md) and use `--skip-packages`. Distribution recipes outside Arch have not been execution-tested here.

## The whole desktop

| Component | Included behavior |
| --- | --- |
| Apps menu | Resizable menu, search and categories, draggable favorite groups, medium/icon-only small tiles, custom icons/commands, terminal options, duplicate shortcuts, floating launch, and hotkey badges/editing. |
| Top bar | Per-display workspaces, every app's icon, + to add a workspace, red × to remove an empty one, draggable pinned apps, media controls, device/status indicators and tray. Right-click → Options to show or hide items. |
| Control desk | Hotkeys, Audio, Network, Bluetooth, Displays, Input, Theme, Calendar and System tabs, with visible close controls. |
| Hotkeys | Capture/edit shortcuts, searchable categories, pending-change log, Apply/Discard, remove confirmation, validation, history and rollback. |
| Audio | Output/microphone controls and an embedded mixer with horizontally scrolling columns for each app, playback/recording, mute and routing. |
| Displays | Drag monitor rectangles; configure resolution, refresh, scaling, rotation and mirroring with timed Keep/Revert protection. |
| Theme | Xetal Raw, Xetal Modern and BreakPoint, each with Dark, Light and High contrast colors. Live Qt 5/6 palettes, matching bar and notifications, window effects and per-monitor wallpapers. |
| Wallpaper | The exact included image, monitor previews, individual assignments, fit modes, and image-picker previews/file properties. |
| Startup | Five-second login delay, then the staggered Fastfetch, Matrix, clock and Xetal companion consoles. Click the companion to switch between animated ASCII and the static original PNG mascot; your choice survives login. |
| App switcher | Super+Tab across all monitors/workspaces; release Super to focus the selected app on its original monitor. |
| Dolphin | Separate themed profile, Places icons, image wallpaper action, and folder-link handling. |
| Xetal Images | Default image viewer with mouse-wheel zoom, drag to pan, folder navigation, animated GIFs, and centered floating windows with size memory for each resolution and scale. |
| Kitty | Animated cursor, themed colors and an interactive scrollback scrollbar. |
| Screenshots | Area/all-display capture, clipboard copy, clickable notifications and Open containing folder with the image selected. |
| Screen sharing | Custom Hyprland portal picker with updating monitor/window previews and region selection. |
| Session | Matching lock screen, notifications and session-owned helpers. |

## Your hardware and existing desktop

The default install uses **your current monitor names, positions, resolutions and scaling**. Outside a running Hyprland session, it uses preferred modes and automatic placement. The startup scene uses the second display when available, and fits a single-display setup too. Click the companion artwork or press Space in its console to switch views. Network adapters and temperature sensors are detected at runtime.

The complete original three-monitor configuration is retained in [`profiles/xetal-original`](profiles/xetal-original). Use `--profile original` only for the original DP-4/DP-5/DP-6 arrangement and supported modes. You can otherwise arrange screens through Control desk → Displays.

Installation is scoped to `~/.config/hypr` and private backups under `~/.local/state/xetal-hyprland`. It preserves shared KDE/Plasma settings, shell profiles, application associations outside this session, and system autostart. It does not restart portal/audio services, close your applications, or change your login manager. Package installation uses your distribution's package manager and its normal administrator permissions.

Right-click the wallpaper for the desktop context menu. **Control desk → Context Menu** provides a visual editor for shortcuts, submenus, dividers, spacers, columns, icons, global hotkeys and appearance, with Apply/Discard and JSON presets.

Choose **Control desk → Theme → Design** to switch between **Xetal Raw**, the original cyan desktop, and **Xetal Modern**, with soft blue accents, rounded cards, an icon rail and a Home overview. Choose a design and color mode, then **Apply theme**. Modern is the included default; Raw remains available at any time. The themes share the same engine, hotkeys, favorite groups, tile positions and workspace behavior.

**BreakPoint** adds charcoal glass, silver text and crimson focus accents, with Inter interface text and JetBrains Mono terminals and technical labels. Its Dark palette uses `#090A0E`, `#12141B`, `#1B1E27`, `#E53945`, `#E6E8EF` and `#9298A8`. It keeps your launcher groups, tile sizes, app icons and shortcuts, and includes matching bar, notifications, context menus, controls and lock screen colors. Defaults use 12px corners, 8px gaps, 2px focused borders, subtle blur and 150–180ms transitions; saved Window effects continue to take precedence. The bundled fonts stay inside this Hyprland profile.

In **Theme → Wallpapers**, **BreakPoint set** previews three new crimson workstation wallpapers across connected displays from left to right; choose **Apply wallpaper** to keep them. Original artwork is unchanged. The new images and their generation prompts are in [`wallpaper/breakpoint`](config/hypr/wallpaper/breakpoint). Wallpaper selection stays independent of theme selection.

**Start menu style** lets you mix any of the three Apps menus with any desktop theme: use the Raw menu on Modern, or the BreakPoint menu on Raw, for example. **Follow desktop theme** keeps them matched and is the default. Choose the menu style, then **Apply theme**; it remembers your choice across logins and desktop theme changes. The previews show the combination, and **Apps tiles & groups** edits the selected menu style’s transparency and artwork. The menu keeps its own styling while sharing the desktop’s Dark, Light or High contrast mode. Apps launched from it keep the desktop theme.

**Design → Shortcut labels** has global **Show shortcut names** and **Show hotkeys** switches. They follow you across all menu styles. Hiding labels centers the remaining tile content without changing the tile size, favorite positions, tooltips or shortcuts; small tiles remain icon-only. **Apps background → Background visibility** controls how strongly the chosen image appears, from 0% to its full colors at 100%, with matching previews. Choose **Apply theme** to save. Design edits merge with unrelated changes from another window; conflicting choices stay as a draft until you choose which values to keep.

Apps indexes launch hotkeys once per configuration change and reuses those lookups while open. The first page appears without a second tile fade, and clicking Apps to close an existing menu sends a direct local message instead of loading another Qt process. The binding inspector keeps **Duplicate** and **Remove** in a fixed footer while its fields scroll on smaller windows.

Opening Apps, including clicking the bar button, puts the keyboard straight into search. The bar hands focus to the newly mapped menu once, and an outside click cancels any pending activation. Start typing immediately, or press Down to navigate the results; opening the menu does not later pull focus back from your selected tile.

In **Design → Apps tiles & groups**, adjust **Icon backgrounds** and **Group strips** from 0% (transparent) to 100% (opaque). Each design remembers its own settings. Choose an image or animated GIF for the group strips; the illustrations and sample menu preview your changes before **Apply theme**. **Remove image** returns to a plain strip, and **Reset surfaces** restores that design’s original surface settings. Icons, labels and selection outlines remain readable at every opacity. Strip art is copied into the private profile; GIF animation and timing are preserved, shared across the visible strips, and paused while Apps is hidden.

All three designs show your account image or a selected image/GIF in Apps. **Use account picture** resets that avatar to your Linux account photo, with the bundled Xetal image as a fallback; it does not change your account settings. In **Theme → Design → Apps background**, use **Choose image…** for a separate menu background, or **Use desktop wallpaper** to follow the current monitor. Clear **Show background image** for the plain theme background, then **Apply theme**. Custom backgrounds are saved as private PNG copies inside this profile, so moving the original does not break them. These choices stay separate from the avatar and desktop wallpapers and persist across logins and design changes. Clicking the Apps bar button again closes the menu. Click the Modern account picture to open Home on a Modern desktop; otherwise the account picture opens Theme settings. Home provides player controls, the clock, resource usage and links to the existing settings pages. The bar, notifications, desktop context menu, floating tools, startup terminal colors and lock screen follow the desktop design; Apps uses **Start menu style**. Explicit Window effects settings continue to override design defaults. Qt applications using system colors pick up the selected palette; applications with their own themes keep those choices, and older open applications may need reopening. The settings stay inside this Hyprland profile.

The Modern layout takes visual inspiration from [Noctalia](https://github.com/noctalia-dev/noctalia); it uses our existing Xetal implementation and does not install or replace the shell with Noctalia.

The bundled Fira Code Nerd Font is loaded by this session's font configuration. Papirus and Noto are installed as dependencies. Your existing shell and prompt stay available in Kitty.

Favorites retain the original desktop-entry IDs and include portable terminal, file manager and browser entries. Apps appear when installed. **Separate programs such as Echo, XMusic, CachyOS Tools, Linux Studio, Discord and GitHub Desktop are not bundled application binaries or separate source repositories.** This repo contains the entire Hyprland desktop and its custom tools; you install your applications separately. Launch preferences, pinning and app hotkeys work with any installed application.

In Apps → Favorites, use **+ New group**, then drag tiles between groups or drag a group title to move it. Double-click a title to rename it. Right-click a tile → **Tile size** selects Medium (icon, name and hotkey) or Small (icon only); four small tiles fit one medium slot. Drop small tiles directly above, below or beside one another; empty cells stay empty until you use them. Each column is three medium tiles wide. Widening the menu reveals additional columns; shrinking hides them without rearranging your layout. Group names, positions, columns and sizes save automatically. Right-click empty space for **New shortcut**. Print and Shift+Print keep the menu visible during screenshot capture.

The compact header puts the page title, **New group** and **New shortcut** above the slim search field. Drag the bottom edge or corner to shorten the menu, down to 480 pixels high; tiles and sidebar navigation scroll independently when needed. Your window size is remembered.

**Ctrl+click** an app in Favorites, categories or search results to launch it floating for that launch. Normal clicks keep the shortcut's saved preference, and Ctrl+drag still reorders favorites.

Floating launches open centered, using the app's default size the first time and its last floating size afterwards. Resize a floating window once to remember that size across launches and logins. Tiling, maximizing and fullscreen do not replace the remembered floating size; deliberately tall floating windows retain their size. Size memory is local to this desktop profile, with separate preferences for app and terminal launches.

Floating launches also follow child processes through script, sudo and AppImage wrappers. Password prompts stay separate from the application's size preference. For a graphical program requiring administrator access, use `~/.config/hypr/scripts/xsudo.sh command [arguments...]`; it preserves the display connection, asks for a password when needed, and removes any temporary root display access when the command exits.

**Xetal Images** opens pictures and screenshot notifications in a centered floating window. Scroll to zoom around the pointer, drag to pan, double-click to switch between Fit and 100%, and use the arrows or Left/Right keys to browse the folder. GIFs include Play/Pause, F11 toggles fullscreen, and the folder button reveals the current image in Dolphin. Images remain unchanged. Each screen resolution and display scale remembers its own normal window size; the next launch fits that size inside the monitor's usable area, including its taskbar. Fullscreen and maximize do not replace the normal size. These preferences stay in `theme/qt-settings/Xetal/Images.conf` inside the private profile.

## Check, prepare, restore

```bash
./x_hyperinstall.sh --check                         # Dependencies and versions; no writes
./x_hyperinstall.sh --dry-run                       # Installation plan; no writes
./x_hyperinstall.sh --skip-packages                 # Use dependencies already installed
./x_hyperinstall.sh --prepare /tmp/xetal-review      # Build/validate a separate review copy
./x_hyperinstall.sh --no-startup                    # Keep Super+D; skip the login animation
./x_hyperinstall.sh --yes                           # Accept package/install prompts
./x_hyperinstall.sh --restore /path/printed/backup  # Restore the previous configuration
```

The prepare destination must not already exist. The normal installer builds in a staging directory and refuses to overwrite configuration edited during preparation. Restore retains the replaced Xetal profile in the installer's `replaced/` directory, including any changes you made after installing. A symlinked previous Hyprland directory is backed up/restored as a symlink; its original target is left intact.

## Shortcuts

| Shortcut | Action |
| --- | --- |
| Super+Space / Super+R | Apps |
| Super+K | Control desk / Hotkeys |
| Super+A | Audio mixer |
| Super+Q / Super+Enter | Kitty |
| Super+M | Log out after confirmation; Cancel is selected by default |
| Super+E | Dolphin |
| Super+Ctrl+P | YouTube MP3/MP4 downloader |
| Super+Tab / Super+Shift+Tab | App switcher, forward/reverse |
| Super+number | Switch workspace |
| Super+Shift+number | Move the focused app to that workspace |
| Super+V | Toggle floating |
| Super+C | Close the focused window |
| Super+Shift+K | Force-kill the application under the pointer |
| Super+/ | Window shortcut overlay |
| Super+D | Show/hide the animated dashboard |
| Super+Shift+S / Super+S | Send to / show the Magic workspace |
| Super+L | Lock |
| Print / Shift+Print | Capture an area / all displays |

Super+Shift+K is for stuck applications: it sends SIGKILL without a save prompt, which can close other windows belonging to the same app process. It targets the window under the pointer, does nothing over empty desktop or the bar, and appears in Control desk → Hotkeys → Window hover.

The floating Media downloader captures selected YouTube links before taking focus and also supports Paste or manual entry. MP3 uses the best audio source and highest-quality MP3 encoding; MP4 merges the best video and audio without a resolution cap. Files go to your XDG Music/Videos folders. The popup includes progress, a live log, cancellation and file/folder actions. **Update yt-dlp** verifies and installs an official private copy for this popup under `~/.local/state/hyprland-media`; it does not upgrade system packages.

Right-click the taskbar and open **Options** to choose **Top** or **Bottom** and which items are visible: CPU, RAM, temperature, disk, Wi-Fi, LAN, VPN, media, audio, the clock and more. Changes apply immediately on every monitor and remain saved after login in `waybar/options.json`. Apps opens beside the chosen edge, fitting the monitor's available space; popup menus turn inward at screen edges. **Show all items** restores visibility while keeping your chosen position. Tray icons keep their application menus; pinned apps include Options in their existing menu. The menu follows Xetal Raw/Modern and the selected color palette.

Floating windows also have an invisible title grip: left-drag the upper central area without holding Super. A small movement threshold preserves ordinary clicks; resize edges, common title-button areas and tiled/fullscreen windows are excluded. Applications with their own title-bar dragging keep that behavior. This session-owned helper uses explicit window addresses and stops on release or when the compositor exits.

Dolphin and compatible KDE/KIO file jobs use **Xetal Files**, a compact 448 × 168 floating progress card with animated flying files, real progress, speed and source/destination details. Drag its background normally; pause/resume appears when the operation supports it, and cancellation is acknowledged by the originating application. Errors remain visible with a Details button. The session helper uses KDE's JobView interfaces, respects an existing job service and releases its names on logout; it never performs or cancels file operations just because the desktop ends. Jobs already running when the helper starts can finish in their existing progress windows.

## Source and checks

`config/hypr/` contains the complete desktop payload. `installer/` handles dependency checks, rendering, builds, installation and restore. Machine-specific original settings live under `profiles/`. Native modules are compiled locally, rather than distributing binaries tied to the author's Qt version or architecture.

```bash
python3 -m unittest discover -s tests -v
./tests/run-desktop-tests.sh
python3 config/hypr/waybar/options/test_options.py --native  # optional GTK checks in a Wayland session
./x_hyperinstall.sh --skip-packages --prepare /tmp/xetal-build-check
```

See [validation notes](docs/VALIDATION.md), [dependencies](docs/DEPENDENCIES.md), [third-party notices](THIRD_PARTY_NOTICES.md), and the detailed [desktop guide](config/hypr/README.txt).

Browser profiles, credentials, caches, recent-file history, private bookmarks, session logs and compiled build artifacts are excluded. The wallpaper, mascot and font assets have checksums in [`assets-manifest.json`](assets-manifest.json).
