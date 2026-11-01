<h1 align="center">Hyper Fusion</h1>

<p align="center"><strong>Your workspace. Your colors. Your kind of Linux desktop.</strong><br>A complete Xetal desktop for Hyprland, with native settings, custom menus, KVM tools and a little Compiz nostalgia.</p>

<p align="center">
  <a href="#install">Install</a> ·
  <a href="#tested-on">Tested on</a> ·
  <a href="#four-looks-one-desktop">Themes</a> ·
  <a href="#compiz-spirit-hyprland-desktop">Effects</a> ·
  <a href="#kvm-settings">KVM</a> ·
  <a href="docs/GALLERY.md">Gallery</a> ·
  <a href="#documentation">Documentation</a>
</p>

[![Hyper Fusion desktop with system information, Matrix rain, clock and interactive project cubes](docs/screenshots/startup-dashboard.png)](docs/GALLERY.md)

<!-- GitHub renders this attachment as an inline video player. -->
https://github.com/user-attachments/assets/8a20af5b-ec30-4bbb-ad7f-06d4e392a57d

<p align="center"><sub>48-second desktop tour · Original 1440p recording · <a href="docs/GALLERY.md">Explore the full gallery</a></sub></p>

Hyper Fusion brings the whole desktop together: a launcher you can arrange yourself, four coordinated visual styles, a configurable taskbar, native settings, themed file tools, virtual-machine management and original Compiz effects adapted to Hyprland. The graphical installer builds the included desktop components for your system, and the updater keeps your personal choices between releases.

## Tested on

<table>
  <tr>
    <td align="center" width="20%"><a href="https://archlinux.org/"><img src="docs/media/distros/archlinux.svg" width="52" height="52" alt="Arch Linux"><br><strong>Arch Linux</strong></a></td>
    <td align="center" width="20%"><a href="https://cachyos.org/"><img src="docs/media/distros/cachyos.svg" width="52" height="52" alt="CachyOS"><br><strong>CachyOS</strong></a></td>
    <td align="center" width="20%"><a href="https://manjaro.org/"><img src="docs/media/distros/manjaro.svg" width="52" height="52" alt="Manjaro"><br><strong>Manjaro</strong></a></td>
    <td align="center" width="20%"><a href="https://fedoraproject.org/"><img src="docs/media/distros/fedora.svg" width="52" height="52" alt="Fedora"><br><strong>Fedora</strong></a></td>
    <td align="center" width="20%"><a href="https://www.debian.org/"><img src="docs/media/distros/debian.svg" width="52" height="52" alt="Debian"><br><strong>Debian</strong></a></td>
  </tr>
</table>

| Distribution | Current testing and installation scope |
| --- | --- |
| **Arch Linux** | Development desktop and fresh-install testing; automatic setup on x86-64. |
| **CachyOS** | Fresh-install testing; automatic x86-64 setup, with repository checks for v3/v4 packages. |
| **Manjaro** | Project-reported testing and stable-repository compatibility checks; uses the Arch-family setup path. |
| **Fedora 44** | Native x86-64 RPM setup, desktop build and recovery checks; graphical VM testing is ongoing. Targets mutable Workstation/KDE installations. |
| **Debian 13 (trixie)** | Native x86-64 DEB bundle, clean-container installation and complete desktop build; graphical VM login testing is pending. |

These notes describe project testing, not certification of every release or GPU. Setup checks the recipient's repositories and dependencies before changing the compositor. Fedora Atomic/OSTree editions, Ubuntu and other Debian releases are outside the current automatic setup paths. See [dependencies and compatibility](docs/DEPENDENCIES.md) for the exact scope.

> **Control Panel compatibility:** Some features currently work **only on Arch-based systems, until further notice**. These include Pacman/Paru/Yay, Arch package repair and kernel-management tools. Fedora and Debian desktop support do not provide distribution-specific equivalents for these features.

## Install

Open a terminal in your graphical Linux session and run as your **regular desktop user**:

```bash
git clone --depth 1 https://github.com/XetalEngine/x_hyperland.git
cd x_hyperland
./x_hyperinstall.sh
```

