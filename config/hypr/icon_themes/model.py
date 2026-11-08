"""One local icon selection for Qt, GTK and native Fusion applications.

The saved document includes a prebuilt theme for every palette. Readers never
change global icon settings, and theme switches need no cache rebuild or restart.
"""
from copy import deepcopy
import configparser
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from functools import lru_cache
from . import art

ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = {'version': 1, 'system': 'other', 'other': 'theme:Papirus-Dark', 'overrides': {}}
NAME = re.compile(r'[^/\\\x00-\x1f,=]{1,160}\Z')
ICON = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.+@-]{0,179}\Z')
MODES = ('dark','light','contrast')


def encode(value): return (json.dumps(value, indent=2, ensure_ascii=False)+'\n').encode()
def token(path): return hashlib.sha256(path.read_bytes() if path.exists() else b'').hexdigest()


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.'+path.name+'-', dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def validate(value):
    if not isinstance(value,dict) or value.get('version',1)!=1: raise ValueError('Unsupported icon preferences.')
    result=deepcopy(DEFAULTS);result.update({k:value[k] for k in DEFAULTS if k in value})
    for key in ('system','other'):
        selection=result[key]
        valid=isinstance(selection,str) and (selection in (('follow','other') if key=='system' else ('auto',))
            or selection.startswith('theme:') and bool(NAME.fullmatch(selection[6:]))
            or key=='system' and selection.startswith('builtin:') and selection[8:] in art.STYLES)
        if not valid: raise ValueError('Choose an available '+key+' icon set.')
    overrides=result['overrides']
    if not isinstance(overrides,dict) or len(overrides)>512: raise ValueError('Invalid individual icon choices.')
    normalized={}
    for name,path in overrides.items():
        if not isinstance(name,str) or not ICON.fullmatch(name): raise ValueError('Use an icon name without spaces or slashes.')
        if not isinstance(path,str): raise ValueError('Choose an image for '+name+'.')
        parts=Path(path).parts
        if not path.startswith('icon_themes/custom/') or len(parts)!=3 or '..' in parts or not re.fullmatch(r'[a-f0-9]{32}\.(svg|png)',parts[-1]):
            raise ValueError('Individual icons must be imported into this profile.')
        normalized[art.ALIASES.get(name,name)]=path
    result['overrides']=normalized
    return result


def load(root=None):
    root=Path(root or ROOT);path=root/'theme/icons.json'
    raw=path.read_bytes() if path.exists() else b''
    try: data=json.loads(raw) if raw else DEFAULTS
    except ValueError as error: raise ValueError('Icon preferences could not be read. Your saved choices were kept.') from error
    return validate(data),hashlib.sha256(raw).hexdigest()


def search_paths(root=None):
    root=Path(root or ROOT)
    data_home=Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))
    paths=[root/'icon_themes/.build/icons',root/'icon_themes/packs',root/'icon_themes/imported',data_home/'icons',Path.home()/'.icons']
    paths += [Path(p)/'icons' for p in os.environ.get('XDG_DATA_DIRS','/usr/local/share:/usr/share').split(':') if p]
    paths += [Path('/usr/local/share/icons'),Path('/usr/share/icons')]
    return list(dict.fromkeys(str(p) for p in paths))


def installed(root=None):
    found={}
    for directory in search_paths(root)[2:]:
        parent=Path(directory)
        if not parent.is_dir(): continue
        for path in sorted(parent.iterdir()):
            if path.name in found or path.name.startswith('Xetal-') or not NAME.fullmatch(path.name): continue
            index=path/'index.theme'
            if not index.is_file(): continue
            try:
                cfg=configparser.ConfigParser(interpolation=None,strict=False);cfg.read(index)
                item=cfg['Icon Theme'];directories=item.get('Directories','')+item.get('ScaledDirectories','')
                if not directories.strip(): continue  # cursor-only themes
                found[path.name]={'name':item.get('Name',path.name),'path':str(path), 'comment':item.get('Comment','')}
            except (OSError,ValueError,configparser.Error,KeyError): continue
    return found


