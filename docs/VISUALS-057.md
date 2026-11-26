# Window appearance and focus

Open **Fusion Settings → Theme → Window effects → Window appearance**.

Fresh profiles enable **Coordinate borders, shadows and headers** and **Glow around
the active window**, with a **3 px glow**, **8 px shadow** and no application
exceptions. Both switches remain editable; existing saved focus choices are kept.

Shape, spacing, opacity, shadows and focus styling now share one editor. The preview shows active and inactive windows; click either sample to change its focus. Editing this preview does not change your desktop until you choose **Apply appearance**. **Discard** returns to the saved values.

Resize ordinary windows by left-dragging any edge or corner, without holding
Super. Fresh profiles enable **Resize from edges and corners**, with a **15 px**
grab area outside the border and a resize cursor on hover. Adjust **Resize grab
area** under Shape & spacing to change that margin without thickening the visible
border. Maximized and fullscreen windows keep their size; restore them first.
Fusion title bars include the same grab area above their top edge and corners;
their buttons and drag-to-move area keep their normal behavior.

Focus preferences are saved across themes and future logins. Applying a theme changes the accent colors, while your border width, shadow size, glow and application exceptions stay as you saved them. Existing Focus settings are carried into the combined editor.

## Try it

1. Change the corner rounding and border width; inspect both sample windows.
2. Enable **Coordinate borders, shadows and headers**, then try **Glow around the active window** and adjust its size.
3. Choose **Apply appearance** and switch between two real windows. Their borders, shadows and Fusion headers follow focus.
4. Apply another theme preset. Reopen Window appearance and confirm your values stayed the same; only the theme colors should change.
5. To exclude an application from glow and shadows, add its exact class under **No glow or shadow for**, one per line. The window lister shows application classes.
6. Change a value and choose **Discard**. The saved look should remain unchanged.

The **Visuals** tab and its Glass & materials, Quality & previews and Workspace tools pages are hidden for now. Their code and old preferences remain available for later work, but their settings do not override your effects. The new taskbar hover-preview option and automatic Overview shortcut are also parked. Existing Compiz effect controls remain under Window effects.

## Install from a working checkout

Normal desktop updates include these files. For a local checkout on the matching Hyprland 0.57.2 desktop, the existing helper remains available:

```bash
python3 ~/Desktop/x_hyperland/tools/install-visuals-preview.py
```

It checks saved appearance, native focus rendering, sharing, cube rendering and minimize/restore on private outputs before installing managed files with a backup. It preserves current focus choices and other saved desktop preferences. Results are under `~/.local/state/hyperfusion/visuals/`. The helper also includes the image-picker size correction. Follow its final login instructions if native modules were rebuilt.

## Validation

```bash
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -p test_visuals.py -q
python3 tools/install-visuals-preview.py --check-only
```

The first command checks preference migration, theme-independent settings, Apply/Discard, failed-save recovery and native configuration validation. The second needs a desktop terminal and uses a separate compositor for rendering checks. GPU rendering and the actual multi-monitor image picker still need a check on the target desktop.

`tests/check-border-resize.py WINDOW_CONTROLS_PLUGIN CURSOR_PROBE_PLUGIN`
checks all eight resize directions with and without Fusion title bars, the grab
area and cursor switches, maximized/fullscreen windows, application clicks,
overlapping windows, title-bar controls and plugin reload. It sends virtual input
only to a disposable compositor isolated from the login seat.
Add `--wobbly-plugin WOBBLY_PLUGIN` to check real rendered settling after every
resize; this mode opens a temporary Wayland output and verifies that the spring
mesh returns to the final window rectangle before its transformer is removed.
