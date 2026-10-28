Hyprland-only configuration

KDE/Plasma and shared desktop settings are off-limits. Keep all Hyprland-specific
configuration and scripts in this directory. Do not run ML4W installers, GTK theme
sync scripts, shared environment changes, or scripts that restart portal/audio
services. The old ML4W files remain outside this active configuration.

Shortcuts (Super is the Windows key):
  Super + Ctrl + P        Floating YouTube MP3/MP4 downloader
  Super + Q or Return     Terminal (its own Kitty config)
  Super + R or Space      Xetal application menu (search, categories, KDE favorites)
  Super + E               Dolphin with its separate dark Hyprland profile
  Super + D               Show / hide the animated Xetal dashboard
  Super + Tab             Cycle all apps; release Super to focus the selected app
  Super + Shift + Tab     Cycle apps in reverse
  Super + Shift + S       Send the focused app to the Magic scratch workspace
  Super + S               Show / hide Magic; its bar button remains while occupied
  Super + C               Close active window
  Super + Shift + K       Force-kill the application under the pointer
  Super + V               Toggle floating
  Super + F               Fullscreen
  Super + J               Toggle tiling split
  Super + K               Open the tabbed hotkey editor / control desk
  Super + A               Audio levels, output/input device picker
  Super + N               Notification center
  Super + Ctrl + N        Wired / Wi-Fi / VPN controls
  Super + /               Window shortcuts for the window under the pointer
  Super + Shift + arrows  Move a window in the indicated direction
  Super + Ctrl + arrows   Resize a window by 40 pixels
  Super + Alt + Left/Right Move a window to the previous/next monitor
  Super + L               Lock screen
  Super + M               Confirm logout (Cancel is selected by default)
  Print                   Capture a selected region; Esc cancels
  Shift + Print           Capture all displays

Screenshots are saved under your Pictures/Screenshots directory and copied to
the clipboard. Existing workspace, move/resize and media shortcuts are retained.

Media downloader: Super+Ctrl+P, Apps → Xetal Media Downloader, or run
~/.config/hypr/scripts/media-download.sh. Choose MP3 for the XDG Music folder
or MP4 for the XDG Videos folder, enter a YouTube link and select Download.
YouTube IDs, regular links, Shorts and youtu.be links are accepted; playlists
are not downloaded. MP3 uses the best audio source and ffmpeg VBR quality 0.
MP4 uses the best video and audio streams, with no resolution cap, and remuxes
to MP4 without video re-encoding. Existing completed files are not overwritten.
Selected text is captured from Wayland PRIMARY before the popup opens.
For apps that do not publish PRIMARY selection, use Copy and the Paste button.
Selecting text or opening the popup never starts a download automatically.
The progress display and compact log show downloads and post-processing. Cancel
stops the job and its ffmpeg children; closing an active job asks first. Reopening
the shortcut focuses the existing popup and keeps an active download intact.
Update yt-dlp fetches an official stable release, checks its SHA-256 and version,
then atomically installs it under ~/.local/state/hyprland-media/bin/yt-dlp.
The previous private version is retained. System packages and dmp3/dmp4 aliases
remain managed separately. FFmpeg and a supported Deno/Node/QuickJS runtime are
required. The popup remembers format and window size, not the selected address.

The session helper starts the local Waybar, Hyprpaper, desktop context menu and, if needed, notifications and an
authentication agent. It stops its own child processes when this Hyprland instance
ends. It does not install or enable systemd services or global autostart entries.

The panel has a real application tray, workspace window icons, media controls,
CPU/RAM/temperature/disk meters, internet and separate LAN/Wi-Fi indicators, VPN,
Bluetooth status, speaker volume slider, microphone level, keep-awake toggle,
notifications and a clock/calendar. Click most indicators to open their controls.
Scroll the speaker or mic indicator to adjust its level; right-click to mute.
Left-click notifications to open them; right-click to toggle Do Not Disturb.

