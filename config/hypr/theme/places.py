#!/usr/bin/env python3
"""Read the Hyprland Dolphin Places; resolve devices only on explicit selection.

No shared KDE/GTK preferences are written. Native Qt and GTK hooks use this
small process so neither toolkit needs to load the other's libraries.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent


def source():
    return Path(os.environ.get('XETAL_PLACES_FILE', ROOT/'dolphin/data/user-places.xbel'))


def bookmarks(path=None):
    path = path or source()
    try:
        if path.stat().st_size > 4*1024*1024: return []
        root = ET.fromstring(path.read_bytes())
    except (OSError, ET.ParseError): return []
    hidden_groups = {node.tag.removeprefix('GroupState-').removesuffix('-IsHidden')
                     for node in root.findall('./info/metadata/*')
                     if node.tag.startswith('GroupState-') and node.text == 'true'}
    result = []
    for node in root.findall('bookmark'):
        metadata = {item.tag.rsplit('}', 1)[-1]: item.text for item in node.findall('./info/metadata/*')}
        # Device bookmark UDIs are resolved from the live volume list below.
        if metadata.get('UDI') or metadata.get('isHidden') == 'true': continue
        if metadata.get('OnlyInApp') not in (None, '', 'dolphin'): continue
        url = node.get('href', '')
        scheme = urlsplit(url).scheme
        if not scheme: continue
        group = ('RecentlySaved' if scheme in ('recentlyused', 'timeline') else
                 'SearchFor' if scheme in ('search', 'tags', 'baloosearch') else
                 'Places' if scheme in ('file', 'trash', 'admin') else 'Remote')
        if group in hidden_groups: continue
        icon = next((item.get('name', '') for item in node.findall('./info/metadata/*')
                     if item.tag.rsplit('}', 1)[-1] == 'icon'), '')
        result.append(dict(name=node.findtext('title') or unquote(url.rsplit('/', 1)[-1]) or url,
                           url=url, icon=icon or 'folder', group=group))
    return result


def fallback():
    result = [dict(name='Home', url=Path.home().as_uri(), icon='user-home', group='Places')]
    from gi.repository import GLib
    for name, code, icon in [('Desktop', GLib.UserDirectory.DIRECTORY_DESKTOP, 'user-desktop'),
                            ('Documents', GLib.UserDirectory.DIRECTORY_DOCUMENTS, 'folder-documents'),
                            ('Downloads', GLib.UserDirectory.DIRECTORY_DOWNLOAD, 'folder-download'),
                            ('Music', GLib.UserDirectory.DIRECTORY_MUSIC, 'folder-music'),
                            ('Pictures', GLib.UserDirectory.DIRECTORY_PICTURES, 'folder-pictures'),
                            ('Videos', GLib.UserDirectory.DIRECTORY_VIDEOS, 'folder-videos')]:
        folder = GLib.get_user_special_dir(code)
        if folder and Path(folder) != Path.home():
            result.append(dict(name=name, url=Path(folder).as_uri(), icon=icon, group='Places'))
    return result


def volumes():
    from gi.repository import Gio, GLib
    monitor = Gio.VolumeMonitor.get()
    # Let the GVfs remote volume monitor finish its initial asynchronous scan.
    end = time.monotonic() + .25
    context = GLib.MainContext.default()
    while time.monotonic() < end:
        while context.pending(): context.iteration(False)
        time.sleep(.01)
    return monitor


def snapshot():
    result = bookmarks()
    try: root = ET.parse(source()).getroot() if source().stat().st_size <= 4*1024*1024 else None
    except (OSError, ET.ParseError): root = None
    if root is None: result = fallback()
    hidden_groups = {node.tag.removeprefix('GroupState-').removesuffix('-IsHidden')
                     for node in root.findall('./info/metadata/*')
                     if node.tag.startswith('GroupState-') and node.text == 'true'} if root is not None else set()
    hidden_devices = set()
    if root is not None:
        for node in root:
            metadata = {item.tag.rsplit('}', 1)[-1]: item.text for item in node.findall('./info/metadata/*')}
            if metadata.get('UDI') and metadata.get('isHidden') == 'true':
                hidden_devices.add(metadata['UDI'].rsplit('/', 1)[-1])
    from gi.repository import Gio
    monitor = volumes()
    for volume in sorted(monitor.get_volumes(), key=lambda v: v.get_identifier(Gio.VOLUME_IDENTIFIER_KIND_UNIX_DEVICE) or v.get_name()):
        device = volume.get_identifier(Gio.VOLUME_IDENTIFIER_KIND_UNIX_DEVICE)
        if device and Path(device).name in hidden_devices: continue
        mount = volume.get_mount()
        url = mount.get_root().get_uri() if mount else ''
        drive = volume.get_drive()
        removable = drive and drive.is_removable()
        if ('RemovableDevices' if removable else 'Devices') in hidden_groups: continue
        icon = volume.get_icon()
        names = icon.get_names() if isinstance(icon, Gio.ThemedIcon) else []
        result.append(dict(name=volume.get_name(), url=url, device=device or '',
                           icon=names[0] if names else 'drive-harddisk',
                           group='Removable Devices' if removable else 'Devices',
                           mounted=bool(mount)))
    seen = {item['url'] for item in result if item['url']}
    for mount in monitor.get_mounts():
        if mount.get_volume() is not None: continue  # Already listed, or deliberately hidden above.
        url = mount.get_root().get_uri()
        if not mount.is_shadowed() and url not in seen and 'Remote' not in hidden_groups:
            result.append(dict(name=mount.get_name(), url=url, icon='folder-remote', group='Remote'))
            seen.add(url)
    # A system root is useful even when GVfs omits the system volume.
    if 'file:///' not in seen and 'Devices' not in hidden_groups:
        result.append(dict(name='File System', url='file:///', icon='drive-harddisk', group='Devices'))
    return result


def resolve(url='', device=''):
    from gi.repository import Gio, GLib
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk
    Gtk.init_check()
    operation = Gtk.MountOperation.new(None)
    loop = GLib.MainLoop()
    outcome = {}
    if device:
        volume = next((v for v in volumes().get_volumes()
                       if v.get_identifier(Gio.VOLUME_IDENTIFIER_KIND_UNIX_DEVICE) == device), None)
        if volume is None: raise RuntimeError('This drive is no longer connected. Refresh and try again.')
        mount = volume.get_mount()
        if mount: return dict(url=mount.get_root().get_uri(), path=mount.get_root().get_path() or '')
        def done(obj, result):
            try:
                obj.mount_finish(result)
                root = obj.get_mount().get_root()
                outcome.update(url=root.get_uri(), path=root.get_path() or '')
            except GLib.Error as error: outcome['error'] = error.message
            loop.quit()
        volume.mount(Gio.MountMountFlags.NONE, operation, None, done)
    else:
        location = Gio.File.new_for_uri(url)
        local = location.get_path()
        if local: return dict(url=url, path=local)
        # KIO-only virtual views are opened in the profile's Dolphin. Real remote
        # shares use GVfs, exposing a local path to applications that require one.
        if urlsplit(url).scheme in ('trash', 'admin', 'remote', 'network', 'recentlyused', 'timeline', 'search', 'tags', 'baloosearch'):
            return dict(dolphin=url)
        def done(obj, result):
            try: obj.mount_enclosing_volume_finish(result)
            except GLib.Error as error:
                if not error.matches(Gio.io_error_quark(), Gio.IOErrorEnum.ALREADY_MOUNTED): outcome['error'] = error.message
            if 'error' not in outcome:
                outcome.update(url=url, path=Gio.File.new_for_uri(url).get_path() or '')
                if not outcome['path']:
                    outcome['error'] = 'This application needs a local file. Open this location in Dolphin and copy the file locally first.'
            loop.quit()
        location.mount_enclosing_volume(Gio.MountMountFlags.NONE, operation, None, done)
    loop.run()
    return outcome


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--open', default=''); parser.add_argument('--device', default='')
    args = parser.parse_args()
    try: answer = resolve(args.open, args.device) if args.open or args.device else snapshot()
    except Exception as error: answer = {'error': str(error)}
    print(json.dumps(answer, ensure_ascii=False))
