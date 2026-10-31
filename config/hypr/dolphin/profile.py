#!/usr/bin/env python3
"""Portable Dolphin defaults, confined to this Hyprland profile."""
from pathlib import Path
import os
import re
import tempfile
import xml.etree.ElementTree as ET

BOOKMARK_NS = 'http://www.freedesktop.org/standards/desktop-bookmarks'
# KDE's bookmark reader expects the conventional prefix as well as this URI.
ET.register_namespace('bookmark', BOOKMARK_NS)

FOLDERS = (
    ('DESKTOP', 'Desktop', 'user-desktop'),
    ('DOCUMENTS', 'Documents', 'folder-documents'),
    ('DOWNLOAD', 'Downloads', 'folder-download'),
    ('MUSIC', 'Music', 'folder-music'),
    ('PICTURES', 'Pictures', 'folder-pictures'),
    ('VIDEOS', 'Videos', 'folder-videos'),
)


def default_places(home):
    """Use only this recipient's standard directories, never imported bookmarks."""
    home = Path(home)
    directories = {}
    try: text = (home/'.config/user-dirs.dirs').read_text()
    except FileNotFoundError: text = ''
    for line in text.splitlines():
        match = re.fullmatch(r'\s*XDG_([A-Z]+)_DIR="([^"`\\]*)"\s*(?:#.*)?', line)
        if not match: continue
        value = match[2]
        for prefix in ('$HOME', '${HOME}'):
            if value == prefix or value.startswith(prefix+'/'):
                value = str(home)+value[len(prefix):]; break
        if '$' not in value and Path(value).is_absolute(): directories[match[1]] = Path(value)
    places = ET.Element('xbel', {'version':'1.0'})
    entries = [('Home', home.as_uri(), 'user-home')]
    seen = {home}
    for key, label, icon in FOLDERS:
        path = directories.get(key, home/label)
        if path in seen or not path.is_dir(): continue
        entries.append((label, path.as_uri(), icon)); seen.add(path)
    entries += [('Trash', 'trash:/', 'user-trash'), ('Network', 'remote:/', 'network-workgroup')]
    for label, url, icon in entries:
        bookmark = ET.SubElement(places, 'bookmark', {'href':url})
        ET.SubElement(bookmark, 'title').text = label
        metadata = ET.SubElement(ET.SubElement(bookmark, 'info'), 'metadata', {'owner':'http://freedesktop.org'})
        ET.SubElement(metadata, '{'+BOOKMARK_NS+'}icon', {'name':icon})
    return ET.tostring(places, encoding='utf-8', xml_declaration=True)


def write_changed(path, data):
    path = Path(path)
    if path.is_file() and path.read_bytes() == data: return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.'+path.name+'-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream: stream.write(data)
        os.replace(temporary, path)
    finally: Path(temporary).unlink(missing_ok=True)


def set_default(path, section, key, value):
    """Add a missing setting while preserving KConfig syntax and user choices."""
    try: text = path.read_text()
    except FileNotFoundError: text = ''
    if text and not text.endswith('\n'): text += '\n'
    lines = text.splitlines(keepends=True)
    begin = next((i+1 for i, line in enumerate(lines) if line.strip() == '['+section+']'), None)
    if begin is None:
        text = text.rstrip()+'\n\n['+section+']\n'+key+'='+value+'\n'
    else:
        end = next((i for i in range(begin, len(lines)) if lines[i].startswith('[')), len(lines))
        if any(re.match(re.escape(key)+r'(?:\[\$[ei]\])*\s*=', line.strip()) for line in lines[begin:end]): return
        lines.insert(begin, key+'='+value+'\n')
        text = ''.join(lines)
    write_changed(path, text.encode())


def prepare_terminal(root):
    """Match Kitty's current colors without touching the user's Konsole profile."""
    root = Path(root)
    text = (root/'theme/kitty-colors.conf').read_text()
    colors = dict(re.findall(r'^(\w+)\s+(#[0-9a-fA-F]{6})\s*$', text, re.M))
    groups = {'Background':colors['background'], 'Foreground':colors['foreground']}
    for i in range(8):
        groups['Color'+str(i)] = colors['color'+str(i)]
        groups['Color'+str(i)+'Intense'] = colors['color'+str(i+8)]
    for name in ('Background', 'Foreground'):
        groups[name+'Intense'] = groups[name]
        groups[name+'Faint'] = groups[name]
    for i in range(8): groups['Color'+str(i)+'Faint'] = groups['Color'+str(i)]
    scheme = '[General]\nDescription=Hyper Fusion Dolphin\nOpacity=1\n'
    for name, color in groups.items():
        rgb = ','.join(str(int(color[i:i+2], 16)) for i in (1,3,5))
        scheme += '\n['+name+']\nColor='+rgb+'\n'
    directory = root/'dolphin/data/konsole'
    write_changed(directory/'Xetal-Dolphin.colorscheme', scheme.encode())
    profile = (root/'dolphin/terminal.profile').read_text()
    font = re.search(r'^font_family (.+)$', text, re.M)
    profile = profile.replace('@FONT@', font[1] if font else 'DejaVu Sans Mono')
    write_changed(directory/'Xetal-Dolphin.profile', profile.encode())
    set_default(root/'dolphin/config/dolphinrc', 'Desktop Entry', 'DefaultProfile', 'Xetal-Dolphin.profile')
    set_default(root/'dolphin/config/kdeglobals', 'General', 'TerminalApplication',
                'kitty --config '+str(root/'kitty.conf'))


if __name__ == '__main__':
    prepare_terminal(Path(__file__).resolve().parents[1])
