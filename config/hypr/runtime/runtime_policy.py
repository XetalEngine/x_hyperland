"""The compositor contract shared by Setup, updates and native effects."""
import json
import os
from pathlib import Path
import pwd
import platform
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def manifest(root=ROOT):
    data = json.loads((Path(root)/'runtime/manifest.json').read_text())
    checks = {'hyprland': r'\d+\.\d+\.\d+', 'commit': r'[a-f0-9]{40}',
              'arch_package': r'\d+\.\d+\.\d+-\d+',
              'package_sha256': r'[a-f0-9]{64}', 'signature_sha256': r'[a-f0-9]{64}'}
    if data.get('schema') != 1 or data.get('architecture') != 'x86_64':
        raise ValueError('Unsupported desktop runtime manifest.')
    for name, pattern in checks.items():
        if not isinstance(data.get(name), str) or not re.fullmatch(pattern, data[name]):
            raise ValueError('Invalid desktop runtime field: '+name)
    if data['arch_package'].rsplit('-', 1)[0] != data['hyprland']:
        raise ValueError('Compositor and package versions differ.')
    return data


def authenticated_account():
    """Recover the desktop identity supplied by Setup's administrator backend."""
    identities = {os.environ[key] for key in ('SUDO_UID', 'PKEXEC_UID', 'XETAL_SETUP_SU_UID') if key in os.environ}
    if len(identities) != 1:
        raise ValueError('Cannot identify the authenticated desktop user. Open Setup as your desktop user.')
    value = identities.pop()
    if not value.isascii() or not value.isdecimal() or int(value) <= 0:
        raise ValueError('Cannot identify the authenticated desktop user. Open Setup as your desktop user.')
    try:
        return pwd.getpwuid(int(value))
    except KeyError:
        raise ValueError('The authenticated desktop account no longer exists.') from None


def installed(binary='Hyprland'):
    try:
        options = {}
        if os.geteuid() == 0:
            # Hyprland needs XDG_RUNTIME_DIR even for --version. Probe as the
            # authenticated desktop user, never as the privileged package helper.
            account = authenticated_account()
            uid = account.pw_uid
            options = {'user':uid, 'group':account.pw_gid, 'extra_groups':[],
                       'env':{**os.environ, 'XDG_RUNTIME_DIR':'/run/user/'+str(uid),
                              'HOME':account.pw_dir, 'USER':account.pw_name, 'LOGNAME':account.pw_name}}
            if binary == 'Hyprland': binary = '/usr/bin/Hyprland'
        result = subprocess.run([binary, '--version'], capture_output=True, text=True, timeout=10, **options)
    except FileNotFoundError:
        return {'version': 'not installed', 'commit': ''}
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        return {'version': 'unavailable', 'commit': '', 'error': str(error)}
    if result.returncode:
        diagnostic = ' '.join((result.stderr or result.stdout).split())[:500] or 'no diagnostic output'
        return {'version': 'unavailable', 'commit': '',
                'error': 'Hyprland --version failed (exit '+str(result.returncode)+'): '+diagnostic}
    text = result.stdout+result.stderr
    version = re.search(r'Hyprland\s+(\d+\.\d+\.\d+)', text)
    commit = re.search(r'\bcommit ([a-f0-9]{40})\b', text)
    return {'version': version[1] if version else 'unknown', 'commit': commit[1] if commit else ''}


def problem(root=ROOT, binary='Hyprland'):
    target, actual = manifest(root), installed(binary)
    if actual.get('error'):
        return 'Could not verify Hyprland: '+actual['error']
    if actual['version'] == target['hyprland'] and actual['commit'] == target['commit']:
        fedora = fedora_manifest(root)
        if fedora and fedora_host():
            expected = {p['name']: p['evr']+'.'+p['architecture'] for p in fedora['packages']}
            if rpm_versions(expected) != expected:
                return 'The Fedora compositor packages differ from this desktop release. Open Setup to install the matching runtime and rebuild its effects.'
        debian = debian_manifest(root)
        if debian and debian_host():
            expected = {p['name']+':'+p['architecture']: p['version'] for p in debian['packages']}
            if deb_versions(expected) != expected:
                return 'The Debian compositor packages differ from this desktop release. Open Setup to install the matching runtime and rebuild its effects.'
        return ''
    return ('This desktop requires Hyprland '+target['hyprland']+' ('+target['commit'][:8]+
            '); found '+actual['version']+'. Open Setup to install the matching compositor before applying this desktop.')


