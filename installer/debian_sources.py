#!/usr/bin/env python3
"""Prepare Debian 13 DVD installs for authenticated online package downloads."""
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile

import debian_runtime as debian
import runtime_install as runtime
from system_runtime import atomic

APT_DIR = Path('/etc/apt')
STATE = Path('/var/lib/xetal-hyprland/apt-sources')
KEYRING = Path('/usr/share/keyrings/debian-archive-keyring.gpg')
MARKER = '# Official Debian 13 mirrors added by Hyper Fusion Setup.\n'
SUITES = ('trixie', 'trixie-updates', 'trixie-security')
ALIASES = dict(zip(('stable', 'stable-updates', 'stable-security'), SUITES))


def covered(types, uris, suites, components):
    """Preserve existing mirrors, including deliberately configured local mirrors."""
    if 'deb' not in types or 'main' not in components or not uris:
        return set()
    # Many third-party repositories also call their suite "stable". Only
    # recognize that alias on Debian archive paths, not a browser/vendor feed.
    debian_archive = any(re.search(r'/debian(?:-security)?/?$', uri) for uri in uris)
    return {ALIASES.get(suite, suite) if debian_archive else suite for suite in suites} & set(SUITES)


def list_sources(text):
    lines, suites = [], set()
    for line in text.splitlines(keepends=True):
        entry = re.match(r'^\s*(deb(?:-src)?)\s+(?:\[[^\]\n]*\]\s+)?(.*)', line)
        if entry and entry[2].lower().startswith('cdrom:'):
            # A CD label may contain spaces and brackets, so do not tokenize it.
            line = '# Disabled installation media by Hyper Fusion Setup: '+line
        elif entry:
            words = entry[2].split('#', 1)[0].split()
            if len(words) >= 3:
                suites |= covered([entry[1]], [words[0]], [words[1]], words[2:])
        lines.append(line)
    return ''.join(lines), suites


def fields(lines):
    """Read deb822 fields and their continuation lines without rewriting the stanza."""
    values, locations, current = {}, {}, None
    for index, line in enumerate(lines):
        if line.startswith('#'):
            continue
        match = re.match(r'^([A-Za-z][A-Za-z0-9-]*):[ \t]*(.*)', line)
        if match:
            current = match[1].lower()
            if current in values:
                raise RuntimeError('Duplicate field in a Debian .sources stanza: '+match[1])
            values[current] = match[2].strip()
            locations[current] = [index]
        elif current and line[:1].isspace() and line.strip():
            values[current] += ' '+line.strip()
            locations[current].append(index)
    return values, locations


def replace_field(lines, locations, key, value):
    indexes = locations.get(key.lower(), [])
    if not indexes:
        text = ''.join(lines)
        return text+('' if not text or text.endswith('\n') else '\n')+key+': '+value+'\n'
    return ''.join(key+': '+value+'\n' if index == indexes[0] else line
                   for index, line in enumerate(lines) if index == indexes[0] or index not in indexes)


def deb822_sources(text):
    parts = re.split(r'(\r?\n[ \t]*\r?\n)', text)
    suites = set()
    for index in range(0, len(parts), 2):
        lines = parts[index].splitlines(keepends=True)
        values, locations = fields(lines)
        if values.get('enabled', 'yes').lower() in ('no', 'false', '0', 'off'):
            continue
        # Debian installation media URIs contain a bracketed label with spaces.
        uris = re.findall(r'cdrom:(?://)?\[[^\]]*\]\S*|\S+', values.get('uris', ''), re.I)
        remaining = [uri for uri in uris if not uri.lower().startswith('cdrom:')]
        if remaining != uris:
            parts[index] = replace_field(lines, locations, 'URIs', ' '.join(remaining)) if remaining else \
                replace_field(lines, locations, 'Enabled', 'no')
        suites |= covered(values.get('types', '').split(), remaining,
                          values.get('suites', '').split(), values.get('components', '').split())
    return ''.join(parts), suites


def prepare(contents):
    """Plan minimal source changes; a configured base mirror is left as chosen."""
    result, suites = {}, set()
    for name, text in contents.items():
        result[name], found = (deb822_sources if name.endswith('.sources') else list_sources)(text)
        suites |= found
    # A working base mirror means the administrator already selected repositories.
    # Only bootstrap missing online sources for DVD-only / unconfigured installs.
    if 'trixie' not in suites:
        text = MARKER
        for uri, group in (('https://deb.debian.org/debian', SUITES[:2]),
                           ('https://security.debian.org/debian-security', SUITES[2:])):
            missing = [suite for suite in group if suite not in suites]
            if missing:
                text += ('\nTypes: deb\nURIs: '+uri+'\nSuites: '+' '.join(missing)+
                         '\nComponents: main non-free-firmware\nSigned-By: '+str(KEYRING)+'\n')
        name = 'sources.list.d/xetal-debian.sources'
        number = 1
        while name in contents:
            name = f'sources.list.d/xetal-debian-{number}.sources'
            number += 1
        result[name] = text
    return result