Right-click uncovered wallpaper for File Manager, Wallpaper and Display Settings.
The native menu has a thin accent strip and follows the current desktop theme.
It works on each monitor, stays below app windows until opened, closes on an
outside click or Escape, and stops when this Hyprland session ends.

Control desk → Context Menu edits its contents and appearance. Drag items to
reorder them or into submenus; add app shortcuts, custom commands, folders,
websites, section headings, dividers, spacers and column splits. Items can be
disabled without deleting them. The appearance controls change column width,
row and icon sizes, font, padding, rounding, opacity, shadow and accent strip.
Choose custom colors or follow the system's light/dark/high-contrast theme.
The preview never runs commands. Apply changes saves the draft; Discard returns
to the saved menu. Changes appear on the next wallpaper right-click. Removing
an item also removes its assigned global hotkeys on Apply. Backups are saved in
~/.local/state/hyprland-control/context-menu-*.json. Save/Load preset transfers
the complete menu as JSON; loading and resetting defaults create drafts.
After applying menu edits, Configure hotkey opens the shared shortcut recorder.
These bindings appear in Hotkeys → Applications with the same validation,
external-edit detection, recovery key and rollback as the rest of the desktop.

The control desk has Hotkeys, Audio, Network, Bluetooth, Displays, Input, Theme,
Context Menu, Calendar and System tabs.
Hotkey categories include Window hover, Applications, Workspaces, Media & Devices,
and System. Live shows every binding loaded by the compositor, including runtime
additions. History can load previous versions as drafts for review and restoration.
Reset defaults loads the 76 saved bindings captured on 27 October 2026 from
control_center/keybindings-defaults.conf. It asks for confirmation and creates a
draft; Apply changes activates it, and Discard changes returns to your saved set.
Save current exports all editor bindings, including pending edits, to a .conf
preset. Load preset imports that file as a reviewable draft. Presets preserve
names, categories, disabled bindings, mouse shortcuts and shortcut modes. The
local shortcut-recording recovery key is always retained. Saving a preset does
not apply pending edits or replace the fixed defaults.

The editor modifies only keybindings.conf. Apply or Ctrl+S checks conflicts and
validates the complete config before saving/reloading. It saves previous versions
under ~/.local/state/hyprland-control/ and rolls back if the live reload fails.
It refuses to overwrite external edits. Record shortcut temporarily switches to
a recovery submap; Escape or the ten-second timer restores normal shortcuts.
Global bindings require Super so typing and application Ctrl/Shift shortcuts
stay available. Dedicated media, Print Screen and function keys are exempt.
Any edit opens an animated Pending changes log below the bindings. It shows
additions, removals and before/after values as you type. Apply clears it only
after a successful save; Discard changes restores the saved bindings and hides
the log. Remove asks for confirmation. The inspector scrolls when space is tight.

Window hints read the same saved bindings as the editor. The Super+/ binding uses
physical US slash key code 61. The table accepts wheel scrolling and scrollbar
input. The 18-second dismissal timer pauses while the pointer is inside it;
Escape, the close button, or another Super+/ dismisses it immediately.
Mouse/window operations are listed with their actual current modifiers.

Super+Shift+K force-kills a stuck application under the pointer. It sends SIGKILL
without a save prompt, so unsaved work and other windows of the same process may
be lost. Empty desktop, top bars and notification surfaces do not target an app
behind them. The helper rechecks the hovered window before sending the signal;
it never substitutes the keyboard-focused window when there is no target.

The window is branded Xetal / Session tools. Control desk, Apps, Theme, and the
app switcher have a visible close button. Their Qt dialogs and file pickers also
have a close header; normal cancel, discard-confirmation, and display-revert
handlers still run when X is clicked.

