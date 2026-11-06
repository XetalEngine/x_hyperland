#!/usr/bin/env python3
"""Real install and recovery, ONLY in an explicitly disposable Arch container."""
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'installer'))
import arch_runtime as arch
import dependencies
import runtime_install as runtime
import system_arch_runtime as system


def main():
    if (os.environ.get('XETAL_DISPOSABLE_ARCH') != '1' or os.geteuid() != 0
            or dependencies.distribution().get('ID') != 'arch'
            or not (Path('/run/.containerenv').exists() or Path('/.dockerenv').exists())):
        raise SystemExit('Requires an explicitly disposable Arch container; never run on a desktop host.')
    try:
        account = pwd.getpwnam('tester')
    except KeyError:
        subprocess.run(['useradd', '-m', 'tester'], check=True)
        account = pwd.getpwnam('tester')
    os.environ['SUDO_UID'] = str(account.pw_uid)
    directory = Path('/run/user')/str(account.pw_uid)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chown(directory, account.pw_uid, account.pw_gid)
    user = ['runuser', '-u', 'tester', '--', 'env', 'XDG_RUNTIME_DIR='+str(directory),
            'GIT_CONFIG_COUNT=1', 'GIT_CONFIG_KEY_0=safe.directory', 'GIT_CONFIG_VALUE_0='+str(ROOT)]
    if '--existing-runtime' in sys.argv:
        # Disposable fixture only: reproduce a current upstream desktop before
        # installing our older ABI, including real library downgrades/recovery.
        if runtime.PIN.exists():
            conf = system.CONF.read_text().splitlines(keepends=True)
            system.CONF.write_text(''.join(line for line in conf if line.strip() != 'Include = '+str(runtime.PIN)))
            runtime.PIN.unlink()
        subprocess.run(['pacman', '-Syu', '--noconfirm', *arch.expected()], check=True)
    before = runtime.policy.arch_versions(arch.expected())
    system.install()
    backup = max(p for p in system.STATE.iterdir() if p.is_dir())
    assert arch.pinned()
    assert runtime.policy.arch_versions(arch.expected()) == arch.expected()
    probe = 'import sys;sys.path.insert(0,sys.argv[1]+"/installer");import dependencies;errors=dependencies.check();assert not errors,errors'
    subprocess.run([*user, '/usr/bin/python3', '-c', probe, str(ROOT)], check=True)
    subprocess.run([*user, '/usr/bin/python3', str(ROOT/'installer/install.py'),
                    '--skip-packages', '--yes', '--prepare',
                    str(Path(account.pw_dir)/('arch-review-'+str(os.getpid())))], check=True)
    system.restore(backup)
    after = runtime.policy.arch_versions(arch.expected())
    assert all(after.get(name) == version for name, version in before.items())
    assert ('hyprland' in after) == ('hyprland' in before)
    before_failure = after.copy()
    with patch.object(runtime.policy, 'require', side_effect=RuntimeError('injected post-install failure')):
        try:
            system.install()
        except RuntimeError as error:
            assert 'injected post-install failure' in str(error), error
        else:
            raise AssertionError('Injected validation failure was ignored')
    assert runtime.policy.arch_versions(before_failure) == before_failure
    assert ('hyprland' in runtime.policy.arch_versions(['hyprland'])) == ('hyprland' in before_failure)
    print(json.dumps(dict(distribution='Arch', existing_runtime='--existing-runtime' in sys.argv,
                          install=True, dependencies=True, native_builds=True,
                          complete_desktop_build=True,
                          rollback=True, failed_install_recovery=True)))


if __name__ == '__main__':
    main()