def require(root=ROOT):
    message = problem(root)
    if message: raise RuntimeError(message)


def matches_requirement(required):
    actual = installed()
    if actual['version'] != required['hyprland'] or actual['commit'] != required['commit']: return False
    packages = required.get('fedora_packages')
    if packages and fedora_host() and rpm_versions(packages) != packages: return False
    packages = required.get('debian_packages')
    return not packages or not debian_host() or deb_versions(packages) == packages


def filename(target):
    return 'hyprland-'+target['arch_package']+'-'+target['architecture']+'.pkg.tar.zst'


def package_url(target):
    return 'https://archive.archlinux.org/packages/h/hyprland/'+filename(target)


def arch_manifest(root=ROOT):
    target = manifest(root)
    if target.get('arch_manifest') != 'arch.json':
        raise ValueError('Missing Arch runtime manifest.')
    data = json.loads((Path(root)/'runtime/arch.json').read_text())
    if (data.get('schema'), data.get('distribution'), data.get('architecture'),
        data.get('hyprland'), data.get('commit')) != (1, 'arch', 'x86_64', target['hyprland'], target['commit']):
        raise ValueError('Arch and desktop compositor requirements differ.')
    names = set()
    for package in data['packages']:
        name, version, arch = package['name'], package['version'], package['architecture']
        if (name in names or not re.fullmatch(r'[a-z][a-z0-9+-]*', name)
            or not re.fullmatch(r'[0-9][A-Za-z0-9.+:~-]*', version) or arch != 'x86_64'
            or package['file'] != name+'-'+version.split(':')[-1]+'-'+arch+'.pkg.tar.zst'
            or not re.fullmatch(r'[a-f0-9]{64}', package['sha256'])
            or not re.fullmatch(r'[a-f0-9]{64}', package['signature_sha256'])
            or not 0 < package['bytes'] < 100_000_000):
            raise ValueError('Invalid Arch runtime package: '+name)
        names.add(name)
    if not {'hyprland', 'aquamarine', 'hyprgraphics', 'hyprtoolkit', 'hyprlock'} <= names:
        raise ValueError('Incomplete Arch runtime bundle.')
    compositor = next(p for p in data['packages'] if p['name'] == 'hyprland')
    if (compositor['version'], compositor['sha256'], compositor['signature_sha256']) != (
            target['arch_package'], target['package_sha256'], target['signature_sha256']):
        raise ValueError('Arch compositor differs from the main manifest.')
    return data


def arch_versions(names):
    result = subprocess.run(['/usr/bin/pacman', '-Q', *names], capture_output=True, text=True,
                            timeout=15, env={**os.environ, 'LC_ALL':'C'})
    return dict(line.split() for line in result.stdout.splitlines()
                if len(line.split()) == 2 and line.split()[0] in names)


def fedora_host(data=None):
    if data is None:
        try: data = platform.freedesktop_os_release()
        except OSError: return False
    return data.get('ID') == 'fedora' and data.get('VERSION_ID') == '44'


