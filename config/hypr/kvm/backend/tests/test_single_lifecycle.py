"""Execute generated launch control flow with inert hooks and a fake guest."""
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import launcher
import mac_memory
import profiles
from model import VMConfig


@pytest.mark.parametrize('ending', ['normal', 'start-failure', 'guest-failure', 'terminated'])
def test_single_launch_reverts_once_and_stops_its_guest(tmp_path, monkeypatch, ending):
    for name, filename in profiles.RUNTIME_FILES.items():
        monkeypatch.setattr(launcher, name, str(tmp_path / filename))
    monkeypatch.setattr(launcher, 'RUN_DIR', str(tmp_path))
    events = tmp_path / 'events'
    guest = tmp_path / 'guest'
    pidfile = tmp_path / 'guest.pid'
    guest.write_text('#!' + sys.executable + '\nfrom pathlib import Path\nimport os,time\n'
                     + f'Path({str(pidfile)!r}).write_text(str(os.getpid()))\n'
                     + ('time.sleep(60)\n' if ending == 'terminated' else '')
                     + ('raise SystemExit(3)\n' if ending == 'guest-failure' else ''))
    guest.chmod(0o700)
    Path(launcher.START).write_text('#!/bin/bash\nexit ' + ('1' if ending == 'start-failure' else '0') + '\n')
    Path(launcher.START).chmod(0o700)
    Path(launcher.REVERT).write_text('#!/bin/bash\nprintf "%s\\n" "$1" >> ' + shlex.quote(str(events)) + '\n')
    Path(launcher.REVERT).chmod(0o700)
    cfg = VMConfig({'_meta': {'binary': str(guest)}, 'simple': {}, 'machine': {'type': 'q35', 'opts': {}},
                    'cpu': {'model': 'host', 'features': {}}, 'smp': {'vcpus': '1', 'topology': {}}})
    script = tmp_path / 'launch.sh'
    script.write_text(launcher.build_script(cfg, {}, reboot_after=False))
    subprocess.run(['bash', '-n', str(script)], check=True)
    with (tmp_path / 'supervisor.log').open('w') as log:
        child = subprocess.Popen(['bash', str(script)], stdout=log, stderr=log, start_new_session=True)
        try:
            if ending == 'terminated':
                deadline = time.monotonic() + 5
                while not pidfile.exists() and child.poll() is None and time.monotonic() < deadline:
                    time.sleep(.02)
                assert pidfile.exists(), (tmp_path / 'supervisor.log').read_text()
                child.terminate()
            child.wait(timeout=15)
            assert child.returncode == {'normal': 0, 'start-failure': 1, 'guest-failure': 3, 'terminated': 143}[ending]
            assert events.read_text().splitlines() == ['ok' if ending == 'normal' else 'failed']
            if pidfile.exists():
                with pytest.raises(ProcessLookupError): os.kill(int(pidfile.read_text()), 0)
        finally:
            if child.poll() is None: os.killpg(child.pid, signal.SIGKILL);child.wait(timeout=5)


@pytest.mark.parametrize('script', ['mac_memory.py', 'mac_hugepages.py'])
def test_mac_helpers_are_runnable_from_the_installed_source_without_pythonpath(tmp_path, script):
    helper = launcher.SOURCE_DIR / 'lib' / script
    result = subprocess.run([sys.executable, '-E', '-s', str(helper), '--help'], cwd=tmp_path,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


def test_mac_helpers_keep_recipient_workspace_under_elevation(tmp_path):
    code = ('import sys;sys.path.insert(0,' + repr(str(launcher.SOURCE_DIR / 'lib')) + ');'
            'import mac_memory;print(mac_memory.TEMP_ROOT)')
    result = subprocess.run([sys.executable, '-E', '-s', '-c', code], cwd=tmp_path,
                            env={**os.environ, 'XETAL_KVM_DATA': str(tmp_path / 'recipient')},
                            capture_output=True, text=True, timeout=10, check=True)
    assert result.stdout.strip() == str(tmp_path / 'recipient/macos/run')


def test_failed_single_handoff_clears_override_and_restores_original_amd_driver(tmp_path, monkeypatch):
    for name, filename in profiles.RUNTIME_FILES.items():
        monkeypatch.setattr(launcher, name, str(tmp_path / filename))
    monkeypatch.setattr(launcher, 'RUN_DIR', str(tmp_path))
    slot='0000:03:00.0';sysfs=tmp_path/'sys'
    device=sysfs/'bus/pci/devices'/slot;device.mkdir(parents=True)
    (device/'driver_override').write_text('vfio-pci')
    # Binding failed: no driver symlink. The failed override must still clear.
    (sysfs/'bus/pci/drivers_probe').touch();(sysfs/'bus/pci/rescan').touch()
    for index in range(2):
        console=sysfs/f'class/vtconsole/vtcon{index}';console.mkdir(parents=True)
        (console/'bind').write_text('0')
    (tmp_path/'.handover').touch();state=tmp_path/'host-handoff';state.mkdir()
    (state/slot).write_text('amdgpu')
    commands=tmp_path/'commands';commands.mkdir();events=tmp_path/'commands.log'
    for command in ('systemctl','modprobe','sleep'):
        stub=commands/command
        stub.write_text('#!/bin/bash\nprintf "%s\\n" '+shlex.quote(command)+' "$@" >> '+shlex.quote(str(events))+'\n')
        stub.chmod(0o700)
    cfg=VMConfig({'_meta':{'binary':'true'},'simple':{},'network':{'mode':'user'},
                  'machine':{'type':'q35','opts':{}},'devices':[{'driver':'vfio-pci','host':slot}]})
    script=tmp_path/'restore.sh'
    script.write_text(launcher.build_revert(cfg,reboot_after=False).replace('/sys/',str(sysfs)+'/'))
    result=subprocess.run(['bash',str(script),'failed'],env={**os.environ,'PATH':str(commands)+':'+os.environ['PATH']},
                          capture_output=True,text=True,timeout=5)
    assert result.returncode==0,result.stderr
    assert not (device/'driver_override').read_text().strip()
    assert (sysfs/'bus/pci/drivers_probe').read_text().strip()==slot
    assert 'amdgpu' in events.read_text()
    assert 'nvidia' not in events.read_text()
    assert not (tmp_path/'.handover').exists()
