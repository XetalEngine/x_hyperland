#!/usr/bin/env python3
"""GRUB designs, unprivileged previews, and backed-up appearance transactions.

The desktop prepares artwork as the calling user. The authenticated editor only
publishes a bounded set of assets and a generated presentation block. It never
runs grub-install or regenerates the existing menu.
"""
from __future__ import annotations

import base64
import io
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
import grub_editor as grub

ROOT = Path(__file__).resolve().parents[1]
SIZE = (1920, 1080)
GENERATOR = '/etc/grub.d/99_hyper_fusion_appearance'
BEGIN = '### BEGIN ' + GENERATOR + ' ###'
END = '### END ' + GENERATOR + ' ###'
SIGNATURE = '# Hyper Fusion GRUB Appearance v1'
NAMES = {'modern': 'Hyper Fusion', 'shadowedge': 'Shadow Edge', 'hollowgrove': 'Hollow Grove',
         'tidalglass': 'Tidal Glass', 'porcelainink': 'Porcelain Ink',
         'obsidianforge': 'Obsidian Forge', 'candycloud': 'Candy Cloud',
         'breakpoint': 'Breakpoint', 'binaryknife': 'Binary Knife', 'raw': 'Original'}
SLICES = ('nw', 'n', 'ne', 'w', 'c', 'e', 'sw', 's', 'se')
FILES = {'background.png', 'source.png', 'menu.pf2', 'selected.pf2', 'heading.pf2', 'detail.pf2',
         *(f'select_{part}.png' for part in SLICES)}


def presets():
    palettes = json.loads((ROOT/'theme/palettes.json').read_text())
    pictures = json.loads((ROOT/'wallpaper/sets.json').read_text())
    result = []
    for key, title in NAMES.items():
        if key not in palettes or key not in pictures: continue
        palette = palettes[key]['dark']
        result.append({'id': key, 'name': title, 'options': {
            'preset': key, 'background': str(ROOT/'wallpaper'/pictures[key][0]),
            'layout': 'left', 'heading': 'HYPER FUSION' if key == 'modern' else title.upper(),
            'subtitle': 'Choose a system to start', 'size': 22, 'dimming': 28, 'contrast': 78,
            'accent': palette['Accent'], 'text': palette['Text'], 'base': palette['Base'],
            'hints': True}})
    return result


