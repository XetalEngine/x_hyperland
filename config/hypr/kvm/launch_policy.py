#!/usr/bin/env python3
"""Root-owned, no-argument broker for one explicitly approved VM setup.

Installation always uses ordinary sudo authentication. The resulting sudoers
entry names only the protected broker, with no command-line arguments allowed.
Runtime requests cannot supply a script, executable, configuration or path.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import stat
import subprocess
import sys
import tempfile

BASE = Path('/var/lib/hyperfusion-kvm-launch')
LIBEXEC = Path('/usr/local/libexec')
SUDOERS = Path('/etc/sudoers.d')
MAIN_SUDOERS = Path('/etc/sudoers')
MAX_REQUEST = 4 * 1024 * 1024
SECURE_PATH = '/usr/sbin:/usr/bin:/sbin:/bin'


def device_identity(path):
    """Identify an explicitly selected disk, including its hardware identity."""
    canonical = Path(path).resolve(strict=True)
    info = canonical.stat()
    if not stat.S_ISBLK(info.st_mode) or not canonical.is_relative_to('/dev'):
        raise ValueError('The approved VM disk is not a block device: '+str(path))
    sysfs = (Path('/sys/dev/block')/f'{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}').resolve(strict=True)
    identity = {}
    # Partitions inherit the parent drive's identity. Major/minor alone can be
    # reused after hotplug, so retain sysfs location and any available WWID.
    for base in (sysfs, sysfs.parent):
        for name in ('wwid', 'device/wwid', 'device/serial', 'uuid', 'diskseq'):
            file = base/name
            if file.is_file(): identity[str(file)] = file.read_text().strip()
    return dict(path=str(path), canonical=str(canonical), rdev=info.st_rdev,
                sysfs=str(sysfs), identity=identity)


def device_file(record, *, writable=True, direct=False):
    if device_identity(record['path']) != record:
        raise RuntimeError('An approved VM disk changed. Approve this setup again.')
    flags = (os.O_RDWR if writable else os.O_RDONLY) | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    if direct: flags |= os.O_DIRECT
    fd = os.open(record['canonical'], flags)
    if os.fstat(fd).st_rdev != record['rdev'] or not stat.S_ISBLK(os.fstat(fd).st_mode):
        os.close(fd); raise RuntimeError('The VM disk changed while opening it.')
    return fd


def protected_directory(path):
    path = Path(path)
    if not path.exists():
        protected_directory(path.parent)
        path.mkdir(mode=0o755)
        path.chmod(0o755)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise RuntimeError('Unsafe administrator-owned directory: ' + str(path))
    return path


@contextmanager
def desktop_user(uid):
    """Open user inputs with that account's access, even during sudo setup."""
    if os.geteuid() == uid:
        yield
        return
    account = pwd.getpwuid(uid)
    previous = os.geteuid(), os.getegid(), os.getgroups()
    try:
        os.setgroups(os.getgrouplist(account.pw_name, account.pw_gid))
        os.setegid(account.pw_gid); os.seteuid(uid)
        yield
    finally:
        os.seteuid(previous[0]); os.setegid(previous[1]); os.setgroups(previous[2])


def user_file(path, uid, *, writable=False, directory=False, direct=False):
    flags = (os.O_RDWR if writable else os.O_RDONLY) | os.O_CLOEXEC | os.O_NONBLOCK
    if directory:
        flags |= os.O_DIRECTORY
    if direct:
        flags |= os.O_DIRECT
    with desktop_user(uid):
        fd = os.open(path, flags)
    info = os.fstat(fd)
    if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
        os.close(fd)
        raise ValueError('VM inputs must be ordinary files: ' + str(path))
    return fd


def copy_file(source, destination, uid):
    with os.fdopen(user_file(source, uid), 'rb') as stream:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('xb') as target:
            shutil.copyfileobj(stream, target, length=1024*1024)
        destination.chmod(0o755 if os.fstat(stream.fileno()).st_mode & 0o111 else 0o644)


def copy_tree(source, destination, uid):
    source = Path(source)
    with desktop_user(uid):
        files = list(source.rglob('*'))
    for path in files:
        if path.is_dir():
            continue
        copy_file(path, destination/path.relative_to(source), uid)


