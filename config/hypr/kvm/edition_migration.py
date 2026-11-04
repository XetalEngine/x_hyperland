"""Adopt a pre-edition installation without moving guest data or components."""
import fcntl
import os

import editions
import packages
import portable


def migrate(root=None):
    root=root or portable.data_root()
    legacy=root/'components'
    if not legacy.is_dir():return False
    marker=root/'.edition-migration.json'
    with (root/'.edition-migration.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if marker.exists():return False
        names=[name for name in packages.IDS if (legacy/name/'current/.component.json').is_file()]
        if not names:return False
        releases=[]
        for file in (root/'release.json',portable.ROOT/'catalog.json'):
            if file.is_file():
                release=packages.decode(file.read_bytes(),local_legacy=True)
                if release.get('edition') in (None,'xetallic'):releases.append(release)
        # Validate against signed metadata before touching any legacy adapter.
        runtimes=[]
        for name in names:
            entry=packages.installed(name,root)
            if entry.get('runtime'):
                if not any(release['components'].get(name)==entry for release in releases):
                    raise ValueError('Cannot verify the installed '+name+' release for migration.')
                runtimes.append((name,entry))
        for name,entry in runtimes:
            packages.prepare_runtime(name,entry,legacy/name/'current')
        destination=editions.component_root(root,'xetallic')
        (destination/'components').mkdir(parents=True,exist_ok=True,mode=0o700)
        for name in names:
            target=destination/'components'/name
            # Existing namespaced installations always take precedence.
            if not target.exists() and not target.is_symlink():
                target.symlink_to(os.path.relpath(legacy/name,target.parent),target_is_directory=True)
        if (root/'downloads').is_dir() and not (destination/'downloads').exists():
            (destination/'downloads').symlink_to('../../downloads',target_is_directory=True)
        if not (destination/'release.json').exists() and (root/'release.json').exists():
            portable._copy_new(root/'release.json',destination/'release.json')
        # Only an upgrade adopts Enhanced. A clean installation starts Basic.
        if not (root/'edition.json').exists():editions.select('xetallic',root)
        packages.atomic_json(marker,{'schema':1,'legacy_edition':'xetallic'})
        return True
