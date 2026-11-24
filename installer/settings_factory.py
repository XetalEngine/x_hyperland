"""First-install system baseline; upgrades must never adopt personal state."""
from pathlib import Path
import os
import subprocess


def record(profile, first_install, skip_packages):
    # ISO installation records this later, after its final GRUB, login, driver
    # and package steps. A normal reinstall/update never redefines defaults.
    if not first_install or os.environ.get('XETAL_FACTORY_SYSTEM_DEFER') == '1': return
    import runtime_install
    prefix = runtime_install.administrator()
    if prefix and Path(prefix[0]).name == 'sudo': prefix = [prefix[0], '-k', *prefix[1:]]
    print('Recording the original system settings and installed application set…', flush=True)
    result = subprocess.run([*prefix, '/usr/bin/python3', str(Path(profile)/'settings_profiles/system.py'), 'factory'],
                            capture_output=True, text=True)
    runtime_install.check_administrator_result(prefix, result.returncode, result.stdout + result.stderr)
    if result.returncode: raise RuntimeError('Could not record factory system settings: ' + result.stderr[-2000:])
