"""Distribution packages and capability checks. No installation at import time."""
from pathlib import Path
from ctypes.util import find_library
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import runtime_install

PACKAGES = {
    'arch': '''git gvfs gvfs-smb hyprpaper hyprlock waybar kitty dolphin konsole swaync grim slurp wl-clipboard
        xdg-desktop-portal-hyprland xdg-desktop-portal-gtk xdg-utils xdg-user-dirs
        python python-psutil python-pyqt6 python-gobject python-pillow gcc cmake libxcb pkgconf gtk3 gtk-layer-shell libepoxy json-glib json-c
        qt5-base qt5-wayland qt6-base qt6-wayland qt6-svg qt6-tools wayland wayland-protocols
        networkmanager network-manager-applet blueman bluez-utils pipewire-pulse wireplumber
        playerctl brightnessctl fastfetch htop libnotify polkit-gnome papirus-icon-theme noto-fonts ttf-dejavu
        yt-dlp ffmpeg deno sudo xorg-xhost xorg-xcursorgen hyprcursor openssl virt-viewer virt-firmware gnutls
        base-devel autoconf automake libtool make perl gettext gawk expect socat
        libtasn1 gmp libseccomp fuse3 libei tpm2-tools dmidecode pciutils usbutils
        mtools dosfstools util-linux kmod'''.split(),
    'fedora': '''git gvfs gvfs-smb hyprpaper hyprlock waybar kitty dolphin konsole konsole-part SwayNotificationCenter grim slurp wl-clipboard
        xdg-desktop-portal-hyprland xdg-desktop-portal-gtk xdg-utils xdg-user-dirs
        python3 python3-psutil python3-pyqt6 python3-gobject python3-pillow gcc gcc-c++ cmake libxcb-devel pkgconf-pkg-config procps-ng glslang-devel
        gtk3-devel gtk-layer-shell-devel libepoxy-devel json-glib-devel json-c-devel qt5-qtbase-devel qt5-qtbase-private-devel
        qt5-qtwayland qt6-qtbase-devel qt6-qtbase-private-devel qt6-qtwayland qt6-qtsvg qt6-qttools-devel qt6-linguist wayland-devel wayland-protocols-devel
        NetworkManager NetworkManager-tui network-manager-applet nm-connection-editor blueman bluez
        pipewire-pulseaudio wireplumber pulseaudio-utils playerctl brightnessctl fastfetch htop SDL3
        libnotify hyprpolkitagent papirus-icon-theme papirus-icon-theme-dark google-noto-sans-fonts dejavu-sans-fonts dejavu-sans-mono-fonts
        yt-dlp+default ffmpeg-free nodejs sudo xhost xcursorgen hyprcursor openssl virt-viewer python3-virt-firmware gnutls-utils
        autoconf automake libtool make perl gettext gawk expect socat openssl-devel
        libtasn1-devel gmp-devel glib2-devel gnutls-devel libseccomp-devel fuse3-devel libei-devel libeis-devel
        tpm2-tools dmidecode pciutils usbutils mtools dosfstools util-linux kmod'''.split(),
    'debian': '''git gvfs gvfs-backends gvfs-fuse hyprpaper hyprlock waybar kitty dolphin konsole konsole-kpart sway-notification-center grim slurp wl-clipboard xwayland
        xdg-desktop-portal-hyprland xdg-desktop-portal-gtk xdg-utils xdg-user-dirs
        python3 python3-psutil python3-pyqt6 python3-pyqt6.qtsvg python3-gi python3-pil gir1.2-gtk-3.0 gir1.2-gtklayershell-0.1 build-essential cmake libxcb1-dev libxcb-res0-dev pkg-config glslang-dev libsdl3-0
        libgtk-3-dev libgtk-layer-shell-dev libepoxy-dev libjson-glib-dev libjson-c-dev qtbase5-dev qtbase5-private-dev qtwayland5
        qt6-base-dev qt6-base-dev-tools qt6-base-private-dev qt6-wayland libqt6svg6 qt6-tools-dev qt6-l10n-tools libwayland-dev libwayland-bin wayland-protocols
        network-manager network-manager-gnome blueman bluez pipewire-pulse wireplumber pulseaudio-utils
        playerctl brightnessctl fastfetch htop libnotify-bin hyprpolkitagent papirus-icon-theme fonts-noto-core fonts-dejavu-core
        yt-dlp ffmpeg nodejs sudo pkexec x11-xserver-utils x11-apps hyprcursor-util openssl virt-viewer python3-virt-firmware gnutls-bin
        autoconf automake libtool libtool-bin make perl gettext gawk expect socat libssl-dev
        libtasn1-6-dev libgmp-dev libglib2.0-dev libgnutls28-dev libseccomp-dev libfuse3-dev libei-dev libeis-dev
        tpm2-tools dmidecode pciutils usbutils mtools dosfstools util-linux kmod'''.split(),
}
COMMANDS = '''git Hyprland hyprctl hyprpaper hyprlock waybar kitty dolphin konsole swaync swaync-client grim slurp
    wl-copy wl-paste xdg-open xdg-user-dir nmcli nm-applet nm-connection-editor bluetoothctl blueman-manager
    pactl wpctl playerctl brightnessctl fastfetch htop notify-send gdbus pgrep flock
    xcursorgen hyprcursor-util cc c++ cmake pkg-config wayland-scanner fc-match yt-dlp ffmpeg ffprobe sudo xhost openssl remote-viewer virt-fw-vars certtool
    make autoconf autoreconf automake aclocal libtool libtoolize perl pod2man gettext gawk expect socat
    tpm2_getcap dmidecode lspci lsusb mcopy mtype fsck.fat losetup modinfo'''.split()
