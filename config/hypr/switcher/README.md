# Task Switcher

New installations use **Ring Switcher** by default. Existing saved choices are preserved.

Open **Fusion Settings → Theme → Task Switcher**. Choose a style, adjust its
preview, and press **Apply Task Switcher**. The next **Super+Tab** uses that choice;
no compositor reload is required. **Show task switcher on** selects the active
monitor, the primary monitor, or the monitor under the pointer. Set the primary
monitor using its checkbox in **Displays & Arrangement**. The overlay is positioned
before its first frame; this choice does not change which windows are included. Hold Super while cycling, use Shift+Tab for
reverse order, and release Super to focus the selection. Escape cancels. Clicking
a window preview also selects it.

| Style | Appearance | Individual controls |
| --- | --- | --- |
| Fusion Cards | Existing icon cards | Columns |
| Application Switcher | Compiz's moving thumbnail strip | Preview size, icons only |
| Static Application Switcher | Stationary thumbnail grid | Columns, preview size |
| Ring Switcher | Elliptical carousel with depth | Ring dimensions, preview size, depth scale/brightness, direction |
| Shift · Cover | Perspective covers with a reflected floor | Window size, cover offset, reflection/intensity |
| Shift · Flip | Angled window deck | Window size, flip angle, reflection/intensity |
| Stack Window Switcher | Tilted, aspect-aware window rows | Tilt, inactive window rotation |
| Scale · Window Overview | Window overview | Spacing |

![Eight Task Switcher styles, using example windows and the Binary Knife theme](../../../docs/screenshots/task-switchers.png)

Shared controls cover the window scope, animation duration, overall size,
inactive window opacity, live previews, **Window preview FPS** (1–144, default
**60**), titles, and icons. Appearance
follows all desktop themes and color modes. Each style keeps its own settings.
Mouse-wheel gestures over the settings controls scroll the page without changing
their values. The preview buttons operate on example windows; they never switch
applications or save settings. Cards float directly over the desktop, without a
surrounding panel, header, footer, blur, or compositor shadow. Click empty space
to cancel, including in the larger preview. Reload detects external edits, and
Discard restores the last saved choices. Closing Fusion Settings includes these unsaved edits in
its existing confirmation.

All monitors/workspaces are included by default, including mapped hidden group
members and special workspaces. Optional scopes narrow this to the current
monitor, workspace, or application. Choosing a window only calls `focuswindow`;
windows retain their monitor, workspace, size, and tiled/floating state. The
switcher fits the focused monitor's logical dimensions and reserved panel area.
Grid styles page through large lists; keyboard cycling reaches every window.

## Implementation

This is a **Wayland adaptation** of all application-switching plugins found in
the supplied Compiz source: Application, Static Application, Ring, Shift's two
modes, and Stack. Scale is included as a window overview; Fusion Cards remains
available. Compiz's `vpswitch` and `mswitch` change viewports and belong to desktop
navigation rather than Super+Tab.

The original sources and option metadata are bundled in [compiz](compiz/NOTICE.md).
`geometry.py` adapts Ring's ellipse/depth equations, Shift's cover/flip equations,
and Stack's aspect-aware rows and tilt. `scene.py` projects captured window
textures onto these layouts. Application/Static/Scale use bounded strip/grid
layouts appropriate to a monitor-local popup. This does not load X11 Compiz
plugins into Hyprland, or reproduce their compositor-wide dimming/zooming of
other windows. Animation duration replaces Compiz's frame-dependent spring
speed/timestep; X11-only plugin options are not exposed as nonfunctional controls.

Thumbnails use the already-bundled `share-picker/window-preview` helper and
Hyprland's toplevel export protocol. A persistent helper keeps one Wayland
connection and reuses up to eight asynchronous SHM capture buffers within a
256 MiB budget. Raw thumbnail pixels avoid starting a process and encoding a
PNG for each frame. Each visible window has its own target FPS deadline, with a
2.2-second stalled-source timeout and bounded pipe output. At most 24 scaled
previews are held in memory. Nothing is written to disk; hiding the switcher
stops the stream and clears the cache. Missing or unavailable previews fall
back to app icons. Actual FPS depends on source frames, monitor refresh and
capture workload. The existing one-shot PNG mode remains available to the
screen-share picker. The installer builds the helper; the switcher and its
capture process exit with the compositor.

The session's shared native Cube adapter also wakes exported windows on inactive
workspaces, even when the Cube effect is disabled. Normal suspension returns
within two seconds after capture stops; no workspace or focus changes are used.
Its matching Hyprland headers/ABI are required for this inactive-window fix;
the ordinary export stream still works when the optional adapter is unavailable.

Settings are stored in `switcher/preferences.json` inside the Hyprland profile,
using a locked, atomic write and external-edit detection. Missing settings use
the existing Fusion Cards default. The shipped default JSON is safe for the
updater's preference-preserving three-way merge.

The adapted renderer/layout and this combined switcher are distributed under
**GPL-2.0-or-later**; original permissive portions retain their notices. Original
copyrights, licenses, source paths, and SHA-256 hashes are in
[compiz/NOTICE.md](compiz/NOTICE.md) and [compiz/COPYING](compiz/COPYING).

## Verification

```sh
cd config/hypr/switcher
QT_QPA_PLATFORM=offscreen QT_QPA_PLATFORMTHEME= python3 -m unittest test_switcher test_styles
```

`tests/check-preview-fps.py` at the repository root runs a disposable compositor
with three animated windows, including an inactive workspace, to measure live
capture at 10/60 FPS and verify stream shutdown and native wake-state cleanup.

For a standalone sample preview, run `app.py --demo --style ring`. To render an
image without interacting with the desktop, use
`QT_QPA_PLATFORM=offscreen app.py --style cover --preview /tmp/switcher.png`.