Audio now includes its per-application mixer in the Audio tab. Playback and
Recording show one column per application with its icon, vertical volume fader,
mute, and device route. Multiple streams from one app stay together; channel and
stream balance are retained when changing the group level. The strip scrolls
horizontally with its scrollbar, mouse wheel, or touchpad. App/device changes
update live, and meter probes do not appear as recording apps. Audio event
listeners run only while this page is visible. No audio service is restarted.
Audio device selection routes existing streams to the chosen device. Network,
audio and power actions run only when selected. Bluetooth is not started by setup;
the Bluetooth tab can start it on demand without enabling it at boot.
External GTK controls keep preferences under hypr/apps using the keyfile backend.

The application menu reads favorites from the active KDE Kickoff menu without
writing KDE settings. Right-click app tiles for Open, Open in terminal, pin/unpin,
Duplicate into Favorites, Properties, Change icon, Always run in terminal,
Copy command, Show shortcut file, and Restore original settings. F2 edits the
selected shortcut; Ctrl+N or New shortcut creates a favorite from a command.
Properties is the last item in each app's context menu. Group creation is
available from empty space or New group in the header.
Favorites can be dragged to reorder or moved between named groups. Use + New
group or right-click empty space to create a group. Drag its title to move the
whole group, double-click to rename, or use its ellipsis menu. Removing a group
keeps its apps in another group. Right-click a favorite -> Tile size chooses
Medium or Small; four icon-only small tiles fit one medium tile's footprint.
Drops save the chosen cell, so small tiles can form a vertical column without
filling the row first. Intentional gaps stay empty. The drop outline shows the
destination; an occupied cell makes room without repacking unrelated tiles.
New shortcut is available on empty space and beside New group in the header,
not on an app's menu. The page title replaces the greeting above the slim search
field. Permanent navigation/drag hints and the footer have been removed.
Each column is three medium tiles wide. Widen the menu to reveal more columns;
shrinking hides columns without moving their contents. Drop a tile or group in
an empty column to use it. Order, titles, sizes and columns save automatically
in launcher/favorite-layout.json, separate from KDE settings. Search and other
categories continue to show the alphabetical app grid.
Medium favorite tiles show their enabled launch hotkey below the app name. A +N badge
indicates additional bindings; hovering lists them all. Right-click any app for
Set/Change launch hotkey. Record a shortcut or enter its modifiers and key,
enable/disable it, add another binding, or remove one after confirmation.
These edits use the same validated keybindings.conf store and appear under
Control desk -> Hotkeys -> Applications. Both views update when saved bindings
change; an unsaved Control desk draft is preserved until Reload or Discard.
New app hotkeys launch the saved shortcut by ID, retaining its current command,
working folder and terminal preferences. Existing direct launch bindings are
recognized by command, including the terminal and isolated Dolphin aliases.
The editor supports a name, description, command, working folder, themed/custom
icon, terminal preference and terminal keep-open option. Icon selection includes
a searchable installed-icon gallery and image files. Shortcut copies are separate
entries; deleting one requires confirmation and does not remove the application.
All overrides and copies live in launcher/shortcuts.json; chosen image icons are
cached in launcher/icons/. Installed desktop entries and KDE favorites are never
written. Terminal launches use the local Kitty config; Dolphin keeps its isolated
profile. Commands use desktop-entry arguments, not an implicit shell; use an
explicit shell command if shell syntax is intended.
Ctrl+click any app tile, including search results, to launch it floating once.
Right-click -> Launch floating does the same. Normal clicks and keyboard launches
use the saved preference; Ctrl+drag still rearranges favorites without launching.
Floating launches are centered. Their first launch uses the app's requested size;
later launches use the current or last remembered floating size, including a tall
size you deliberately chose. Tiled, maximized and fullscreen geometry is ignored.
Sizes survive logins in launcher/floating-sizes.json, separately for each shortcut
and its terminal mode. The size tracker starts on demand and exits with this
Hyprland session. A single-instance app which reactivates its existing window can
be floated and centered as well; a slow new instance is left to finish launching.
Always start floating saves the preference for that shortcut; the
same option appears in Properties. Copies can have independent preferences,
and saved app hotkeys use the same launch settings. Super+V toggles any focused
window, including an existing window reused by a single-instance application.
Typing searches all installed visible applications, even while Favorites is selected.
Escape dismisses the menu. Its settings live in launcher/.
Clicking outside Apps dismisses it, including the desktop wallpaper and clicks
during its brief opening delay. Non-consuming compositor click events cover
wallpaper clicks that leave keyboard focus on the menu. Dialogs, screenshots,
and tile drags temporarily protect it; losing focus is checked again afterward.
Print and Shift+Print keep Apps visible until screenshot capture finishes.
Drag its edges, corners or bottom-right grip to resize it. The size is remembered
in launcher/window.json, including heights down to 480 pixels. The tile area and
sidebar navigation scroll independently in shorter windows without overlapping
the header or bottom edge. The icon file chooser includes an image preview, size,
dimensions, creation time (when recorded by the filesystem) and modified time.

