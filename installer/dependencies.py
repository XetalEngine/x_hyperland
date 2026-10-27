"""Distribution packages and capability checks. No installation at import time."""
from pathlib import Path
import os
import re
import shlex
import shutil
import subprocess
import sys

PACKAGES = {
    'arch': '''hyprland hyprpaper hyprlock waybar kitty dolphin swaync grim slurp wl-clipboard
        xdg-desktop-portal-hyprland xdg-desktop-portal-gtk xdg-utils xdg-user-dirs
        python python-pyqt6 python-gobject python-pillow gcc pkgconf gtk3 gtk-layer-shell json-glib
        qt5-base qt5-wayland qt6-base qt6-wayland wayland wayland-protocols
        networkmanager network-manager-applet blueman bluez-utils pipewire-pulse wireplumber
        playerctl brightnessctl fastfetch htop libnotify polkit-gnome papirus-icon-theme noto-fonts ttf-dejavu'''.split(),
    'fedora': '''hyprland hyprpaper hyprlock waybar kitty dolphin SwayNotificationCenter grim slurp wl-clipboard
        xdg-desktop-portal-hyprland xdg-desktop-portal-gtk xdg-utils xdg-user-dirs
        python3 python3-qt6 python3-gobject python3-pillow gcc gcc-c++ pkgconf-pkg-config
        gtk3-devel gtk-layer-shell-devel json-glib-devel qt5-qtbase-devel qt5-qtbase-private-devel
        qt5-qtwayland qt6-qtbase-devel qt6-qtbase-private-devel qt6-qtwayland wayland-devel wayland-protocols-devel
        NetworkManager NetworkManager-tui network-manager-applet nm-connection-editor blueman bluez
        pipewire-pulseaudio wireplumber pulseaudio-utils playerctl brightnessctl fastfetch htop
        libnotify polkit-gnome papirus-icon-theme google-noto-sans-fonts dejavu-sans-fonts dejavu-sans-mono-fonts'''.split(),
    'debian': '''hyprland hyprpaper hyprlock waybar kitty dolphin sway-notification-center grim slurp wl-clipboard
        xdg-desktop-portal-hyprland xdg-desktop-portal-gtk xdg-utils xdg-user-dirs
        python3 python3-pyqt6 python3-gi python3-pil gir1.2-gtk-3.0 gir1.2-gtklayershell-0.1 build-essential pkg-config
        libgtk-3-dev libgtk-layer-shell-dev libjson-glib-dev qtbase5-dev qtbase5-private-dev qtwayland5
        qt6-base-dev qt6-base-dev-tools qt6-base-private-dev qt6-wayland libwayland-dev libwayland-bin wayland-protocols
        network-manager network-manager-gnome blueman bluez pipewire-pulse wireplumber pulseaudio-utils
        playerctl brightnessctl fastfetch htop libnotify-bin policykit-1-gnome papirus-icon-theme fonts-noto-core fonts-dejavu-core'''.split(),
}
COMMANDS = '''Hyprland hyprctl hyprpaper hyprlock waybar kitty dolphin swaync swaync-client grim slurp
    wl-copy xdg-open xdg-user-dir nmcli nm-applet nm-connection-editor bluetoothctl blueman-manager
    pactl wpctl playerctl brightnessctl fastfetch htop notify-send gdbus pgrep flock
    cc c++ pkg-config wayland-scanner fc-match'''.split()
LIBRARIES = ['gtk+-3.0','gtk-layer-shell-0','json-glib-1.0','Qt5Widgets','Qt6Widgets','wayland-client']
MINIMUM = {'Hyprland':(0,56,0),'waybar':(0,15,0),'kitty':(0,49,0),'hyprpaper':(0,8,0)}


def distro():
    data = {}
    for line in Path('/etc/os-release').read_text().splitlines():
        if '=' in line:
            key,value=line.split('=',1);data[key]=value.strip('"')
    values=[data.get('ID',''),*data.get('ID_LIKE','').split()]
    for name in values:
        if name in ('arch','cachyos','manjaro','endeavouros'):return 'arch'
        if name in ('fedora','rhel'):return 'fedora'
        if name in ('debian','ubuntu','linuxmint','pop'):return 'debian'
    return None


