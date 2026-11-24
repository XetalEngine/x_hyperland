#!/usr/bin/env python3
"""Read-only app catalog: local Pacman/AppStream data, atomic cache, opt-in AUR.

No refresh or install commands run here. Package transactions stay in the panel's
reviewed terminal flow. Browsing never downloads icons or contacts a web service.
"""
from __future__ import annotations
import argparse
import configparser
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SEED = Path(__file__).with_name('software') / 'catalog.json'
SCHEMA = 2
DEB_APPS = Path(__file__).with_name('deb_apps.json')
NAME = re.compile(r'[a-zA-Z0-9@_+][a-zA-Z0-9@_.+\-]*\Z')
LANG = '{http://www.w3.org/XML/1998/namespace}lang'
MAX_CACHE = 40 * 1024 * 1024


def safe_url(text):
    if not isinstance(text,str): return ''
    try: value = urllib.parse.urlsplit(text or '')
    except ValueError: return ''
    return text if value.scheme in ('https', 'http') and value.hostname and not value.username else ''


def command(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=10,
                            env={**os.environ, 'LC_ALL': 'C'})
    if result.returncode:
        raise RuntimeError(result.stderr.strip()[:400] or 'Could not read Pacman configuration.')
    return result.stdout.strip()


def system_paths():
    if not shutil.which('pacman-conf'):
        raise RuntimeError('The app catalog requires an Arch-based system with Pacman.')
    db = Path(command(['pacman-conf', 'DBPath']))
    repos = [n for n in command(['pacman-conf', '--repo-list']).splitlines() if NAME.fullmatch(n)]
    data = [Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share')))]
    data += [Path(p) for p in os.environ.get('XDG_DATA_DIRS', '/usr/local/share:/usr/share').split(':') if p]
    desktops = list(dict.fromkeys(p/'applications' for p in data))
    return db, repos, desktops, Path('/usr/share/swcatalog')


def fields(data):
    values = {}; key = ''
    for line in data.decode('utf-8', 'replace').splitlines():
        if line.startswith('%') and line.endswith('%'):
            key = line.strip('%'); values[key] = []
        elif line and key:
            values[key].append(line)
    return values


def first(values, key):
    return next(iter(values.get(key, [])), '')


def package_records(db, repos):
    packages = {}; warnings = []
    for repo in repos:
        path = db/'sync'/(repo+'.db')
        try:
            with tarfile.open(path, 'r:*') as archive:
                for member in archive:
                    if not member.isfile() or not member.name.endswith('/desc') or member.size > 512*1024:
                        continue
                    stream = archive.extractfile(member)
                    if stream is None: continue
                    value = fields(stream.read()); name = first(value, 'NAME')
                    if not NAME.fullmatch(name) or name in packages: continue
                    packages[name] = dict(id='pacman/'+name, package=name, name=name,
                        summary=first(value, 'DESC'), description='', version=first(value, 'VERSION'),
                        repository=repo, source='pacman', kind='package', categories=[],
                        icon='package-x-generic', website=safe_url(first(value, 'URL')),
                        license=', '.join(value.get('LICENSE', [])), installed=False,
                        available=True, desktop_id='', desktop_file='')
        except (OSError, tarfile.TarError) as error:
            warnings.append(f'{repo}: {str(error)[:180]}')
    return packages, warnings


def installed_records(db):
    result = {}
    for path in (db/'local').glob('*/desc'):
        try:
            data = fields(path.read_bytes()); name = first(data, 'NAME')
            if NAME.fullmatch(name): result[name] = first(data, 'VERSION')
        except OSError: continue
    return result


def english(node, tag):
    values = node.findall(tag)
    element = next((n for n in values if not n.get(LANG)), None)
    if element is None: element = next((n for n in values if n.get(LANG) in ('en', 'en-US', 'en-GB')), None)
    return element


def text(node, tag):
    element = english(node, tag)
    return ''.join(element.itertext()).strip() if element is not None else ''


def description(node):
    element=english(node,'description')
    if element is None: return ''
    blocks=[]
    for part in element.iter():
        if part.tag not in ('p','li') or part.get(LANG) not in (None,'en','en-US','en-GB'): continue
        value=' '.join(''.join(part.itertext()).split())
        if value: blocks.append(('• ' if part.tag=='li' else '')+value)
    return '\n\n'.join(blocks)[:12000] or ' '.join(''.join(element.itertext()).split())[:12000]


def appstream_records(catalog, packages):
    count = 0; warnings = []
    for path in sorted((catalog/'xml').glob('*.xml*')):
        try:
            opener = gzip.open if path.suffix == '.gz' else open
            with opener(path, 'rb') as stream:
                events = ET.iterparse(stream, events=('start','end'))
                _, root = next(events); origin = root.get('origin', '')
                for event, node in events:
                    if event != 'end' or node.tag != 'component': continue
                    if node.get('type') == 'desktop-application':
                        for package in node.findall('pkgname'):
                            value = packages.get(package.text or '')
                            if value is None: continue
                            value.update(name=text(node,'name') or value['name'], summary=text(node,'summary') or value['summary'],
                                description=description(node),
                                categories=list(dict.fromkeys([*value['categories'],*(c.text for c in node.findall('categories/category') if c.text)])),
                                kind='app')
                            value['desktop_id'] = next((e.text for e in node.findall('launchable') if e.get('type')=='desktop-id'), '') or ''
                            value['website'] = next((safe_url(e.text or '') for e in node.findall('url') if e.get('type')=='homepage'), '') or value['website']
                            value['license'] = text(node, 'project_license') or value['license']
                            stock = next((i.text for i in node.findall('icon') if i.get('type')=='stock'), '')
                            if stock: value['icon'] = stock
                            for icon in node.findall('icon'):
                                if icon.get('type') != 'cached' or not icon.text: continue
                                # Never interpret icon metadata as a URL or an arbitrary filesystem path.
                                if Path(icon.text).name != icon.text or not re.fullmatch(r'[\w.\-]+', origin): continue
                                size = icon.get('width', '64')
                                if size not in ('64','128'): continue
                                candidate = catalog/'icons'/origin/(size+'x'+size)/icon.text
                                if candidate.is_file(): value['cached_icon'] = str(candidate)
                            count += 1
                    root.clear()
        except (OSError, ValueError, ET.ParseError) as error:
            warnings.append('App descriptions: '+str(error)[:180])
    return count, warnings


def desktop_entries(directories):
    result = {}
    for folder in directories:
        for path in sorted(folder.glob('*.desktop')):
            if path.name in result: continue
            try:
                ini = configparser.ConfigParser(interpolation=None, strict=False)
                ini.read(path, encoding='utf-8')
                data = dict(ini['Desktop Entry'])
                # A user's Hidden override also masks the system desktop file.
                result[path.name] = {} if data.get('hidden','').lower()=='true' else dict(data, path=str(path))
            except (OSError, UnicodeError, configparser.Error, KeyError): continue
    return result


def attach_desktop(value, desktops):
    ids = [value.get('desktop_id',''), value['package']+'.desktop']
    for name in ids:
        data = desktops.get(name)
        if not data or data.get('type') != 'Application': continue
        value['desktop_file'] = data['path']
        return


def merge_seed(packages, seed, desktops):
    for entry in seed['apps']:
        package = entry['package']; value = packages.get(package) if entry['source']=='pacman' else None
        available = value is not None
        if value is None:
            value = dict(version='',repository='',license='',description='',desktop_file='',installed=False)
            packages[entry['source']+'/'+package] = value
        value.update(entry)
        value['id'] = entry['source']+'/'+package
        value['available'] = available if entry['source']=='pacman' else entry['source']=='aur'
        value['desktop_id'] = entry.get('desktop_id', value.get('desktop_id',''))
        value['website'] = safe_url(value.get('website',''))
        if '/' in value['icon']:
            value['icon'] = str(ROOT/value['icon'])
        attach_desktop(value, desktops)
        if value['desktop_file'] and entry['source']=='vendor': value['installed'] = True


def fingerprint(db, repos, desktops, catalog):
    files = [SEED, DEB_APPS, Path(__file__), db/'local', *(db/'sync'/(r+'.db') for r in repos)]
    files += sorted((catalog/'xml').glob('*.xml*'))
    for folder in desktops:
        files.append(folder); files += sorted(folder.glob('*.desktop'))
    signature = [str(ROOT), repos]
    for path in files:
        try:
            s=path.stat(); signature.append([str(path), s.st_mtime_ns, s.st_size])
        except OSError: signature.append([str(path), None])
    return hashlib.sha256(json.dumps(signature,sort_keys=True).encode()).hexdigest()


def attach_deb_choices(apps):
    try: deb_apps = json.loads(DEB_APPS.read_text()).get('apps', [])
    except (OSError, ValueError): deb_apps = []
    choices = {name: app for app in deb_apps if app.get('status') in ('tested', 'launch_tested')
               for name in app.get('packages', []) if NAME.fullmatch(name)}
    for value in apps:
        if value.get('package') in choices:
            deb = choices[value['package']]
            value['deb_id'] = deb['id']; value['deb_note'] = deb.get('note', '')


def build_catalog(db, repos, desktops, catalog):
    seed = json.loads(SEED.read_text())
    packages, warnings = package_records(db, repos)
    needs_sync = bool(warnings) or not packages
    installed = installed_records(db)
    count, extra = appstream_records(catalog, packages); warnings += extra
    entries = desktop_entries(desktops)
    merge_seed(packages, seed, entries)
    attach_deb_choices(packages.values())
    for value in packages.values():
        name = value['package']; attach_desktop(value, entries)
        candidates=[name,*value.get('installed_aliases',[])]
        installed_name=next((n for n in candidates if n in installed),'')
        value['installed'] = value['installed'] or bool(installed_name)
        value['installed_version'] = installed.get(installed_name, '')
        value['installed_package'] = installed_name
    return dict(schema=SCHEMA,type='catalog',generated=time.time(),apps=list(packages.values()),
                categories=seed['categories'], repositories=repos, multilib='multilib' in repos,
                appstream_count=count, warnings=warnings, installed_packages=installed, needs_sync=needs_sync)


def cache_root():
    base = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home()/'.cache')))/'hyper-fusion/software'
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    return base