def resolve_system(value, design):
    return 'Xetal-System-'+(design if design in art.STYLES else 'hollowgrove') if value=='follow' else 'Xetal-System-'+value[8:] if value.startswith('builtin:') else value[6:] if value.startswith('theme:') else ''


def resolve_other(value,mode): return ('Papirus-Light' if mode=='light' else 'Papirus-Dark') if value=='auto' else value[6:]


def prepared(value,root=None):
    """Build immutable, content-addressed overlays before making them visible."""
    root=Path(root or ROOT);value=validate(value);themes={}
    for path in value['overrides'].values():
        if not (root/path).is_file(): raise ValueError('An individual icon is missing. Choose it again or reset that icon.')
    for design in art.STYLES:
        for mode in MODES:
            parents=list(dict.fromkeys(filter(None,(resolve_system(value['system'],design),resolve_other(value['other'],mode),'hicolor'))))
            digest=hashlib.sha256(encode([art.VERSION,parents,value['overrides']])).hexdigest()[:24]
            name='Xetal-Icons-'+digest;target=root/'icon_themes/.build/icons'/name
            if not (target/'index.theme').is_file():
                target.parent.mkdir(parents=True,exist_ok=True)
                with tempfile.TemporaryDirectory(prefix='.icons-',dir=target.parent) as temporary:
                    folder=Path(temporary);(folder/'scalable').mkdir()
                    inherited=list(parents)
                    if inherited[0].startswith('Xetal-System-'):
                        # Keep our layer in this theme, ahead of the chosen app
                        # pack. An implicit hicolor in an inherited theme would
                        # otherwise take precedence over the Other Icons choice.
                        builtin=root/'icon_themes/packs'/inherited.pop(0)/'scalable'
                        if not builtin.is_dir(): raise ValueError('The built-in icon artwork is missing. Repair this profile.')
                        for source in builtin.glob('*.svg'):
                            shutil.copyfile(source,folder/'scalable'/source.name)
                    for icon,source in value['overrides'].items():
                        suffix=Path(source).suffix
                        for alias in (icon,*art.CATALOG.get(icon,('','','',()))[3]):
                            for ext in ('.png','.svg'):(folder/'scalable'/(alias+ext)).unlink(missing_ok=True)
                            shutil.copyfile(root/source,folder/'scalable'/(alias+suffix))
                    (folder/'index.theme').write_text('[Icon Theme]\nName=Fusion Icons\nInherits='+','.join(inherited)+'\nDirectories=scalable\n\n[scalable]\nSize=64\nType=Scalable\nMinSize=8\nMaxSize=1024\n')
                    try: os.rename(folder,target)
                    except OSError:
                        if not (target/'index.theme').is_file(): raise
            themes[design+':'+mode]=name
    # Relative profile paths survive staging and moving the checkout. User paths
    # are resolved by each reader on its own machine, never baked into releases.
    return {**value,'resolved':{'art_version':art.VERSION,'themes':themes}}


def ensure(root=None):
    root=Path(root or ROOT);path=root/'theme/icons.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        value,_=load(root);result=prepared(value,root)
        data=encode(result)
        if not path.exists() or path.read_bytes()!=data: atomic(path,data)
    return result


def save(value,expected,root=None):
    root=Path(root or ROOT);path=root/'theme/icons.json'
    value=validate(value)
    # Fail early for removed aftermarket themes. Built-ins and Follow are fully offline.
    available=installed(root)
    for key in ('system','other'):
        if value[key].startswith('theme:') and value[key][6:] not in available:
            raise ValueError('That icon set is no longer available. Choose another set or import it again.')
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if token(path)!=expected: raise ValueError('Icons changed elsewhere. Reload before applying your choices.')
        data=encode(prepared(value,root))
        if path.exists():
            stamp=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
            backup=root/'icon_themes/backups'/('icons-'+stamp+'.json');atomic(backup,path.read_bytes())
        atomic(path,data)
    return load(root)


