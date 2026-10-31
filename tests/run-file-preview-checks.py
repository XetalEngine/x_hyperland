#!/usr/bin/env python3
"""Build and exercise the native file-picker integrations in private test dirs."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import time

REPO = Path(__file__).resolve().parents[1]


def run(args, **kwargs):
    return subprocess.run(args, check=True, timeout=60, **kwargs)


def main():
    with tempfile.TemporaryDirectory(prefix='xetal-file-previews-') as directory:
        root = Path(directory); theme = root/'theme'; theme.mkdir()
        bookmark = root/'user-places.xbel'
        bookmark.write_text('<xbel><bookmark href="'+root.as_uri()+'"><title>My Dolphin Places</title></bookmark></xbel>')
        for name in ('build.py', 'platformtheme.cpp', 'file_preview.hpp', 'gtk_file_preview.c',
                     'file_places.hpp', 'gtk_file_places.h', 'places.py', 'plugin.json', 'palettes.json', 'state.json'):
            shutil.copy2(REPO/'config/hypr/theme'/name, theme/name)
        run(['python3', str(theme/'build.py')])
        for major in (5, 6):
            flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs',
                                f'Qt{major}Widgets', f'Qt{major}Test'], text=True))
            binary = root/f'qt{major}-preview'
            run(['c++', '-std=c++17', '-O2', '-fPIC', '-Wall', '-Wextra', '-Werror',
                 str(REPO/'tests/file-preview-qt.cpp'), '-o', str(binary), *flags])
            env = {**os.environ, 'QT_QPA_PLATFORM': 'offscreen', 'QT_QPA_PLATFORMTHEME': 'xetal',
                   'QT_PLUGIN_PATH': str(theme/f'qt{major}'), 'XETAL_THEME_CONFIG': str(theme/'state.json'),
                   'HYPRLAND_INSTANCE_SIGNATURE': 'preview-test', 'XETAL_PLACES_FILE': str(bookmark)}
            run([str(binary)], env=env)
        if not shutil.which('broadwayd'):
            print('GTK display probe skipped: broadwayd is not installed. Module build passed.')
            return
        runtime = root/'runtime'; runtime.mkdir(mode=0o700)
        env = {**os.environ, 'XDG_RUNTIME_DIR': str(runtime), 'XDG_CONFIG_HOME': str(root/'config'),
               'XDG_DATA_HOME': str(root/'data'), 'GSETTINGS_BACKEND': 'memory', 'GIO_USE_VFS': 'local',
               'GDK_BACKEND': 'broadway', 'BROADWAY_DISPLAY': ':7', 'NO_AT_BRIDGE': '1',
               'GTK3_MODULES': str(theme/'gtk3/libxetal-file-preview.so'),
               'HYPRLAND_INSTANCE_SIGNATURE': 'preview-test', 'XETAL_THEME_CONFIG': str(theme/'state.json'), 'XETAL_PLACES_FILE': str(bookmark)}
        env.pop('GTK_MODULES', None)
        with (root/'broadway.log').open('w') as log:
            daemon = subprocess.Popen(['broadwayd', '--unixsocket='+str(root/'http.sock'), ':7'],
                                      env=env, stdout=log, stderr=log)
            try:
                for _ in range(100):
                    if list(runtime.glob('broadway*.socket')): break
                    if daemon.poll() is not None: raise RuntimeError((root/'broadway.log').read_text())
                    time.sleep(.02)
                run(['python3', str(REPO/'tests/file-preview-gtk.py')], env=env)
            finally:
                daemon.terminate()
                try: daemon.wait(timeout=5)
                except subprocess.TimeoutExpired: daemon.kill(); daemon.wait()


if __name__ == '__main__': main()