def atomic_json(path, value):
    with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,delete=False,prefix='.catalog-') as stream:
        temporary=Path(stream.name)
        json.dump(value,stream,ensure_ascii=False,separators=(',',':'))
    try: temporary.replace(path)
    finally: temporary.unlink(missing_ok=True)


def read_cache(path):
    try:
        if path.stat().st_size > MAX_CACHE: return None
        value=json.loads(path.read_text())
        return value if value.get('schema')==SCHEMA and isinstance(value.get('apps'),list) else None
    except (OSError,ValueError,AttributeError): return None


def emit(value):
    value = {**value, 'helpers':{name:bool(shutil.which(name)) for name in ('pacman','yay','paru')}}
    print(json.dumps(value,ensure_ascii=False,separators=(',',':')),flush=True)


def local_catalog(force=False):
    key = hashlib.sha256(str(ROOT).encode()).hexdigest()[:12]
    path = cache_root()/('catalog-'+key+'.json')
    cached = read_cache(path)
    if cached: emit({**cached, 'cached':True})
    paths = system_paths(); signature = fingerprint(*paths)
    if cached and not force and cached.get('fingerprint')==signature: return cached
    with path.with_suffix('.lock').open('a') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            if cached: return cached
            raise RuntimeError('The app catalog is being prepared. Try Refresh in a moment.')
        value = build_catalog(*paths)
        value['fingerprint'] = signature
        # Keep the last usable list if a repository is missing or being replaced.
        # A later refresh must retry transient failures instead of caching them forever.
        if value['warnings']:
            if cached:
                emit({**cached,'warnings':value['warnings'],'cached':True,'needs_sync':value['needs_sync']})
                return cached
        else: atomic_json(path, value)
        emit(value)
        return value