def info(root=None,design=None,mode=None):
    root=Path(root or ROOT)
    try: state=json.loads((root/'theme/state.json').read_text())
    except (OSError,ValueError): state={}
    design=design or state.get('design','hollowgrove');mode=mode or state.get('mode','dark')
    name='Papirus-Light' if mode=='light' else 'Papirus-Dark'
    try:
        # Readers can outlive an update and have an older art.STYLES catalog.
        # Rebuilding here makes old/new processes overwrite each other's
        # resolved themes, feeding their live-style watchers indefinitely.
        # Installation/startup and explicit Apply prepare the shared document.
        value=json.loads((root/'theme/icons.json').read_text())
        themes=value['resolved']['themes']
        selected=themes.get(design+':'+mode,themes.get('hollowgrove:dark',name))
        if isinstance(selected,str) and NAME.fullmatch(selected):name=selected
    except (OSError,ValueError,KeyError,TypeError,AttributeError):pass
    return {'iconTheme':name,'iconSearchPaths':search_paths(root),'iconFallbackTheme':'hicolor'}


def apply_qt(root=None,design=None,mode=None):
    from PyQt6.QtGui import QIcon
    values=info(root,design,mode)
    QIcon.setThemeSearchPaths(values['iconSearchPaths']);QIcon.setFallbackThemeName('hicolor');QIcon.setThemeName(values['iconTheme'])
    return values['iconTheme']


def import_image(path,root=None):
    """Copy the selection; deleting the original must not break saved icons."""
    root=Path(root or ROOT);source=Path(path)
    if not source.is_file() or source.stat().st_size>8*1024*1024: raise ValueError('Choose an image smaller than 8 MB.')
    data=source.read_bytes()
    if source.suffix.lower()=='.svg':
        import xml.etree.ElementTree as ET
        try: tree=ET.fromstring(data)
        except ET.ParseError as error: raise ValueError('This SVG could not be read.') from error
        if tree.tag.rsplit('}',1)[-1]!='svg': raise ValueError('Choose an SVG image.')
        for node in tree.iter():
            if node.tag.rsplit('}',1)[-1] in ('script','foreignObject','image'): raise ValueError('Choose a self-contained vector icon without embedded content.')
            for key,text in node.attrib.items():
                if key.rsplit('}',1)[-1] in ('href','src') and not text.startswith('#'): raise ValueError('Choose a self-contained icon without external references.')
        suffix='.svg'
    else:
        from PIL import Image, UnidentifiedImageError
        import io
        try:
            with Image.open(source) as picture:
                if picture.width*picture.height>24_000_000: raise ValueError('Choose an image no larger than 24 megapixels.')
                picture=picture.convert('RGBA');picture.thumbnail((512,512),Image.Resampling.LANCZOS)
                output=io.BytesIO();picture.save(output,format='PNG');data=output.getvalue()
        except (UnidentifiedImageError,OSError,Image.DecompressionBombError) as error: raise ValueError('This image could not be read.') from error
        suffix='.png'
    target='icon_themes/custom/'+hashlib.sha256(data).hexdigest()[:32]+suffix
    if not (root/target).exists(): atomic(root/target,data)
    return target


