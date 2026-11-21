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
Closing the app you copied from also keeps the current text or image available
for Ctrl+V. The session retains every offered format of an eligible copy, so
rich-text formatting is preserved along with plain text.

- **Pin / Unpin:** pins survive logout and appear first. Pins are saved locally
  with private file permissions in `clipboard/state/pins.json`.
- **Remove / Delete key:** removes the selected history entry, including a saved pin.
- **Clear recent:** clears recent entries and keeps pins. It does not change
  the system clipboard.
- **Pause history:** stops recording, including in-flight history reads, until
  resumed. This preference survives logout. The current clipboard still stays
  available for pasting; resuming history observes it again.

Recent items remain in memory for this Hyprland login. Limits are 100 recent
items, 32 MiB total, 25 pins / 16 MiB pinned, 1 MiB per text item and 8 MiB per
image (up to 16 million pixels). Oversized or unsupported items are ignored.
File cut/copy and primary selection are not collected. Sources marked sensitive
by password managers are ignored; unmarked text can still enter history.

The session owns a Wayland `wlr-data-control` history collector, a separate
current-clipboard keeper and the PyQt popup. The collector snapshots MIME offers
before requesting data, bounds reads and cancels obsolete transfers. The keeper
captures all formats before replacing an eligible source. Incomplete, oversized,
file and password-manager offers keep their original owner. Its current snapshot
is limited to 16 MiB; transfers have four-second deadlines and bounded nonblocking
paste writes. New copies replace old ones, and an explicitly cleared clipboard
stays empty. Selecting a history entry still uses the bundled `wl-copy`.
No network access, clipboard content logging or extra package is needed. Logout
stops the services; current clipboard contents are never saved to disk.

Build: `python3 config/hypr/clipboard/build.py` from the checkout.
Tests: `QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s config/hypr/clipboard`.
Native transfers: `python3 -m unittest discover -s tests -p test_clipboard_keeper.py`.
Copy/close/paste integration: `python3 tests/check-clipboard-persistence.py OUTPUT_DIRECTORY`
from a graphical terminal. This uses synthetic data on an isolated compositor,
including Wayland/XWayland source exit, rich text, images, newer copies, explicit
clearing, sensitive/file exclusions and size limits. It never reads or writes
the working desktop's clipboard.
