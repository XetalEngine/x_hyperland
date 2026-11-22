# Window appearance and focus

Open **Fusion Settings → Theme → Window effects → Window appearance**.

Shape, spacing, opacity, shadows and focus styling now share one editor. The preview shows active and inactive windows; click either sample to change its focus. Editing this preview does not change your desktop until you choose **Apply appearance**. **Discard** returns to the saved values.

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