def regular(path, directory=False):
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise RuntimeError('APT configuration must not use symbolic links: '+str(path))
    if path.exists() and not (path.is_dir() if directory else path.is_file()):
        raise RuntimeError('Unexpected APT configuration path: '+str(path))


def read_sources(apt_dir):
    regular(apt_dir, directory=True)
    parts = apt_dir/'sources.list.d'
    regular(parts, directory=True)
    paths = [apt_dir/'sources.list'] if (apt_dir/'sources.list').exists() or (apt_dir/'sources.list').is_symlink() else []
    if parts.exists():
        paths += sorted(p for p in parts.iterdir() if re.fullmatch(r'[A-Za-z0-9_.-]+\.(list|sources)', p.name))
    result, modes = {}, {}
    for path in paths:
        regular(path)
        name = str(path.relative_to(apt_dir))
        result[name] = path.read_bytes().decode('utf-8')
        modes[name] = stat.S_IMODE(path.stat().st_mode)
    return result, modes


def publish(apt_dir, before, after, modes, state):
    # Do not overwrite a source edited by another package manager during update.
    if read_sources(apt_dir) != (before, modes):
        raise RuntimeError('APT sources changed during Setup; retry to use the updated configuration.')
    names = [name for name, text in after.items() if before.get(name) != text]
    backup = Path(tempfile.mkdtemp(prefix=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-'), dir=state))
    record = {name: {'existed': name in before, 'mode': modes.get(name, 0o644)} for name in names}
    for name in names:
        if name in before:
            saved = backup/name
            saved.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            atomic(saved, before[name].encode(), 0o600)
    atomic(backup/'record.json', (json.dumps(record, indent=2)+'\n').encode(), 0o600)
    print('Original Debian package sources saved in '+str(backup), flush=True)
    applied = []
    try:
        for name in names:
            path = apt_dir/name
            regular(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic(path, after[name].encode(), modes.get(name, 0o644))
            applied.append(name)
    except BaseException:
        for name in reversed(applied):
            path = apt_dir/name
            regular(path)
            if path.read_bytes() != after[name].encode():
                raise RuntimeError('APT sources changed externally; originals are saved in '+str(backup))
            if name in before:
                atomic(path, before[name].encode(), modes[name])
            else:
                path.unlink()
        raise
    print('Debian package sources are ready for online installation.', flush=True)


def update(source_args=()):
    # Quiet level 1 omits terminal progress redraws but keeps downloads and errors.
    return subprocess.run([*debian.APT, '-q', '-o', 'APT::Update::Error-Mode=any',
                           '-o', 'Acquire::Retries=2', *source_args, 'update'],
                          env=debian.ENV).returncode


def refresh(apt_dir=APT_DIR, state=STATE):
    if os.geteuid() != 0 or not runtime.policy.debian_host():
        raise RuntimeError('Debian package source setup requires administrator access on Debian 13.')
    regular(state, directory=True)
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_path = state/'setup.lock'
    regular(lock_path)
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        before, modes = read_sources(apt_dir)
        after = prepare(before)
        if after == before:
            return update()
        if any(name not in before for name in after) and not KEYRING.is_file():
            raise RuntimeError('The Debian archive keyring is missing; repository signatures cannot be verified.')
        print('Checking Debian online repositories before saving repaired package sources…', flush=True)
        # First validate the repaired configuration with real authenticated APT.
        # Network/signature failures leave all original source files untouched.
        with tempfile.TemporaryDirectory(prefix='xetal-apt-') as temp:
            staging = Path(temp)
            (staging/'sources.list.d').mkdir()
            (staging/'sources.list').touch()
            for name, text in after.items():
                atomic(staging/name, text.encode(), modes.get(name, 0o644))
            code = update(['-o', 'Dir::Etc::sourcelist='+str(staging/'sources.list'),
                           '-o', 'Dir::Etc::sourceparts='+str(staging/'sources.list.d')])
        if code:
            print('Repository check failed; original Debian package sources were left unchanged.', flush=True)
            return code
        publish(apt_dir, before, after, modes, state)
        return 0


if __name__ == '__main__':
    try:
        raise SystemExit(refresh())
    except (OSError, RuntimeError, UnicodeError) as error:
        raise SystemExit('Debian package source setup failed: '+str(error))
