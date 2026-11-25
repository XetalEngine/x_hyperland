"""Kitty and Bash preferences, plus private, generation-scoped command history."""
from __future__ import annotations

import argparse
import copy
import fcntl
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import tempfile
import uuid

ROOT = Path(__file__).resolve().parent
DEFAULTS = dict(
    version=1, shell='bash', enhanced=True, syntax_highlighting=True,
    autosuggestions=True, completion_menu=True, completion_fuzzy=True,
    completion_ignore_case=True, suggestion_delay=150, keymap='emacs',
    history_enabled=True, history_size=20000, history_ignore_space=True,
    history_ignore_duplicates=True, history_share=True,
    follow_theme_font=True, font_family='monospace', font_size=11.0, padding=10, opacity=100,
    cursor_shape='block', cursor_blink=True, cursor_trail=True,
    scrollback_lines=20000, pager_history_mb=16, scrollbar='always',
    tab_style='powerline', tab_edge='top', remember_window_size=False,
    copy_on_select=False, audio_bell=False, confirm_close=True,
)
CHOICES = dict(shell=('bash', 'login'), keymap=('emacs', 'vi'),
               cursor_shape=('block', 'beam', 'underline'),
               scrollbar=('always', 'hovered', 'never'),
               tab_style=('powerline', 'fade', 'separator', 'slant', 'hidden'),
               tab_edge=('top', 'bottom'))
RANGES = dict(suggestion_delay=(0, 2000), history_size=(100, 1000000),
              font_size=(6, 40), padding=(0, 40), opacity=(20, 100),
              scrollback_lines=(100, 1000000), pager_history_mb=(0, 1024))


def validate(value):
    if not isinstance(value, dict) or value.get('version') != 1:
        raise ValueError('Unsupported terminal preferences.')
    result = copy.deepcopy(DEFAULTS)
    for key, default in DEFAULTS.items():
        item = value.get(key, default)
        if type(default) is bool:
            if type(item) is not bool: raise ValueError('Invalid ' + key + ' option.')
        elif key in CHOICES:
            if item not in CHOICES[key]: raise ValueError('Invalid ' + key + ' option.')
        elif key in RANGES:
            kinds = (int, float) if key == 'font_size' else (int,)
            low, high = RANGES[key]
            if type(item) not in kinds or not low <= item <= high:
                raise ValueError(f'{key} must be between {low} and {high}.')
        elif key == 'font_family':
            if not isinstance(item, str) or not item.strip() or len(item) > 160 or any(
                    ord(c) < 32 or ord(c) == 127 for c in item):
                raise ValueError('Choose a valid font family.')
            item = item.strip()
        result[key] = item
    return result


def load(root=None):
    path = (root or ROOT) / 'preferences.json'
    return validate(json.loads(path.read_text())) if path.exists() else copy.deepcopy(DEFAULTS)


def atomic(path, content, mode=0o600):
    """Replace complete files; readers never see half-written configuration."""
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(content.encode() if isinstance(content, str) else content)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


def kitty_config(value):
    v = validate(value)
    yes = lambda key: 'yes' if v[key] else 'no'
    options = dict(font_family=v['font_family'], font_size=v['font_size'],
        window_padding_width=v['padding'], background_opacity=f"{v['opacity'] / 100:.2f}",
        dynamic_background_opacity='yes', cursor_shape=v['cursor_shape'],
        cursor_blink_interval='0.5 ease-in-out' if v['cursor_blink'] else '0',
        cursor_trail=1 if v['cursor_trail'] else 0,
        scrollback_lines=v['scrollback_lines'], scrollback_pager_history_size=v['pager_history_mb'],
        scrollbar=v['scrollbar'], tab_bar_style=v['tab_style'], tab_bar_edge=v['tab_edge'],
        remember_window_size=yes('remember_window_size'), copy_on_select=yes('copy_on_select'),
        enable_audio_bell=yes('audio_bell'), confirm_os_window_close=-1 if v['confirm_close'] else 0)
    if v['follow_theme_font']: options.pop('font_family')
    return '# Managed by Fusion Settings → Terminal. Colors follow the desktop theme.\n' + ''.join(
        f'{key} {item}\n' for key, item in options.items())


