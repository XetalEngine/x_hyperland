#!/usr/bin/env python3
"""Run native interaction tests with isolated D-Bus, config, cache and trash."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
if __name__ == '__main__':
    cache = Path.home()/'.cache'
    cache.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='fusion-files-checks-', dir=cache) as directory:
        base = Path(directory)
        env = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_QPA_PLATFORMTHEME='',
                   XETAL_FILES_ROOT=str(ROOT.parent), XDG_DATA_DIRS='/usr/local/share:/usr/share', TMPDIR=str(base))
        for key, name in [('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'),
                          ('XDG_CACHE_HOME', 'cache'), ('XDG_STATE_HOME', 'state'),
                          ('XDG_RUNTIME_DIR', 'runtime')]:
            path = base/name; path.mkdir(mode=0o700); env[key] = str(path)
        build = Path(os.environ.get('FUSION_FILES_BUILD', str(base/'build')))
        subprocess.run(['cmake', '-S', str(ROOT), '-B', str(build),
                        '-DBUILD_TESTING=ON', '-DCMAKE_BUILD_TYPE=Debug'], check=True, env=env)
        subprocess.run(['cmake', '--build', str(build), '--parallel', '4'], check=True, env=env)
        subprocess.run(['dbus-run-session', '--', str(build/'files-tests')], check=True, env=env)
