"""Fedora 44's signed, versioned runtime; no package changes at import time."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tomllib

import runtime_install as runtime

BUNDLE = runtime.BUNDLED/'fedora-44'
PIN = Path('/etc/dnf/versionlock.toml')
BEGIN = '# BEGIN Xetal Hyprland runtime\n'
END = '# END Xetal Hyprland runtime\n'
COMMENT = 'Managed by Hyper Fusion Setup'


def target():
    value = runtime.policy.fedora_manifest()
    if value is None: raise RuntimeError('This release does not include a Fedora runtime.')
    return value


def split_hold(text):
    if BEGIN not in text and END not in text:
        # `dnf versionlock add` rewrites TOML and drops ordinary comments. Its
        # per-entry comment field survives, so ownership must survive it too.
        starts = list(re.finditer(r'(?m)^[ \t]*\[\[packages\]\][ \t]*(?:#[^\n]*)?\n', text))
        base = text[:starts[0].start()] if starts else text
        owned = []
        for index, match in enumerate(starts):
            chunk = text[match.start():starts[index+1].start() if index+1<len(starts) else len(text)]
            entry = tomllib.loads(chunk)['packages'][0]
            if entry.get('comment') == COMMENT: owned.append(chunk.rstrip()+'\n')
            else: base += chunk
        return base, BEGIN+''.join(owned)+END if owned else ''
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        raise RuntimeError('The managed Fedora version lock was edited; repair its markers before retrying.')
    before, rest = text.split(BEGIN)
    block, after = rest.split(END)
    return before+after, BEGIN+block+END


def same_hold(left, right):
    def entries(text):
        return sorted(json.dumps(p, sort_keys=True) for p in tomllib.loads(text).get('packages', []))
    return entries(left) == entries(right)


def hold_block(required):
    lines = [BEGIN.rstrip()]
    for package in required['packages']:
        lines += ['[[packages]]', 'name = '+json.dumps(package['name']),
                  'comment = '+json.dumps(COMMENT), '[[packages.conditions]]',
                  'key = "evr"', 'comparator = "="', 'value = '+json.dumps(package['evr']),
                  '[[packages.conditions]]', 'key = "arch"', 'comparator = "="',
                  'value = '+json.dumps(package['architecture']), '']
    return '\n'.join(lines)+END


def with_hold(text, required):
    base, _ = split_hold(text)
    parsed = tomllib.loads(base or 'version = "1.0"\n')
    if parsed.get('version') != '1.0': raise RuntimeError('Unsupported DNF version-lock format.')
    names = {p['name'] for p in required['packages']}
    if any(p.get('name') in names for p in parsed.get('packages', [])):
        raise RuntimeError('A user-managed DNF version lock overlaps the compositor bundle. Review that lock before running Setup.')
    return (base if base.strip() else 'version = "1.0"\n').rstrip()+'\n\n'+hold_block(required)


def pinned(required=None):
    required = required or target()
    try:
        text = PIN.read_text()
        with_hold(text, required)  # Check for conflicting user-owned rules.
        return same_hold(split_hold(text)[1], hold_block(required))
    except (OSError, ValueError, RuntimeError): return False


def bundled(required=None):
    required = required or target()
    paths = []
    for item in [dict(file=required['key_file'], sha256=required['key_sha256']), *required['packages']]:
        path = BUNDLE/item['file']
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise RuntimeError('The Fedora runtime bundle is missing or damaged: '+path.name+'. Extract a complete release ZIP and retry.')
        paths.append(path)
    return paths


def preflight(packages):
    required = target(); paths = bundled(required)
    result = subprocess.run(['dnf', '--version'], capture_output=True, text=True, timeout=15)
    if not re.search(r'dnf5 version 5\.', result.stdout):
        raise RuntimeError('Fedora runtime setup requires DNF 5.')
    versions = subprocess.run(['dnf', 'repoquery', '--latest-limit=1', '--queryformat=%{name} %{version}\n',
                               'waybar', 'kitty'], capture_output=True, text=True, timeout=300,
                              env={**os.environ, 'LC_ALL':'C'})
    import dependencies
    wallpaper = next(p for p in required['packages'] if p['name']=='hyprpaper')['evr']
    problems = dependencies.package_version_problems(versions.stdout+'\nhyprpaper '+wallpaper+'\n')
    if versions.returncode or problems:
        raise RuntimeError('Fedora desktop versions could not be verified before setup.\n'+
                           ('\n'.join(problems) or versions.stderr.strip()))
    # --assumeno resolves without installing or downloading RPMs. DNF uses exit
    # status 1 for a resolved transaction declined at its confirmation prompt.
    # Accept only that documented prompt or a successful no-op, in the C locale.
    current = PIN.read_text() if PIN.exists() else ''
    with_hold(current, required)  # Never loosen a user's existing lock.
    old_block = split_hold(current)[1]
    if old_block and not same_hold(old_block, hold_block(required)):
        print('The Fedora runtime requirement changed; Setup will resolve its replacement under administrator authentication.', flush=True)
        return
    result = subprocess.run(['dnf', '--assumeno', '--setopt=install_weak_deps=False',
                             'install', *map(str, paths[1:]), *packages],
                            capture_output=True, text=True, timeout=300,
                            env={**os.environ, 'LC_ALL':'C'})
    output = result.stdout+'\n'+result.stderr
    if result.returncode != 0 and not (result.returncode == 1 and 'Transaction Summary:' in output
                                      and output.rstrip().endswith('Operation aborted by the user.')):
        raise RuntimeError('Fedora dependencies cannot be resolved. No packages have been changed.\n'+output.strip())


def ensure(yes=False):
    required = target()
    if not runtime.policy.problem() and pinned(required): return False
    bundled(required)
    print('Required desktop compositor: Hyprland '+required['hyprland']+'; install and hold the signed Fedora 44 runtime.', flush=True)
    print('Fedora runtime publisher: '+required['publisher']+'. No COPR repository will be enabled.', flush=True)
    if not yes and input('Install the Fedora runtime and its version locks? [y/N] ').strip().lower() not in ('y', 'yes'):
        raise RuntimeError('Compositor setup cancelled.')
    args = [*runtime.administrator(), '/usr/bin/python3', str(runtime.ROOT/'installer/system_fedora_runtime.py')]
    with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as process:
        try:
            for line in process.stdout:
                if line.startswith('XETAL_RUNTIME_TRANSACTION '):
                    runtime.TRANSACTION = Path(line.strip().split(' ', 1)[1])
                    runtime.TRANSACTION_BACKEND = 'fedora'
                else: print(line, end='', flush=True)
            code = process.wait()
        except KeyboardInterrupt:
            process.wait(); raise
    if code: raise RuntimeError('Fedora compositor setup failed. See the package details above.')
    runtime.policy.require()
    if not pinned(required): raise RuntimeError('The Fedora runtime version locks were not installed.')
    return bool(runtime.TRANSACTION)