Prefer a ZIP? Choose **Code → Download ZIP**, extract the entire archive, open a terminal in `x_hyperland-main`, and run `bash ./x_hyperinstall.sh`. A Git checkout is not required. When testing a newer download, extract it into a new folder.

**Hyper Fusion Setup** guides you through Welcome → Your setup → Review → Install → Ready.

- Adapts monitor resolution, placement and scale to your computer.
- Lets you keep existing desktop/startup preferences or install the current defaults.
- Offers an **optional Fusion sign-in screen** with your theme, animated account photo, account selector and installed desktop sessions, including Hyprland, KDE Plasma and XFCE. It is off by default; selecting it reveals a warning with the changed files, backup location and console recovery command. Take a picture of that warning before continuing.
- Installs required packages with a separate administrator-password prompt and builds native components locally. The Control Panel uses all available CPU threads.
- Shows an expanded installation log that grows with the window; **Installing…** stays disabled until the operation finishes. Failed steps show their useful diagnostic and a **Retry** action.
- Backs up the existing profile and validates the complete configuration before replacement. Package recovery is prepared before changing the compositor.

When Setup finishes, **log out, select Hyprland and sign in again**. Your current session is not forcibly restarted. The desktop keeps its themes, Dolphin profile and startup helpers separate from KDE/Plasma and shared desktop preferences.

### One tested compositor version

This release uses **Hyprland 0.56.2** and its exact tested source commit so the desktop, **Cube**, **Burn** and **Minimize** stay compatible. Setup installs or downgrades to that version and applies the appropriate package holds.

| Included runtime | Download ZIP contains |
| --- | --- |
| **Arch family** | Signed official Hyprland **0.56.2-4** package — **51.3 MB**. |
| **Fedora 44** | Signed **0.56.2-6.fc44** runtime, matching libraries and headers — **55.9 MB**; corresponding LGPL source RPMs add **55.4 MB** separately. |
| **Debian 13** | Native **0.56.2** runtime, matching headers/libraries, Waybar, Kitty and SDL3 — **22.3 MB ZIP**; corresponding sources are included separately. |

Each bundled package is below 100 MB. Fedora packages come from the documented giperborey/Hyprland COPR publisher; Setup verifies them without enabling a COPR repository. Other desktop dependencies still download as needed. Future compositor changes go through foreground Setup together with matching desktop/effect builds. [Installer, signatures and recovery →](docs/INSTALLER.md)

<details>
<summary><strong>Terminal options and troubleshooting</strong></summary>

```bash
./x_hyperinstall.sh --cli                          # Use the terminal installer
./x_hyperinstall.sh --check                        # Check dependencies and versions
./x_hyperinstall.sh --dry-run                      # Preview the installation plan
./x_hyperinstall.sh --skip-packages                # Use dependencies already installed
./x_hyperinstall.sh --prepare /tmp/fusion-review   # Build/validate a new review directory
./x_hyperinstall.sh --no-startup                   # Keep the Welcome dashboard manual
./x_hyperinstall.sh --fusion-login                 # Opt in to Fusion sign-in; back up system login settings
./x_hyperinstall.sh --no-fusion-login              # Restore the login settings saved before opting in
./x_hyperinstall.sh --restore /path/to/backup       # Use the backup path printed by Setup
```

The installation log is `~/.local/state/xetal-hyprland/setup.log`. Include the source revision and the first compiler/package error when reporting a failure. Setup keeps the existing desktop profile if preparation fails. If it changed the compositor, its recovery path restores the previous runtime; successfully installed ordinary dependencies remain available for a retry.

On 0.56.2, the brief `.conf` deprecation notice refers to a future Hyprland format change. The pinned release still supports this configuration. [Compatibility notes →](docs/DEPENDENCIES.md)

</details>

## Four looks. One desktop.

| Xetal Raw | Xetal Modern |
| :---: | :---: |
| [![Xetal Raw Apps menu](docs/screenshots/apps-raw.png)](docs/screenshots/apps-raw.png) | [![Xetal Modern Apps menu](docs/screenshots/apps-modern.png)](docs/screenshots/apps-modern.png) |
| Cyan accents and transparent surfaces | Soft blue cards and a Home overview |