Right-click any app → Pin to bar places its icon immediately after Keys. These
pins are independent of Favorites. Drag icons left/right to reorder; a mint edge
marks the drop position. Right-click a bar pin to open it, open in terminal, edit
its shortcut, move left/right, or unpin. The order persists across logins and
updates on every monitor. Custom names, icons and launch settings are shared with
the Hyprland app menu. Missing applications remain removable from the bar.
State: launcher/bar-pins.json (atomic writes with a lock). Native GTK widget:
waybar/pins/pins.c, using Waybar's CFFI v2 interface. Rebuild after editing it:
bash ~/.config/hypr/waybar/pins/build.sh
The compiled module stays inside this profile and exits with Waybar.

The Xetal dashboard waits five seconds after Hyprland login, then opens on the second connected display (or the only display),
in four steps: Fastfetch, Matrix rain, clock/date, then the Xetal Engine banner
and animated original ASCII cyber-cat. Super+D or Escape inside a console hides
it; Super+D reuses existing consoles and recreates any that were closed.
Click the companion or press Space in its console to switch between ASCII and
the supplied Xetal mascot PNG, displayed static with its original transparency.
The last selected view is saved immediately in startup/state/companion.json and
restored next time. The original artwork is in startup/assets/xetal-mascot.png.
The image fits the available space without cropping or changing its proportions.
Dragging, scrolling and right-clicking do not cycle it. Mouse reporting and the
image are cleaned up when the companion console exits.
Super+D stays immediate; the delay applies only to the --login autostart. Exiting
Hyprland during the delay cancels the sequence through its compositor connection.
Animations pause while the dashboard is hidden. It uses a dedicated special
workspace; applications launched from its app menu open on the regular workspace.
startup/kitty.conf and startup/fastfetch.jsonc apply only to these consoles.
Window positions are in startup/window-rules.conf; launch sequencing in startup/launch.py.
Remove the startup-scene.sh exec-once line to disable automatic opening.

Dolphin's separate config/data/cache/state live in dolphin/. KDE bookmarks were
copied, not linked. The Plasma wallpaper action is disabled only in this profile.
Right-click an image → Set as Hyprland wallpaper… opens a preview, display selector,
and fit selector. Apply saves only wallpaper/hyprpaper.conf and selection.json.
The app menu also has a Theme button. Hyprpaper exits with this session.
Existing KDE Dolphin windows keep their own profile; Super+E opens the Hyprland one.
Folder links from applications use the same isolated Dolphin profile. The
directory MIME default and desktop entry live in desktop/{config,data}, added
only to Hyprland's XDG search paths. Existing application settings locations and
shared MIME preferences stay unchanged. Apps already running before this change
need to quit and reopen once to inherit the new folder-handler search paths.

Displays: drag monitor rectangles, select a display and set resolution, refresh,
scale, rotation or mirroring. Apply starts a 20-second preview. Keep saves it;
Revert, timeout, closing the dialog or loss of the parent app restores the previous
arrangement. A separate guardian owns rollback. External edits and hotplug changes
block stale saves. Input controls keyboard layout/repeat and mouse/touchpad behavior.
These settings live in control_center/{displays,input,appearance}.conf.