LIBRARIES = ['gtk+-3.0','gio-unix-2.0','gtk-layer-shell-0','epoxy','json-glib-1.0','Qt5Widgets','Qt6Widgets','Qt5Concurrent','Qt6Concurrent','wayland-client','xcb','xcb-res',
             'openssl','libtasn1','gmp','glib-2.0','gnutls','libseccomp','fuse3','libeis-1.0','json-c']
# Hyprland comes from the exact, signed package selected by Setup.
MINIMUM = {'waybar':(0,15,0),'kitty':(0,49,0),'hyprpaper':(0,8,0)}
PERL_SCRIPT_DIRS = ('/usr/bin/site_perl', '/usr/bin/vendor_perl', '/usr/bin/core_perl')


def distribution():
    # The standard reader handles quoted values, ID_LIKE and /usr/lib fallback
    # without executing the file as a shell script.
    try: return platform.freedesktop_os_release()
    except OSError: return {'ID':'linux','PRETTY_NAME':'Unidentified Linux distribution'}


def distro(data=None):
    data = distribution() if data is None else data
    values=[data.get('ID',''),*data.get('ID_LIKE','').split()]
    for name in values:
        if name in ('arch','cachyos','manjaro','endeavouros'):return 'arch'
        if name in ('fedora','rhel'):return 'fedora'
        if name in ('debian','ubuntu','linuxmint','pop'):return 'debian'
    return None


def minimum_versions():
    # Fedora's Kitty 0.47 supports the dashboard, PNG graphics and theme config.
    if runtime_install.policy.debian_host(distribution()): return {**MINIMUM, 'kitty':(0,48,2)}
    return {**MINIMUM, 'kitty':(0,47,1)} if runtime_install.policy.fedora_host(distribution()) else MINIMUM


def platform_problems(auto_packages=True):
    problems=[];data=distribution();family=distro(data)
    name=data.get('PRETTY_NAME',data.get('ID','Linux'))
    if platform.system() != 'Linux':
        return ['Hyper Fusion requires Linux.']
    if platform.machine() != runtime_install.policy.manifest()['architecture']:
        problems.append('This release requires x86-64; detected '+platform.machine()+'.')
    if auto_packages:
        if family not in PACKAGES:
            problems.append(name+' has no automatic package installer in this release. '+
                            'Use --skip-packages only after supplying the exact compositor and all dependencies.')
        elif family != 'arch' and not runtime_install.policy.fedora_host(data) and not runtime_install.policy.debian_host(data) and runtime_install.policy.problem():
            problems.append(name+' needs a native installation of the exact Hyprland version first. '+
                            'The bundled Arch package cannot be installed on this distribution.')
        if Path('/run/ostree-booted').exists():
            problems.append('Automatic package installation is unavailable on an immutable OSTree desktop.')
        tools={'arch':('pacman','pacman-conf','pacman-key','sudo'),
               'fedora':('dnf','rpm','rpmkeys','sudo'),'debian':('apt-get','dpkg-query','dpkg-deb')}.get(family,())
        problems.extend('Required package tool is missing: '+tool for tool in tools if not shutil.which(tool))
        if family == 'debian' and not runtime_install.graphical_administrator(data) and not shutil.which('sudo'):
            problems.append('Administrator authentication is unavailable. Install pkexec for graphical '
                            'Debian Setup, or install sudo and authorize your desktop account.')
    return problems


def package_version_problems(output):
    versions={}
    for line in output.splitlines():
        fields=line.split()
        if len(fields)==2: versions[fields[0]]=fields[1]
    problems=[]
    for name,minimum in minimum_versions().items():
        value=versions.get(name,'')
        match=re.search(r'(\d+)\.(\d+)\.(\d+)',value.split(':')[-1])
        if not match or tuple(map(int,match.groups()))<minimum:
            problems.append(f'The configured repositories offer {name} {value or "(unknown)"}; '+
                            '.'.join(map(str,minimum))+' or newer is required.')
    return problems


