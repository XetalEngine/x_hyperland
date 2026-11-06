#!/usr/bin/env python3
"""Resolve the desktop against fresh distro repositories without installing it.

Every pacman command uses --print and a disposable database/root/cache. This is
an availability and dependency check, not a claim that GPU/session tests passed.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tarfile
from urllib.request import Request, urlopen

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'installer'))
import dependencies
import runtime_install
import arch_runtime

ARCH=[(name,'https://geo.mirror.pkgbuild.com/'+name+'/os/x86_64') for name in ('core','extra','multilib')]
CACHY=('cachyos','https://cdn77.cachyos.org/repo/x86_64/cachyos')
MATRIX={
    'arch':('x86_64',ARCH),
    'endeavouros':('x86_64',[('endeavouros','https://mirror.alpix.eu/endeavouros/repo/endeavouros/x86_64'),*ARCH]),
    'cachyos-v3':('x86_64_v3 x86_64',[(name,'https://cdn77.cachyos.org/repo/x86_64_v3/'+name)
                    for name in ('cachyos-v3','cachyos-core-v3','cachyos-extra-v3')]+[CACHY,*ARCH]),
    'cachyos-v4':('x86_64_v4 x86_64_v3 x86_64',[(name,'https://cdn77.cachyos.org/repo/x86_64_v4/'+name)
                    for name in ('cachyos-v4','cachyos-core-v4','cachyos-extra-v4')]+[CACHY,*ARCH]),
    'manjaro':('x86_64',[(name,'https://mirror.alpix.eu/manjaro/stable/'+name+'/x86_64')
                    for name in ('core','extra','multilib')]),
}


def download_database(url, destination):
    request=Request(url,headers={'User-Agent':'HyperFusion-RepositoryCheck/1.0'})
    with urlopen(request,timeout=45) as response, destination.open('wb') as output:
        total=0
        while chunk:=response.read(1024*1024):
            total+=len(chunk)
            if total>100_000_000:raise RuntimeError('Repository database exceeds 100 MB: '+url)
            output.write(chunk)


def entries(path):
    result = {}
    with tarfile.open(path) as archive:
        for item in archive:
            if not item.name.endswith('/desc'):
                continue
            raw = archive.extractfile(item).read()
            fields = dict(block.split('\n', 1) for block in raw.decode().strip().split('\n\n') if '\n' in block)
            result[fields['%NAME%']] = (fields, raw)
    return result


def populate_older_system(root, date):
    """Create installed metadata from real historical packages and dependencies."""
    old = root/'historical'
    for directory in ('db/local', 'db/sync', 'cache', 'root'):
        (old/directory).mkdir(parents=True)
    config = '[options]\nArchitecture = x86_64\nSigLevel = Required DatabaseOptional\n'
    available = {}
    for repo in ('core', 'extra', 'multilib'):
        server = 'https://archive.archlinux.org/repos/'+date+'/'+repo+'/os/x86_64'
        database = old/'db/sync'/(repo+'.db')
        download_database(server+'/'+repo+'.db', database)
        available.update(entries(database))
        config += '['+repo+']\nServer = '+server+'\n'
    (old/'pacman.conf').write_text(config)
    wanted = ['base', 'linux', 'pacman', 'archlinux-keyring', 'hyprland', *dependencies.PACKAGES['arch']]
    args = [p for p in dict.fromkeys(wanted) if p in available]
    result = subprocess.run(['pacman', '--config', str(old/'pacman.conf'), '--dbpath', str(old/'db'),
                             '--root', str(old/'root'), '--cachedir', str(old/'cache'),
                             '--logfile', str(old/'pacman.log'), '-Sp', '--noconfirm',
                             '--print-format', '%n', *args], capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise RuntimeError(runtime_install.package_error_output(result))
    names = [name for name in result.stdout.splitlines() if name in available]
    for name in names:
        fields, raw = available[name]
        entry = root/'db/local'/(name+'-'+fields['%VERSION%'])
        entry.mkdir()
        (entry/'desc').write_bytes(raw)
        (entry/'files').write_text('%FILES%\n\n')
    (root/'db/local/ALPM_DB_VERSION').write_text('9\n')
    return len(names)


def resolve(name, historical=None):
    architecture,repositories=MATRIX[name]
    with tempfile.TemporaryDirectory(prefix='xetal-repository-check-') as temporary:
        root=Path(temporary)
        for directory in ('db/local','db/sync','cache','root'):(root/directory).mkdir(parents=True)
        config='[options]\nArchitecture = '+architecture+'\nSigLevel = Required DatabaseOptional\n'
        for repo,url in repositories:
            print(name+': reading '+repo,flush=True)
            download_database(url+'/'+repo+'.db',root/'db/sync'/str(repo+'.db'))
            config+='\n['+repo+']\nServer = '+url+'\n'
        index = arch_runtime.repository(root/'runtime')
        shutil.copyfile(index, root/'db/sync'/index.name)
        (root/'pacman.conf').write_text(arch_runtime.configuration(config, root/'runtime'))
        installed = populate_older_system(root, historical) if historical else 0
        prefix=['--dbpath',str(root/'db'),
                '--root',str(root/'root'),'--cachedir',str(root/'cache'),'--logfile',str(root/'pacman.log')]
        selected = arch_runtime.resolve(root/'pacman.conf', dependencies.PACKAGES['arch'], prefix)
        return {'status':'passed', 'historical':historical, 'installed_packages':installed,
                'resolved_packages':selected}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--distro',choices=MATRIX,action='append')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--historical', action='append', help='Also test an Arch snapshot, YYYY/MM/DD.')
    args=parser.parse_args()
    if not shutil.which('pacman'):parser.error('Run on an Arch-family host or in an Arch Linux CI container.')
    report={'checked_at':datetime.now(timezone.utc).isoformat(),'checks':{}}
    for name in args.distro or MATRIX:
        try:report['checks'][name]=resolve(name)
        except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:
            report['checks'][name]={'status':'failed','error':str(error)}
        item=report['checks'][name]
        print(name+': '+item['status']+('\n'+item['error'] if 'error' in item else ''),flush=True)
    for date in args.historical or []:
        import re
        if not re.fullmatch(r'\d{4}/\d{2}/\d{2}', date):
            parser.error('Historical date must be YYYY/MM/DD.')
        name = 'arch-from-'+date
        try:report['checks'][name] = resolve('arch', date)
        except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:
            report['checks'][name]={'status':'failed','error':str(error)}
        print(name+': '+report['checks'][name]['status'], flush=True)
    if args.output:args.output.write_text(json.dumps(report,indent=2)+'\n')
    return int(any(item['status']!='passed' for item in report['checks'].values()))


if __name__=='__main__':raise SystemExit(main())
