# Recent desktop changes and remaining work

This records the November 22–23, 2026 desktop updates. The new integrations are
in the repository, installer and live profile. Online/offline ISO images have
not been rebuilt for this integration pass. See the [main README](../README.md#recent-desktop-updates)
for the feature overview and the sections below for behavior and validation limits.

## Desktop integrations · November 23, 2026

- **Super+W → Pictures / Videos** remembers the selected media type. Wallpaper
  Selector settings manages picture folders and video folders separately. Video
  playback is local, muted and looping, with a saved still fallback, fullscreen
  auto-pause, and optional pause on battery. Applying a picture stops that
  monitor's video. A missing video does not remove the still fallback.
- **Start menu search** includes installed applications, all 35 Control Panel
  tools, and Fusion Settings destinations. Searching `grub`, `governor`, `phone`,
  or `rdp` opens the corresponding page directly.
- **Control Panel → RDP** keeps the existing saved Windows connections, wallet,
  clipboard, sound and folder options in **Connect to a PC · RDP / VNC out**.
  New connections default to RDP. The protocol selector also opens saved VNC
  connections in TigerVNC, with separate wallet credentials, encryption choices,
  clipboard, resizing, full screen, view-only and shared-session options.
  Old RDP profiles and wallet keys keep their existing behavior.
  **Share this desktop · RDP / VNC in** adds authenticated TLS VNC (WayVNC) and
  NLA/TLS RDP (hypr-rdp). Select a protocol, monitor, LAN address and a password,
  then Start sharing. Only one protocol runs at a time. RDP works with Windows
  Remote Desktop; encrypted VNC works with TigerVNC. Hosting defaults to off,
  local-only and no automatic startup. No firewall ports are opened silently.
  Sharing belongs to the logged-in session and ends at logout; this is active
  desktop sharing, not a remote login greeter. RDP includes remote input,
  clipboard and mirrored audio; VNC can be view-only. File clipboard transfer
  is disabled in the RDP backend. Verify the displayed certificate fingerprint.
  The page distinguishes starting, listening, active TCP connections and stopped
  sharing. Status polling leaves buttons enabled, user actions queue behind reads,
  and failed starts keep their error visible. A sharing password is required
  before Start becomes available. The connection count includes connections
  negotiating authentication; it is not a list of authenticated users.
  The endpoint card describes the running server while unsaved edits stay in
  the form. Terminal color/control sequences are removed from existing and
  running-server logs, and new server processes request plain text. The log pane
  therefore stays readable without restarting an active sharing session.
- **Fusion Settings → Phone** pairs with KDE Connect, sends files/clipboard text,
  and sends SMS through a supported Android phone. WhatsApp opens its official
  linked web client for text, voice recordings, audio and video attachments.
  The optional `whatsapp://send` handler is registered only when selected.
- **Fusion Settings → Power** is also accessible from the Waybar power panel
  and Start menu's session/power page. CPU governor, energy preference, boost
  and supported battery charge limits use authenticated, backed-up transactions.
  They are restored at boot and after sleep. Saving takes over management from
  competing power daemons; restoring all Fusion hardware choices reinstates
  those daemons' original state. Idle/lid preferences have separate AC/battery
  choices, honor idle inhibitors, and are restored at login. They remain off
  until explicitly enabled. Hibernate still requires working swap/resume setup.
- **Displays & arrangement** adds per-monitor color-space presets and hardware
  brightness, contrast and RGB gain where supported. DDC/CI must be enabled on
  external displays. A separate process restores unconfirmed picture previews
  after 20 seconds or if the editor exits. Kept hardware values follow the
  monitor's EDID identity across login, hotplug and resume. This is not an ICC
  calibration workflow.

## Recent interface and reliability changes

| Area | Changes |
| --- | --- |
| **Fusion Viewer** | Renamed from Xetal Images. Fit, 100%, zoom, fullscreen and Open share a centered top toolbar; previous/next navigation sits below the picture. Right-click to rotate left/right or set wallpaper. One monitor applies immediately; multiple monitors open Choose a display. The Open picker is bounded to one display. Extra KDE title bars and injected controls default to off, and the line beneath the built-in window buttons is removed. |
| **Wallpaper chooser** | Floating cards opens centered on the monitor under the pointer every time. It has no enclosing border, hover border, shadow or focus glow. Its KDE title bar defaults to off and controls to Automatic · add missing controls. Gallery window, Frame Lab and Orbit Atlas remain available. |
| **Session popups** | Shutdown, restart and logout confirmations default to no extra KDE title bar or injected controls. Their own close button is visible. |
| **Clock and clipboard** | Calendar opens on click only; the overlapping hover calendar is removed. Clipboard history is roughly twice as tall, constrained to the available monitor height. |
| **Window appearance** | Focus, shape, spacing, opacity and shadows share one editor with an active/inactive preview and Apply/Discard. Saved Focus choices and application exceptions persist across theme presets and logins. Visuals, Glass & materials, Quality & previews, Workspace tools and the new large taskbar-hover preview switch are hidden for later work. [Guide →](VISUALS-057.md) |
| **KVM layout** | SMBIOS identity, Machine & network, Single GPU, Memory, CPU pinning and PCI/USB use tighter layouts. Memory's left and right panels align. Paths & tools separates components, QEMU/firmware, kernel/helpers and ACPI into tabs. Single GPU's Clear history no longer closes the app. [Guide →](KVM.md) |
| **KVM compatibility and permission** | Signed catalogs select the exact matching module build and retain older releases. The compatible-kernel installer offers releases newest first. Supported Windows Virtual GPU launches can remember permission for an approved setup; this does not disable sudo authentication for other commands. |
| **GRUB Boot Editor** | Entering the editor requests authentication and loads the current menu. Names, commands, order, default entry, timeout and remembered selection are editable. UEFI boot registration can add this installation to firmware boot choices, with review, backups and undo where applicable. [Guide →](GRUB-BOOT-EDITOR.md) |
| **Control Panel lifetime** | GRUB readers, dashboard probes, Favorites jobs and credential workers disconnect callbacks before their UI objects are destroyed. Navigation previews avoid authentication, and integration checks use isolated compositor/session environments. |

## Components and validation

The native sources and their licenses are pinned under
`config/hypr/desktop_services/third_party/`; each has an
`HYPERFUSION-UPSTREAM.json` provenance record. `desktop_services/build.py` builds
mpvpaper 1.9 and hypr-rdp 0.1.9. The installer includes their dependencies and
build steps. Building RDP from source requires Cargo's pinned dependencies to
be cached or an Internet connection; an offline system snapshot must include
its already-built `.build/hypr-rdp/release/hypr-rdp` and mpvpaper binary.

Validation includes fake-hardware transaction/rollback tests, separate wallpaper
libraries and persistence, search routing, UI rendering, and an isolated nested
Hyprland check with a real video decoder and authenticated VNC/RDP connections
(correct and incorrect passwords). Nested compositor pixel capture is not
reliable on this NVIDIA session; physical-screen playback and the Windows
client's input/audio need an interactive check. Phone pairing/SMS and laptop-only
hardware have not been exercised on this desktop; tests do not send messages or
change its power policy.

The combined native RDP page has regression checks for saved PCs, password
handling, tab switching, hosting start/stop, and preserving drafts during status
refreshes. The native navigation preview never authenticates with GRUB. Desktop
integration tests use private compositor sockets and no real display or session
bus. Shutdown checks also cover GRUB helpers, dashboard probes and Favorites;
callbacks are disconnected before their widgets or timers are destroyed.

Outgoing VNC uses the distribution's TigerVNC viewer (`tigervnc` on Arch/Fedora,
`tigervnc-viewer` on Debian/Ubuntu). The current live system also has a local
viewer cache from verified Arch packages, without a system package transaction.
The viewer receives session credentials through its supported private child
environment, never command-line arguments or temporary password files. Passwords
remain saved only in the system wallet. Closing the Control Panel window leaves
the viewer running; exiting the desktop session closes it.

