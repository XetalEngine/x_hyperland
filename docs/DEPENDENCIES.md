# Dependencies and portability

Run `./x_hyperinstall.sh --check` before installing. The package recipes are in [`installer/dependencies.py`](../installer/dependencies.py); the same file checks executable versions, Python imports, development libraries, Qt private headers and the portal/authentication helpers.

| Area | Required components |
| --- | --- |
| Desktop | Hyprland 0.56+, Hyprpaper 0.8+, Hyprlock, Waybar 0.15+, Kitty 0.49+, Dolphin, SwayNotificationCenter |
| Python | Python 3.11+, PyQt6 Widgets/Network/DBus, PyGObject with Gio/GTK 3/GtkLayerShell, Pillow |
| Native builds | C/C++17/20 compiler, pkg-config, GTK 3, gio-unix, gtk-layer-shell, json-glib, Wayland client/scanner; Qt 5 and 6 Widgets/Concurrent, development tools and private QtGui/QtCore headers |
| Capture | grim, slurp, wl-clipboard, xdg-desktop-portal-hyprland, GTK desktop portal |
| Audio | PipeWire PulseAudio compatibility, pactl, WirePlumber/wpctl, playerctl |
| Media downloader | yt-dlp, FFmpeg/ffprobe, and a supported Deno, Node.js or QuickJS runtime; wl-paste for selected links |
| Network | NetworkManager/nmcli, network-manager-applet, nm-connection-editor, BlueZ/bluetoothctl, Blueman |
| Desktop updates | Git, Python standard-library HTTPS, access to the GitHub repository; native builds use the dependencies above. No automatic system-package installation. |
| Session/tools | libnotify/notify-send, GDBus, GNOME PolicyKit agent, xdg-utils, xdg-user-dirs, util-linux/flock, procps/pgrep, brightnessctl, Fastfetch, htop, sudo and xhost for elevated graphical tools |
| Appearance | Papirus icon theme, Noto Sans, DejaVu Sans/Mono, Fontconfig; licensed Fira Code Nerd Font, Inter 4.1 and JetBrains Mono 2.304 files are bundled |

The custom Waybar modules use its CFFI v2 interface and its 0.15 workspace taskbar structure. Qt theme plugins use private APIs and are built against the installed Qt versions; session startup checks and rebuilds them after Qt changes. Their source is included.

The private GTK 3 preview module is built by the same theme builder. Qt previews use Qt Concurrent for background loading; both dependencies are supplied by the existing GTK/Qt development package recipes. See [file picker coverage](FILE-PREVIEWS.md).

The optional **Compiz Burn** close effect supports Hyprland **0.56.2** at the tested commit documented in [its guide](../config/hypr/effects/burn/README.md), x86-64 and the OpenGL renderer. It needs a C++23 compiler, matching Hyprland development headers exposed through `pkg-config hyprland`, and GLESv2 development files. Its build and runtime ABI checks reject mismatched versions; unsupported installations retain normal closing animations and still install the rest of the desktop. Controls are in **Theme → Window effects → Burn**.

**Desktop Cube & 3D Windows** uses the same tested Hyprland ABI and C++23/OpenGL requirements as Burn, plus json-c and libei development headers (`json-c`, `libeis-1.0`). Its sources and optional build are included in the installer. A missing dependency or unsupported compositor leaves ordinary workspace switching available. See the [Cube guide](../config/hypr/effects/cube/README.md).

Xetal Images uses the installed Qt image readers. Common image formats are included with Qt; additional readers such as HEIF, AVIF, camera RAW and PSD depend on the distribution's Qt image-format plugins.

Xetal Files speaks the [KDE JobView interfaces](https://invent.kde.org/frameworks/kjobwidgets) used by Dolphin/KIO and Ark. It starts only for this Hyprland session and leaves any existing job-service owner in charge. Applications that draw their own progress windows independently of these interfaces retain their own UI. No KDE configuration or system service is replaced.

The media popup can update its private copy from the [official yt-dlp releases](https://github.com/yt-dlp/yt-dlp/releases), with SHA-256 verification and an atomic replacement. Current YouTube extraction also needs the [EJS scripts and a supported JavaScript runtime](https://github.com/yt-dlp/yt-dlp/wiki/EJS). The official update archive includes EJS; Deno, Node.js or QuickJS and FFmpeg remain distribution dependencies.

Automatic package recipes cover Arch derivatives, Fedora, and Debian/Ubuntu. Repository availability and versions differ by release. The installer does not add third-party package repositories, run an AUR helper, install pip packages into system Python, or silently downgrade the desktop's features. If a recipe cannot satisfy the requirements, install compatible packages through your distribution and rerun with `--skip-packages`. Other distributions use this same manual-dependency path.

Recent rolling distributions are the easiest match. Older stable distribution releases may ship Hyprland/Waybar/Kitty versions below the requirements. A successful package-manager command alone does not bypass the subsequent version and build checks.

Hardware modes are captured only from the recipient's running compositor. Without that connection, preferred-mode auto placement is used. The included original DP-4/DP-5/DP-6 profile is explicit opt-in. Ordinary Linux home paths are supported; paths containing spaces or configuration metacharacters are rejected before any files are copied, because the upstream configuration formats interpret those characters differently.

Upstream references: [Waybar](https://github.com/Alexays/Waybar), [Hyprpaper](https://github.com/hyprwm/hyprpaper), [Arch Waybar package](https://archlinux.org/packages/extra/x86_64/waybar/), [Arch Kitty package](https://archlinux.org/packages/extra/x86_64/kitty/), [Fedora Qt private headers](https://packages.fedoraproject.org/pkgs/qt6-qtbase/qt6-qtbase-private-devel/), [Debian Qt development packages](https://sources.debian.org/src/qt6-base/6.11.2%2Bdfsg-5/debian/control).

Font package references: [Arch DejaVu](https://archlinux.org/packages/extra/any/ttf-dejavu/), [Fedora DejaVu](https://packages.fedoraproject.org/pkgs/dejavu-fonts/), [Debian DejaVu](https://packages.debian.org/en/stable/fonts-dejavu-core).
