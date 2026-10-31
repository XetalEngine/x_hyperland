# Startup project showcase

Super+D shows the existing system, Matrix and clock consoles alongside **Try my
other projects :D**. Six perspective-rendered cubes float above soft colored
shadows. Hover tilts and highlights a cube; its name and click area stay still.
The panel follows Xetal Raw, Xetal Modern, BreakPoint and Binary Knife, including light and
high-contrast colors. Narrow windows use fewer columns and scroll vertically.

The catalog in `projects.json` links Echo, Linux Studio, Xetal BV (the website's
Binary Knife page), CachyOsTools, XMusic and Xetal Video Editor to their respective
pages on <https://www.xetal.net/community/site/>. Clicking, Enter or Space opens
the selected page in the default browser after hiding the special workspace.
Escape and the X hide the entire dashboard; Super+D shows it again.

**Control Panel → Startup Applications → Desktop startup** controls
whether it appears automatically at login. The default is enabled. Turning it
off skips both the login delay and pane creation; Super+D remains available.
The private preference is saved in `control_panel/state/startup-screen.json`
and survives desktop updates.

Icons are bundled unchanged from the supplied Xetal Community site, with Echo's
newer silver/cyan icon taken from the Echo project's `echoicon_2.png`. Their
sources and SHA-256 checksums are recorded in `assets/projects/SOURCE.json` and the root
asset manifest. Displaying the showcase requires no website connection or files
outside the installed profile. The installer includes the catalog, artwork and
Python source; PyQt6 is already a desktop dependency.

The three terminal consoles use Python, Pillow, Kitty and Fastfetch from the
installer's dependency list. The legacy ASCII mascot also uses Pillow directly;
none of the console modes requires NumPy or packages from the developer's PC.

Compositor events pause cube animation while the dashboard is hidden. The window
exits when its Hyprland session ends. Repeated Super+D toggles reuse the window.
An already-open legacy mascot console is closed only after the new showcase maps;
the other three consoles are reused. The original companion source/art remain
available for compatibility and the profile's account-image fallback.

```sh
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s config/hypr/startup -v
```