The outgoing VNC check has passed real encrypted authentication, rendered pixels,
text clipboard transfer and viewer shutdown using private X servers and the
Control Panel's actual launch path. The sharing log cleanup was checked against
the live server log and fixtures containing color sequences, terminal links and
truncated log tails. Native tests cover stable polling, queued actions, preserved
drafts and visible startup failures. The live RDP page has also shown its
listening state; a listening socket alone does not verify Windows input/audio.

## What remains

- Flatpak, desktop extensions and a separate add-on catalog remain future work;
  Pacman/AUR app discovery is implemented in Control Panel → Software.
- WhatsApp uses the official linked web client; there is no native WhatsApp
  conversation or recording implementation in Fusion Settings.
- Monitor presets/hardware controls are implemented; ICC profile calibration is
  not implemented.
- Physical-display video playback, phone pairing/SMS, laptop hardware power
  controls, and Windows RDP input/audio still need hands-on validation.
- The live profile, repository and installer are updated. New online/offline ISO
  images have not been rebuilt during this desktop integration pass.

### Software discovery — implemented in Control Panel

**Control Panel → Software → Browse** now has an expandable category tree,
recognizable app icons, descriptions and a responsive virtualized card grid.
Top picks starts with Echo, Linux Studio, XMusic and Xetal Video Editor, then
Discord and Chrome. The four Xetal apps resolve current Linux downloads from
the host; Pacman is the default package source, with optional Yay/Paru AUR search.
The local metadata/icon cache keeps browsing independent of network requests.
Installed packages and repair tools remain in their existing tabs. Flatpak and
desktop add-ons are still separate future work. See [the Software guide](CONTROL-PANEL.md#software-catalog).

## Repeatable checks

Run the private protocol/decoder check with:

```sh
python tests/check-desktop-services.py /tmp/fusion-services-check-new
python tests/check-vnc-client.py
```

See [remote desktop checks](../config/hypr/control_panel/rdp/README.md#build-and-checks)
and the [validation record](VALIDATION.md#desktop-integrations-and-remote-desktop--23-november-2026)
for the remaining automated coverage. These checks use temporary profiles and
private servers; they do not send phone messages, change host power policies or
replace the active desktop session.
