# Validation

The initial package was checked on 26 October 2026 on the original Arch Linux desktop. Preparation and tests used disposable directories; the export did not replace or reload the running desktop's configuration.

## Automated checks

**128 tests passed:**

| Suite | Tests |
| --- | ---: |
| Installer | 13 |
| Control desk, hotkeys, audio and display settings | 46 |
| Application launcher, shortcut editing, pins and hotkeys | 31 |
| Theme, wallpaper and window controls | 14 |
| Application switcher | 2 |
| Screen-sharing picker | 10 |
| Workspace and screenshot helpers | 12 |

Installer coverage includes a different home directory, HDMI/eDP connectors, fractional scaling, offline automatic monitor configuration, the optional original monitor layout, disabled login animation, backup/restore, restoration after a failed activation, symlinked existing profiles, concurrent configuration edits, and asset checksums. Existing KDE settings and changes made after installing are retained in the install/restore tests.

GUI tests use Qt's offscreen backend. Tests do not log out, change live display modes, install packages, or replace the real user profile.

## Native build and configuration validation

Two complete `--prepare` builds succeeded: one with no compositor connection, exercising the automatic display fallback, and one reading the original desktop's three connected displays. Each built these components from the copied repository source:

- Qt 5 and Qt 6 platform theme plugins.
- Waybar draggable app pins and workspace controls modules.
- Wayland screen-sharing preview helper and protocol bindings.

The staged Python and JSON files parsed successfully, shell syntax checks passed, and `Hyprland --verify-config` accepted the complete staged configuration and its included files. No source files were borrowed from the live profile for that validation.

| Build component | Version used |
| --- | --- |
| Hyprland | 0.56.2 |
| Waybar | 0.15.0 |
| Kitty | 0.49.2 |
| Hyprpaper | 0.8.4 |
| Qt 5 | 5.15.19 |
| Qt 6 | 6.12.0 |

The bundled wallpaper's SHA-256 matches the original desktop image byte for byte. Wallpaper and font checksums are recorded in [`assets-manifest.json`](../assets-manifest.json).

## Reproduce

```bash
./x_hyperinstall.sh --check
python3 -m unittest discover -s tests -v
./tests/run-desktop-tests.sh
./x_hyperinstall.sh --skip-packages --prepare /tmp/xetal-build-check
```

Use a new destination for each prepare run. These checks cover packaging, native compilation and automated behavior; they are not a full login test on every distribution or GPU. Fedora and Debian/Ubuntu dependency recipes are included but have not been executed here. Their package versions must still pass the same checks before installation.
