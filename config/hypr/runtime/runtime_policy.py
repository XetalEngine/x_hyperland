"""The compositor contract shared by Setup, updates and native effects."""
import json
import os
from pathlib import Path
import pwd
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


def installed(binary='Hyprland'):
    try:
        options = {}
        if os.geteuid() == 0:
            # Hyprland needs XDG_RUNTIME_DIR even for --version. Probe as the
            # authenticated desktop user, never as the privileged package helper.
            uid = int(os.environ.get('SUDO_UID', '0'))
            if uid <= 0: raise ValueError('A desktop user is required for the compositor probe.')
            account = pwd.getpwuid(uid)
            options = {'user':uid, 'group':account.pw_gid, 'extra_groups':[],
                       'env':{**os.environ, 'XDG_RUNTIME_DIR':'/run/user/'+str(uid),
                              'HOME':account.pw_dir, 'USER':account.pw_name, 'LOGNAME':account.pw_name}}
            if binary == 'Hyprland': binary = '/usr/bin/Hyprland'
        result = subprocess.run([binary, '--version'], capture_output=True, text=True, timeout=10, **options)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        return {'version': 'not installed', 'commit': ''}
    text = result.stdout+result.stderr
    version = re.search(r'Hyprland\s+(\d+\.\d+\.\d+)', text)
    commit = re.search(r'\bcommit ([a-f0-9]{40})\b', text)
    return {'version': version[1] if version else 'unknown', 'commit': commit[1] if commit else ''}


def problem(root=ROOT, binary='Hyprland'):
    target, actual = manifest(root), installed(binary)
    if actual['version'] == target['hyprland'] and actual['commit'] == target['commit']:
        return ''
    return ('This desktop requires Hyprland '+target['hyprland']+' ('+target['commit'][:8]+
            '); found '+actual['version']+'. Open Setup to install the matching compositor before applying this desktop.')


def require(root=ROOT):
    message = problem(root)
    if message: raise RuntimeError(message)


def filename(target):
    return 'hyprland-'+target['arch_package']+'-'+target['architecture']+'.pkg.tar.zst'


def package_url(target):
    return 'https://archive.archlinux.org/packages/h/hyprland/'+filename(target)
