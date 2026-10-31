"""Signed KVM component feeds, bounded extraction and atomic per-component updates.

Importing this module performs no network or host modification. Downloaded code
is never executed by the installer, and installing a module never loads it.
"""
from pathlib import Path, PurePosixPath
import base64
import fcntl
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.parse
import urllib.request
import urllib.error

from portable import ROOT, data_root

SITE = 'https://www.xetal.net/community/site'
KEY = ROOT/'update-public.pem'
IDS = {'qemu','ovmf','tpm','kvm-amd','opencore','looking-glass','baseline'}
LEGACY_SOURCES = {'sources-qemu','sources-ovmf','sources-tpm','sources-kvm'}
MAX_MANIFEST = 512*1024
MAX_ARCHIVE = 8*1024**3
MAX_EXPANDED = 32*1024**3


def version(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d{1,9}\.\d{1,9}\.\d{1,9}',value):
        raise ValueError('Invalid release version')
    return tuple(map(int,value.split('.')))


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def validate(release):
    if not isinstance(release,dict) or release.get('schema')!=1 or release.get('app')!='kvm' or release.get('architecture')!='x86_64':
        raise ValueError('Unsupported KVM release')
    version(release.get('version'))
    if not isinstance(release.get('notes'),str) or len(release['notes'].encode())>16384:
        raise ValueError('Invalid release notes')
    entries=release.get('components')
    if not isinstance(entries,dict) or not 1<=len(entries)<=len(IDS) or set(entries)-IDS:
        raise ValueError('Invalid component inventory')
    for name,a in entries.items():
        if not isinstance(a,dict): raise ValueError('Invalid component')
        version(a.get('version'))
        filename=f'XetalKVM-{name}-{a["version"]}-linux-x86_64.tar.xz'
        if a.get('file')!=filename or type(a.get('size')) is not int or not 8<=a['size']<=MAX_ARCHIVE:
            raise ValueError('Invalid component archive')
        if type(a.get('unpacked_size')) is not int or not 1<=a['unpacked_size']<=MAX_EXPANDED:
            raise ValueError('Invalid expanded size')
        if not isinstance(a.get('sha256'),str) or not re.fullmatch('[a-f0-9]{64}',a['sha256']):
            raise ValueError('Invalid component hash')
        if not isinstance(a.get('label'),str) or len(a['label'])>120:
            raise ValueError('Invalid component label')
        if name=='kvm-amd' and (a.get('cpu')!='amd' or not isinstance(a.get('kernel'),str) or not re.fullmatch(r'[A-Za-z0-9_.+-]{1,100}',a['kernel'])):
            raise ValueError('The KVM module requires an exact kernel and processor match')
    return release


def decode(raw, key=KEY, *, local_legacy=False):
    if len(raw)>MAX_MANIFEST: raise ValueError('Release manifest too large')
    envelope=json.loads(raw)
    payload=base64.b64decode(envelope['payload'],validate=True)
    signature=base64.b64decode(envelope['signature'],validate=True)
    if len(signature)!=384: raise ValueError('Invalid release signature')
    with tempfile.TemporaryDirectory(prefix='xetal-kvm-signature-') as directory:
        sig=Path(directory)/'signature'; sig.write_bytes(signature)
        result=subprocess.run(['openssl','dgst','-sha256','-verify',str(key),'-signature',str(sig)],
                              input=payload,capture_output=True,timeout=15)
    if result.returncode: raise ValueError('KVM release signature verification failed')
    release = json.loads(payload)
    # Previous private previews included sources. Verify their signature before
    # filtering the local cache; network releases must always be binaries-only.
    if local_legacy and isinstance(release,dict) and isinstance(release.get('components'),dict):
        release['components'] = {k:v for k,v in release['components'].items() if k not in LEGACY_SOURCES}
    return validate(release)


def cpu_vendor():
    text=Path('/proc/cpuinfo').read_text()
    return 'amd' if 'AuthenticAMD' in text else 'intel' if 'GenuineIntel' in text else 'unknown'


def compatibility(name, entry, kernel=None, cpu=None, arch=None):
    if (arch or platform.machine())!='x86_64': return 'Requires an x86_64 Linux host'
    if name=='kvm-amd':
        if (cpu or cpu_vendor())!=entry['cpu']: return 'Custom module is for AMD; use standard KVM on this host'
        if (kernel or platform.release())!=entry['kernel']: return 'Requires kernel '+entry['kernel']
    return ''


def read_json(path, default=None):
    try: return json.loads(Path(path).read_text())
    except FileNotFoundError: return default


def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix='.'+path.name,dir=path.parent)
    try:
        with os.fdopen(fd,'w') as stream:
            json.dump(value,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp): os.unlink(temp)


def installed(name, root=None):
    if name not in IDS: raise ValueError('Unknown component')
    return read_json((root or data_root())/'components'/name/'current/.component.json',{})


def update_available(name, entry, current):
    """Only advertise installed components that can actually be upgraded."""
    return bool(current and current.get('sha256') != entry['sha256']
                and version(entry['version']) > version(current['version'])
                and not compatibility(name, entry))


