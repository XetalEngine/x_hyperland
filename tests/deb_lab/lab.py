#!/usr/bin/env python3
"""Headless QEMU/KVM lab. Host package installation is deliberately absent."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import gzip
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import subprocess
import sys
import time
import uuid
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
INSTALLER = REPO/'config/hypr/control_panel'
DEFAULT_STATE = Path.home()/'.local/share/hyperfusion-deb-lab'
SIGNER = '1B9A16984A4E8CB448712D2AE0B78BF4326C6F8F'
RUNNER_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def stamp():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def write_json(path, data):
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(data, indent=2)+'\n')
    temporary.replace(path)


def command(args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def fetch(url):
    if urlparse(url).scheme != 'https':
        raise ValueError('Downloads require HTTPS: '+url)
    with urlopen(Request(url, headers={'User-Agent': 'HyperFusion-Compatibility-Lab/1.0'}), timeout=90) as response:
        if urlparse(response.url).scheme != 'https':
            raise ValueError('Download redirected outside HTTPS')
        return response.read()


def download(url, target, expected=None):
    if urlparse(url).scheme != 'https':
        raise ValueError('Downloads require HTTPS')
    temporary = target.with_suffix(target.suffix+'.part')
    command(['curl', '--fail', '--location', '--retry', '3', '--connect-timeout', '30',
             '--max-time', '1800', '--proto', '=https', '--proto-redir', '=https',
             '--silent', '--show-error', '--output', temporary, url])
    actual = digest(temporary)
    if expected and actual != expected:
        raise RuntimeError('Download checksum mismatch: '+url)
    temporary.replace(target)
    return actual


def resolve_app(app):
    if app.get('url'):
        return app['url'], None
    if app.get('github'):
        releases = json.loads(fetch('https://api.github.com/repos/'+app['github']+'/releases?per_page=30'))
        for release in releases:
            if release['draft'] or release['prerelease'] or not release['tag_name'].startswith(app.get('tag_prefix', '')):
                continue
            assets = [a for a in release['assets'] if re.fullmatch(app['asset'], a['name'])
                      and 'arm64' not in a['name'].lower() and 'aarch64' not in a['name'].lower()]
            if len(assets) == 1:
                sha = assets[0].get('digest', '') or ''
                return assets[0]['browser_download_url'], sha.removeprefix('sha256:') if sha.startswith('sha256:') else None
        raise RuntimeError('No unambiguous stable amd64 .deb in official releases')
    if app.get('apt_index'):
        rows = []
        for block in gzip.decompress(fetch(app['apt_index'])).decode().split('\n\n'):
            fields = dict(line.split(': ', 1) for line in block.splitlines() if ': ' in line and not line.startswith(' '))
            if fields.get('Package') == app['package'] and fields.get('Architecture') == 'amd64':
                rows.append(fields)
        row = max(rows, key=lambda r: tuple(map(int, re.findall(r'\d+', r['Version']))))
        if '..' in Path(row['Filename']).parts or row['Filename'].startswith('/'):
            raise RuntimeError('Unexpected repository filename')
        return urljoin(app['apt_root'], row['Filename']), row['SHA256']
    page = html.unescape(fetch(app.get('download_page', app['page'])).decode()).replace('\\/', '/')
    links = sorted(set(re.findall(app['link_pattern'], page)))
    if len(links) != 1:
        raise RuntimeError('Official page changed; expected one .deb URL, found '+str(len(links)))
    return links[0], None


class Lab:
    def __init__(self, state):
        self.state = state.expanduser().resolve()
        self.state.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.data = self.state/'data'
        storage = self.state/'storage.json'
        if storage.exists():
            info = json.loads(storage.read_text())
            if not os.path.ismount(info['mount']):
                raise RuntimeError('Lab NVMe is not mounted. See README; refusing to use the host disk instead.')
            actual = command(['findmnt', '-n', '-o', 'UUID', '--target', info['mount']], capture_output=True, text=True).stdout.strip()
            if actual != info['uuid']:
                raise RuntimeError('Wrong filesystem at lab mountpoint')
            self.data = Path(info['directory'])
        self.data.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.keys = self.state/'keys'
        self.keys.mkdir(mode=0o700, exist_ok=True)
        self.identity = self.keys/'id_ed25519'
        if not self.identity.exists():
            command(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', self.identity])
        config = self.state/'lab.json'
        if not config.exists():
            write_json(config, {'uuid': str(uuid.uuid4()), 'purpose': 'disposable-deb-tests'})
        self.config = json.loads(config.read_text())
        runtime = self.state/'runtime.json'
        self.runtime = json.loads(runtime.read_text()) if runtime.exists() else {}
        self.current = None

    @contextmanager
    def lock(self):
        with (self.state/'lab.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield

    def image(self):
        record = self.state/'image.json'
        if not record.exists():
            cache = self.state/'downloads'; cache.mkdir(exist_ok=True)
            base = 'https://geo.mirror.pkgbuild.com/images/latest/'
            names = sorted(set(re.findall(r'Arch-Linux-x86_64-cloudimg-\d{8}\.\d+\.qcow2', fetch(base).decode())))
            name = names[-1]
            expected = fetch(base+name+'.SHA256').decode().split()[0]
            image = cache/name
            download(base+name, image, expected)
            signature = cache/(name+'.sig'); signature.write_bytes(fetch(base+name+'.sig'))
            readme = fetch('https://raw.githubusercontent.com/archlinux/arch-boxes/master/README.md').decode()
            key = re.search(r'-----BEGIN PGP PUBLIC KEY BLOCK-----.*?-----END PGP PUBLIC KEY BLOCK-----', readme, re.S).group()
            keyfile = cache/'arch-boxes.asc'; keyfile.write_text(key+'\n')
            keyring = self.state/'image-keyring'; keyring.mkdir(mode=0o700, exist_ok=True)
            command(['gpg', '--homedir', keyring, '--batch', '--import', keyfile], capture_output=True)
            result = command(['gpg', '--homedir', keyring, '--batch', '--status-fd', '1', '--verify', signature, image], capture_output=True, text=True)
            if SIGNER not in result.stdout:
                raise RuntimeError('Unexpected Arch image signer')
            write_json(record, {'url': base+name, 'path': str(image), 'sha256': expected, 'signer_primary_fingerprint': SIGNER})
        image = json.loads(record.read_text())
        if digest(Path(image['path'])) != image['sha256'] or image['signer_primary_fingerprint'] != SIGNER:
            raise RuntimeError('Base image integrity record does not match')
        return Path(image['path'])

    def seed(self):
        directory = self.state/'seed'; directory.mkdir(exist_ok=True)
        public = self.identity.with_suffix('.pub').read_text().strip()
        data = {'hostname': 'fusion-deb-lab', 'manage_etc_hosts': True, 'disable_root': True,
                'ssh_pwauth': False, 'users': [{'name': 'tester', 'shell': '/bin/bash', 'lock_passwd': True,
                'sudo': ['ALL=(ALL) NOPASSWD:ALL'], 'ssh_authorized_keys': [public]}],
                'write_files': [{'path': '/etc/hyperfusion-deb-lab.json', 'permissions': '0444',
                                 'content': json.dumps(self.config)}]}
        (directory/'user-data').write_text('#cloud-config\n'+json.dumps(data, indent=2)+'\n')
        (directory/'meta-data').write_text('instance-id: fusion-deb-lab-'+self.config['uuid']+'\n')
        iso = self.state/'seed.iso'
        command(['xorriso', '-as', 'mkisofs', '-quiet', '-output', iso, '-volid', 'CIDATA',
                 '-joliet', '-rock', directory/'user-data', directory/'meta-data'], capture_output=True)
        return iso

    def ssh_args(self):
        vm = self.current
        return ['-i', str(self.identity), '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes',
                '-o', 'ForwardAgent=no', '-o', 'StrictHostKeyChecking=accept-new',
                '-o', 'UserKnownHostsFile='+str(vm/'known_hosts'), '-o', 'ConnectTimeout=3',
                '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=4']

    def ssh(self, args, **kwargs):
        return command(['ssh', *self.ssh_args(), '-p', str(self.port), 'tester@127.0.0.1', shlex.join(list(map(str, args)))], **kwargs)

    def copy(self, sources, destination):
        command(['scp', '-q', *self.ssh_args(), '-P', str(self.port), *sources,
                 'tester@127.0.0.1:'+destination])

    def collect(self, destination):
        command(['scp', '-q', '-r', *self.ssh_args(), '-P', str(self.port),
                 'tester@127.0.0.1:/home/tester/results/.', destination])

    def boot(self, disk, directory, seed=None):
        if self.current is not None:
            raise RuntimeError('A lab guest is already running')
        if not disk.is_file() or disk.suffix != '.qcow2' or not disk.resolve().is_relative_to(self.data.resolve()):
            raise RuntimeError('Lab guests accept only regular qcow2 files inside lab storage')
        directory.mkdir(parents=True, exist_ok=True)
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0)); self.port = s.getsockname()[1]
        self.current = directory
        # No block-device passthrough, host directory shares, USB, clipboard or agent forwarding.
        args = [self.runtime.get('qemu', 'qemu-system-x86_64'), '-name', 'hyperfusion-deb-lab', '-machine', 'q35,accel=kvm',
                '-L', self.runtime.get('firmware_directory', '/usr/share/qemu'),
                '-cpu', self.runtime.get('cpu', 'host'), '-smp', '4', '-m', '4096', '-uuid', self.config['uuid'],
                '-drive', 'file='+str(disk)+',if=virtio,format=qcow2,discard=unmap',
                '-netdev', 'user,id=net,ipv6=off,hostfwd=tcp:127.0.0.1:'+str(self.port)+'-:22',
                '-device', 'virtio-net-pci,netdev=net', '-display', 'none', '-vga', 'std',
                '-serial', 'file:'+str(directory/'serial.log'), '-monitor', 'none',
                '-qmp', 'unix:'+str(directory/'qmp.sock')+',server=on,wait=off',
                '-pidfile', str(directory/'qemu.pid'), '-daemonize']
        if seed:
            args += ['-drive', 'file='+str(seed)+',media=cdrom,readonly=on']
        if self.runtime.get('firmware_code'):
            variables = directory/'OVMF_VARS.fd'
            shutil.copyfile(self.runtime['firmware_vars'], variables)
            args += ['-drive', 'if=pflash,format=raw,readonly=on,file='+self.runtime['firmware_code'],
                     '-drive', 'if=pflash,format=raw,file='+str(variables)]
        write_json(directory/'vm.json', {'port': self.port, 'disk': str(disk), 'command': args})
        command(['nice', '-n', '10', *args])
        for _ in range(90):
            serial = directory/'serial.log'
            if serial.exists() and 'Kernel panic - not syncing' in serial.read_text(errors='replace'):
                raise RuntimeError('Guest kernel panic; inspect '+str(serial))
            result = subprocess.run(['ssh', *self.ssh_args(), '-p', str(self.port), 'tester@127.0.0.1', 'true'], capture_output=True)
            if result.returncode == 0:
                return
            time.sleep(2)
        raise RuntimeError('Guest SSH did not become ready; inspect '+str(directory/'serial.log'))

    def stop(self, graceful=False):
        if self.current is None:
            return
        directory = self.current
        error = None
        try:
            if graceful:
                try:
                    self.ssh(['sudo', 'systemctl', 'poweroff'], capture_output=True)
                    for _ in range(60):
                        if not (directory/'qemu.pid').exists():
                            return
                        time.sleep(0.5)
                    error = RuntimeError('Guest did not shut down cleanly; base not promoted')
                except subprocess.SubprocessError as caught:
                    error = caught
                # Stop only this lab guest even when clean shutdown failed.
                # Propagate the error so an unclean image is never promoted.
            if (directory/'qmp.sock').exists():
                with socket.socket(socket.AF_UNIX) as s:
                    s.settimeout(5)
                    try:
                        s.connect(str(directory/'qmp.sock'))
                    except (FileNotFoundError, ConnectionRefusedError):
                        if error:
                            raise error
                        return
                    stream = s.makefile('rwb', buffering=0); stream.readline()
                    stream.write(b'{"execute":"qmp_capabilities"}\n'); stream.readline()
                    stream.write(b'{"execute":"quit"}\n')
                    try: stream.readline()
                    except OSError: pass
            if error:
                raise error
        finally:
            self.current = None

    def send_code(self, source=INSTALLER, guest_script=HERE/'guest.py'):
        self.ssh(['mkdir', '-p', '/home/tester/installer', '/home/tester/input', '/home/tester/results'])
        self.copy([str(source/name) for name in ('deb_install.py','deb_dependencies.py','deb_recipes.py')], '/home/tester/installer/')
        self.copy([str(guest_script)], '/home/tester/guest.py')

    def initialize(self, args):
        base = self.data/'base.qcow2'
        if base.exists():
            raise RuntimeError('Base already exists. Use a different --state to build a new baseline.')
        image = self.image()
        work = self.data/('initialize-'+stamp()); work.mkdir()
        disk = work/'disk.qcow2'
        command(['qemu-img', 'create', '-q', '-f', 'qcow2', '-F', 'qcow2', '-b', image, disk, '64G'])
        try:
            self.boot(disk, self.state/'boot-init', self.seed())
            self.ssh(['cloud-init', 'status', '--wait'], capture_output=True)
            self.send_code()
            self.copy([str(args.debtap_package.resolve())], '/home/tester/input/debtap.pkg.tar.zst')
            if args.cache:
                cache = work/'debtap-cache.tar'
                command(['tar', '-cf', cache, '-C', args.cache.resolve().parent, 'debtap'])
                self.copy([str(cache)], '/home/tester/input/debtap-cache.tar')
            self.copy([str(HERE/'guest_setup.sh')], '/home/tester/')
            with (work/'setup.log').open('w') as log:
                self.ssh(['sudo', 'bash', '/home/tester/guest_setup.sh'], stdout=log, stderr=subprocess.STDOUT, timeout=3600)
            self.ssh(['test', '-f', '/etc/hyperfusion-deb-lab-ready'])
            self.ssh(['sudo', 'rm', '-f', '/home/tester/input/debtap-cache.tar'])
            self.stop(graceful=True)
            # Flatten once: app overlays never depend on the raw physical disk or the download cache.
            command(['qemu-img', 'convert', '-p', '-O', 'qcow2', disk, base])
            base.chmod(0o444)
            write_json(self.data/'base.json', {'created': stamp(), 'image': json.loads((self.state/'image.json').read_text()),
                       'debtap_package_sha256': digest(args.debtap_package), 'lab': self.config,
                       'scope': 'Arch Linux, real debtap caches, Xvfb/Openbox X11 launch testing'})
            print('Base ready:', base, flush=True)
        finally:
            self.stop()

    def run_app(self, app, local=None):
        if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,60}', app['id']):
            raise ValueError('Invalid app id')
        base = self.data/'base.qcow2'
        if not base.is_file() or not (self.data/'base.json').is_file():
            raise RuntimeError('Run init first')
        run = self.data/'runs'/(stamp()+'-'+app['id']); run.mkdir(parents=True)
        record = {'app': app['id'], 'name': app['name'], 'tested_at': datetime.now(timezone.utc).isoformat(),
                  'scope': 'Automated install and GUI smoke test in disposable Arch/Xvfb VM', 'status': 'infrastructure-failed'}
        snapshot = run/'installer'; snapshot.mkdir()
        for name in ('deb_install.py', 'deb_dependencies.py', 'deb_recipes.py'):
            shutil.copyfile(INSTALLER/name, snapshot/name)
        shutil.copyfile(HERE/'guest.py', run/'guest.py')
        started = time.monotonic()
        record['runtime'] = self.runtime
        record['harness_sha256'] = {'lab.py': RUNNER_SHA256, 'guest.py': digest(run/'guest.py')}
        record['installer_sha256'] = {name: digest(snapshot/name) for name in
                                      ('deb_install.py', 'deb_dependencies.py', 'deb_recipes.py')}
        record['baseline'] = json.loads((self.data/'base.json').read_text())
        try:
            if local:
                package = local.resolve(); url = None
                sha = digest(package)
            else:
                url, expected = resolve_app(app)
                package = run/'source.deb'
                print(app['id']+': downloading '+url, flush=True)
                sha = download(url, package, expected)
            with package.open('rb') as source:
                if source.read(8) != b'!<arch>\n':
                    raise RuntimeError('Downloaded file is not a Debian ar archive')
            record.update(source_url=url, source_sha256=sha)
            write_json(run/'app.json', dict(app, source_sha256=sha, lab_uuid=self.config['uuid']))
            disk = run/'disk.qcow2'
            command(['qemu-img', 'create', '-q', '-f', 'qcow2', '-F', 'qcow2', '-b', base, disk])
            # Short socket path, regardless of report/storage path length.
            vm = self.state/'boot-test'
            if vm.exists():
                pidfile = vm/'qemu.pid'
                if pidfile.exists() and Path('/proc/'+pidfile.read_text().strip()).exists():
                    raise RuntimeError('Previous lab guest is still running; refusing to replace its control files')
                shutil.copytree(vm, run/'previous-boot', ignore=shutil.ignore_patterns('*.sock'))
                shutil.rmtree(vm)
            self.boot(disk, vm)
            self.send_code(snapshot, run/'guest.py')
            self.copy([str(package)], '/home/tester/input/source.deb')
            self.copy([str(run/'app.json')], '/home/tester/input/app.json')
            print(app['id']+': installing and launching in guest', flush=True)
            with (run/'runner.log').open('w') as log:
                try:
                    self.ssh(['python', '/home/tester/guest.py'], stdout=log, stderr=subprocess.STDOUT, timeout=2400)
                except subprocess.CalledProcessError:
                    pass  # Guest results carry install/launch failure details.
                except subprocess.TimeoutExpired:
                    # Preserve partial logs before the disposable guest is stopped.
                    self.collect(run)
                    raise
            self.collect(run)
            result = json.loads((run/'result.json').read_text())
            record.update(result)
        except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
            record['error'] = str(error)
        finally:
            self.stop()
            if (self.state/'boot-test').exists() and (run/'disk.qcow2').exists():
                shutil.copytree(self.state/'boot-test', run/'boot', ignore=shutil.ignore_patterns('*.sock'), dirs_exist_ok=True)
            record['duration_seconds'] = round(time.monotonic()-started, 1)
            write_json(run/'result.json', record)
            print(app['id']+': '+record['status']+' — '+str(run), flush=True)
        return record

    def report(self):
        rows = []
        for path in sorted((self.data/'runs').glob('*/result.json')):
            data = json.loads(path.read_text()); data['report'] = str(path.parent); rows.append(data)
        write_json(self.data/'results.json', rows)
        latest = {row['app']: row for row in rows}
        lines = ['# HyperFusion .deb lab results', '', 'Latest result for each app. All runs remain in [results.json](results.json).', '', 'Automated installation and X11 GUI smoke checks. These do not certify app features, login, audio/video, GPU acceleration, or Hyprland/Wayland behavior.', '', '| App | Version | Result | Report |', '| --- | --- | --- | --- |']
        for row in latest.values():
            lines.append('| '+row['name']+' | '+row.get('deb_version', '—')+' | '+row['status']+' | [logs]('+row['report']+') |')
        (self.data/'RESULTS.md').write_text('\n'.join(lines)+'\n')
        print(self.data/'RESULTS.md')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, default=DEFAULT_STATE)
    sub = parser.add_subparsers(dest='action', required=True)
    init = sub.add_parser('init'); init.add_argument('--debtap-package', required=True, type=Path)
    init.add_argument('--cache', type=Path, help='Existing real /var/cache/debtap directory to seed; never a test fixture.')
    run = sub.add_parser('run'); run.add_argument('apps', nargs='*'); run.add_argument('--all', action='store_true')
    file = sub.add_parser('run-file'); file.add_argument('deb', type=Path); file.add_argument('--id', required=True)
    file.add_argument('--command', nargs='+', required=True)
    sub.add_parser('report')
    args = parser.parse_args(argv)
    if os.geteuid() == 0:
        parser.error('Run as your normal user. No host root or package installation is needed.')
    lab = Lab(args.state)
    failed = False
    with lab.lock():
        if args.action == 'init': lab.initialize(args)
        elif args.action == 'run-file':
            failed = lab.run_app({'id': args.id, 'name': args.id, 'launch': args.command}, args.deb)['status'] != 'gui-smoke-passed'
        elif args.action == 'run':
            apps = json.loads((HERE/'apps.json').read_text())['apps']
            known = {app['id'] for app in apps}
            if set(args.apps)-known: parser.error('Unknown apps: '+', '.join(sorted(set(args.apps)-known)))
            if not args.all and not args.apps: parser.error('Select app ids or --all')
            for app in apps:
                if args.all or app['id'] in args.apps:
                    result = lab.run_app(app)
                    failed |= result['status'] != 'gui-smoke-passed'
                    lab.report()
        lab.report()
    return 1 if failed else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
