#!/usr/bin/env python3
"""Run one saved menu action. Importing this module never launches a program."""
import argparse
import os
from pathlib import Path
import shlex
import subprocess
import sys
from urllib.parse import quote
import menu_config

ROOT = menu_config.ROOT


def invocation(item, root=ROOT):
    target, value = item['target'], item['value']
    scripts = root/'scripts'
    builtins = {
        'file_manager': [str(scripts/'files.sh'), str(Path.home())],
        'wallpaper': [str(scripts/'wallpaper.sh')],
        'displays': [str(scripts/'control-center.sh'), '--tab', 'displays'],
        'control_desk': [str(scripts/'control-center.sh')],
        'menu_settings': [str(scripts/'control-center.sh'), '--tab', 'context-menu'],
        'apps': [str(scripts/'launcher.sh')],
        'terminal': ['kitty', '--config', str(root/'kitty.conf')],
    }
    if target in builtins:
        return builtins[target], None
    if target == 'application':
        return ['python3', str(root/'launcher/launch.py'), '--app', quote(value, safe='')], None
    if target == 'folder':
        folder = Path(value).expanduser()
        if not folder.is_dir():
            raise ValueError('Folder does not exist: '+str(folder))
        return [str(scripts/'files.sh'), str(folder)], None
    if target == 'url':
        return ['xdg-open', value], None
    if target != 'command':
        raise ValueError('This item has no launch action.')
    argv = ['/bin/sh', '-lc', value] if item['shell'] else [os.path.expanduser(arg) for arg in shlex.split(value)]
    directory = str(Path(item['directory']).expanduser()) if item['directory'] else None
    if directory and not Path(directory).is_dir():
        raise ValueError('Working folder does not exist: '+directory)
    if item['terminal']:
        argv = ['kitty', '--config', str(root/'kitty.conf'), *(['--hold'] if item['hold'] else []), '-e', *argv]
    return argv, directory


def execute(ident, store=None, popen=subprocess.Popen):
    config, _ = (store or menu_config.Store()).load()
    item = menu_config.find(config, ident, active=True)
    if item is None or item['kind'] != 'action':
        raise ValueError('This menu shortcut was removed or disabled.')
    argv, directory = invocation(item)
    sys.path.insert(0, str(ROOT/'theme'))
    import runtime
    return popen(argv, cwd=directory, env=runtime.environment(), start_new_session=True,
                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--item', required=True)
    args = parser.parse_args()
    if not os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'):
        return 1
    try:
        execute(args.item)
    except Exception as error:
        subprocess.run(['notify-send', '-a', 'Xetal', 'Could not open menu shortcut', str(error)],
                       check=False, timeout=4)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
