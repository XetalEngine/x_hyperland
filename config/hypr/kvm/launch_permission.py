"""Desktop side of opt-in permission for an approved Virtual GPU setup.

No passwords, Echo tokens or executable commands are saved in the permission.
The root broker accepts a fixed action and a matching configuration identity.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

import portable

_active = None


def helper(uid=None):
    return Path('/usr/local/libexec') / ('hyperfusion-kvm-' + str(os.getuid() if uid is None else uid))


def source_files():
    root = portable.ROOT
    return sorted(p for p in root.rglob('*') if p.is_file()
                  and '__pycache__' not in p.parts and '.git' not in p.parts
                  and p.suffix in ('.py', '.sh', '.json', '.pem')
                  and not p.name.startswith('test_') and 'tests' not in p.parts)


def specification(cfg):
    import editions
    import virtual_gpu
    plan = virtual_gpu.prepare(cfg, workdir='/run/hyperfusion-approved-guest', token='approved')
    if plan['options']['keep_pci'] or plan['options']['keep_usb']:
        raise ValueError('Remembered access is available for Virtual GPU without physical PCI or USB passthrough.')
    if cfg.profile != 'windows':
        raise ValueError('This permission currently supports Windows Virtual GPU setups. Other launch modes use normal authentication.')
    if plan.get('huge') and any(item.get('qom-type') == 'memory-backend-memfd' for item in plan['config'].get('objects', [])):
        raise ValueError('Use ordinary RAM or file-backed hugepages to remember Virtual GPU launch access.')
    if shutil.which('bwrap') is None:
        raise ValueError('Install bubblewrap to use remembered VM launch access.')
    components = {}
    for name in ('qemu', 'tpm', 'kvm-amd', 'ovmf', 'baseline'):
        path = portable.component_path(name)
        if path.is_dir():
            manifest = path / '.component.json'
            components[name] = dict(path=str(path.resolve()),
                manifest=hashlib.sha256(manifest.read_bytes()).hexdigest() if manifest.is_file() else '')
    if 'qemu' not in components:
        raise ValueError('Install the managed QEMU component before remembering launch access.')
    if Path(plan['argv'][0]).resolve() != (portable.component_path('qemu')/'bin/qemu-system-x86_64').resolve():
        raise ValueError('Select the managed QEMU build to remember launch access.')
    tools=cfg.data.get('tools',{})
    if tools.get('kvm_build_enabled') and Path(tools.get('kvm_build','')).resolve() != portable.ROOT/'module-tool.sh':
        raise ValueError('Custom module scripts require ordinary administrator authentication. Select the published module to remember access.')
    from launch_sandbox import file_paths
    from launch_policy import device_identity
    plan['approved_disks'] = [device_identity(path) for path in sorted(file_paths(plan['argv'])) if Path(path).is_block_device()]
    code = hashlib.sha256()
    for path in source_files():
        code.update(str(path.relative_to(portable.ROOT)).encode() + b'\0' + path.read_bytes())
    value = dict(version=1, config=cfg.data, plan=plan, components=components,
                 source=str(portable.ROOT), data=str(portable.data_root()),
                 edition=editions.selected(), kernel=platform.release(), code=code.hexdigest())
    value['fingerprint'] = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
    return value


def call(action, fingerprint='', *, token='', timeout=60):
    if not helper().is_file():
        raise RuntimeError('Remembered VM launch access is not installed.')
    request = dict(action=action, fingerprint=fingerprint)
    if token:
        request['token'] = token
    reply = subprocess.run(['sudo', '-n', str(helper())], input=json.dumps(request),
                           capture_output=True, text=True, timeout=timeout)
    if reply.returncode:
        raise RuntimeError(reply.stderr.strip() or 'The VM launch permission is unavailable.')
    return json.loads(reply.stdout)


def forget():
    global _active
    result = call('forget')
    _active = None
    return result


def authorize(cfg, parent, token=''):
    """Return True for an approved setup, False to keep normal authentication."""
    global _active
    import launch_wait
    from uiutil import sudo_command
    _active = None
    try:
        spec = launch_wait.run(lambda: specification(cfg), parent)
    except ValueError:
        raise
    try:
        result = launch_wait.run(lambda: call('status'), parent)
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        result = {}
    if result.get('fingerprint') != spec['fingerprint']:
        # Authenticate the actual installation command. A cached sudo timestamp
        # is not treated as a persistent permission, and no password is retained.
        with tempfile.TemporaryDirectory(prefix='hyperfusion-launch-approval-') as temporary:
            request = Path(temporary)/'request.json'
            request.write_text(json.dumps(spec)); request.chmod(0o600)
            command, environment, available = sudo_command(
                ['/usr/bin/python3', '-I', str(portable.ROOT/'launch_policy.py'), '--install', str(request)],
                'Approve this Hyper Fusion VM setup')
            if not available:
                raise RuntimeError('The desktop password prompt is unavailable.')
            parent.status.setText('Approving this VM setup…')
            reply = launch_wait.run(lambda: subprocess.run(command, env=environment,
                capture_output=True, text=True, timeout=300), parent)
            if reply.returncode:
                raise RuntimeError(reply.stderr.strip() or 'VM launch approval was cancelled.')
    if token:
        launch_wait.run(lambda: call('arm', spec['fingerprint'], token=token), parent)
    _active = spec['fingerprint']
    return True


def preferred():
    try:
        return json.loads((portable.data_root()/'launch-permission.json').read_text()).get('remember') is True
    except (OSError, ValueError, AttributeError):
        return False


def preference(enabled):
    from packages import atomic_json
    atomic_json(portable.data_root()/'launch-permission.json', {'remember':bool(enabled)})


def inspection():
    if _active is None:
        return None
    return call('probe', _active, timeout=90)


def launch(cfg):
    if _active is None:
        return None
    # Catch an edit or component operation between authorization and submission.
    if specification(cfg)['fingerprint'] != _active:
        raise RuntimeError('The VM setup changed. Choose Launch VM again to approve it.')
    return call('launch', _active)


def reset():
    global _active
    _active = None
