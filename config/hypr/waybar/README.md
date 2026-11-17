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
