#!/usr/bin/env python3
"""Real native package/build/recovery test, ONLY in a disposable Debian 13 container."""
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'installer'))
import debian_runtime as debian
import runtime_install as runtime
import system_debian_runtime as system


def main():
    if os.environ.get('XETAL_DISPOSABLE_DEBIAN') != '1' or os.geteuid() != 0 or not runtime.policy.debian_host():
        raise SystemExit('Requires root inside disposable Debian 13 and XETAL_DISPOSABLE_DEBIAN=1; never run on a desktop host.')
    try: account = pwd.getpwnam('tester')
    except KeyError:
        subprocess.run(['useradd', '-m', 'tester'], check=True); account = pwd.getpwnam('tester')
    os.environ['SUDO_UID'] = str(account.pw_uid)
    directory = Path('/run/user')/str(account.pw_uid); directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chown(directory, account.pw_uid, account.pw_gid)
    user = ['runuser', '-u', 'tester', '--', 'env', 'XDG_RUNTIME_DIR='+str(directory),
            'GIT_CONFIG_COUNT=1', 'GIT_CONFIG_KEY_0=safe.directory', 'GIT_CONFIG_VALUE_0='+str(ROOT)]
    # Existing desktop applications and older libraries must survive rollback.
    subprocess.run([*debian.APT, '-y', 'install', 'kitty', 'waybar', 'dolphin', 'libwayland-dev', 'libsdl3-0'], check=True)
    before = system.versions()
    subprocess.run([*user, sys.executable, '-c', f'import sys;sys.path.insert(0,{str(ROOT/"installer")!r});import dependencies;dependencies.preflight()'], check=True)
    system.install()
    backup = max(p for p in system.STATE.iterdir() if p.is_dir())
    assert debian.pinned()
    subprocess.run([*user, sys.executable, str(ROOT/'installer/install.py'), '--skip-packages', '--yes',
                    '--prepare', str(Path(account.pw_dir)/'debian-review')], check=True)
    system.restore(backup)
    restored = system.versions()
    assert all(restored.get(key) == value for key, value in before.items())
    bundled = {p['name']+':'+p['architecture'] for p in debian.target()['packages']}
    assert all(key not in restored for key in bundled if key not in before)
    before_failure = system.versions()
    with patch.object(runtime.policy, 'require', side_effect=RuntimeError('injected post-install failure')):
        try: system.install()
        except RuntimeError as error: assert 'injected post-install' in str(error), error
        else: raise AssertionError('The injected failure was ignored')
    restored = system.versions()
    assert all(restored.get(key) == value for key, value in before_failure.items())
    assert all(key not in restored for key in bundled if key not in before_failure)
    print(json.dumps(dict(distribution='Debian 13', install=True, build=True, configuration=True,
                          rollback=True, failed_install_recovery=True)))


if __name__ == '__main__': main()
