"""The shared ownership registry for inventory, export, import and reset.

Paths are relative to a named root. Archives never choose arbitrary destinations.
Release code, personal documents, VM disks and caches are not preferences.
"""
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import fnmatch
import os


@dataclass(frozen=True)
class Category:
    id: str
    title: str
    description: str
    administrator: bool = False


CATEGORIES = (
    Category('desktop', 'Desktop & shortcuts', 'Hotkeys, input, monitors, context menus, calendar and notifications.'),
    Category('appearance', 'Themes & artwork', 'Design, colors, wallpapers, cursors, icons, custom presets and their artwork.'),
    Category('windows', 'Windows & workspaces', 'Every remembered size and position, individual title bars, controls, snapping and effects.'),
    Category('launcher', 'Apps menu & taskbar', 'Favorites, pins, copies, launch options, workspace bar and task switcher.'),
    Category('audio', 'Audio & system sounds', 'Devices, volume, microphone, mixer state, sound packs and event choices.'),
    Category('files', 'Fusion Files & default apps', 'Views, geometry, bookmarks, templates, searches, mounts and file associations.'),
    Category('tools', 'Control Panel & desktop tools', 'Panel preferences, calculator, clipboard pins, recorder, startup dashboard and updates.'),
    Category('terminal', 'Terminal & shell', 'Terminal appearance, fetch, aliases and shell preferences.'),
    Category('remote', 'RDP, VNC & phone', 'Saved connections, hosting options, passwords, certificates and device pairing.'),
    Category('virtualization', 'KVM & Proton settings', 'Machine definitions, presets, launch options and prefix configuration; disk contents stay in place.'),
    Category('power', 'Desktop power', 'Idle, lid, battery, monitor brightness and charging preferences.'),
    Category('applications', 'Other application preferences', 'Account application configuration, autostart, user services and desktop entries.'),
    Category('system', 'System configuration & services', 'System configuration, enabled services, CPU governor, power policy and kernel tuning.', True),
    Category('network', 'Network, firewall & shares', 'Wi-Fi/VPN profiles, firewall rules, shares and Bluetooth pairing.', True),
    Category('boot', 'GRUB boot settings', 'GRUB theme, pictures, menu entries and boot preferences.', True),
    Category('packages', 'Installed applications', 'Pacman packages, AUR/foreign packages, versions, install reasons and repository settings.', True),
)
BY_ID = {c.id: c for c in CATEGORIES}
USER_IDS = frozenset(c.id for c in CATEGORIES if not c.administrator)
SYSTEM_IDS = frozenset(BY_ID) - USER_IDS

# A registry entry owns a complete file or directory, including newly created
# preferences. All updater-owned preference files are added below as well.
PROFILE_DIRS = {
    'appearance': ('icon_themes/custom', 'icon_themes/imported', 'theme/backgrounds'),
    'windows': ('runtime/window_memory/state', 'workspaces/state'),
    'launcher': ('launcher/icons',),
    'files': ('file_manager/state', 'dolphin/config', 'dolphin/state', 'dolphin/data'),
    'tools': ('control_panel/state', 'calculator/state', 'clipboard/state', 'startup/state', 'recording/state'),
    'terminal': ('terminal_fetch/logos',),
    'applications': ('apps', 'qt-settings', 'theme/qt-settings', 'desktop/config', 'desktop/state'),
    'power': ('wallpaper/state',),
}
EXTRA_FILES = {'effects/window_close/saved-windows.json': 'windows', 'settings_profiles/audio.json': 'audio'}
TRANSIENT_PARTS = {'__pycache__', '.build', 'cache', 'Cache', 'Code Cache', 'GPUCache',
                   'backups', 'logs', 'Crash Reports', 'DawnCache', 'ShaderCache'}
