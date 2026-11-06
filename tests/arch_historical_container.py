#!/usr/bin/env python3
"""Install from a real old Arch base inside a disposable bubblewrap filesystem.

The host needs python3, bsdtar and bwrap. Root is used for namespace ownership;
the host package manager is never invoked. Intended for disposable CI runners.
"""
import argparse
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iso', default='2025.11.01')
    parser.add_argument('--snapshot', default='2025/11/05')
    parser.add_argument('--log', type=Path, default=Path('arch-historical-install.log'))
    parser.add_argument('--minimal', action='store_true', help='Start without Python or sudo and test prerequisite bootstrap.')
    args = parser.parse_args()
    if os.geteuid() != 0 or os.environ.get('XETAL_DISPOSABLE_ARCH_HISTORICAL') != '1':
        parser.error('Use only on a disposable CI runner with root and XETAL_DISPOSABLE_ARCH_HISTORICAL=1.')
    if not re.fullmatch(r'\d{4}\.\d{2}\.\d{2}', args.iso) or not re.fullmatch(r'\d{4}/\d{2}/\d{2}', args.snapshot):
        parser.error('Invalid archive date.')
    if not all(shutil.which(tool) for tool in ('bwrap', 'bsdtar')):
        parser.error('The runner needs bubblewrap and libarchive-tools.')
    with tempfile.TemporaryDirectory(prefix='fusion-historical-arch-') as temp:
        directory = Path(temp)
        base = 'https://archive.archlinux.org/iso/'+args.iso+'/'
        name = 'archlinux-bootstrap-x86_64.tar.zst'
        with urlopen(base+'sha256sums.txt', timeout=60) as response:
            expected = next(line.split()[0] for line in response.read().decode().splitlines()
                            if line.split()[-1].lstrip('*') == name)
        archive = directory/name
        with urlopen(base+name, timeout=120) as response, archive.open('wb') as output:
            shutil.copyfileobj(response, output)
        with archive.open('rb') as source:
            if hashlib.file_digest(source, 'sha256').hexdigest() != expected:
                raise RuntimeError('Historical bootstrap checksum mismatch.')
        subprocess.run(['bsdtar', '--no-same-owner', '-xf', str(archive), '-C', temp], check=True)
        root = directory/'root.x86_64'
        resolver = root/'etc/resolv.conf';resolver.unlink(missing_ok=True)
        shutil.copyfile('/etc/resolv.conf', resolver)
        (root/'etc/pacman.d/mirrorlist').write_text(
            'Server = https://archive.archlinux.org/repos/'+args.snapshot+'/$repo/os/$arch\n')
        script = '''set -e
touch /run/.containerenv
pacman-key --init
pacman-key --populate archlinux
if [ "$FUSION_TEST_MINIMAL" != 1 ]; then
    pacman -Syu --noconfirm --needed python sudo git
    python --version
fi
pacman -Q pacman glibc archlinux-keyring
printf '%s\n' 'Server = https://geo.mirror.pkgbuild.com/$repo/os/$arch' > /etc/pacman.d/mirrorlist
if [ "$FUSION_TEST_MINIMAL" = 1 ]; then
    /bin/bash /src/installer/bootstrap_packages.sh python
    python --version
fi
export XETAL_DISPOSABLE_ARCH=1
python /src/tests/arch_container.py
'''
        command = ['bwrap', '--bind', str(root), '/', '--ro-bind', str(ROOT), '/src',
                   '--dev', '/dev', '--proc', '/proc', '--tmpfs', '/tmp', '--tmpfs', '/run',
                   '--unshare-pid', '--unshare-ipc', '--unshare-uts', '--die-with-parent', '--new-session']
        for cap in ('CHOWN', 'FOWNER', 'DAC_OVERRIDE', 'SETUID', 'SETGID', 'SETFCAP'):
            command += ['--cap-add', 'CAP_'+cap]
        command += ['--setenv', 'HOME', '/root', '--setenv', 'PATH', '/usr/local/sbin:/usr/local/bin:/usr/bin',
                    '--setenv', 'FUSION_TEST_MINIMAL', '1' if args.minimal else '0',
                    '--chdir', '/src', '/bin/bash', '-c', script]
        with args.log.open('w') as log:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
        print('Historical Arch installation exit:', result.returncode, 'Log:', args.log, flush=True)
        return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