def save(value, *, root=None, expected=None):
    root = root or ROOT; value = validate(value)
    root.mkdir(parents=True, exist_ok=True)
    with (root / 'preferences.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if expected is not None and load(root) != expected:
            raise ValueError('Terminal preferences changed elsewhere. Reload before saving.')
        # Roll back both artifacts if either write fails. Both are owned preferences
        # in desktop updates and in Save / Load / Reset System Settings.
        targets = {root / 'kitty-settings.conf': kitty_config(value),
                   root / 'preferences.json': json.dumps(value, indent=2) + '\n'}
        before = {p: p.read_bytes() if p.exists() else None for p in targets}
        written = []
        try:
            for path, content in targets.items():
                atomic(path, content); written.append(path)
        except OSError:
            for path in written:
                if before[path] is None: path.unlink(missing_ok=True)
                else: atomic(path, before[path])
            raise
    return value


def state_root():
    return Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local/state') / 'hyperfusion/terminal'


def private_directory(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise ValueError('Terminal history must be a private directory owned by your account.')
    path.chmod(0o700)


def generation(root):
    try: value = (root / 'generation').read_text().strip()
    except FileNotFoundError: return ''
    if not re.fullmatch(r'[a-f0-9]{32}', value): raise ValueError('Invalid terminal history state.')
    return value


def history_path(root, token):
    return root / token / 'commands.bash'


def prepare_history(root=None, *, import_from=None):
    root = root or state_root(); private_directory(root)
    with (root / 'history.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        token = generation(root)
        if not token:
            token = uuid.uuid4().hex
            private_directory(root / token)
            source = import_from if import_from is not None else Path.home() / '.bash_history'
            data = b''
            # Seed once, preserving the original history. Never reimport after Clear.
            if source.is_file() and not source.is_symlink() and source.stat().st_size <= 32 * 1024 * 1024:
                data = source.read_bytes()
            atomic(history_path(root, token), data)
            atomic(root / 'generation', token + '\n')
        private_directory(root / token)
        path = history_path(root, token)
        if path.is_symlink() or not path.is_file(): raise ValueError('Terminal history is unavailable.')
        path.chmod(0o600)
        return token, path


def clear_history(root=None):
    """Retire the entire old directory so stale shells cannot recreate its file."""
    root = root or state_root(); private_directory(root)
    with (root / 'history.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        token = uuid.uuid4().hex
        private_directory(root / token)
        atomic(history_path(root, token), b'')
        atomic(root / 'generation', token + '\n')
        for old in root.iterdir():
            if old.name != token and re.fullmatch(r'[a-f0-9]{32}', old.name):
                if old.is_symlink(): old.unlink()
                elif old.is_dir(): shutil.rmtree(old)
        return token


def history_status(root=None):
    root = root or state_root()
    token = generation(root)
    if not token: return 'A private Fusion history will be created when you open a terminal.'
    path = history_path(root, token)
    size = path.stat().st_size if path.is_file() else 0
    return f'Saved command history: {size / 1024:.1f} KiB. Stored privately in {root}.'


def shell_settings(value, root=None):
    value = validate(value); root = root or state_root()
    token, path = prepare_history(root) if value['history_enabled'] else ('', '')
    variables = {'FUSION_HISTORY_ROOT': str(root), 'FUSION_HISTORY_GENERATION': token,
                 'FUSION_HISTORY_FILE': str(path)}
    for key in ('enhanced', 'syntax_highlighting', 'autosuggestions', 'completion_menu',
                'completion_fuzzy', 'completion_ignore_case', 'suggestion_delay', 'keymap',
                'history_enabled', 'history_size', 'history_ignore_space',
                'history_ignore_duplicates', 'history_share'):
        item = value[key]
        variables['FUSION_' + key.upper()] = str(int(item)) if type(item) is bool else str(item)
    return '\n'.join(f'{key}={shlex.quote(item)}' for key, item in variables.items())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('shell', 'shell-mode'))
    args = parser.parse_args()
    try:
        value = load()
        print(value['shell'] if args.action == 'shell-mode' else shell_settings(value))
    except (OSError, ValueError) as error:
        # A broken preference must never prevent a recovery shell from opening.
        import sys
        print('Fusion terminal: ' + str(error), file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__': main()