TRANSIENT_SUFFIXES = ('.lock', '.log', '.pyc', '.tmp', '.bak', '.socket', '.pid')
CUSTOM_CONFIG_DIRS = ('user', 'custom', 'conf.d', 'settings', 'configs')
# These are user account identity / OS installation data, not desktop settings.
# Restoring them would replace users, disks or the machine's cryptographic identity.
SYSTEM_IDENTITY = {'etc/passwd', 'etc/shadow', 'etc/group', 'etc/gshadow', 'etc/subuid', 'etc/subgid',
                   'etc/machine-id', 'etc/mtab',
                   'etc/os-release', 'etc/arch-release', 'etc/ld.so.cache', 'etc/.pwd.lock'}


def safe_name(value):
    if not isinstance(value, str) or not value or '\\' in value or '\x00' in value:
        raise ValueError('Invalid settings path.')
    path = PurePosixPath(value)
    if path.is_absolute() or any(p in ('', '.', '..') for p in value.split('/')):
        raise ValueError('Settings paths must stay inside their registered directory.')
    return value


def below(name, prefix):
    return name == prefix or name.startswith(prefix + '/')


def transient(name):
    parts = PurePosixPath(name).parts
    return bool(set(parts) & TRANSIENT_PARTS) or name.endswith(TRANSIENT_SUFFIXES) or any(
        p.startswith(('Singleton', '.~', '.nfs')) for p in parts)


def profile_category(name):
    from updates.file_policy import KEEP, PREFERENCES
    if transient(name) or name.startswith('.xetal-'): return None
    if name in EXTRA_FILES: return EXTRA_FILES[name]
    if name in ('dolphin/config/kdeglobals', 'dolphin/data/konsole/Xetal-Dolphin.colorscheme'): return 'appearance'
    if name.startswith(('control_panel/state/rdp/', 'control_panel/state/vnc/')): return 'remote'
    for group, prefixes in PROFILE_DIRS.items():
        if any(below(name, p) for p in prefixes): return group
    if name not in KEEP | PREFERENCES:
        if (name.endswith(('.conf', '.ini', '.json', '.toml', '.yaml', '.yml'))
                and ('/' not in name or any(below(name, p) for p in CUSTOM_CONFIG_DIRS))): return 'desktop'
        return None
    if name.startswith(('effects/', 'workspaces/')): return 'windows'
    if name.startswith(('theme/', 'cursors/', 'visuals/', 'wallpaper/')) or name == 'control_center/theme.conf': return 'appearance'
    if name.startswith(('launcher/', 'waybar/', 'switcher/')): return 'launcher'
    if name.startswith('sounds/'): return 'audio'
    if name.startswith(('file_manager/', 'file_jobs/', 'dolphin/')) or name == 'desktop/config/mimeapps.list': return 'files'
    if name.startswith(('terminal_fetch/',)) or name == 'kitty.conf': return 'terminal'
    if name.startswith(('recording/', 'startup/')): return 'tools'
    return 'desktop'


HOME_PATHS = {
    'audio': ('.local/state/wireplumber', '.config/pulse', '.config/pipewire', '.config/wireplumber'),
    'files': ('.config/mimeapps.list', '.config/user-dirs.dirs', '.config/user-dirs.locale', '.local/share/user-places.xbel'),
    'tools': ('.config/XetalHyperland', '.local/state/xetal-hyprland/updates/settings.json'),
    'terminal': ('.bashrc', '.bash_profile', '.bash_aliases', '.profile', '.zshrc', '.zprofile', '.zshenv', '.kshrc', '.cshrc', '.tcshrc', '.config/fish'),
    'remote': ('.local/state/hyperfusion/remote-desktop', '.config/kdeconnect', '.local/share/kdeconnect',
               '.local/share/kwalletd', '.local/share/keyrings'),
    'virtualization': ('.config/XetalProton',),
    'power': ('.local/state/hyperfusion/power.json', '.local/state/hyperfusion/monitor-picture.json'),
    'appearance': ('.face', '.face.icon', '.icons', '.local/share/icons', '.local/share/themes'),
    'applications': ('.local/share/applications', '.config'),
}


