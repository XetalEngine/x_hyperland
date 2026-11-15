# Clipboard history

Click the **clipboard icon beside Notifications** on Waybar, press
**Super+Shift+V**, or open **Clipboard history** from Apps. Search recent
text and images, use the arrow keys to choose an entry, then **Enter** (or Copy).
The popup closes and returns focus to the previous app; press **Ctrl+V** there.
Escape closes without changing the clipboard. No keystrokes are injected.

History opens as a compact, themed dropdown on the current monitor, beside the
clicked bar icon (above a bottom bar). Click an entry to select it, then use
Copy, Enter, or double-click it. Click outside, change workspace, click the bar
icon again, or press Escape to close. The popup shares the Apps/Power menu
surface styling and normal compositor open/close effects, including Burn when
enabled. It has no KDE titlebar and never restores a saved window position.
Closing the popup keeps the background collector and recent history alive.

- **Pin / Unpin:** pins survive logout and appear first. Pins are saved locally
  with private file permissions in `clipboard/state/pins.json`.
- **Remove / Delete key:** removes the selected history entry, including a saved pin.
- **Clear recent:** clears recent entries and keeps pins. It does not change
  the system clipboard.
- **Pause history:** stops observation, including in-flight reads, until resumed.
  This preference survives logout. Resuming observes the current clipboard.

Recent items remain in memory for this Hyprland login. Limits are 100 recent
items, 32 MiB total, 25 pins / 16 MiB pinned, 1 MiB per text item and 8 MiB per
image (up to 16 million pixels). Oversized or unsupported items are ignored.
File cut/copy and primary selection are not collected. Sources marked sensitive
by password managers are ignored; unmarked text can still enter history.

The session owns a small Wayland `wlr-data-control` collector and the PyQt popup.
The collector snapshots MIME offers before requesting data, bounds reads and
cancels obsolete transfers. Only selecting Copy takes clipboard ownership,
using the already bundled `wl-copy`; observing history never replaces a source.
No network access or clipboard content logging is used. Logout stops both.

Build: `python3 config/hypr/clipboard/build.py` from the checkout.
Tests: `QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s config/hypr/clipboard`.