| BreakPoint | Binary Knife |
| :---: | :---: |
| [![BreakPoint Apps menu](docs/screenshots/apps-breakpoint.png)](docs/screenshots/apps-breakpoint.png) | [![Binary Knife Apps menu](docs/screenshots/apps-binaryknife.png)](docs/screenshots/apps-binaryknife.png) |
| Charcoal glass and crimson highlights | Graphite panels and electric blue edges |

Colors follow you through Apps, the taskbar, Fusion Settings, Control Panel, KVM, file pickers, notifications, lock screen and session tools. Choose **Dark**, **Light** or **High contrast**, with a separate wallpaper for each monitor.

**Fusion Settings → Theme** lets you mix the pieces: any Start menu with any palette, Classic/Modern/Gallery/Studio navigation, an account picture or animated GIF, menu backgrounds and transparency, custom cursors, task switchers and transfer animations. **Apply theme** lets you choose which components change. Save your combination as a named **Custom** preset and restore it selectively later.

Each theme includes its own three-screen wallpaper set. The [gallery](docs/GALLERY.md) shows all four designs, their tools and artwork.

## Make the desktop yours

### Apps, favorites and shortcuts

Press **Super+Space** and start typing. Arrange favorites into named groups, drag them into place, and mix medium tiles with compact icons. Resize the menu without losing your layout. Right-click an app to pin it to Favorites or the taskbar, assign a global hotkey, edit its command/icon, or choose terminal and floating behavior.

**Ctrl+click** launches an app floating once. Floating windows remember their size, open centered, and support Maximize/Restore. **Super+F** brings the active window to the front; **Super+B** sends it behind overlapping windows. These actions preserve its size and position.

### Settings and desktop menus

**Super+K** opens Fusion Settings: editable hotkeys with validation and recovery, per-application audio routing, network/Bluetooth controls, keyboard/mouse/touchpad options, calendar, session controls and display arrangement with timed **Keep/Revert** protection.

Right-click the wallpaper for your desktop menu. Its editor supports commands, icons, headings, submenus, hotkeys, multiple columns and live styling previews. Save/load presets to reuse a layout.

### A taskbar for each display

Workspaces, running apps, draggable pins and your chosen status modules stay close to the screen where you work. **Right-click → Options** moves the bar to the top or bottom and shows/hides individual modules. The clock opens a calendar; power opens a compact system dashboard. A session helper restores the bar if it exits unexpectedly.

### Wallpaper carousel

**Super+W** opens a flowing ribbon of wallpaper cards, with search, collections and a slideshow preview. All twelve bundled wallpapers are included. Add or remove your own folders directly in the browser; folder choices stay on your computer and removing a folder never deletes its images.

**Theme → Wallpapers → Wallpaper Selector** defaults to **Floating cards**, which places the carousel and compact controls directly over your desktop. The original **Gallery window** is also available. Your chosen style is used by Super+W, and both styles share your collection.

The center card opens on the current wallpaper for the display hosting the selector, even if its image is outside your selected folders. Click an image to choose its display from a preview of your real monitor arrangement. A single display applies immediately. **Bloom**, **Crossfade**, **Silk sweep**, **Ripple**, **Iris** and **Glide** transitions run behind your apps. **Random** picks an animated effect each time; **Instant** and reduced-motion settings skip the animation. Choices are saved per monitor and theme, and also appear in Fusion Settings. [Wallpaper guide →](config/hypr/wallpaper/README.md)

### Screen recording

**Alt+F9** records the monitor under your pointer, with **64 FPS MP4**, **desktop audio**, and automatic saving to **Videos** by default. Press the shortcut again or click the taskbar's **REC** timer to stop and save. The **Recording saved** notification has a **📂 Show in folder** button that opens Dolphin with the video selected; the action also works from notification history during the same desktop session.

Choose frame rate, quality, encoding, desktop/microphone/no audio and the save folder in **Fusion Settings → Capture**. [Screen recording guide →](config/hypr/recording/README.md)

### Welcome and startup