def aur_search(query, force=False, opener=urllib.request.urlopen):
    if any(ord(c)<32 for c in query):
        raise ValueError('Use 2–100 characters for an AUR search.')
    query = query.strip()
    if len(query)<2 or len(query)>100 or any(ord(c)<32 for c in query):
        raise ValueError('Use 2–100 characters for an AUR search.')
    path = cache_root()/('aur-'+hashlib.sha256(query.casefold().encode()).hexdigest()+'.json')
    cached = read_cache(path)
    if cached and not force and time.time()-cached['generated']<21600:
        return {**cached,'cached':True}
    url = 'https://aur.archlinux.org/rpc/v5/search/'+urllib.parse.quote(query,safe='')+'?by=name-desc'
    request = urllib.request.Request(url,headers={'User-Agent':'HyperFusion-Software/1','Accept':'application/json'})
    try:
        with opener(request,timeout=12) as response:
            raw=response.read(4*1024*1024+1)
        if len(raw)>4*1024*1024: raise RuntimeError('Too many AUR results. Narrow your search.')
        data=json.loads(raw)
        if not isinstance(data,dict): raise RuntimeError('The AUR returned an unexpected response.')
        if data.get('type')=='error': raise RuntimeError(str(data.get('error','AUR search failed.')))
        if data.get('version')!=5 or not isinstance(data.get('results'),list): raise RuntimeError('The AUR returned an unexpected response.')
        installed=installed_records(system_paths()[0]); apps=[]
        for item in data['results'][:500]:
            if not isinstance(item,dict): continue
            name=item.get('Name','')
            if not isinstance(name,str) or not NAME.fullmatch(name): continue
            licenses=item.get('License') or []
            if not isinstance(licenses,list): licenses=[]
            apps.append(dict(id='aur/'+name,package=name,name=name,summary=str(item.get('Description') or '')[:2000],description='',
                version=str(item.get('Version',''))[:200],source='aur',repository='AUR',kind='package',icon='package-x-generic',
                categories=[],installed=name in installed,installed_version=installed.get(name,''),available=True,
                website=safe_url(item.get('URL') or ''),desktop_file='',license=', '.join(s for s in licenses if isinstance(s,str))))
        attach_deb_choices(apps)
        result=dict(schema=SCHEMA,type='aur',query=query,generated=time.time(),apps=apps,truncated=len(data['results'])>500)
        atomic_json(path,result)
        # Bound this one-purpose search cache; never touch any other cache files.
        files=sorted(path.parent.glob('aur-*.json'),key=lambda p:p.stat().st_mtime,reverse=True)
        for old in files[128:]: old.unlink(missing_ok=True)
        return result
    except (OSError,ValueError,RuntimeError) as error:
        if cached: return {**cached,'cached':True,'warning':'AUR unavailable; showing saved results. '+str(error)[:160]}
        raise RuntimeError('Could not search the AUR. '+str(error)[:240]) from error


