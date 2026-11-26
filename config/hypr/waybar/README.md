# Taskbar

CPU, RAM, temperature and disk indicators start hidden. Right-click the taskbar
and open **Options → System** to enable individual indicators; **Show all items**
explicitly enables everything. The power popup also contains system metrics.

**Network & Bluetooth** is one icon with no label. It follows the active Wi-Fi
or Ethernet connection, preferring the physical default route when both are
connected. A VPN does not replace the underlying connection icon. Offline
connections use a dimmed icon; the tooltip shows connection and internet status.

Click it for the themed network popup: internet connectivity, Ethernet, Wi-Fi,
VPN and Bluetooth are together. Wi-Fi and Bluetooth have explicit radio switches;
the other buttons open connection settings and device management. Status refreshes
are read-only and do not scan, connect, disconnect or change radio settings.
The popup shares the power menu's placement, theme, Escape and outside-click
dismissal, including bottom taskbars and scaled monitors.

The shared snapshot is `quick_panel/network_status.py`;
`scripts/panel-status.py network` emits the icon for Waybar. The popup is opened through
`scripts/quick-panel.sh network`. Theme rearrangements retain this single module.

## Workspace transitions

Adding or closing an empty workspace uses a 220 ms slide-and-fade transition.
The horizontal row grows or contracts smoothly, including the + button and
controls beside it. Repeated changes continue from the current position.
GTK's animation-off setting skips the transition.

Cube faces keep their local 1–10 labels during compositor configuration reloads;
internal workspace IDs do not flash on screen. The workspace mode indicator
updates before painting too. The existing cube limits remain: at least four
workspaces and at most ten per display, with close controls only on empty sides.

`workspaces/button.c` prepares labels and metadata before the frame is laid out.
`workspaces/motion.h` retains presentation by workspace identity across Waybar's
button rebuilds, animates row width and positions, and fades snapshots of removed
buttons. Native buttons retain their app icons and click handlers. All callbacks
and snapshots are released when the module reloads. The regular installer build
in `workspaces/build.sh` includes this code.

After replacing these shared libraries locally, restart the session-owned Waybar
child so it loads the new binaries. A configuration reload alone can retain the
previous libraries in memory; the compositor and other apps need no restart.

Native pointer/layout checks run in a disposable X server; the integration check
observes real Waybar frames on two isolated Hyprland outputs:

```sh
xvfb-run -a env GDK_BACKEND=x11 python3 config/hypr/waybar/workspaces/test_close.py
xvfb-run -a env GDK_BACKEND=x11 python3 config/hypr/waybar/workspaces/test_mode.py
xvfb-run -a env GDK_BACKEND=x11 python3 config/hypr/waybar/workspaces/test_motion.py
python3 tests/check-workspace-transitions.py /tmp/fusion-workspace-check-new
```

Run these commands from the repository root. The pointer suites require
`xdotool`; the integration check uses the shared nested-session isolation helper
and never clicks the real desktop's add/remove controls.

## Audio shortcuts

The **Mixer** button beside the output volume slider opens the app mixer popup.
The volume percentage opens the full Audio settings window. These bar shortcuts
focus and raise the exact requested window, including its pointer-input order
above a maximized window in KDE mode. They do not change the background window's
maximized state or either window's geometry. The handoff ends after activation
and cancels on user input; it is not an always-on-top or focus-stealing rule.

See the [audio guide](../../../docs/AUDIO.md) for devices, monitor outputs and the
fixed main-volume strip.

## Tray clicks

Left-clicking an application's tray icon reveals its most recently used window
on its existing monitor and workspace. A click on another monitor switches to
the window; it does not move the window or its workspace. Repeated clicks keep
the window visible. Minimized windows use the same restore path as taskbar clicks.

If the application is still running but has no window, the click asks it to
reopen one and focuses it when it appears. Right-click menus, middle-clicks and
scroll keep the application's native behavior. Menu-only applets without a
window also keep their normal menu. Items that cannot be identified uniquely
fall back to Waybar's normal handling.

The existing `cffi/bar-options` module includes `tray/activation.h`. It intercepts
left clicks before Waybar's app toggle, matches the attached D-Bus menu endpoint
(or an exact unique title for menu-less items), and calls `scripts/tray-activate.py`.
Window ownership comes from the item's D-Bus process, including its children and
process start time. No global focus policy or application-specific launch command
is changed. The helper runs only on clicks; unknown items, timeouts and bar
teardown have a bounded fallback. GTK double/triple-click notifications are
consumed to prevent an extra show/hide toggle.

The regular installer/update build already compiles this module. Check the real
tray, three monitors, native menus and widget teardown in a private session with:

```sh
python3 tests/check-tray-activation.py /tmp/fusion-tray-check-new
```

## Media indicator

Now playing shows the current title and elapsed playback time. It refreshes once
per second, follows pause/resume and seeking, and shows the full title and artist
in its tooltip. Click to pause/resume, right-click for the next track, or
middle-click for the previous track.

The `mpris` configuration in `config.json` deliberately sets `interval: 1`:
Waybar defaults to refreshing only on player events, which leaves the clock
stationary between clicks or metadata changes. Its `{dynamic}` field contains
only title/artist, with a matching 20-column title limit so long titles are
shortened rather than omitted. Elapsed time is outside that text budget.

Total duration is omitted because live streams can advertise an unknown length
as a very large integer. This prevents that value from occupying the title's
space or appearing in the tooltip. The player still supplies the elapsed time.

These settings use Waybar's built-in MPRIS module and survive theme changes.
See [Waybar's MPRIS options](https://github.com/Alexays/Waybar/wiki/Module:-MPRIS).