def normalize(value):
    if not isinstance(value, dict): raise ValueError('Invalid appearance settings.')
    defaults = presets()[0]['options']
    result = {key: value.get(key, default) for key, default in defaults.items()}
    if result['preset'] not in NAMES or result['layout'] not in ('left', 'center', 'right'):
        raise ValueError('Choose a bundled theme and menu position.')
    for key, maximum in (('heading', 64), ('subtitle', 100)):
        text = result[key]
        if not isinstance(text, str) or len(text) > maximum or any(ord(c) < 32 for c in text):
            raise ValueError('Heading and subtitle must be short, single-line text.')
    if type(result['size']) is not int or result['size'] not in (18, 22, 28):
        raise ValueError('Choose a supported menu text size.')
    for key in ('dimming', 'contrast'):
        if type(result[key]) is not int or not 0 <= result[key] <= 95:
            raise ValueError('Picture dimming and menu contrast must be between 0 and 95.')
    for key in ('accent', 'text', 'base'):
        if not isinstance(result[key], str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', result[key]):
            raise ValueError('Choose an RGB color for '+key+'.')
    if type(result['hints']) is not bool: raise ValueError('Invalid navigation hint setting.')
    path = result['background']
    if not isinstance(path, str) or len(path) > 4096 or '\0' in path or (path and not Path(path).is_absolute()):
        raise ValueError('Choose a picture using its full path.')
    return result


def geometry(options):
    # Percentages match theme.txt, including the centered and right-hand layouts.
    left = {'left': 7, 'center': 28, 'right': 50}[options['layout']]
    return {'left': left, 'width': 43, 'top': 36,
            'height': options['size'] + 26, 'spacing': 24, 'border': 8, 'padding': 16}


def theme_text(options):
    o = normalize(options); g = geometry(o)
    def quoted(text): return '"'+text.replace('\\', '\\\\').replace('"', '\\"')+'"'
    labels = [(20, 8, o['heading'], 'Fusion Heading Bold 44', o['text']),
              (28, 4, o['subtitle'], 'Fusion Detail Regular 17', o['text'])]
    if o['hints']:
        labels.append((82, 4, '↑ ↓ Select   Enter Start   E Edit   C Console', 'Fusion Detail Regular 17', o['text']))
    text = f'''{SIGNATURE}
title-text: ""
desktop-image: "background.png"
desktop-image-scale-method: "stretch"
desktop-color: "{o['base']}"
message-font: "Fusion Detail Regular 17"
message-color: "{o['text']}"
message-bg-color: "{o['base']}"
terminal-font: "Fusion Detail Regular 17"
'''
    for top, height, title, font, color in labels:
        text += f'''+ label {{
  left = {g['left']}%
  top = {top}%
  width = {g['width']}%
  height = {height}%
  text = {quoted(title)}
  font = "{font}"
  color = "{color}"
}}
'''
    selected_color = '#111820' if sum(bytes.fromhex(o['accent'][1:])) > 360 else '#ffffff'
    text += f'''+ boot_menu {{
  left = {g['left']}%
  top = 36%
  width = {g['width']}%
  height = 43%
  item_font = "Fusion Menu Regular {o['size']}"
  selected_item_font = "Fusion Selected Regular {o['size']}"
  item_color = "{o['text']}"
  selected_item_color = "{selected_color}"
  item_height = {g['height']}
  item_padding = 16
  item_spacing = {g['spacing']}
  icon_width = 0
  icon_height = 0
  selected_item_pixmap_style = "select_*.png"
  scrollbar = false
}}
+ label {{
  id = "__timeout__"
  left = {g['left']}%
  top = 89%
  width = {g['width']}%
  height = 4%
  text = "Starting the default system in %d seconds"
  font = "Fusion Detail Regular 17"
  color = "{o['accent']}"
}}
'''
    return text


def source_image(options, expected=''):
    from PIL import Image, ImageOps
    if not options['background']: return Image.new('RGB', SIZE, options['base']), ''
    path = Path(options['background'])
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 40*1024*1024:
            raise ValueError('Choose a regular picture smaller than 40 MiB.')
        data = stream.read(40*1024*1024+1)
    fingerprint = grub.digest(data)
    if expected and fingerprint != expected:
        raise ValueError('The background picture changed. Refresh its preview before applying.')
    with Image.open(io.BytesIO(data)) as opened:
        if opened.width*opened.height > 40_000_000: raise ValueError('Choose a picture of at most 40 megapixels.')
        image = ImageOps.exif_transpose(opened).convert('RGB')
        return ImageOps.fit(image, SIZE, Image.Resampling.LANCZOS), fingerprint


def artwork(options, source):
    from PIL import Image, ImageDraw, ImageEnhance
    art = ImageEnhance.Brightness(source).enhance(1-options['dimming']/100).convert('RGBA')
    g = geometry(options); left = round(SIZE[0]*g['left']/100); width = round(SIZE[0]*g['width']/100)
    base = tuple(bytes.fromhex(options['base'][1:])); maximum = round(options['contrast']*2.55)
    strip = Image.new('RGBA', (SIZE[0], 1)); pixels = strip.load()
    for x in range(SIZE[0]):
        distance = max(left-x, x-(left+width), 0)
        pixels[x, 0] = (*base, round(maximum*max(.08, 1-distance/440)))
    art = Image.alpha_composite(art, strip.resize(SIZE))
    draw = ImageDraw.Draw(art); accent = options['accent']
    draw.rounded_rectangle((left-22, 216, left-16, 289), radius=3, fill=accent)
    draw.line((left, 885, left+width, 885), fill=accent, width=2)
    return art.convert('RGB')


def png(image):
    stream = io.BytesIO(); image.save(stream, format='PNG'); return stream.getvalue()


def preview(options, entries=()):
    from PIL import ImageDraw, ImageFont
    options = normalize(options); source, fingerprint = source_image(options)
    art = artwork(options, source); draw = ImageDraw.Draw(art); g = geometry(options)
    fonts = ROOT/'assets/fonts'
    heading = ImageFont.truetype(str(fonts/'Inter-Bold.otf'), 44)
    detail = ImageFont.truetype(str(fonts/'Inter-Medium.otf'), 17)
    menu = ImageFont.truetype(str(fonts/'Inter-Regular.otf'), options['size'])
    selected = ImageFont.truetype(str(fonts/'Inter-SemiBold.otf'), options['size'])
    left = round(SIZE[0]*g['left']/100); width = round(SIZE[0]*g['width']/100)
    def elide(text, face):
        while text and draw.textlength(text, font=face) > width-34: text = text[:-2]+'…'
        return text
    draw.text((left, 218), elide(options['heading'], heading), font=heading, fill=options['text'])
    draw.text((left, 303), elide(options['subtitle'], detail), font=detail, fill=options['text'])
    entries = entries or ['Arch Linux', 'Advanced options for Arch Linux', 'UEFI Firmware Settings']
    selected_color = '#111820' if sum(bytes.fromhex(options['accent'][1:])) > 360 else '#ffffff'
    for index, entry in enumerate(entries[:max(1, 464//(g['height']+g['spacing']))]):
        top = 389+g['padding']+index*(g['height']+g['spacing'])
        if index == 0:
            draw.rounded_rectangle((left+g['padding'], top, left+width-g['padding'], top+g['height']+2*g['border']),
                                   radius=8, fill=options['accent'])
        draw.text((left+g['padding']+g['border']+4, top+g['border']+(g['height']-options['size'])//2), elide(str(entry)[:200], selected if index == 0 else menu),
                  font=selected if index == 0 else menu, fill=selected_color if index == 0 else options['text'])
    if options['hints']:
        draw.text((left, 895), '↑ ↓ Select   Enter Start   E Edit   C Console', font=detail, fill=options['text'])
    draw.text((left, 970), 'Your existing boot countdown is kept', font=detail, fill=options['accent'])
    art.thumbnail((1120, 630))
    return {'image': base64.b64encode(png(art)).decode(), 'background_sha': fingerprint}


def prepare(options, expected=''):
    from PIL import Image, ImageDraw
    options = normalize(options); source, fingerprint = source_image(options, expected)
    files = {'source.png': png(source), 'background.png': png(artwork(options, source))}
    # GRUB adds the top/bottom slices outside item_height. Keep their sum below
    # item_spacing so the highlight never overlaps the following entry.
    selection = Image.new('RGBA', (24, 24)); draw = ImageDraw.Draw(selection)
    draw.rounded_rectangle((0, 0, 23, 23), radius=8, fill=options['accent'])
    cuts = (0, 8, 16, 24)
    for row, vertical in enumerate(('n', '', 's')):
        for col, horizontal in enumerate(('w', '', 'e')):
            files['select_'+(vertical+horizontal or 'c')+'.png'] = png(selection.crop((cuts[col], cuts[row], cuts[col+1], cuts[row+1])))
    with tempfile.TemporaryDirectory(prefix='fusion-grub-fonts-') as directory:
        for name, face, font_name, size in (
                ('menu', 'Regular', 'Fusion Menu', options['size']),
                ('selected', 'SemiBold', 'Fusion Selected', options['size']),
                ('heading', 'Bold', 'Fusion Heading', 44), ('detail', 'Medium', 'Fusion Detail', 17)):
            if options['size'] == 22:
                files[name+'.pf2'] = (ROOT/'grub/hyper-fusion'/(name+'.pf2')).read_bytes()
            else:
                target = Path(directory)/(name+'.pf2')
                grub.command([grub.executable('grub-mkfont', 'grub2-mkfont'), '--name', font_name, '--size', size,
                              '--output', target, ROOT/'assets/fonts'/('Inter-'+face+'.otf')])
                files[name+'.pf2'] = target.read_bytes()
    return {'files': {name: base64.b64encode(data).decode() for name, data in files.items()}, 'background_sha': fingerprint}


def prepared_as_user(options, expected):
    kwargs = {}
    if os.geteuid() == 0:
        value = os.environ.get('PKEXEC_UID', '')
        if not value.isdecimal() or int(value) == 0:
            raise RuntimeError('Open the Appearance tab as your desktop user to apply a design.')
        account = pwd.getpwuid(int(value))
        kwargs.update(user=account.pw_uid, group=account.pw_gid,
                      extra_groups=os.getgrouplist(account.pw_name, account.pw_gid))
    result = subprocess.run(['/usr/bin/python3', '-I', str(Path(__file__).resolve()), 'prepare'],
        input=grub.encoded({'options': options, 'background_sha': expected}), capture_output=True, timeout=90,
        env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8'}, **kwargs)
    if result.returncode:
        try: message = json.loads(result.stdout)['error']
        except (ValueError, KeyError): message = 'Could not prepare this design. Check the preview and try again.'
        raise RuntimeError(message)
    if len(result.stdout) > 32*1024*1024: raise ValueError('The prepared theme is too large.')
    return json.loads(result.stdout)


def appearance_block(fs_uuid, relative):
    if not re.fullmatch(r'[a-zA-Z0-9-]{4,80}', fs_uuid) or not re.fullmatch(r'/[a-zA-Z0-9_./@+-]+', relative):
        raise ValueError('This boot filesystem path cannot be represented safely in GRUB.')
    base = '($fusion_theme_device)'+relative
    return f'''{BEGIN}
{SIGNATURE}
if search --no-floppy --fs-uuid --set=fusion_theme_device {fs_uuid}; then
  if [ -f {base}/theme.txt ]; then
    insmod all_video
    insmod gfxterm
    insmod gfxmenu
    insmod png
    if loadfont {base}/menu.pf2; then
      loadfont {base}/selected.pf2
      loadfont {base}/heading.pf2
      loadfont {base}/detail.pf2
      set gfxmode=1920x1080,1280x720,1024x768,auto
      if terminal_output gfxterm; then
        set theme={base}/theme.txt
        export theme
      fi
    fi
  fi
fi
{END}
'''


def replace_appearance(config, block):
    if config.count(BEGIN) != config.count(END) or config.count(BEGIN) > 1:
        raise ValueError('The saved appearance section needs repair before it can be changed.')
    if BEGIN in config:
        pattern = r'(?m)^'+re.escape(BEGIN)+r'\n.*?^'+re.escape(END)+r'\n?'
        config, count = re.subn(pattern, lambda _: block, config, flags=re.S)
        if count != 1: raise ValueError('Could not locate the appearance section safely.')
        return config
    return config + ('' if not config or config.endswith('\n') else '\n') + block


class AppearanceStore(grub.Store):
    def __init__(self, root=Path('/'), checker=None):
        super().__init__(root, checker)
        self.state = root/'var/lib/hyper-fusion/grub-appearance'
        self.generator = root/GENERATOR.lstrip('/')
        self.assets = self.config.parent/'themes/hyper-fusion-editor'

    def safe_paths(self):
        super().safe_paths()
        for path in (self.assets, *self.assets.parents):
            if path == self.root: break
            if path.is_symlink(): raise RuntimeError('A theme destination is a symbolic link. Nothing was changed.')
            if path.exists() and self.root == Path('/'):
                info = path.stat()
                if info.st_uid != 0 or info.st_mode & 0o022: raise RuntimeError('Theme destinations must be writable only by root.')

    def status(self):
        data = grub.read_optional(self.state/'entries.json')
        value = json.loads(data) if data else {}
        return {'revision': self.revision(), 'can_undo': (self.state/'last.json').is_file(),
                'active': BEGIN in self.config.read_text(), 'options': value.get('options', {})}

    def unchanged_targets(self):
        return {key: (grub.read_optional(path), stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600)
                for key, path in self.files().items()}

    def apply(self, options, expected, menu_revision, background_sha='', alive=lambda: None, prepare_fn=prepared_as_user):
        options = normalize(options); config = self.config.read_text()
        if (expected and expected != self.revision()) or menu_revision != grub.digest(config.encode()):
            raise RuntimeError('The boot menu changed. Reload it before applying your design.')
        expected = self.revision()
        old = grub.read_optional(self.generator)
        if old and SIGNATURE.encode() not in old: raise RuntimeError('Another tool owns the appearance generator. Nothing was changed.')
        if not grub.menu_entries(config) and not re.search(r'\bblscfg\b', config):
            raise RuntimeError('This is a forwarding or empty GRUB configuration. Open the installed boot menu before changing its appearance.')
        self.check(config)
        prepared = prepare_fn(options, background_sha)
        if set(prepared.get('files', {})) != FILES: raise ValueError('The prepared theme is incomplete.')
        files = {name: base64.b64decode(data, validate=True) for name, data in prepared['files'].items()}
        if sum(map(len, files.values())) > 24*1024*1024: raise ValueError('The theme is too large.')
        for name, data in files.items():
            if not data.startswith(b'\x89PNG\r\n\x1a\n' if name.endswith('.png') else b'FILE\0\0\0\x04PFF2'):
                raise ValueError('Invalid theme asset: '+name)
        alive(); self.safe_paths(); self.assets.mkdir(parents=True, exist_ok=True, mode=0o755)
        target = self.assets/('design-'+uuid.uuid4().hex)
        target.mkdir(mode=0o755)
        try:
            for name, data in files.items(): grub.atomic(target/name, data, 0o644)
            grub.atomic(target/'theme.txt', theme_text(options).encode(), 0o644)
            saved = {**options, 'background': str(target/'source.png') if options['background'] else ''}
            grub.atomic(target/'appearance.json', grub.encoded(saved), 0o644)
            fs_uuid = grub.command([grub.executable('grub-probe', 'grub2-probe'), '--target=fs_uuid', target]).decode().strip()
            relative = grub.command([grub.executable('grub-mkrelpath', 'grub2-mkrelpath'), target]).decode().strip()
            block = appearance_block(fs_uuid, relative)
            revised = replace_appearance(config, block); self.check(revised)
            targets = {'config': (revised.encode(), stat.S_IMODE(self.config.stat().st_mode)),
                       'generator': (('#!/bin/sh\nexec tail -n +3 "$0"\n'+block).encode(), 0o755),
                       'entries': (grub.encoded({'version': 1, 'options': saved}), 0o600)}
            backup = self.publish(targets, expected, alive)
        except BaseException:
            # If a concurrent edit prevented rollback, retain any referenced
            # assets. A still-referenced design must never disappear.
            if target.name not in self.config.read_text(errors='replace') and target.name not in (grub.read_optional(self.generator) or b'').decode(errors='replace'):
                shutil.rmtree(target)
            raise
        return backup

    def system_appearance(self, expected, menu_revision, alive=lambda: None):
        config = self.config.read_text()
        if (expected and expected != self.revision()) or menu_revision != grub.digest(config.encode()):
            raise RuntimeError('The boot menu changed. Reload before restoring its appearance.')
        old = grub.read_optional(self.generator)
        if old and SIGNATURE.encode() not in old: raise RuntimeError('Another tool owns the appearance generator.')
        revised = replace_appearance(config, ''); self.check(revised)
        targets = self.unchanged_targets(); targets['config'] = (revised.encode(), targets['config'][1])
        targets['generator'] = (None, 0o755); targets['entries'] = (None, 0o600)
        return self.publish(targets, self.revision(), alive)


def catalog():
    result = {'presets': presets(), 'pictures': [], 'active': False, 'options': {}, 'can_undo': False}
    sets = json.loads((ROOT/'wallpaper/sets.json').read_text())
    for key, paths in sets.items():
        for relative in paths:
            result['pictures'].append({'name': NAMES.get(key, key)+' · '+Path(relative).stem.replace('-', ' ').title(),
                                       'path': str(ROOT/'wallpaper'/relative)})
    try:
        store = AppearanceStore()
        try: result.update(store.status())
        except PermissionError:
            text = store.config.read_text()
            result['active'] = BEGIN in text
            if result['active']:
                # Read only our immutable, public design metadata, never an
                # arbitrary path extracted from another GRUB theme.
                block = text.split(BEGIN, 1)[1].split(END, 1)[0]
                match = re.search(r'/hyper-fusion-editor/(design-[0-9a-f]{32})/theme.txt', block)
                if match:
                    result['options'] = normalize(json.loads((store.assets/match[1]/'appearance.json').read_text()))
    except (OSError, ValueError, RuntimeError): pass
    return result


def main():
    try:
        action = sys.argv[1] if len(sys.argv) == 2 else ''
        if action == 'catalog': result = catalog()
        elif action in ('preview', 'prepare'):
            request = json.loads(sys.stdin.read(65537))
            if action == 'preview': result = preview(request['options'], request.get('entries', [])[:32])
            else: result = prepare(request['options'], request.get('background_sha', ''))
        else: raise ValueError('Open the Appearance tab in GRUB Boot Editor.')
        print(json.dumps(result)); return 0
    except Exception as error:
        print(json.dumps({'error': str(error)})); return 1


if __name__ == '__main__': raise SystemExit(main())
