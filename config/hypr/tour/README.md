# Hyper Fusion tour

The welcome dashboard’s **Take the Tour** and **Send Feedback** buttons open
`index.html` in the user’s default browser. Everything needed for the guide is
bundled here. No server, CDN, telemetry, login, or desktop command bridge is used.
The Echo download link is the only external destination, and opens on request.

The guide includes 51 lessons in eight chapters, a guided first visit, full-text
search, level/video filters, screenshots, ten captioned short demonstrations,
interactive workspace explanations, a printable shortcut reference, and the
Control Panel tool directory. Reading progress and the light/dark reading choice
use browser-local storage and tolerate storage being disabled. The feedback
template stays in memory until copied; it never submits or sends a message.

## Maintain content

Edit `build_content.py`, then run `python3 config/hypr/tour/build_content.py` from
the repository root. Each lesson lists the implementation or documentation used
to verify it. The builder imports the shipped hotkey metadata and Control Panel
inventory. Do not replace these with a particular user’s saved preferences.
Run `python3 config/hypr/tour/test_tour.py` and
`python3 config/hypr/startup/test_projects.py` after changes.

Keep media local and lightweight: WebP pictures, H.264 MP4 plus VP9 WebM video
fallbacks, and English WebVTT captions. Videos are silent and have visible
instruction captions; accompanying steps provide a text alternative. They play
only when requested. Inspect `file://` use in a real browser, including search,
both reading modes, keyboard use, small widths, and video playback. No build
tool or network connection is required at runtime.

## Media provenance

The interface captures show this repository’s actual Qt/C++ applications and
native Hyprland plugins. New recordings used a disposable profile, sample
documents, a private D-Bus session, and a separate nested compositor. Recording
and settings changes did not touch the working desktop, bootloader, or VMs.
The two small interactive workspace diagrams are explicitly marked illustrations.

Earlier screenshots were reused from `docs/screenshots` for Apps, context menus,
Control Panel, taskbar options, wallpaper browsing, file-transfer settings,
shortcut properties, the task switcher, System ISO, and updates. The GRUB
appearance screenshot was supplied by the user. The scenery comes from the
bundled Hollow Grove wallpaper. Updated screenshots show Recorder, Icons,
Window Rules, the dock gallery, Fusion Settings, and KVM Settings using sample
configuration. The feedback illustration is the guide’s own feedback page.

## Integration

`launch.py` accepts only the home, feedback, or shortcut entry points and passes
an encoded local file URL to `xdg-open` as a separate argument. The current
Fusion design and mode set the initial reading palette. Opening the guide hides
the welcome workspace through its existing helper, so the browser opens in the
normal desktop. No system associations or shared desktop settings are changed.