def safe_members(archive, maximum):
    members=[];seen=set();total=0
    for item in archive:
        path=PurePosixPath(item.name)
        if (not item.name or item.name.startswith('/') or '\\' in item.name or any(p in ('','..','.') for p in item.name.split('/'))
                or not (item.isfile() or item.isdir()) or item.name in seen or len(item.name)>4096
                or path.parts[0]=='.component.json'):
            raise ValueError('Unsafe or duplicate archive entry: '+item.name[:120])
        seen.add(item.name);members.append(item);total+=item.size
        if len(members)>500000 or item.size<0 or total>maximum: raise ValueError('Archive exceeds its declared limits')
    if total!=maximum: raise ValueError('Expanded size does not match signed metadata')
    return members


def install_archive(name, entry, archive, root=None):
    root=root or data_root()
    problem=compatibility(name,entry)
    if problem: raise ValueError(problem)
    archive=Path(archive)
    if archive.stat().st_size!=entry['size'] or digest(archive)!=entry['sha256']:
        raise ValueError('Downloaded archive checksum or size is wrong')
    base=root/'components'/name;base.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (base/'.install.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        previous=installed(name,root)
        if previous and version(entry['version'])<version(previous['version']):
            raise ValueError('Refusing a component downgrade')
        if previous.get('sha256')==entry['sha256']: return False
        if previous.get('version')==entry['version']: raise ValueError('This component version has different bytes')
        if shutil.disk_usage(base).free<entry['unpacked_size']+64*1024**2: raise OSError('Not enough disk space to unpack the component')
        target=base/(entry['version']+'-'+entry['sha256'][:12])
        with tempfile.TemporaryDirectory(prefix='.unpack-',dir=base) as directory:
            stage=Path(directory)
            with tarfile.open(archive,'r:xz') as tar:
                members=safe_members(tar,entry['unpacked_size'])
                for member in members:
                    destination=stage/member.name
                    if member.isdir(): destination.mkdir(parents=True,exist_ok=True)
                    else:
                        destination.parent.mkdir(parents=True,exist_ok=True)
                        with tar.extractfile(member) as source, destination.open('xb') as output:
                            shutil.copyfileobj(source,output)
                        destination.chmod(0o755 if member.mode & 0o111 else 0o644)
            atomic_json(stage/'.component.json',entry)
            if target.exists():
                # A previous interrupted install may have finished extraction.
                if read_json(target/'.component.json')!=entry: raise ValueError('Conflicting installed component directory')
            else: os.replace(stage,target)
            temp=base/'.current-new'
            temp.unlink(missing_ok=True);temp.symlink_to(target.name)
            os.replace(temp,base/'current')
    return True


class Store:
    def __init__(self,site=SITE,root=None,key=KEY):
        url=urllib.parse.urlsplit(site)
        if url.scheme!='https' and not (url.scheme=='http' and url.hostname in ('127.0.0.1','localhost','::1')):
            raise ValueError('KVM downloads require HTTPS')
        if url.username or url.password or url.query or url.fragment: raise ValueError('Invalid release server URL')
        self.site=site.rstrip('/');self.root=root or data_root();self.key=key

    def _open(self,url):
        response=urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'XetalKVM/1','Accept':'application/json, application/octet-stream'}),timeout=45)
        if urllib.parse.urlsplit(response.url).scheme!=urllib.parse.urlsplit(url).scheme:
            response.close();raise ValueError('Download redirected to an insecure transport')
        return response

    def check(self):
        try:
            with self._open(self.site+'/api/app-release.php?app=kvm&signed=1') as stream:
                raw=stream.read(MAX_MANIFEST+1)
        except urllib.error.HTTPError as error:
            if error.code==404:
                raise RuntimeError('No online KVM release is published yet. Try checking for updates later.') from None
            raise
        release=decode(raw,self.key)
        cached=self.cached()
        if cached and version(release['version'])<version(cached['version']): raise ValueError('Server offered an older release')
        if cached and release['version']==cached['version'] and release!=cached:
            raise ValueError('Server changed a release without increasing its version')
        self.root.mkdir(parents=True,exist_ok=True)
        atomic_json(self.root/'release.json',json.loads(raw))
        return release

    def cached(self):
        path=self.root/'release.json'
        if not path.exists(): return None
        return decode(path.read_bytes(),self.key,local_legacy=True)

    def download(self,name,entry,progress=lambda *_:None):
        problem=compatibility(name,entry)
        if problem: raise ValueError(problem)
        cache=self.root/'downloads';cache.mkdir(parents=True,exist_ok=True,mode=0o700)
        target=cache/entry['file']
        with (cache/(name+'.lock')).open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            if target.exists() and target.stat().st_size==entry['size'] and digest(target)==entry['sha256']:
                return install_archive(name,entry,target,self.root)
            if shutil.disk_usage(cache).free<entry['size']+entry['unpacked_size']+64*1024**2: raise OSError('Not enough free space for download and extraction')
            partial=target.with_suffix('.part')
            try:
                from download_access import open_component
                with open_component(self.site,self.root,entry['file']) as stream, partial.open('wb') as output:
                    size=0
                    while chunk:=stream.read(1024*1024):
                        size+=len(chunk)
                        if size>entry['size']: raise ValueError('Download exceeded signed size')
                        output.write(chunk);progress(size,entry['size'])
                    output.flush();os.fsync(output.fileno())
                if size!=entry['size'] or digest(partial)!=entry['sha256']: raise ValueError('Incomplete or corrupt download')
                os.replace(partial,target)
            finally: partial.unlink(missing_ok=True)
            return install_archive(name,entry,target,self.root)
