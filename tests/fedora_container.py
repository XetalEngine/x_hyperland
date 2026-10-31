#!/usr/bin/env python3
"""Real RPM install/build/recovery check. ONLY for a disposable Fedora 44 container."""
import argparse
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'installer'))
import dependencies
import fedora_runtime as fedora
import runtime_install as runtime
import system_fedora_runtime as system


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared-profile',type=Path,help='Reuse an already built profile for local package-recovery testing.')
    args=parser.parse_args()
    if os.environ.get('XETAL_DISPOSABLE_FEDORA') != '1' or os.geteuid()!=0 or not runtime.policy.fedora_host():
        parser.error('Requires root inside disposable Fedora 44 and XETAL_DISPOSABLE_FEDORA=1; never run on a desktop host.')
    try: account=pwd.getpwnam('tester')
    except KeyError:
        subprocess.run(['useradd','-m','tester'],check=True); account=pwd.getpwnam('tester')
    os.environ['SUDO_UID']=str(account.pw_uid)
    directory=Path('/run/user')/str(account.pw_uid);directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chown(directory,account.pw_uid,account.pw_gid)
    user=['runuser','-u','tester','--','env','XDG_RUNTIME_DIR='+str(directory),
          'GIT_CONFIG_COUNT=1','GIT_CONFIG_KEY_0=safe.directory','GIT_CONFIG_VALUE_0='+str(ROOT)]
    required=fedora.target(); names={p['name'] for p in required['packages']}
    before=runtime.policy.rpm_versions(names)
    subprocess.run([*user,sys.executable,'-c',f'import sys;sys.path.insert(0,{str(ROOT/"installer")!r});import dependencies;dependencies.preflight()'],check=True)
    system.install()
    backup=max(p for p in system.STATE.iterdir() if p.is_dir())
    assert fedora.pinned()
    subprocess.run(['dnf','-y','--setopt=install_weak_deps=False','install',*dependencies.PACKAGES['fedora']],check=True)
    if args.prepared_profile:
        subprocess.run([*user,sys.executable,'-c',f'import sys;from pathlib import Path;sys.path.insert(0,{str(ROOT/"installer")!r});import install;install.validate(Path({str(args.prepared_profile)!r}))'],check=True)
    else:
        subprocess.run([*user,sys.executable,str(ROOT/'installer/install.py'),'--skip-packages','--yes',
                        '--prepare',str(Path(account.pw_dir)/'fedora-review')],check=True)
    system.restore(backup)
    assert runtime.policy.rpm_versions(names)==before
    # A failure after a real package operation must recover packages and locks.
    with patch.object(runtime.policy,'require',side_effect=RuntimeError('injected post-install validation failure')):
        try: system.install()
        except RuntimeError as error:
            assert 'injected post-install' in str(error),error
        else: raise AssertionError('The injected failure was ignored')
    assert runtime.policy.rpm_versions(names)==before
    print(json.dumps(dict(distribution='Fedora 44',install=True,build=True,configuration=True,
                          rollback=True,failed_install_recovery=True)))


if __name__=='__main__':main()