**Super+D** opens or hides the four-window Welcome dashboard: system information, Matrix rain, a large clock and six interactive project cubes. The taskbar groups it as **Welcome**, without four duplicate app icons.

Uncheck **Show this dashboard at login** right on the dashboard to disable all four startup windows. Re-enable it in **Control Panel → Startup Applications**; Super+D continues to work manually. **Num Lock starts on by default**, with a matching switch in Startup Applications and Fusion Settings → Input.

## Compiz spirit. Hyprland desktop.

| Burn | Desktop Cube + 3D Windows |
| :---: | :---: |
| [![Burn effect controls](docs/screenshots/burn.png)](docs/screenshots/burn.png) | [![Desktop Cube and 3D Windows controls](docs/screenshots/cube.png)](docs/screenshots/cube.png) |

**Burn** closes windows with the original Compiz particle flame and smoke. Tune the color, direction, particle count, size, lifetime and timing, or try a disposable preview window.

**Super+Z** minimizes the active window into **Fireball** or **Splat** at the bottom-left of its screen, stacking upward. Choose either screen edge and either stacking direction in Minimize settings. Fireball uses Compiz's particle flames; Splat is living, glossy slime with boiling bubbles, eight fixed or randomized silhouettes, and Living slime, Alien membrane and Glossy paint surfaces. Both follow the theme accent, with an optional custom color. Click to restore; scroll the single column when it fills up. The taskbar shows minimized apps as **M3 + app icons**, using their original workspace number. Apps keep running. Adjust size, travel time, animation speed and boiling intensity, or restore all windows in **Theme → Window effects → Minimize**. [Minimize guide →](config/hypr/effects/minimize/README.md)

**Desktop Cube + 3D Windows** gives each monitor its own four workspace faces. Hold **Ctrl+Alt+left mouse** and drag to rotate; release to select or press Escape to cancel. Adjust transparency, edge colors, ceiling/floor artwork, a moving sky, and raised windows with depth and spacing. **Standard animation is the default for ordinary workspace switching**; automatic cube rotation is an option. The drag gesture works with either choice.

**Super+Tab** uses Ring Switcher by default, with seven alternatives: Fusion Cards, Application, Static Application, Shift Cover, Shift Flip, Stack and Scale overview. Live previews follow your selected monitor and style. [Task switcher guide →](config/hypr/switcher/README.md)

Five cursor designs add optional Comet, Soft glow or Stardust trails and click ripples. Cursor effects start disabled and stop rendering when idle. [Cursor guide →](config/hypr/cursors/README.md)

The native [Burn](config/hypr/effects/burn/README.md), [Cube](config/hypr/effects/cube/README.md) and [Minimize](config/hypr/effects/minimize/README.md) sources are included, along with Compiz attribution for Burn, Cube and the minimize flame. Setup builds them against the pinned **0.56.2 x86-64/OpenGL** runtime; their effects remain individually configurable. Front/Back also handles floating windows above maximized windows and preserves their order across workspace switches.

## KVM Settings

Open **Apps → KVM** for the integrated Windows/Mac VM editor and setup wizard.

- **Single GPU, Virtual GPU and Dual GPU** launch modes, with floating console/viewer controls.
- CPU pinning/features, RAM, disks, PCI/USB passthrough, UEFI firmware, TPM, SMBIOS, OpenCore settings, command previews and saved presets.
- A first-run wizard that downloads missing components and walks through the recipient computer's hardware.
- **Create Bridge** for a suitable wired NetworkManager connection, preserving IP/DNS settings with recovery checkpoints. **NAT** shares the host connection and also works over Wi-Fi.
- Signed downloads for QEMU, OVMF, TPM, OpenCore, Looking Glass and support files. **Paths & Tools pulses red** for missing required components or a newer compatible installed-component release; updates remain an explicit action.
- Private disks, TPM state and writable NVRAM stay separate from component and desktop updates.

The **Custom KVM module · Ultra AMD Stealth Interceptor** is **optional** and appears last in Downloads. It requires the published matching AMD CPU/kernel combination; standard system KVM remains available when it does not match. The built-in Windows guest-script preview and **Copy** action are available before downloading that module; using the script still requires a compatible custom host module and SSH setup.

