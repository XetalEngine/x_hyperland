"""Package inventory and explicit, reviewable reconciliation (no database copying)."""
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess

NAME = re.compile(r'[A-Za-z0-9@_+][A-Za-z0-9@_.+:-]*\Z')
PROTECTED = {'base', 'filesystem', 'glibc', 'pacman', 'bash', 'coreutils', 'systemd', 'systemd-libs',
             'sudo', 'python', 'python-pyqt6', 'linux', 'linux-lts', 'linux-zen', 'linux-firmware',
             'hyprland', 'aquamarine', 'waybar', 'kitty', 'grub', 'mkinitcpio'}


def command(argv):
    result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60,
                            env={**os.environ, 'LC_ALL': 'C'})
    if result.returncode == 1 and argv == ['pacman', '-Qqm'] and not result.stderr.strip(): return ''
    if result.returncode: raise RuntimeError(result.stderr.strip() or 'Package inventory failed.')
    return result.stdout


def snapshot(run=command):
    all_packages = run(['pacman', '-Q']).splitlines()
    explicit = set(run(['pacman', '-Qqe']).split())
    # Empty foreign package lists legitimately return pacman's status 1.
    foreign = set(run(['pacman', '-Qqm']).split())
    rows = []
    for line in all_packages:
        name, version = line.split(maxsplit=1)
        rows.append(dict(name=name, version=version, explicit=name in explicit, source='foreign' if name in foreign else 'pacman'))
    validate(rows)
    return rows


def validate(rows):
    if not isinstance(rows, list) or len(rows) > 100000: raise ValueError('Invalid installed application list.')
    seen = set()
    for row in rows:
        if (not isinstance(row, dict) or not isinstance(row.get('name'), str) or not NAME.fullmatch(row['name'])
                or row['name'] in seen or row.get('source') not in ('pacman', 'foreign')
                or type(row.get('explicit')) is not bool or not isinstance(row.get('version'), str)
                or len(row['version']) > 200 or any(c.isspace() for c in row['version'])):
            raise ValueError('Invalid installed application record.')
        seen.add(row['name'])


def plan(wanted, current, protected=()):
    validate(wanted); validate(current)
    old = {p['name']: p for p in current}; new = {p['name']: p for p in wanted}
    missing = set(new) - set(old); extra = set(old) - set(new)
    blocked = sorted(extra & (PROTECTED | set(protected)))
    if blocked: raise ValueError('This package selection would remove desktop or boot requirements: ' + ', '.join(blocked))
    return dict(pacman=sorted(p for p in missing if new[p]['source'] == 'pacman'),
                foreign=sorted(p for p in missing if new[p]['source'] == 'foreign'), remove=sorted(extra),
                explicit=sorted(p for p in new if new[p]['explicit']),
                dependencies=sorted(p for p in new if not new[p]['explicit']),
                different_versions=[dict(name=p, saved=new[p]['version'], installed=old[p]['version'])
                                    for p in sorted(set(new) & set(old)) if new[p]['version'] != old[p]['version']])


def apply(wanted, administrator, run=None):
    """Called in a terminal, so AUR review/build/authentication remains usable.

    Install before removal. Pacman decides dependency validity; never -Rdd,
    --overwrite, raw database replacement or an implicit partial upgrade.
    """
    run = run or (lambda args: subprocess.run(args, check=True))
    current = snapshot(); operations = plan(wanted, current)
    cache = cached_foreign(wanted, operations['foreign'])
    missing_foreign = [p for p in operations['foreign'] if p not in cache]
    if missing_foreign and not (shutil.which('yay') or shutil.which('paru')):
        raise RuntimeError('Install Yay or Paru before restoring AUR applications: ' + ', '.join(missing_foreign))
    if operations['pacman']:
        administrator(['pacman', '-S', '--needed', '--noconfirm', '--', *operations['pacman']])
    if cache: administrator(['pacman', '-U', '--needed', '--noconfirm', '--', *map(str, cache.values())])
    if missing_foreign:
        # Foreign includes local .deb conversions as well as AUR. Try a locally
        # cached package first, otherwise the selected AUR helper must resolve
        # it; unavailable packages stop the operation before removal.
        helper = shutil.which('yay') or shutil.which('paru')
        run(['sudo', '-k'])
        try: run([helper, '-S', '--needed', '--', *missing_foreign])
        finally: run(['sudo', '-k'])
    if operations['remove']: administrator(['pacman', '-R', '--noconfirm', '--', *operations['remove']])
    for flag, key in (('--asexplicit', 'explicit'), ('--asdeps', 'dependencies')):
        if operations[key]: administrator(['pacman', '-D', flag, '--', *operations[key]])
    final = snapshot()
    expected = {p['name'] for p in wanted}; present = {p['name'] for p in final}
    extras = [p for p in final if p['name'] not in expected]
    if expected - present or any(p['explicit'] for p in extras):
        raise RuntimeError('The final installed application set does not match the archive. Review the operation report before continuing.')
    old = {p['name']:p for p in wanted}
    return {'different_versions': [dict(name=p['name'], saved=old[p['name']]['version'], installed=p['version'])
                                  for p in final if p['name'] in old and p['version'] != old[p['name']]['version']],
            'additional_dependencies': [p['name'] for p in extras]}


def cached_foreign(wanted, missing, directories=None, query=command):
    """Reuse locally built packages, including .deb conversions absent from AUR."""
    wanted = {p['name']:p['version'] for p in wanted if p['name'] in missing}; result = {}
    directories = directories or [Path('/var/cache/pacman/pkg'), Path.home()/'.cache/yay', Path.home()/'.cache/paru/clone']
    for directory in directories:
        if not wanted: break
        for path in Path(directory).glob('**/*.pkg.tar.*'):
            if path.name.endswith('.sig') or not any(path.name.startswith(name + '-') for name in wanted): continue
            if not path.is_file() or path.is_symlink(): continue
            try: name, version = query(['pacman', '-Qp', '--', str(path)]).strip().split(maxsplit=1)
            except (RuntimeError, ValueError): continue
            if name in wanted and version == wanted[name]: result[name] = path; wanted.pop(name)
    return result
