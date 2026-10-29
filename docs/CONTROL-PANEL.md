# Control Panel

Open **Apps → Control Panel**, immediately above Fusion Settings. It opens as a centered floating window. Drag its header to move it, use the bottom-right grip to resize it, and search by name or purpose. **Alt+Left** returns to all tools; **Ctrl+F** searches. Window size and preferences are saved separately from CachyOsTools.

The minus button hides the panel while its work continues. Open Control Panel from Apps again to return to the same instance and tool.

The native Qt/C++ interface uses a complete copy of the **CachyOsTools** engine. The original application is not replaced or modified. System operations, dialogs, scripts, translations and ISO resources are included in [`control_panel/backend`](../config/hypr/control_panel/backend). [`UPSTREAM.json`](../config/hypr/control_panel/UPSTREAM.json) records the original source revision and file hashes. The engine and integration use [GPLv3](../config/hypr/control_panel/LICENSE).

![Control Panel in BreakPoint](screenshots/control-panel.png)

## Tools and feature coverage

| Control Panel entry | Included tools |
| --- | --- |
| System ISO | Full system clone, exclusions, online/offline packages, archive selection/verification, first-boot hardware/identity changes, output, restore guide, dependency checks and dummy installer preview |
| System Backup / System Restore | Source/destination drives, filesystem browsing, rsync backup and restore |
| Drives & Storage | Filters, mounts, labels, formatting, ownership/permissions, SMART health, benchmarking and ISO to USB |
| Restore Points | Snapper/Btrfs snapshot management |
| Logs & Reports | Plain-text hardware reports, decoded login history, journal filters, boot selection and live following |
| System Overview | Health, resource use, quick actions and language selection |
| Device Manager | Hardware categories, drivers and device operations |
| Sensors & Power | Temperatures, fans, power profiles and diagnostics |
| Users & Groups | Accounts, passwords, membership and administration |
| Kernel Manager | Installed kernels, install/remove and boot defaults |
| System Properties | Hardware, identity and hostname |
| Environment Variables | System environment editor and separate Hyprland login environment |
| Window Inspector | Window/process inspection, X11/Wayland backends and window actions |
| **Pacman / Paru / Yay** | Three adjacent entries: installed packages, repository/AUR searches, details, installation and helper management |
| Install .deb | Convert with debtap and install through pacman, with the original terminal review |
| Package Updates | System upgrades, package checks and Arch news |
| Package Repair | Mirrors, keyrings, locks, diagnostics and downgrades |
| Installed Software | Package removal, orphans and caches |
| System Cleaner | Review cache/disk usage and select cleanup operations |
| Network | Interfaces, Wi-Fi, connections, bridges, libvirt networks and ports |
| Firewall | UFW/firewalld rules and configuration |
| Network Shares | Discovery, mounts, sharing and associated services |
| Shell & Apps Shortcuts | Alias add/edit/remove, shell configuration editor, terminal actions and Apps favorites |
| Services | System/user service controls, failed services, journals and boot analysis |
| Startup Applications | Choose whether Xetal Engine appears at login; add/edit, enable/disable, remove and run login applications; manage user units |
| System Tweaks | Performance, security, network, storage, desktop and system settings |
| System Configuration | Privileged editor and configuration catalog, extended with Hyprland and Kitty |
| Panel Preferences | Language, visible tool families, startup page, size memory, autosave, drive/package/editor defaults, ISO defaults and debug preview |
| Hyper Fusion Updates | The existing desktop updater, including Control Panel updates |

Package Repair, Shares, Firewall, Services and Startup Applications each have a dedicated entry. Yay and Paru keep their own helper controls. KDE Plasma tweaks and the old KVM interface are omitted from this Hyprland panel; their upstream source remains in the engine archive.

The separate CachyOsTools Theme page is replaced by the **desktop master theme**. Raw, Modern and BreakPoint, including Dark/Light/High contrast, apply to the panel and its dialogs. Appearance preferences link to Fusion Settings. Hyper Fusion's updater supersedes the original application's self-updater.

The backend targets **Arch Linux/CachyOS**. Package, kernel, boot and ISO tools retain their platform/dependency requirements; installing Hyper Fusion on another distribution does not translate these commands to another package manager. Existing confirmation and privilege prompts remain. Opening or searching the panel does not execute a system-changing operation.

## Hyprland integration

- Shell detection follows the terminal shell, including literal Kitty shell overrides, Zsh's `ZDOTDIR` and Fish's config directory. Supported aliases/abbreviations are parsed without executing shell configuration.
- Alias saves preserve surrounding configuration/functions and simple user-owned source files. External changes block stale saves. Private backups are kept in `control_panel/state/alias-backups`.
- **Add to Apps…** opens the existing shortcut editor, including command, directory, icon, terminal, keep-open and floating options. Saving creates a favorite in Apps.
- Terminal operations use the private Kitty profile. Control Panel runs as the ordinary desktop user; individual administrative tools request privileges when used.
- New login applications are saved in `control_panel/state/autostart` and run at the next Hyprland login. Shared desktop autostart files are not edited. Package entries require explicit opt-in; user systemd units remain separately identified.
- **Startup Applications → Xetal Engine startup screen** controls automatic login display. **Super+D** still opens or hides it manually. The preference defaults to on and is stored in the update-preserved `control_panel/state/startup-screen.json`.
- User environment values are literal `NAME=value` lines in `control_panel/state/environment.env`, applied at the next Hyprland login. The explicit system pane still edits `/etc/environment` when requested.
- The panel, shortcut editor and startup helper are tied to the active compositor connection.

## System ISO

![System ISO with pinned build controls](screenshots/control-panel-iso.png)

At the default 1280 × 800 size, the ISO settings fit above a compact, internally scrolling output area, with build actions pinned below. The window remains constrained to the current monitor. On smaller screens, the page can scroll to keep every control accessible.

All original ISO scripts are embedded as Qt resources: builder, common helpers, installer/TUI, boot restoration, first-boot adjustments and dummy build. The adapted interface uses the existing generator and preserves these script bytes. **Panel Preferences → ISO → Debug ISO Creator** enables the dummy preview.

Read the retained [compatibility notes](../config/hypr/control_panel/backend/docs/ISO_COMPATIBILITY.md) and [validation guide](../config/hypr/control_panel/backend/docs/ISO_VALIDATION.md). The ISO remains a file-based snapshot with the original exclusions and restoration behavior. The interface retains its snapshot/target-disk confirmations. Closing Control Panel is blocked during an ISO build; Home and Minimize remain available.

Integration validation includes all 151 upstream ISO regression checks, resource-hash comparisons, isolated shell/startup tests, native navigation checks and the desktop/installer suites. This is not a new end-to-end physical-machine restore test. Test a generated recovery ISO in a VM before depending on it.

## Building and updating

`./x_hyperinstall.sh` builds the copied C++ application automatically. For development:

```bash
python3 config/hypr/control_panel/build.py
```

The executable lives in ignored `control_panel/.build`. Required components include CMake, Qt Widgets/Network/DBus/Linguist, XCB/XCB-RES, Wayland development files and Qt SVG readers. Installer recipes include these dependencies. Updates build the executable before activation and preserve private Control Panel state.