VENDOR_SITE = 'https://www.xetal.net/community/site/'
VENDOR_MANIFESTS = {
    'echo':'https://www.xetal.net/echo_f_updates/manifest.json',
    'linuxstudio':VENDOR_SITE+'api/release.php',
    'xmusic':VENDOR_SITE+'api/app-release.php?app=xmusic',
    'xvideo':VENDOR_SITE+'api/app-release.php?app=xvideo',
}


def vendor_release(product, opener=urllib.request.urlopen):
    """Resolve only published Linux artifacts, on an explicit Downloads action.

    These are explicit file downloads, never automatic execution or package installs.
    No versioned download links are frozen into the catalog.
    """
    if product not in VENDOR_MANIFESTS: raise ValueError('Unknown Xetal app.')
    request=urllib.request.Request(VENDOR_MANIFESTS[product],headers={'User-Agent':'HyperFusion-Software/1','Accept':'application/json'})
    with opener(request,timeout=12) as response: raw=response.read(1024*1024+1)
    if len(raw)>1024*1024: raise RuntimeError('The download service returned an oversized response.')
    data=json.loads(raw)
    if not isinstance(data,dict): raise RuntimeError('The download service returned an unexpected response.')
    release=data.get('release',data); choices=[]
    if not isinstance(release,dict): raise RuntimeError('The download service returned an unexpected release.')

    def add(artifact,label,expected,url,instructions):
        if not isinstance(artifact,dict): return
        filename=artifact.get('file',artifact.get('filename',''))
        checksum=artifact.get('sha256','');size=artifact.get('sizeBytes',artifact.get('size',0))
        if (not isinstance(filename,str) or not re.fullmatch(expected,filename)
            or not isinstance(checksum,str) or not re.fullmatch(r'[a-fA-F0-9]{64}',checksum)
            or type(size) is not int or size<=0): return
        choices.append(dict(label=label,filename=filename,sha256=checksum,size=size,
                            url=url(filename),instructions=instructions))

    installer_help='After downloading, open a terminal in Downloads and run sh followed by the .run filename. The installer guides you through setup.'
    appimage_help='After downloading, make the AppImage executable in its file properties, then open it.'
    archive_help='Extract the downloaded archive into a folder, then open run.sh from that folder.'
    platforms=release.get('platforms',{})
    linux=platforms.get('linux',{}) if isinstance(platforms,dict) else {}
    if not isinstance(linux,dict): linux={}
    if product=='echo':
        version=linux.get('version','')
        if not isinstance(version,str) or not re.fullmatch(r'\d+\.\d+\.\d+',version): raise RuntimeError('No published Linux release was found.')
        stem=re.escape('Echo_Future-'+version+'-linux-x86_64')
        url=lambda filename:'https://www.xetal.net/echo_f_updates/files/'+urllib.parse.quote(filename,safe='')
        installer=linux.get('installer',{})
        if isinstance(installer,dict) and installer.get('mode')=='bundled' and installer.get('version')==version:
            add(installer,'Installer · .run',stem+r'-setup\.run',url,installer_help)
        add(linux,'Portable · .tar.gz',stem+r'\.tar\.gz',url,archive_help)
    elif product=='linuxstudio':
        version=release.get('buildVersion','')
        if release.get('arch')!='x86_64' or not isinstance(version,str) or not re.fullmatch(r'\d+(?:\.\d+){2,4}',version): raise RuntimeError('No published Linux x86_64 release was found.')
        stem=r'ls2026-x86_64_[a-z]+-'+re.escape(version)
        add(release,'AppImage',stem+r'\.AppImage',lambda _:VENDOR_SITE+'api/d.php?t=a',appimage_help)
        add(release.get('targz'),'Portable · .tar.gz',stem+r'\.tar\.gz',lambda _:VENDOR_SITE+'api/d.php?t=g',archive_help)
    else:
        version=release.get('version','')
        if release.get('app')!=product or release.get('architecture')!='x86_64' or not isinstance(version,str) or not re.fullmatch(r'\d+\.\d+\.\d+',version): raise RuntimeError('No published Linux x86_64 release was found.')
        stem=re.escape(('XMusic' if product=='xmusic' else 'XVideo')+'-'+version+'-linux-x86_64')
        url=lambda filename:VENDOR_SITE+'Downloads/'+product+'/'+urllib.parse.quote(filename,safe='')
        add(linux.get('installer'),'Installer · .run',stem+r'-install\.run',url,installer_help)
        add(linux.get('appimage'),'AppImage',stem+r'\.AppImage',url,appimage_help)
        add(linux.get('archive'),'Portable · .tar.gz',stem+r'\.tar\.gz',url,archive_help)
    if not choices: raise RuntimeError('No Linux download is published right now. Check the official downloads page.')
    return dict(type='vendor',product=product,version=version,choices=choices)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh',action='store_true');mode=parser.add_mutually_exclusive_group();mode.add_argument('--aur');mode.add_argument('--vendor',choices=tuple(VENDOR_MANIFESTS))
    args=parser.parse_args()
    try:
        if args.vendor is not None: emit(vendor_release(args.vendor))
        elif args.aur is not None: emit(aur_search(args.aur,args.refresh))
        else: local_catalog(args.refresh)
        return 0
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:
        emit(dict(type='error',message=str(error)[:600]));return 1

if __name__=='__main__': raise SystemExit(main())