Theme: Dark, Light and High contrast include complete Qt palettes, GTK appearance,
bar/notification colors and this profile's Dolphin colors. Native Qt 5/6 platform
theme plugins live under theme/ and rebuild against the installed Qt headers.
New Qt apps use these plugins; running apps that loaded an earlier plugin must be
reopened once. Our tools and compatible Qt apps then follow theme changes live.
GTK apps normally need reopening; applications with their own fixed styles retain
those styles. No shared KDE/GTK/Qt preference file is written. Window effects are
inside Theme. Wallpaper previews show the current picture on each monitor; choose
one monitor or All displays, preview, then Apply or Discard. Image pickers include
the right-hand preview and filesystem properties. A failed apply restores files
and any wallpaper outputs already changed.

The tiny red × beside an empty numbered workspace removes it from the bar and
forgets its saved persistence. Workspaces with windows and the last workspace on
each monitor have no ×. Removing the current empty workspace selects another
workspace on that same monitor. Clicks recheck live occupancy; no windows are
closed or moved. Workspace + and × share a lock and use validated, backed-up
configuration changes. Rebuild their local Waybar module with:
bash ~/.config/hypr/waybar/workspaces/build.sh

The + beside workspaces creates an empty persistent workspace on that bar's
monitor. Each workspace shows an icon for every mapped window, including inactive
workspaces; clicking an icon focuses that exact window. Occupied special workspaces
stay discoverable. Workspace assignments live in control_center/workspaces.conf.
Super+Tab includes apps from all monitors and workspaces, including Magic. Releasing
Super reveals and focuses the selection in its original workspace and monitor;
it never moves that app. Escape cancels. The switcher ends with this compositor.

Kitty's Hyprland profile has a visible, interactive scrollbar whenever scrollback
is available, a 10,000-line history for new terminals, a smooth blinking cursor
and a cursor trail. Apps > Kitty, Super+Q and Super+Return all use kitty.conf.
Theme generates theme/kitty-colors.conf and reloads only this session's terminals
using that profile. Zsh is the shell inside Kitty; its familiar prompt and aliases
remain available. The startup consoles retain their own animation profile.
Their original ASCII companion is named Xetal.

Screenshot notifications: click the banner to open the image; the folder action
opens this profile's Dolphin with that file selected. Both work in notification
history after a banner expires. One session-owned broker handles all new captures
and exits when the compositor disconnects.

Screen sharing: xdph.conf selects scripts/share-picker.sh for Hyprland's portal.
It shows updating screen and window previews, a draggable region selection,
searchable app cards, Cancel and an explicit Share selected button. Thumbnails
stay in memory and are captured only while visible. Remember this selection is
off by default. Choosing a source returns the upstream XDPH selection contract;
the portal owns the actual stream and permissions. Echo needs no code change for
this picker. The active backend reads xdph.conf at startup: activation requires
a new backend/session or explicit user approval for a backend restart. Do not
restart shared portal/audio services as part of setup.
Preview without streaming: ~/.config/hypr/scripts/share-picker.sh --preview
Rebuild the window capture helper: bash ~/.config/hypr/share-picker/build.sh
Its protocol definitions retain their upstream licenses under share-picker/protocols/:
https://github.com/hyprwm/hyprland-protocols
https://github.com/swaywm/wlr-protocols


See the repository README.md for installation, compatibility, validation and restore instructions.

Xetal designs
Choose Control desk > Theme > Design for Xetal Raw (original cyan) or Xetal Modern
(rounded blue cards, account GIF and Home overview). Each supports Dark, Light and
High contrast. Apply theme keeps the same hotkeys, favorites and desktop engine.
Click your account picture in Apps to open Home. Change the image/GIF on the
Design page. Reopen older applications if they have not picked up the palette.
