# Taskbar media indicator

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