def atomic(path, content, mode=0o644):
    fd, temporary = tempfile.mkstemp(prefix='.'+path.name+'-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(content); stream.flush(); os.fsync(stream.fileno()); os.fchmod(stream.fileno(), mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def rule(uid):
    # sudoers' empty argument string means no arguments, not arbitrary ones.
    return (f'# Hyper Fusion: approved Virtual GPU setup for UID {uid}.\n'
            f'#{uid} ALL=(root) NOPASSWD: NOSETENV: {LIBEXEC}/hyperfusion-kvm-{uid} ""\n')


def check_sudoers(path=None):
    binary = shutil.which('visudo', path=SECURE_PATH)
    if not binary: raise RuntimeError('Install sudo and visudo before approving launch access.')
    command = [binary, '-c']
    if path is not None: command += ['-f', str(path)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise RuntimeError('sudoers validation failed: ' + (result.stdout + result.stderr).strip())


def include_line(uid):
    return '@include '+str(SUDOERS/f'hyperfusion-kvm-{uid}')


def policy_include(uid, enabled):
    """Keep this exact exception after distro/account PASSWD: ALL rules."""
    info = MAIN_SUDOERS.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022 or info.st_nlink != 1:
        raise RuntimeError('sudoers needs a regular administrator-owned policy file.')
    before = MAIN_SUDOERS.read_text()
    line = include_line(uid)
    after = ''.join(item for item in before.splitlines(keepends=True) if item.strip() != line)
    if enabled: after = after.rstrip('\n')+'\n'+line+'\n'
    if after == before: return before, after
    fd, name = tempfile.mkstemp(prefix='.hyperfusion-sudoers-', dir=MAIN_SUDOERS.parent)
    candidate = Path(name)
    try:
        with os.fdopen(fd,'w') as stream: stream.write(after); os.fchmod(stream.fileno(), 0o440)
        check_sudoers(candidate)
        if MAIN_SUDOERS.read_text() != before:
            raise RuntimeError('sudoers changed during VM approval. Try again.')
        atomic(MAIN_SUDOERS, after, stat.S_IMODE(info.st_mode))
    finally: candidate.unlink(missing_ok=True)
    return before, after


def install(request, uid):
    if os.geteuid() != 0 or uid <= 0:
        raise RuntimeError('Approve launch access using sudo from your desktop account.')
    if not shutil.which('bwrap'):
        raise RuntimeError('Install bubblewrap before enabling remembered VM launch access.')
    with os.fdopen(user_file(request, uid)) as stream:
        spec = json.loads(stream.read(MAX_REQUEST + 1))
    fingerprint = spec.get('fingerprint', '')
    if not re.fullmatch('[a-f0-9]{64}', fingerprint):
        raise ValueError('Invalid VM configuration identity.')
    if spec.get('version') != 1 or spec.get('edition') not in ('stock', 'xetallic'):
        raise ValueError('Unsupported VM approval.')
    account = pwd.getpwuid(uid)
    check_sudoers()
    protected_directory(SUDOERS); protected_directory(LIBEXEC)
    owner = protected_directory(protected_directory(BASE)/str(uid))
    with (owner/'approval.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        destination = owner/fingerprint
        if destination.exists():
            # Never reuse a potentially interrupted snapshot or replace code
            # underneath a running service.
            destination = owner/(fingerprint+'-'+os.urandom(6).hex())
        destination.mkdir(mode=0o755); destination.chmod(0o755)
        try:
            source = Path(spec['source'])
            with desktop_user(uid):
                files = sorted(p for p in source.rglob('*') if p.is_file()
                    and '__pycache__' not in p.parts and '.git' not in p.parts
                    and p.suffix in ('.py', '.sh', '.json', '.pem')
                    and not p.name.startswith('test_') and 'tests' not in p.parts)
            for path in files:
                copy_file(path, destination/'app'/path.relative_to(source), uid)
            code = hashlib.sha256()
            for path in files:
                relative = path.relative_to(source)
                code.update(str(relative).encode()+b'\0'+(destination/'app'/relative).read_bytes())
            if code.hexdigest() != spec['code']:
                raise RuntimeError('Launch code changed during approval. Try again.')
            mappings = {str(source): str(destination/'app')}
            for name, component in spec['components'].items():
                if name not in ('qemu', 'tpm', 'kvm-amd', 'ovmf', 'baseline'):
                    raise ValueError('Unsupported VM component.')
                target = destination/'data/editions'/spec['edition']/'components'/name/'current'
                copy_tree(component['path'], target, uid)
                manifest = target/'.component.json'
                if component['manifest'] and hashlib.sha256(manifest.read_bytes()).hexdigest() != component['manifest']:
                    raise RuntimeError('A VM component changed during approval. Try again.')
                mappings[component['path']] = str(target)
                mappings[str(Path(spec['data'])/'editions'/spec['edition']/'components'/name/'current')] = str(target)
                mappings[str(Path(spec['data'])/'components'/name/'current')] = str(target)
            # Runtime adapters must refer to the protected copy of Python code.
            qemu = destination/'data/editions'/spec['edition']/'components/qemu/current'
            if (qemu/'.vm-runtime.json').is_file():
                import shlex
                adapter = qemu/'bin/qemu-system-x86_64'
                adapter.write_text('#!/usr/bin/bash\nset -euo pipefail\nexec /usr/bin/python3 '+
                    shlex.quote(str(destination/'app/vm_memory.py'))+' '+shlex.quote(str(qemu))+' "$@"\n')
                adapter.chmod(0o755)
            def remap(value):
                if isinstance(value, dict): return {key:remap(item) for key,item in value.items()}
                if isinstance(value, list): return [remap(item) for item in value]
                if isinstance(value, str):
                    for old,new in sorted(mappings.items(), key=lambda pair:-len(pair[0])):
                        value = new if value == old else value.replace(old+'/', new+'/')
                return value
            plan = remap(spec['plan'])
            for record in plan.get('approved_disks', []):
                if device_identity(record['path']) != record:
                    raise RuntimeError('A selected VM disk changed during approval. Try again.')
            plan['uid'], plan['gid'] = uid, account.pw_gid
            # TPM deliberately runs as the desktop account. Its protected
            # executable/libraries need traversal even under a private umask.
            for directory in destination.rglob('*'):
                if directory.is_dir(): directory.chmod(0o755)
            approved = dict(fingerprint=fingerprint, uid=uid, gid=account.pw_gid,
                kernel=spec['kernel'], edition=spec['edition'], plan=plan,
                data=str(destination/'data'), snapshot=str(destination))
            (destination/'approved.json').write_text(json.dumps(approved))
            (destination/'approved.json').chmod(0o600)
            # All following commands load only protected copies. The broker
            # itself receives no user-controlled command-line arguments.
            boot = ('#!/usr/bin/python3 -I\nimport sys\n'
                    f'sys.path.insert(0, {str(destination/"app")!r})\n'
                    'import launch_policy\n'
                    f'launch_policy.entry({uid})\n')
            executable = LIBEXEC/f'hyperfusion-kvm-{uid}'
            policy = SUDOERS/f'hyperfusion-kvm-{uid}'
            old_executable = executable.read_bytes() if executable.exists() else None
            old_policy = policy.read_bytes() if policy.exists() else None
            changed_main = None
            try:
                atomic(executable, boot, 0o755)
                atomic(policy, rule(uid), 0o440)
                check_sudoers(policy)
                changed_main = policy_include(uid, True)
                (destination/'sudoers-before').write_text(changed_main[0]); (destination/'sudoers-before').chmod(0o600)
                check_sudoers()
                atomic(owner/'current.json', json.dumps(approved), 0o600)
            except BaseException:
                if changed_main is not None and MAIN_SUDOERS.read_text() == changed_main[1]:
                    atomic(MAIN_SUDOERS, changed_main[0], 0o440)
                for path, old, mode in ((executable, old_executable, 0o755), (policy, old_policy, 0o440)):
                    if old is None: path.unlink(missing_ok=True)
                    else: atomic(path, old.decode(), mode)
                raise
        except BaseException:
            shutil.rmtree(destination)
            raise


def environment(approved):
    return dict(PATH=SECURE_PATH, HOME='/root', LANG='C.UTF-8',
                XETAL_KVM_DATA=approved['data'], XETAL_KVM_EDITION=approved['edition'])


def dispatch(approved, request):
    uid = approved['uid']
    action = request.get('action')
    if set(request) - {'action', 'fingerprint', 'token'}:
        raise ValueError('Unexpected VM permission fields.')
    if action == 'status':
        return {'fingerprint': approved['fingerprint']}
    if action == 'forget':
        policy_include(uid, False)
        (SUDOERS/f'hyperfusion-kvm-{uid}').unlink(missing_ok=True)
        (BASE/str(uid)/'current.json').unlink(missing_ok=True)
        (LIBEXEC/f'hyperfusion-kvm-{uid}').unlink(missing_ok=True)
        # Keep the snapshot for an already running service. No command can
        # use it passwordlessly after the rule has been removed.
        return {'forgotten': True}
    if request.get('fingerprint') != approved['fingerprint']:
        raise ValueError('This VM setup needs administrator approval again.')
    if os.uname().release != approved['kernel']:
        raise ValueError('The kernel changed. Approve the VM setup again.')
    root = Path(approved['snapshot'])
    os.environ.clear(); os.environ.update(environment(approved))
    if action == 'arm':
        from runtime_access import arm
        arm(Path(approved['data']), request.get('token', ''))
        return {'ready': True}
    if action == 'probe':
        result = subprocess.run(['/usr/bin/python3', str(root/'app/runtime_probe.py')],
                                capture_output=True, text=True, timeout=90, env=environment(approved))
        if result.returncode: raise RuntimeError(result.stderr.strip() or 'QEMU check failed.')
        return json.loads(result.stdout)
    if action == 'launch':
        return submit(approved)
    raise ValueError('Unknown VM permission action.')


def submit(approved):
    root = Path(approved['snapshot'])
    runbase = protected_directory(Path('/run/hyperfusion-kvm-launch'))
    directory = Path(tempfile.mkdtemp(prefix=f'{approved["uid"]}-', dir=runbase))
    directory.chmod(0o750); os.chown(directory, 0, approved['gid'])
    log = directory/'output.log'; log.touch(mode=0o640); log.chmod(0o640); os.chown(log, 0, approved['gid'])
    plan = json.loads(json.dumps(approved['plan']).replace('/run/hyperfusion-approved-guest', str(directory)))
    if plan.get('tap'):
        name = 'hfv'+os.urandom(5).hex()
        previous = plan['tap']['name']
        plan = json.loads(json.dumps(plan).replace(previous, name))
    plan['approved_snapshot'] = approved['snapshot']
    (directory/'plan.json').write_text(json.dumps(plan)); (directory/'plan.json').chmod(0o600)
    command = ['/usr/bin/systemd-run', '--unit', 'vmstart2-vm', '--description=Hyper Fusion approved VM',
               '--property=KillMode=mixed', '--property=TimeoutStopSec=120', '--service-type=exec',
               '--property=LimitMEMLOCK=infinity',
               '--property=UMask=0077', '--property=StandardOutput=append:'+str(log),
               '--property=StandardError=append:'+str(log)]
    for key, value in environment(approved).items(): command.append('--setenv='+key+'='+value)
    command += ['/usr/bin/python3', str(root/'app/vm_session.py')]
    tools = plan['config'].get('tools', {})
    if approved['edition'] == 'xetallic' and tools.get('kvm_build_enabled'):
        command += ['--module-options', json.dumps(tools.get('kvm_env') or {})]
    command += ['--', '/usr/bin/python3', str(root/'app/launch_sandbox.py'), str(directory/'plan.json')]
    subprocess.run(['/usr/bin/systemctl', 'reset-failed', 'vmstart2-vm'], capture_output=True, timeout=10)
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    if result.returncode:
        shutil.rmtree(directory)
        raise RuntimeError((result.stdout + result.stderr).strip() or 'VM submission failed.')
    return dict(workdir=str(directory), options=plan['options'], qmp=plan['qmp'],
                agent_chardev=plan['agent_chardev'], remembered=True)


def entry(uid):
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        if len(sys.argv) != 1 or os.geteuid() != 0 or os.environ.get('SUDO_UID') != str(uid):
            raise PermissionError('Use this launcher from its approved desktop account, without arguments.')
        raw = sys.stdin.buffer.read(16385)
        if len(raw) > 16384: raise ValueError('VM request is too large.')
        request = json.loads(raw)
        if not isinstance(request, dict): raise ValueError('Invalid VM request.')
        approved = json.loads((BASE/str(uid)/'current.json').read_text())
        if approved['uid'] != uid: raise PermissionError('VM permission owner differs.')
        print(json.dumps(dispatch(approved, request)))
    except Exception as error:
        print(str(error), file=sys.stderr); raise SystemExit(1)


if __name__ == '__main__':
    try:
        if len(sys.argv) != 3 or sys.argv[1] != '--install':
            raise ValueError('Use KVM Settings to approve a VM setup.')
        install(sys.argv[2], int(os.environ.get('SUDO_UID', '-1')))
    except Exception as error:
        print(str(error), file=sys.stderr); raise SystemExit(1)
