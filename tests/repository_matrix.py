#!/usr/bin/env python3
"""Resolve the desktop against fresh distro repositories without installing it.

Every pacman command uses --print and a disposable database/root/cache. This is
an availability and dependency check, not a claim that GPU/session tests passed.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'installer'))
import dependencies
import runtime_install

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


def resolve(name):
    architecture,repositories=MATRIX[name]
    with tempfile.TemporaryDirectory(prefix='xetal-repository-check-') as temporary:
        root=Path(temporary)
        for directory in ('db/local','db/sync','cache','root'):(root/directory).mkdir(parents=True)
        config='[options]\nArchitecture = '+architecture+'\nSigLevel = Required DatabaseOptional\n'
        for repo,url in repositories:
            print(name+': reading '+repo,flush=True)
            download_database(url+'/'+repo+'.db',root/'db/sync'/str(repo+'.db'))
            config+='\n['+repo+']\nServer = '+url+'\n'
        (root/'pacman.conf').write_text(config)
        prefix=['pacman','--config',str(root/'pacman.conf'),'--dbpath',str(root/'db'),
                '--root',str(root/'root'),'--cachedir',str(root/'cache'),'--logfile',str(root/'pacman.log')]
        def plan(operation,targets):
            result=subprocess.run([*prefix,operation,'--noconfirm','--print-format','%n %v',*targets],
                                  capture_output=True,text=True,timeout=120,env={**os.environ,'LC_ALL':'C'})
            if result.returncode:raise RuntimeError(runtime_install.package_error_output(result))
            return result.stdout
        desktop=plan('-Sp',dependencies.PACKAGES['arch'])
        problems=dependencies.package_version_problems(desktop)
        if problems:raise RuntimeError('\n'.join(problems))
        target=runtime_install.policy.manifest()
        package=runtime_install.BUNDLED/('hyprland-'+target['arch_package']+'-x86_64.pkg.tar.zst')
        if hashlib.sha256(package.read_bytes()).hexdigest()!=target['package_sha256']:
            raise RuntimeError('Bundled compositor hash mismatch')
        compositor=plan('-Up',[str(package)])
        return {'status':'passed','desktop_packages':desktop.strip().splitlines(),
                'compositor_packages':compositor.strip().splitlines()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--distro',choices=MATRIX,action='append')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if not shutil.which('pacman'):parser.error('Run on an Arch-family host or in an Arch Linux CI container.')
    report={'checked_at':datetime.now(timezone.utc).isoformat(),'checks':{}}
    for name in args.distro or MATRIX:
        try:report['checks'][name]=resolve(name)
        except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:
            report['checks'][name]={'status':'failed','error':str(error)}
        item=report['checks'][name]
        print(name+': '+item['status']+('\n'+item['error'] if 'error' in item else ''),flush=True)
    if args.output:args.output.write_text(json.dumps(report,indent=2)+'\n')
    return int(any(item['status']!='passed' for item in report['checks'].values()))


if __name__=='__main__':raise SystemExit(main())
