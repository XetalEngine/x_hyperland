"""Verified native Debian 13 runtime and a dedicated APT preference file."""
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile

import runtime_install as runtime

BUNDLE = runtime.BUNDLED/'debian-13'
PIN = Path('/etc/apt/preferences.d/xetal-hyprland')
MARKER = '# Managed by Hyper Fusion Setup: Debian 13 runtime\n'
ENV = {**os.environ, 'LC_ALL': 'C', 'DEBIAN_FRONTEND': 'noninteractive'}
APT = ['/usr/bin/apt-get', '-o', 'APT::Install-Recommends=false',
       '-o', 'APT::Get::AllowUnauthenticated=false']


def target():
    value = runtime.policy.debian_manifest()
    if value is None:
        raise RuntimeError('This release does not include a Debian runtime.')
    return value


def hold_text(required):
    return MARKER+'\n'+''.join(
        'Package: '+p['name']+'\nPin: version '+p['version']+'\nPin-Priority: 1001\n\n'
        for p in required['packages'])


def check_hold(text):
    if text and not text.startswith(MARKER):
        raise RuntimeError('The Xetal APT preference file belongs to another configuration. Review it before running Setup.')


def pinned(required=None):
    try:
        return not PIN.is_symlink() and PIN.read_text() == hold_text(required or target())
    except OSError:
        return False


def extract(directory, required=None):
    """Validate the complete archive before writing any flat package member."""
    required = required or target()
    archive = BUNDLE/required['file']
    if (not archive.is_file() or archive.stat().st_size != required['bytes']
            or hashlib.sha256(archive.read_bytes()).hexdigest() != required['sha256']):
        raise RuntimeError('The Debian runtime ZIP is missing or damaged. Extract the complete release and retry.')
    expected = {p['file']: p for p in required['packages']}
    with zipfile.ZipFile(archive) as source:
        members = source.infolist()
        if (len(members) != len(expected) or {m.filename for m in members} != set(expected)
                or any(m.file_size != expected[m.filename]['bytes'] for m in members)):
            raise RuntimeError('The Debian runtime ZIP does not match its package manifest.')
        paths = []
        for member in members:
            item = expected[member.filename]
            data = source.read(member)
            if hashlib.sha256(data).hexdigest() != item['sha256']:
                raise RuntimeError('Debian package checksum failed: '+member.filename)
            path = directory/member.filename
            with path.open('xb') as stream:
                stream.write(data)
            paths.append(path)
    return paths


def parse_plan(output):
    """Read APT's C-locale simulation, rejecting removals and ambiguous actions."""
    installed, removed = {}, set()
    for line in output.splitlines():
        if line.startswith('Remv '):
            removed.add(line.split()[1])
        elif line.startswith('Inst '):
            match = re.match(r'^Inst ([a-z0-9][a-z0-9+.-]*(?::[a-z0-9-]+)?) (?:\[[^\]]+\] )?\(([^\s()]+) ', line)
            if not match or match[1] in installed:
                raise RuntimeError('Unsupported APT transaction output; no package changes were requested.')
            installed[match[1]] = match[2]
    return installed, removed


def simulate(args, allow_remove=()):
    result = subprocess.run([*APT, '-s', '--allow-downgrades',
                             *([] if allow_remove else ['--no-remove']), 'install', *map(str, args)],
                            capture_output=True, text=True, timeout=300, env=ENV)
    if result.returncode:
        raise RuntimeError('Debian dependencies cannot be resolved. No packages have been changed. '
                           'Check that APT has an enabled Debian 13 (trixie) network mirror, '
                           'not only the installation DVD, and that its package lists refreshed successfully.\n'+
                           (result.stdout+'\n'+result.stderr).strip())
    plan, removed = parse_plan(result.stdout)
    if not removed <= set(allow_remove):
        raise RuntimeError('APT would remove an unrelated application: '+', '.join(sorted(removed-set(allow_remove))))
    return plan, removed


def package_args(paths, required, packages):
    bundled = {p['name'] for p in required['packages']}
    return [*map(str, paths), *[p for p in packages if p not in bundled]]


def refresh():
    """Refresh metadata before resolution; never install packages or edit sources."""
    print('Refreshing Debian package lists from the configured repositories…', flush=True)
    # APT normally succeeds even if some downloads fail and stale lists remain.
    # Setup must report that failure before resolving or changing the runtime.
    prefix = runtime.administrator()
    result = subprocess.run([*prefix, *APT,
                             '-o', 'APT::Update::Error-Mode=any',
                             '-o', 'Acquire::Retries=2', 'update'],
                            stderr=subprocess.PIPE, text=True, env={**os.environ, 'LC_ALL': 'C'})
    if result.stderr:
        print(result.stderr, end='' if result.stderr.endswith('\n') else '\n', flush=True)
    runtime.check_administrator_result(prefix, result.returncode, result.stderr or '')
    if result.returncode:
        raise RuntimeError('Debian package lists could not be refreshed. Check the network and the APT '
                           'repository errors above. A Debian 13 (trixie) network mirror is required; '
                           'an installation DVD alone is not enough. No packages have been changed.')


def preflight(packages):
    required = target()
    check_hold(PIN.read_text() if PIN.exists() else '')
    with tempfile.TemporaryDirectory(prefix='xetal-debian-preflight-') as temp:
        paths = extract(Path(temp), required)
        simulate(package_args(paths, required, packages))


def ensure(yes=False):
    required = target()
    if not runtime.policy.problem() and pinned(required):
        return False
    print('Installing the native Debian 13 Hyprland runtime and desktop dependencies, with exact-version recovery.', flush=True)
    if not yes and input('Install the Debian runtime and its package pins? [y/N] ').strip().lower() not in ('y', 'yes'):
        raise RuntimeError('Compositor setup cancelled.')
    prefix = runtime.administrator()
    args = [*prefix, '/usr/bin/python3', str(runtime.ROOT/'installer/system_debian_runtime.py')]
    with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as process:
        try:
            for line in process.stdout:
                if line.startswith('XETAL_RUNTIME_TRANSACTION '):
                    runtime.TRANSACTION = Path(line.strip().split(' ', 1)[1])
                    runtime.TRANSACTION_BACKEND = 'debian'
                else:
                    print(line, end='', flush=True)
            code = process.wait()
        except KeyboardInterrupt:
            process.wait()
            raise
    runtime.check_administrator_result(prefix, code)
    if code:
        raise RuntimeError('Debian runtime setup failed. See the package details above.')
    runtime.policy.require()
    if not pinned(required):
        raise RuntimeError('The Debian runtime package pins were not installed.')
    return bool(runtime.TRANSACTION)