def import_pack(path,root=None):
    """Import an extracted freedesktop theme, including safe local symlink aliases."""
    root=Path(root or ROOT);source=Path(path).resolve();index=source/'index.theme'
    if not index.is_file(): raise ValueError('Choose the extracted icon-set folder containing index.theme.')
    cfg=configparser.ConfigParser(interpolation=None,strict=False)
    try: cfg.read(index);name=cfg['Icon Theme'].get('Name',source.name)
    except (OSError,ValueError,configparser.Error,KeyError) as error: raise ValueError('The icon set has an invalid index.theme.') from error
    if not cfg['Icon Theme'].get('Directories','').strip(): raise ValueError('This folder does not contain an icon set.')
    files=[];total=0
    for folder,dirs,names in os.walk(source,followlinks=True):
        current=Path(folder);ancestors={p.resolve() for p in (current,*current.parents) if p==source or p.is_relative_to(source)}
        allowed=[]
        for directory in dirs:
            child=current/directory;resolved=child.resolve()
            if directory.startswith('.'):continue
            if not resolved.is_relative_to(source):raise ValueError('The icon set references folders outside its folder. Import a self-contained copy.')
            if resolved in ancestors:raise ValueError('This icon set contains a circular folder link.')
            allowed.append(directory)
        dirs[:]=allowed
        for filename in names:
            entry=Path(folder)/filename
            if entry.suffix.lower() not in ('.svg','.png','.xpm') and entry!=index: continue
            resolved=entry.resolve()
            if not resolved.is_relative_to(source) or not resolved.is_file(): raise ValueError('The icon set references files outside its folder. Import a self-contained copy.')
            total+=resolved.stat().st_size;files.append(entry)
            if total>512*1024*1024 or len(files)>80000: raise ValueError('Choose an icon set smaller than 512 MB and 80,000 files.')
    parent=root/'icon_themes/imported';parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.import-',dir=parent) as temporary:
        digest=hashlib.sha256()
        for sourcefile in sorted(files):
            relative=sourcefile.relative_to(source);data=sourcefile.read_bytes()
            digest.update(str(relative).encode());digest.update(b'\0');digest.update(hashlib.sha256(data).digest())
            to=Path(temporary)/relative;to.parent.mkdir(parents=True,exist_ok=True);to.write_bytes(data)
        ident='Fusion-Imported-'+digest.hexdigest()[:16];target=parent/ident
        if target.exists():return ident
        os.rename(temporary,target)
    return ident


def application_name(ident,original='',custom=False):
    """Recognize our legacy absolute .desktop icons; explicit shortcut edits win."""
    if custom:return ''
    if ident in art.APPLICATIONS:return art.APPLICATIONS[ident]
    for suffix,name in (('/file_manager/computer.svg','computer'),('/calculator/programmer_calculator/assets/calculator.svg','accessories-calculator'),('/kvm/icon.svg','xetal-kvm-settings')):
        if original.endswith(suffix):return name
    return ''


@lru_cache(maxsize=256)
def _index(path,mtime):
    cfg=configparser.ConfigParser(interpolation=None,strict=False)
    try:
        cfg.read(path);entry=cfg['Icon Theme']
        directories=list(dict.fromkeys((entry.get('Directories','')+','+entry.get('ScaledDirectories','')).split(',')))
        def rank(directory):
            size=cfg.getint(directory,'Size',fallback=48)
            return (0 if cfg.get(directory,'Type',fallback='')=='Scalable' else abs(size-64),directory)
        return sorted(filter(None,directories),key=rank),list(filter(None,entry.get('Inherits','').split(',')))
    except (OSError,ValueError,configparser.Error,KeyError): return [],[]


@lru_cache(maxsize=4096)
def lookup(theme,name,paths,seen=()):
    """Resolve preview artwork without changing the application's active theme."""
    if theme in seen or len(seen)>16: return ''
    inherited=[]
    for parent in paths:
        root=Path(parent)/theme;index=root/'index.theme'
        if not index.is_file(): continue
        directories,parents=_index(str(index),index.stat().st_mtime_ns);inherited+=parents
        for directory in directories:
            if Path(directory).is_absolute() or '..' in Path(directory).parts: continue
            for ext in ('.svg','.png','.xpm'):
                candidate=root/directory/(name+ext)
                if candidate.is_file(): return str(candidate)
    for parent in dict.fromkeys([*inherited,'hicolor']):
        result=lookup(parent.strip(),name,paths,(*seen,theme))
        if result:return result
    return ''


def preview_path(value,name,design='hollowgrove',mode='dark',root=None):
    root=Path(root or ROOT);canonical=art.ALIASES.get(name,name)
    if canonical in value['overrides']:return str(root/value['overrides'][canonical])
    system=resolve_system(value['system'],design);paths=tuple(search_paths(root))
    if system.startswith('Xetal-System-') and name in art.ALIASES:
        return str(root/'icon_themes/packs'/system/'scalable'/(name+'.svg'))
    return (lookup(system,name,paths) if system and not system.startswith('Xetal-System-') else '') or lookup(resolve_other(value['other'],mode),name,paths)


if __name__=='__main__': ensure()