def check():
    errors=[]
    if sys.version_info < (3,11): errors.append('Python 3.11 or newer is required.')
    errors += ['Missing command: '+command for command in COMMANDS if not shutil.which(command)]
    result=subprocess.run([sys.executable,'-c',
        "import PyQt6.QtWidgets, PyQt6.QtNetwork; from PIL import Image; import gi; gi.require_version('Gtk','3.0'); gi.require_version('GtkLayerShell','0.1'); from gi.repository import Gio,Gtk,GtkLayerShell"],
        capture_output=True,text=True)
    if result.returncode:errors.append('Python GUI/image dependencies: '+result.stderr.strip().splitlines()[-1])
    if shutil.which('pkg-config'):
        for package in LIBRARIES:
            if subprocess.run(['pkg-config','--exists',package]).returncode:errors.append('Missing development library: '+package)
        for major in (5,6):
            package=f'Qt{major}Gui'
            version=subprocess.run(['pkg-config','--modversion',package],capture_output=True,text=True).stdout.strip()
            headers=subprocess.run(['pkg-config','--variable=includedir',package],capture_output=True,text=True).stdout.strip()
            if version and not (Path(headers)/f'QtGui/{version}/QtGui/qpa/qplatformtheme.h').is_file():
                errors.append(f'Qt {major} private development headers are missing.')
    for command,minimum in MINIMUM.items():
        if not shutil.which(command):continue
        result=subprocess.run([command,'--version'],capture_output=True,text=True,timeout=10)
        match=re.search(r'(?<!\d)(\d+)\.(\d+)\.(\d+)',result.stdout+result.stderr)
        if not match or tuple(map(int,match.groups())) < minimum:
            errors.append(f'{command} {".".join(map(str,minimum))}+ is required for the complete desktop (found {match[0] if match else "unknown"}).')
    if not any(Path(p).is_file() for p in ['/usr/lib/xdg-desktop-portal-hyprland','/usr/libexec/xdg-desktop-portal-hyprland']):
        errors.append('The Hyprland desktop portal backend is missing.')
    if not any(Path(p).is_file() for p in ['/usr/lib/polkit-gnome/polkit-gnome-authentication-agent-1',
        '/usr/libexec/polkit-gnome-authentication-agent-1','/usr/lib/policykit-1-gnome/polkit-gnome-authentication-agent-1']):
        errors.append('The graphical PolicyKit authentication agent is missing.')
    if not Path('/usr/share/icons/Papirus-Dark/index.theme').is_file():errors.append('Papirus icon theme is missing.')
    if shutil.which('fc-match'):
        for family in ('Noto Sans','DejaVu Sans','DejaVu Sans Mono'):
            result=subprocess.run(['fc-match','-f','%{family}',family],capture_output=True,text=True,timeout=10)
            if family not in result.stdout.split(','):errors.append('Missing font family: '+family)
    return errors


def install(yes=False):
    family=distro()
    if family not in PACKAGES:
        raise RuntimeError('No automatic package recipe for this distribution. Install the dependencies in docs/DEPENDENCIES.md, then use --skip-packages.')
    prefix=['sudo'] if shutil.which('sudo') else ['doas'] if shutil.which('doas') else None
    if prefix is None:raise RuntimeError('Install the dependency packages as administrator, then run with --skip-packages.')
    command={'arch':['pacman','-S','--needed'], 'fedora':['dnf','install'], 'debian':['apt-get','install']}[family]
    if yes:command+=['--noconfirm' if family=='arch' else '-y']
    command=prefix+command+PACKAGES[family]
    print('Package command: '+shlex.join(command),flush=True)
    if not yes and input('Install these desktop/build packages? [y/N] ').strip().lower() not in ('y','yes'):
        raise RuntimeError('Package installation cancelled. Your Hyprland configuration is unchanged.')
    subprocess.run(command,check=True)
