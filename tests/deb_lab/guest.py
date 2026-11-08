#!/usr/bin/env python3
"""Guest-only installer and GUI smoke test. Never run on a development host."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

WORK = Path('/home/tester')
RESULTS = WORK/'results'


def run(args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def guard(expected):
    marker = Path('/etc/hyperfusion-deb-lab.json')
    if os.geteuid() == 0 or not marker.is_file() or marker.stat().st_uid != 0:
        raise RuntimeError('Requires the lab-created disposable guest and its normal tester user')
    data = json.loads(marker.read_text())
    if data != {'uuid': expected, 'purpose': 'disposable-deb-tests'}:
        raise RuntimeError('Lab identity mismatch')
    run(['systemd-detect-virt', '--vm', '--quiet'])
    actual = run(['sudo', '-n', 'cat', '/sys/class/dmi/id/product_uuid'], capture_output=True, text=True).stdout.strip().lower()
    if actual != expected:
        raise RuntimeError('Virtual-machine identity mismatch')


def install():
    import pexpect
    logpath = RESULTS/'install.log'
    deadline = time.monotonic()+1800
    temporary = WORK/'tmp'
    temporary.mkdir(mode=0o700, exist_ok=True)
    with logpath.open('w') as log:
        child = pexpect.spawn(sys.executable, [str(WORK/'installer/deb_install.py'), str(WORK/'input/source.deb')],
                              encoding='utf-8', codec_errors='replace', timeout=30,
                              env=dict(os.environ, LC_ALL='C', TERM='xterm', TMPDIR=str(temporary)))
        child.logfile_read = log
        try:
            while time.monotonic() < deadline:
                match = child.expect([r'Proceed with installation\?\s*\[Y/n\]', pexpect.EOF, pexpect.TIMEOUT])
                if match == 0:
                    # Only pacman's ordinary installation confirmation is automated.
                    child.sendline('y')
                elif match == 1:
                    child.close()
                    return child.exitstatus == 0
            raise TimeoutError('Installer exceeded 30 minutes')
        finally:
            if child.isalive(): child.terminate(force=True)


def window_info(window):
    result = subprocess.run(['xprop', '-id', window, '_NET_WM_PID', 'WM_CLASS', '_NET_WM_NAME'], capture_output=True, text=True)
    match = re.search(r'_NET_WM_PID\(CARDINAL\) = (\d+)', result.stdout)
    if not match:
        return None
    pid = int(match[1])
    try:
        executable = os.readlink('/proc/'+str(pid)+'/exe')
    except PermissionError:
        # Read-only observation inside the guarded guest. Some sandboxed apps
        # deny the normal user's access to their /proc executable symlink.
        inspected = subprocess.run(['sudo', '-n', 'readlink', '--', '/proc/'+str(pid)+'/exe'], capture_output=True, text=True)
        if inspected.returncode:
            return None
        executable = inspected.stdout.strip()
    except OSError:
        return None
    geometry = subprocess.run(['xwininfo', '-id', window], capture_output=True, text=True).stdout
    width = re.search(r'Width: (\d+)', geometry)
    height = re.search(r'Height: (\d+)', geometry)
    if 'IsViewable' not in geometry or not width or not height or int(width[1]) < 250 or int(height[1]) < 120:
        return None
    owner = subprocess.run(['pacman', '-Qqo', '--', executable], capture_output=True, text=True)
    return dict(id=window, pid=pid, executable=executable, package=owner.stdout.strip(),
                properties=result.stdout.strip(), width=int(width[1]), height=int(height[1]))


def windows():
    text = subprocess.run(['xprop', '-root', '_NET_CLIENT_LIST'], capture_output=True, text=True).stdout
    return re.findall(r'0x[0-9a-fA-F]+', text)


def screenshot():
    run(['xwd', '-root', '-silent', '-out', RESULTS/'screen.xwd'], timeout=15)
    run(['magick', RESULTS/'screen.xwd', RESULTS/'screen.png'], timeout=30)
    (RESULTS/'screen.xwd').unlink()


def gui(app, package):
    processes = []
    streams = []
    result = {'passed': False, 'backend': 'X11 / Xvfb / Openbox', 'sandbox_disabled': False}
    with tempfile.TemporaryDirectory(prefix='fusion-gui-') as runtime:
        os.chmod(runtime, 0o700)
        os.environ.update(DISPLAY=':99', XDG_RUNTIME_DIR=runtime, XDG_SESSION_TYPE='x11',
                          GDK_BACKEND='x11', QT_QPA_PLATFORM='xcb', LIBGL_ALWAYS_SOFTWARE='1')
        try:
            for name, args in [('xvfb', ['Xvfb', ':99', '-screen', '0', '1280x800x24', '-nolisten', 'tcp']),
                               ('openbox', ['openbox', '--sm-disable'])]:
                output = (RESULTS/(name+'.log')).open('w'); streams.append(output)
                process = subprocess.Popen(args, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
                processes.append(process)
                time.sleep(1)
                if process.poll() is not None:
                    raise RuntimeError(name+' did not start')
            baseline = set(windows())
            output = (RESULTS/'application.log').open('w'); streams.append(output)
            application = subprocess.Popen(app['launch'], cwd=app.get('cwd'), stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
            processes.append(application)
            deadline = time.monotonic()+90
            first_seen = {}
            while time.monotonic() < deadline:
                current = set(windows())-baseline
                first_seen = {key: value for key, value in first_seen.items() if key in current}
                for window in current:
                    info = window_info(window)
                    if not info or info['package'] != package:
                        continue
                    first_seen.setdefault(window, time.monotonic())
                    if time.monotonic()-first_seen[window] < 12:
                        continue
                    result.update(passed=True, window=info, visible_seconds=12)
                    screenshot()
                    return result
                if application.poll() is not None and application.returncode != 0 and not current:
                    result['exit_code'] = application.returncode
                    break
                time.sleep(1)
            result['error'] = 'No package-owned visible app window survived the launch observation period'
            result['observed_windows'] = [window_info(window) for window in windows()]
            screenshot()
            return result
        finally:
            for process in reversed(processes):
                try: os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError: pass
            for process in reversed(processes):
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try: os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                    process.wait()
            for stream in streams: stream.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gui', metavar='PACKAGE')
    args = parser.parse_args()
    app = json.loads((WORK/'input/app.json').read_text())
    guard(app['lab_uuid'])
    RESULTS.mkdir(exist_ok=True)
    if args.gui:
        try:
            result = gui(app, args.gui)
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            result = {'passed': False, 'error': str(error)}
        (RESULTS/'gui.json').write_text(json.dumps(result, indent=2)+'\n')
        return 0 if result['passed'] else 1
    sys.path.insert(0, str(WORK/'installer'))
    from deb_dependencies import read_control
    source = read_control(WORK/'input/source.deb')
    record = {'app': app['id'], 'name': app['name'], 'deb_package': source['package'],
              'deb_version': source['version'], 'status': 'install-failed',
              'tested_at': datetime.now(timezone.utc).isoformat(),
              'install_passed': False, 'gui_smoke_passed': False, 'functional_tested': False,
              'wayland_tested': False, 'uninstall_passed': False, 'reinstall_tested': False}
    try:
        for name in ('base-packages.txt', 'base-kernel.txt', 'base-created.txt'):
            shutil.copyfile(WORK/name, RESULTS/name)
        with (RESULTS/'storage-before.txt').open('w') as log:
            run(['df', '-h', '/', '/tmp', str(WORK)], stdout=log)
        run(['pacman', '-Q'], stdout=(RESULTS/'packages-before.txt').open('w'))
        if not install():
            log = (RESULTS/'install.log').read_text(errors='replace')
            failure = re.findall(r'== Installation stopped: (.*)', log)
            record['error'] = failure[-1] if failure else 'Installer failed; see install.log'
            return 1
        text = (RESULTS/'install.log').read_text()
        found = re.search(r'Installed successfully: (\S+) (\S+)\. Package registration and files verified\.', text)
        if not found:
            raise RuntimeError('Installer exited without its package-verification result')
        package, version = found.groups()
        record.update(install_passed=True, installed_package=package, installed_version=version, status='launch-failed')
        with (RESULTS/'package-check.log').open('w') as log:
            run(['pacman', '-Qk', '--', package], stdout=log, stderr=subprocess.STDOUT)
        subprocess.run(['dbus-run-session', '--', sys.executable, str(Path(__file__)), '--gui', package], timeout=150)
        if (RESULTS/'gui.json').exists():
            record['gui'] = json.loads((RESULTS/'gui.json').read_text())
            record['gui_smoke_passed'] = record['gui']['passed']
            if not record['gui_smoke_passed']:
                record['error'] = record['gui'].get('error', 'GUI smoke check failed')
        if record['gui_smoke_passed']:
            record['status'] = 'gui-smoke-passed'
        with (RESULTS/'uninstall.log').open('w') as log:
            removed = subprocess.run(['sudo', 'pacman', '-R', '--noconfirm', '--', package], stdout=log, stderr=subprocess.STDOUT)
        record['uninstall_passed'] = removed.returncode == 0 and subprocess.run(['pacman', '-Q', '--', package], capture_output=True).returncode != 0
        if not record['uninstall_passed']:
            record['status'] = 'uninstall-failed'
        return 0 if record['status'] == 'gui-smoke-passed' else 1
    except (OSError, ValueError, RuntimeError, TimeoutError, subprocess.SubprocessError) as error:
        record['error'] = str(error)
        return 1
    finally:
        run(['pacman', '-Q'], stdout=(RESULTS/'packages-after.txt').open('w'))
        (RESULTS/'result.json').write_text(json.dumps(record, indent=2)+'\n')


if __name__ == '__main__':
    raise SystemExit(main())