Runtime components download inside KVM Settings; they are not bundled with the desktop. Supply your own guest installation media and disks. Physical GPU passthrough and guest behavior still depend on the host hardware. [KVM setup, components and recovery →](docs/KVM.md)

## Tools that fit the desktop

| Control Panel | File picker with previews |
| :---: | :---: |
| [![Hyper Fusion Control Panel](docs/screenshots/control-panel-binaryknife.png)](docs/CONTROL-PANEL.md) | [![Themed file picker with Places and preview pane](docs/screenshots/file-picker-binaryknife.png)](docs/FILE-PREVIEWS.md) |

| Tool | What you get |
| --- | --- |
| **Control Panel** | A searchable native interface built from CachyOsTools: hardware, storage, services, startup apps, backups, system tools and shortcuts. **Some features remain Arch-only until further notice**, including Pacman/Paru/Yay and Arch package repair/kernel tools. [Feature map and platform requirements →](docs/CONTROL-PANEL.md) |
| **System ISO** | Create an Arch-based system clone, then restore through a graphical Hyper Fusion wizard with drive cards, review and progress, plus an automatic console fallback. Choose whether the ISO requires a fresh administrator account or preserves existing accounts. Try **Control Panel → System ISO → Preview installer…** with sample drives first. [Restore wizard →](docs/CONTROL-PANEL.md#system-iso) |
| **RAM Cleaner** | Manual **Normal** and **Aggressive** cache cleanup with before/after readings. It keeps applications running and does not reclaim their active memory. Linux already reclaims cache when needed; this is an occasional troubleshooting tool. |
| **Disk Visualizer** | A directory-size tree and treemap, folder navigation, allocated/apparent sizes, and confirmed file actions inside System Cleaner. |
| **Dolphin** | Recipient-specific **Places**, no developer bookmarks, and the redundant Folders tree hidden by default. The bottom terminal starts open using Konsole's embedded component; **Kitty** remains the external terminal. F4 toggles the terminal, F7 toggles Folders. |
| **File pickers** | Matching Places and image/text/folder previews in Xetal, Qt Widgets and standard GTK 3 dialogs. Custom application and portal pickers have their own integration limits. [Coverage →](docs/FILE-PREVIEWS.md) |
| **Xetal Files** | Four animated transfer-card designs for Dolphin/KIO and Ark, with real progress, pause/cancel where supported, error details and appearance controls. |
| **Xetal Images** | Pointer-centered zoom, pan, Fit/100%, folder navigation, GIF playback, fullscreen and remembered window sizing. |
| **Capture and sharing** | Alt+F9 screen recording with audio, 64 FPS MP4 saved to Videos by default, area/all-display screenshots, clipboard support and a custom Hyprland screen-share picker. Recording options live in Fusion Settings → Capture. |
| **Media downloader** | **Super+Ctrl+P** opens an MP3/MP4 popup with progress, cancellation and updates for its private yt-dlp copy. |
| **Kitty** | Matching colors, animated cursor, a draggable scrollback scrollbar and a configurable Fastfetch welcome. |

## Shortcuts at a glance

| Shortcut | Action |
| --- | --- |
| **Super+Space / Super+R** | Open Apps and search |
| **Super+K / Super+A** | Fusion Settings / audio mixer |
| **Super+Q / Super+Enter** | Kitty |
| **Super+E** | Dolphin |
| **Super+D** | Show/hide Welcome |
| **Super+W** | Wallpaper carousel, slideshow preview and display picker |
| **Super+Tab / Super+Shift+Tab** | Switch applications forward/backward |
| **Super+1–4** | Select a cube workspace on the monitor under the pointer |
| **Super+Shift+1–4** | Move the focused window to that workspace |
| **Ctrl+Alt+left mouse drag** | Rotate this monitor's cube |
| **Super+V** | Toggle floating |
| **Super+Z** | Minimize the active window |
| **Super+Ctrl+Z** | Hide/show minimized Fireball and Splat effects |
| **Super+F / Super+B** | Bring to front / send to back |
| **Super+Shift+F** | Toggle fullscreen |
| **Super+left / right mouse drag** | Move / resize a window |
| **Super+C** | Close the focused window |
| **Super+/** | Show window shortcut hints |
| **Super+Ctrl+P** | MP3/MP4 downloader |
| **Print / Shift+Print** | Capture an area / all displays |
| **Alt+F9** | Start/stop recording the monitor under the pointer; save an MP4 with desktop audio |
| **Super+L / Super+M** | Lock / confirm logout |

Turn Cube off for global workspace numbering and add/remove controls. All bindings remain editable in Fusion Settings.

## Updates that keep your settings

The taskbar's **UPDATE** badge announces a newer desktop release. Automatic updates prepare in the background, merge personal settings, build native components and validate the result. **UPDATE READY** activates at the next Hyprland login, without forcing you to log out.

Click the badge to inspect the live log, check now, pause automatic updates or queue a rollback. The log follows new output, and the main button changes from **Update!** to **Updating…** to **Restart** when ready. Restart requires your confirmation; updates never reboot the computer automatically. A changed compositor requirement shows **SETUP REQUIRED** and opens the graphical installer so the system runtime and desktop move together. KVM component updates are managed separately in Paths & Tools.

Your hotkeys, monitor arrangement, chosen wallpapers, private Dolphin Places and startup preferences are preserved. Conflicting edits stop an update for review. [Update behavior and recovery →](docs/UPDATES.md)

## Documentation

| Guide | Details |
| --- | --- |
| [Full gallery](docs/GALLERY.md) | Themes, panels, menus, transfer cards and wallpapers |
| [Installer](docs/INSTALLER.md) | GUI choices, pinned runtimes, backups and recovery |
| [Dependencies](docs/DEPENDENCIES.md) | Distro scope, required tools and compatibility checks |
| [Desktop updates](docs/UPDATES.md) | Settings preservation, activation and rollback |
| [KVM Settings](docs/KVM.md) | VM setup, downloads, networking and private state |
| [Control Panel](docs/CONTROL-PANEL.md) | Administration tools, RAM Cleaner and Disk Visualizer |
| [Screen recording](config/hypr/recording/README.md) | Alt+F9, audio, video settings and saved-recording notifications |
| [File previews](docs/FILE-PREVIEWS.md) | Supported applications, Places and preview behavior |
| [Validation](docs/VALIDATION.md) | Test suites and the limits of automated coverage |
| [Desktop reference](config/hypr/README.txt) | Configuration and component layout |

<details>
<summary><strong>Development checks</strong></summary>

```bash
python3 -m unittest discover -s tests -v
./tests/run-desktop-tests.sh
python3 tests/run-file-preview-checks.py
```

The [installer compatibility workflow](.github/workflows/installer-compatibility.yml) checks Arch-family repositories and runs Fedora and Debian installation, native builds and recovery in disposable containers. Graphical login, GPU/driver and physical passthrough testing remain separate.

</details>

## Credits and licenses

Made by **Xetal**, on [Hyprland](https://github.com/hyprwm/Hyprland), with Qt, GTK, Waybar, Kitty, Dolphin and the wider Linux desktop community. Compiz effects retain their original authorship and licenses; the Control Panel includes the CachyOsTools engine. Modern takes visual inspiration from [Noctalia](https://github.com/noctalia-dev/noctalia).

See the [repository license](LICENSE), [third-party notices](THIRD_PARTY_NOTICES.md), [asset manifest](assets-manifest.json) and [distro icon sources](docs/media/distros/README.md). Distribution names and logos identify tested environments and do not imply endorsement.

Screenshots may show separately installed applications. Echo, XMusic, Linux Studio, Xetal BV and other featured projects are available separately; their presence in the launcher or Welcome dashboard does not install them. Personal bookmarks, credentials, browser profiles and runtime caches are excluded from this repository.

<p align="center"><strong>Hyper Fusion · Made for your workspace.</strong><br><a href="https://www.xetal.net/community/site/">Explore Xetal's other projects</a> · <a href="docs/GALLERY.md">See every panel</a></p>