def preflight():
    """Resolve packages without sudo, installation or refreshing host databases."""
    data=distribution()
    print('Checking distribution: '+data.get('PRETTY_NAME',data.get('ID','Linux'))+' ('+platform.machine()+')',flush=True)
    problems=platform_problems()
    if problems: raise RuntimeError('\n'.join(problems))
    if runtime_install.policy.fedora_host(data):
        import fedora_runtime
        fedora_runtime.preflight(PACKAGES['fedora'])
        return
    if runtime_install.policy.debian_host(data):
        import debian_runtime
        debian_runtime.preflight(PACKAGES['debian'])
        return
    if distro(data) != 'arch': return
    result=subprocess.run(['pacman','-Sp','--noconfirm','--print-format','%n %v',*PACKAGES['arch']],
                          capture_output=True,text=True,timeout=60)
    if result.returncode:
        raise RuntimeError('Desktop packages cannot be resolved from this system’s configured repositories. '+
                           'No packages or desktop settings have been changed.\n'+(result.stderr or result.stdout).strip())
    problems=package_version_problems(result.stdout)
    if problems: raise RuntimeError('\n'.join(problems)+'\nNo packages or desktop settings have been changed.')


def prepare_repositories():
    """Foreground Setup refreshes Debian's lists before its read-only preflight."""
    if runtime_install.policy.debian_host(distribution()):
        problems = platform_problems()
        if problems:
            raise RuntimeError('\n'.join(problems))
        import debian_runtime
        debian_runtime.refresh()


def prepare_account():
    """Finish Debian administrator setup after its sudo dependency is installed."""
    if runtime_install.policy.debian_host(distribution()):
        import debian_administrator
        debian_administrator.prepare()


def prepare_environment():
    """Expose installed Perl scripts to checks and their subsequent build processes."""
    # Arch adds these directories at login through /etc/profile.d/perlbin.sh.
    # A fresh install can add Perl after this terminal was opened. Refresh before
    # every check so the post-package-install check sees newly created directories.
    # Keep caller overrides first and change only this process and its children.
    paths = os.environ.get('PATH', os.defpath).split(os.pathsep)
    for directory in PERL_SCRIPT_DIRS:
        if directory not in paths and Path(directory).is_dir():
            paths.append(directory)
    os.environ['PATH'] = os.pathsep.join(paths)


def konsole_part_available():
    try:
        from PyQt6.QtCore import QLibraryInfo
        return (Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath))/'kf6/parts/konsolepart.so').is_file()
    except ImportError:
        return False


def check(runtime=True):
    prepare_environment()
    errors=platform_problems(auto_packages=False)
    if runtime:
        message=runtime_install.policy.problem()
        if message:errors.append(message)
    if sys.version_info < (3,11): errors.append('Python 3.11 or newer is required.')
    errors += ['Missing command: '+command for command in COMMANDS if not shutil.which(command)]
    if runtime_install.policy.fedora_host(distribution()) and not find_library('SDL3'):
        errors.append('QEMU needs the SDL3 runtime: install SDL3.')
    if runtime_install.policy.debian_host(distribution()) and not find_library('SDL3'):
        errors.append('QEMU needs the SDL3 runtime: install libsdl3-0 from the matching Debian bundle.')
    if not konsole_part_available():
        errors.append('Dolphin terminal component is missing: install Konsole (konsole-part on Fedora, konsole-kpart on Debian).')
    if not any(shutil.which(command) for command in ('deno','node','qjs')):
        errors.append('Install Deno, Node.js or QuickJS for YouTube downloads.')
    result=subprocess.run([sys.executable,'-c',
        "import psutil; import PyQt6.QtWidgets, PyQt6.QtNetwork, PyQt6.QtDBus, PyQt6.QtSvg; from PIL import Image; import gi; gi.require_version('Gtk','3.0'); gi.require_version('GtkLayerShell','0.1'); from gi.repository import Gio,Gtk,GtkLayerShell"],
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
    for command,minimum in minimum_versions().items():
        if not shutil.which(command):continue
        result=subprocess.run([command,'--version'],capture_output=True,text=True,timeout=10)
        match=re.search(r'(?<!\d)(\d+)\.(\d+)\.(\d+)',result.stdout+result.stderr)
        if not match or tuple(map(int,match.groups())) < minimum:
            errors.append(f'{command} {".".join(map(str,minimum))}+ is required for the complete desktop (found {match[0] if match else "unknown"}).')
    if not any(Path(p).is_file() for p in ['/usr/lib/xdg-desktop-portal-hyprland','/usr/libexec/xdg-desktop-portal-hyprland']):
        errors.append('The Hyprland desktop portal backend is missing.')
    if not any(Path(p).is_file() for p in ['/usr/lib/polkit-gnome/polkit-gnome-authentication-agent-1',
        '/usr/libexec/polkit-gnome-authentication-agent-1','/usr/lib/policykit-1-gnome/polkit-gnome-authentication-agent-1',
        '/usr/libexec/hyprpolkitagent']):
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
    prefix=runtime_install.administrator()
    command={'arch':['pacman','-S','--needed'], 'fedora':['dnf','install'], 'debian':['apt-get','install']}[family]
    if yes:command+=['--noconfirm' if family=='arch' else '-y']
    command=prefix+command+PACKAGES[family]
    print('Package command: '+shlex.join(command),flush=True)
    if not yes and input('Install these desktop/build packages? [y/N] ').strip().lower() not in ('y','yes'):
        raise RuntimeError('Package installation cancelled. Your Hyprland configuration is unchanged.')
    subprocess.run(command,check=True)
