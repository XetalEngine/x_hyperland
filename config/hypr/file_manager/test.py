#!/usr/bin/env python3
"""Run native interaction tests with isolated D-Bus, config, cache and trash."""
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
if __name__ == '__main__':
    cache = Path.home()/'.cache'
    cache.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='fusion-files-checks-', dir=cache) as directory:
        base = Path(directory)
        # Assets remain readable, while Files preferences and Auto mount
        # observations belong only to this test run.
        profile = base/'profile'; profile.mkdir()
        for source in ROOT.parent.iterdir():
            if source.name in ('theme', 'icon_themes'):
                shutil.copytree(source, profile/source.name, ignore=shutil.ignore_patterns('__pycache__', '.build', 'generated', 'backups'))
            elif source.name != 'file_manager': (profile/source.name).symlink_to(source)
        (profile/'file_manager').mkdir()
        for source in ROOT.iterdir():
            if source.is_file() and source.suffix in ('.py', '.svg'):
                shutil.copy2(source, profile/'file_manager'/source.name)
        env = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_QPA_PLATFORMTHEME='',
                   XETAL_FILES_ROOT=str(profile), XDG_DATA_DIRS='/usr/local/share:/usr/share',
                   FUSION_FILES_ISOLATED='1', TMPDIR=str(base))
        env.pop('HYPRLAND_INSTANCE_SIGNATURE', None)
        for key, name in [('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'),
                          ('XDG_CACHE_HOME', 'cache'), ('XDG_STATE_HOME', 'state'),
                          ('XDG_RUNTIME_DIR', 'runtime')]:
            path = base/name; path.mkdir(mode=0o700); env[key] = str(path)
        build = Path(os.environ.get('FUSION_FILES_BUILD', str(base/'build')))
        subprocess.run(['cmake', '-S', str(ROOT), '-B', str(build),
                        '-DBUILD_TESTING=ON', '-DCMAKE_BUILD_TYPE=Debug'], check=True, env=env)
        subprocess.run(['cmake', '--build', str(build), '--parallel', '4'], check=True, env=env)
        subprocess.run([sys.executable, str(ROOT/'test_search_worker.py')], check=True, env=env)
        subprocess.run(['dbus-run-session', '--', str(build/'search-tests')], check=True, env=env)
        subprocess.run(['dbus-run-session', '--', str(build/'files-tests')], check=True, env=env)
        subprocess.run(['dbus-run-session', '--', str(build/'picker-tests')], check=True, env=env)
        subprocess.run(['dbus-run-session', '--', str(build/'automount-tests')], check=True, env=env)
        subprocess.run(['dbus-run-session', '--', sys.executable, str(ROOT/'test_service.py'),
                        str(build/'xetal-files')], check=True, env=env)
        subprocess.run(['dbus-run-session', '--', sys.executable, str(ROOT/'test_progress.py'),
                        str(build/'files-tests')], check=True, env=env)
        subprocess.run(['dbus-run-session', '--', sys.executable, str(ROOT/'test_progress.py'),
                        str(build/'files-tests'), '--cancel'], check=True, env=env)
        subprocess.run(['dbus-run-session', '--', sys.executable, str(ROOT/'test_questions.py'),
                        str(build/'files-tests')], check=True, env=env)