def home_category(name):
    if transient(name) or below(name, '.config/hypr'): return None
    if below(name, '.local/share/xetal-kvm'):
        # Source scripts, firmware, components and VM storage are not options.
        if any(p in PurePosixPath(name).parts for p in ('components', 'downloads', 'editions', 'cache', 'logs')): return None
        return 'virtualization' if name.endswith(('.json', '.ini', '.conf', '.xml', '.theme')) else None
    for group, prefixes in HOME_PATHS.items():
        if any(below(name, p) for p in prefixes):
            if group == 'applications' and below(name, '.config'):
                # Browser history, mail, cookies and session databases are user
                # data. Include actual preferences, including binary dconf.
                p = PurePosixPath(name)
                if not (p.suffix.lower() in ('.conf', '.ini', '.json', '.jsonc', '.xml', '.yaml', '.yml', '.toml', '.cfg', '.desktop', '.list', '.service', '.socket', '.timer', '.target', '.path', '.sh')
                        or p.name.endswith('rc') or p.name in ('config', 'settings', 'Preferences', 'Local State', 'user', 'environment')):
                    return None
            return group
    return None


def system_category(name):
    if (name in SYSTEM_IDENTITY or name.startswith(('etc/passwd-', 'etc/shadow-', 'etc/group-', 'etc/gshadow-',
            'etc/ssh/ssh_host_', 'etc/ssl/private/', 'etc/pacman.d/gnupg/', 'etc/ca-certificates/extracted/'))
            or transient(name)): return None
    if any(below(name, p) for p in ('etc/default/grub', 'etc/grub.d', 'boot/grub/themes', 'boot/grub/fonts')): return 'boot'
    if any(below(name, p) for p in ('etc/NetworkManager', 'etc/ufw', 'etc/firewalld', 'etc/iptables', 'etc/nftables.conf',
            'etc/samba', 'etc/exports', 'etc/exports.d', 'etc/bluetooth', 'var/lib/bluetooth', 'etc/systemd/network')): return 'network'
    if any(below(name, p) for p in ('etc/pacman.conf', 'etc/pacman.d', 'etc/makepkg.conf', 'etc/makepkg.conf.d',
            'etc/yay.conf', 'etc/paru.conf')): return 'packages'
    if below(name, 'etc'): return 'system'
    if any(below(name, p) for p in ('var/lib/AccountsService/users', 'var/lib/AccountsService/icons', 'var/lib/alsa')): return 'system'
    return None


def category(scope, name):
    safe_name(name)
    return {'profile': profile_category, 'home': home_category, 'system': system_category}.get(scope, lambda _: None)(name)


def scan_roots(scope, root):
    if scope == 'profile':
        from updates.file_policy import KEEP, PREFERENCES
        return [root / p for p in sorted(KEEP | PREFERENCES | set(EXTRA_FILES))] + [
            root / p for paths in PROFILE_DIRS.values() for p in paths] + [root/p for p in CUSTOM_CONFIG_DIRS] + [
            p for p in root.glob('*') if p.is_file() and profile_category(p.name)]
    if scope == 'home':
        return [root / p for paths in HOME_PATHS.values() for p in paths] + [root / '.local/share/xetal-kvm']
    if scope == 'system': return [root/p for p in ('etc', 'boot/grub/themes', 'boot/grub/fonts', 'var/lib/bluetooth',
        'var/lib/AccountsService/users', 'var/lib/AccountsService/icons', 'var/lib/alsa')]
    raise ValueError('Unknown settings root.')


def roots(profile=None, home=None, system=None):
    return {'profile': Path(profile or Path(__file__).resolve().parents[1]),
            'home': Path(home or Path.home()), 'system': Path(system or '/')}


def selected(values):
    result = sorted(set(values))
    if not result or set(result) - set(BY_ID): raise ValueError('Choose at least one valid settings category.')
    return result
