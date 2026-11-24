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
