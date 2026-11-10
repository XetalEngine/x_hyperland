#!/usr/bin/env python3
"""Prepare and run local applications; elevation is limited to explicit setup."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import stat
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def identity(path):
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError('Choose a regular local file to execute.')
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns]


def appimage_runtime(path):
    """Read bounded ELF load segments, never execute a file to inspect it."""
    with path.open('rb') as source:
        header = source.read(64)
        if len(header) != 64 or header[:4] != b'\x7fELF' or header[8:11] not in (b'AI\x01', b'AI\x02'):
            raise ValueError('This file is not a complete AppImage. Download it again from its publisher.')
        if header[4] not in (1, 2) or header[5] not in (1, 2):
            raise ValueError('Unsupported AppImage executable format.')
        endian = '<' if header[5] == 1 else '>'
        machine = struct.unpack_from(endian+'H', header, 18)[0]
        supported = {'x86_64': 62, 'amd64': 62, 'aarch64': 183, 'arm64': 183}.get(platform.machine().lower())
        if supported and machine != supported:
            raise ValueError('This AppImage is for a different processor. Download the '+platform.machine()+' version.')
        wide = header[4] == 2
        offset = struct.unpack_from(endian+('Q' if wide else 'I'), header, 32 if wide else 28)[0]
        entry, count = struct.unpack_from(endian+'HH', header, 54 if wide else 42)
        minimum = 56 if wide else 32
        size = path.stat().st_size
        if not 1 <= count <= 1024 or entry < minimum or entry > 4096 or offset+entry*count > size:
            raise ValueError('The AppImage has an invalid executable header.')
        dynamic, loaded, data = False, False, bytearray()
        for number in range(count):
            source.seek(offset+entry*number)
            values = struct.unpack(endian+('IIQQQQQQ' if wide else 'IIIIIIII'), source.read(minimum))
            kind, start, length = values[0], values[2 if wide else 1], values[5 if wide else 4]
            dynamic |= kind == 3  # PT_INTERP: the older dynamically linked runtime.
            if kind != 1: continue
            loaded = True
            if start+length > size or len(data)+length > 32*1024*1024:
                raise ValueError('The AppImage runtime is incomplete or too large to inspect.')
            source.seek(start); data.extend(source.read(length))
        if not loaded: raise ValueError('The AppImage contains no executable runtime.')
        # Current static type-2 runtimes bundle libfuse; do not require fuse2
        # for them. Legacy runtimes dlopen libfuse.so.2 (not a DT_NEEDED entry).
        return dynamic or b'libfuse.so.2' in data or header[10] == 1


def library_available(name):
    try: ctypes.CDLL(name); return True
    except OSError: return False


def inspect(path):
    path = Path(path).expanduser().absolute()
    token = identity(path)
    with path.open('rb') as source: head = source.read(4096)
    suffix = path.suffix.lower()
    kind = 'appimage' if suffix == '.appimage' or head[8:11] in (b'AI\x01', b'AI\x02') else 'deb' if suffix == '.deb' else 'script'
    if kind == 'script' and suffix not in ('.sh', '.run', '.bash', '.zsh', '.ksh'):
        raise ValueError('This file type is not supported by Execute.')
    result = dict(path=str(path), identity=token, kind=kind, packages=[], executable=os.access(path, os.X_OK), load_fuse=False)
    if kind == 'deb': return result
    if kind == 'appimage':
        legacy = appimage_runtime(path)
        if legacy:
            if not library_available('libfuse.so.2') or not shutil.which('fusermount'):
                result['packages'].append('fuse2')
        elif not any(shutil.which(name) for name in ('fusermount3', 'fusermount')):
            result['packages'].append('fuse3')
        result['load_fuse'] = not Path('/dev/fuse').exists()
    elif not head.startswith(b'\x7fELF'):
        interpreter = 'zsh' if suffix == '.zsh' else 'ksh' if suffix == '.ksh' else 'bash'
        if head.startswith(b'#!'):
            words = shlex.split(head.split(b'\n', 1)[0][2:].decode('utf-8').strip())
            if not words: raise ValueError('The script has an empty interpreter line.')
            interpreter = words[0]
            if Path(interpreter).name == 'env':
                commands = [word for word in words[1:] if not word.startswith('-') and '=' not in word]
                if commands: interpreter = commands[0]
        if not shutil.which(interpreter):
            name = Path(interpreter).name
            if name not in ('bash', 'sh', 'zsh', 'ksh', 'python', 'python3', 'perl', 'ruby'):
                raise ValueError('This script requires an interpreter that is not installed: '+interpreter)
            result['packages'].append({'sh': 'bash', 'python3': 'python'}.get(name, name))
    return result


def install_command(packages, release=None):
    release = release if release is not None else platform.freedesktop_os_release()
    family = (release.get('ID', '')+' '+release.get('ID_LIKE', '')).split()
    if 'arch' in family:
        return ['sudo', 'pacman', '-S', '--needed', '--noconfirm', '--', *packages]
    if any(name in family for name in ('debian', 'ubuntu')):
        version = release.get('VERSION_ID', '').split('.')[0]
        t64 = version.isdigit() and int(version) >= (24 if 'ubuntu' in family else 13)
        names = {'fuse2': 'libfuse2t64' if t64 else 'libfuse2', 'python': 'python3'}
        return ['sudo', 'apt-get', 'install', '-y', '--', *[names.get(p, p) for p in packages]]
    if any(name in family for name in ('fedora', 'rhel')):
        names = {'fuse2': 'fuse', 'python': 'python3'}
        return ['sudo', 'dnf', 'install', '-y', '--', *[names.get(p, p) for p in packages]]
    raise ValueError('Automatic requirement installation is unavailable on this distribution. Required packages: '+', '.join(packages))


def needs_setup(plan):
    return bool(plan['packages'] or plan['load_fuse'] or not plan['executable'])


def prepare(approved, runner=subprocess.run):
    current = inspect(approved['path'])
    if current['identity'] != approved['identity']:
        raise ValueError('The file changed after confirmation. Choose Execute again.')
    if (not set(current['packages']).issubset(approved['packages']) or
            (current['load_fuse'] and not approved['load_fuse']) or
            (not current['executable'] and approved['executable'])):
        raise ValueError('The requirements changed. Choose Execute again to review them.')
    commands = []
    if current['packages']: commands.append(install_command(current['packages']))
    if current['load_fuse']: commands.append(['sudo', 'modprobe', 'fuse'])
    if not current['executable']: commands.append(['sudo', 'chmod', '+x', '--', current['path']])
    for command in commands:
        if identity(Path(current['path'])) != approved['identity']:
            raise ValueError('The file changed during setup. Choose Execute again.')
        print('+ '+shlex.join(command), flush=True)
        runner(command, check=True)
    ready = inspect(current['path'])
    if ready['identity'] != approved['identity'] or needs_setup(ready):
        raise ValueError('Setup did not complete. Check the terminal output before trying again.')
    return ready


def terminal_command(plan, setup=False):
    return ['kitty', '--config', str(ROOT/'kitty.conf'), '--hold', '--directory', str(Path(plan['path']).parent),
            '-e', sys.executable, str(Path(__file__).resolve()), '--terminal',
            '--approved', json.dumps(plan, separators=(',', ':')), *(['--setup'] if setup else []), '--', plan['path']]


def target_command(plan):
    path = Path(plan['path'])
    with path.open('rb') as source: head = source.read(4)
    if plan['kind'] == 'script' and not head.startswith((b'#!', b'\x7fELF')):
        return [{'zsh': 'zsh', 'ksh': 'ksh'}.get(path.suffix.lower()[1:], 'bash'), str(path)]
    return [str(path)]


def launch_environment(plan):
    env = os.environ.copy()
    if plan['kind'] == 'appimage':
        # An AppImage's bundled Qt must not load Fusion's host-Qt binary plugins.
        for key in ('QT_PLUGIN_PATH', 'QT_QPA_PLATFORMTHEME', 'QT_STYLE_OVERRIDE'):
            env.pop(key, None)
    return env


def confirmation_text(plan):
    steps = []
    if plan['packages']: steps.append('Install required packages: '+', '.join(plan['packages']))
    if plan['load_fuse']: steps.append('Enable FUSE support')
    if not plan['executable']: steps.append('Allow this file to execute (chmod +x)')
    return ('To run “'+Path(plan['path']).name+'”:\n\n'+'\n'.join('• '+step for step in steps)+
            '\n\nContinue in a terminal? Enter your sudo password there if requested.')


def dialog(text, question=False):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication, QMessageBox
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT/'theme'))
    from theme import runtime
    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName('Fusion Files'); app.setDesktopFileName('xetal-files')
    runtime.install(app)
    box = QMessageBox(QMessageBox.Icon.Question if question else QMessageBox.Icon.Warning,
                      'Prepare to execute' if question else 'Could not execute', text)
    box.setTextFormat(Qt.TextFormat.PlainText)
    box.setObjectName('executionRequirements' if question else 'executionError')
    if question:
        proceed = box.addButton('Set up and run', QMessageBox.ButtonRole.AcceptRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        return box.clickedButton() == proceed
    box.addButton(QMessageBox.StandardButton.Ok); box.exec()
    return False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inspect', action='store_true')
    parser.add_argument('--terminal', action='store_true')
    parser.add_argument('--setup', action='store_true')
    parser.add_argument('--approved')
    parser.add_argument('path')
    args = parser.parse_args(argv)
    try:
        plan = inspect(args.path)
        if args.inspect:
            print(json.dumps(plan)); return 0
        if plan['kind'] == 'deb':
            command = [sys.executable, str(ROOT/'session_ui/client.py'), 'panel', '--section', 'deb', '--deb-file', plan['path']]
            os.execv(command[0], command)
        if args.terminal:
            approved = json.loads(args.approved or '{}')
            if plan['path'] != approved.get('path') or plan['identity'] != approved.get('identity'):
                raise ValueError('The file changed. Choose Execute again.')
            if args.setup: plan = prepare(approved)
            if needs_setup(plan): raise ValueError('Requirements are still missing. Choose Execute again to set them up.')
            # Only package installation, module loading and chmod use sudo.
            return subprocess.run(target_command(plan), cwd=Path(plan['path']).parent, env=launch_environment(plan)).returncode
        setup = needs_setup(plan)
        if setup and not dialog(confirmation_text(plan), question=True): return 0
        if setup or plan['kind'] == 'script':
            subprocess.Popen(terminal_command(plan, setup), stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            return 0
        os.chdir(Path(plan['path']).parent)
        os.execve(plan['path'], target_command(plan), launch_environment(plan))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        if args.terminal or args.inspect: print(str(error), file=sys.stderr)
        else: dialog(str(error))
        return 1


if __name__ == '__main__': raise SystemExit(main())
