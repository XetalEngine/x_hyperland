#!/usr/bin/env python3
"""Graphical setup by default; existing automation flags retain their CLI."""
import ctypes
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def main():
    args = sys.argv[1:]
    explicit = '--gui' in args
    gui = explicit or (not args and bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')))
    if not gui:
        if '--cli' in args: args.remove('--cli')
        os.execv(sys.executable, [sys.executable, str(ROOT/'install.py'), *args])
    if any(arg not in ('--gui', '--update') for arg in args):
        raise RuntimeError('Use --cli with installer command-line options, or --gui to open Setup.')
    try: ctypes.CDLL('libgtk-3.so.0')
    except OSError:
        if not sys.stdin.isatty():
            terminal = shutil.which('kitty')
            if terminal:
                return subprocess.call([terminal, '--title', 'Xetal Setup prerequisites', sys.executable, str(__file__), '--gui', *(['--update'] if '--update' in args else [])])
            raise RuntimeError('GTK 3 is required. Run x_hyperinstall.sh in a terminal to install it.')
        import dependencies
        command = {'arch':['pacman','-S','--needed','gtk3'], 'fedora':['dnf','install','gtk3'],
                   'debian':['apt-get','install','libgtk-3-0t64']}.get(dependencies.distro())
        if command is None: raise RuntimeError('Install the GTK 3 runtime, then open Setup again.')
        if input('Install GTK 3 to open the graphical installer? [Y/n] ').strip().lower() not in ('','y','yes'): return 1
        subprocess.run(['sudo',*command], check=True)
    from wizard import main as wizard
    existing = (Path.home()/'.config/hypr/.xetal-update.json').is_file()
    return wizard(update='--update' in args or existing)


if __name__ == '__main__':
    try: sys.exit(main())
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print('Xetal Setup: '+str(error), file=sys.stderr)
        for tool, args in [('kdialog',['--error',str(error)]),('zenity',['--error','--text='+str(error)])]:
            if shutil.which(tool) and (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
                subprocess.run([tool,*args]); break
        sys.exit(1)