def fedora_manifest(root=ROOT):
    target = manifest(root)
    name = target.get('fedora_manifest')
    if name is None: return None
    if name != 'fedora-44.json': raise ValueError('Unsupported Fedora runtime manifest.')
    data = json.loads((Path(root)/'runtime'/name).read_text())
    if (data.get('schema'), data.get('distribution'), data.get('release'), data.get('architecture'),
        data.get('hyprland'), data.get('commit')) != (1, 'fedora', '44', 'x86_64', target['hyprland'], target['commit']):
        raise ValueError('Fedora and desktop compositor requirements differ.')
    if data.get('key_file') != 'copr-key.gpg' or not re.fullmatch(r'[a-f0-9]{64}', data.get('key_sha256', '')):
        raise ValueError('Invalid Fedora signing key manifest.')
    names = set()
    for package in data['packages']:
        name, evr, arch = package['name'], package['evr'], package['architecture']
        if (name in names or not re.fullmatch(r'[a-z][a-z0-9+-]*', name)
            or not re.fullmatch(r'\d+:[\w.+~^-]+-[\w.+~^]+', evr) or arch not in ('x86_64', 'noarch')
            or package['file'] != name+'-'+evr.split(':', 1)[1]+'.'+arch+'.rpm'
            or not re.fullmatch(r'[a-f0-9]{64}', package['sha256']) or not 0 < package['bytes'] < 100_000_000):
            raise ValueError('Invalid Fedora package manifest: '+name)
        names.add(name)
    if not {'hyprland', 'hyprland-devel'} <= names or sum(p['bytes'] for p in data['packages']) >= 100_000_000:
        raise ValueError('Incomplete or oversized Fedora runtime bundle.')
    return data


def rpm_versions(names):
    try:
        result = subprocess.run(['/usr/bin/rpm', '-q', '--qf', '%{NAME} %{EPOCHNUM}:%{VERSION}-%{RELEASE}.%{ARCH}\n',
                                 *names], capture_output=True, text=True, timeout=15,
                                env={**os.environ, 'LC_ALL':'C'})
        return dict(line.split() for line in result.stdout.splitlines()
                    if len(line.split()) == 2 and line.split()[0] in names)
    except (OSError, subprocess.SubprocessError):
        return {}


def debian_host(data=None):
    if data is None:
        try: data = platform.freedesktop_os_release()
        except OSError: return False
    return data.get('ID') == 'debian' and data.get('VERSION_ID') == '13'


def debian_manifest(root=ROOT):
    target = manifest(root)
    name = target.get('debian_manifest')
    if name is None: return None
    if name != 'debian-13.json': raise ValueError('Unsupported Debian runtime manifest.')
    data = json.loads((Path(root)/'runtime'/name).read_text())
    if (data.get('schema'), data.get('distribution'), data.get('release'), data.get('architecture'),
        data.get('hyprland'), data.get('commit')) != (1, 'debian', '13', 'amd64', target['hyprland'], target['commit']):
        raise ValueError('Debian and desktop compositor requirements differ.')
    if (data.get('file') != 'debian-13-runtime.zip' or not re.fullmatch(r'[a-f0-9]{64}', data.get('sha256', ''))
            or not 0 < data.get('bytes', 0) < 100_000_000):
        raise ValueError('Invalid Debian runtime archive.')
    names = set()
    for package in data['packages']:
        name, version, arch = package['name'], package['version'], package['architecture']
        if (name in names or not re.fullmatch(r'[a-z0-9][a-z0-9+.-]*', name)
            or not re.fullmatch(r'[0-9][A-Za-z0-9.+~:-]*', version) or arch not in ('amd64', 'all')
            or not re.fullmatch(r'[A-Za-z0-9+._~%:-]+\.deb', package['file'])
            or not re.fullmatch(r'[a-f0-9]{64}', package['sha256']) or not 0 < package['bytes'] < 100_000_000):
            raise ValueError('Invalid Debian package manifest: '+name)
        names.add(name)
    if not {'hyprland', 'hyprland-dev', 'waybar', 'kitty', 'libsdl3-0'} <= names or sum(p['bytes'] for p in data['packages']) >= 100_000_000:
        raise ValueError('Incomplete or oversized Debian runtime bundle.')
    return data


def deb_versions(names):
    try:
        result = subprocess.run(['/usr/bin/dpkg-query', '-W', '-f=${Package}:${Architecture} ${Version} ${db:Status-Status}\n',
                                 *names], capture_output=True, text=True, timeout=15, env={**os.environ, 'LC_ALL': 'C'})
        return {f[0]: f[1] for line in result.stdout.splitlines()
                if len(f := line.split()) == 3 and f[0] in names and f[2] == 'installed'}
    except (OSError, subprocess.SubprocessError):
        return {}
