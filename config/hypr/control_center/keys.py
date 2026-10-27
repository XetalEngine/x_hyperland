"""Hyprland-only binding storage with validation, conflict checks and rollback."""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
import fcntl
import hashlib
import json
import os
import re
import subprocess
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
STATE = Path.home() / '.local/state/hyprland-control'
CATEGORIES = ['Window hover', 'Applications', 'Workspaces', 'Media & Devices', 'System']
SOURCE = 'source = ~/.config/hypr/keybindings.conf'
CAPTURE_MAP = 'hypr-control-capture'


class ConfigError(Exception):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def without_comment(line: str) -> str:
    return line.replace('##', '\x00').split('#', 1)[0].replace('\x00', '##').strip()


def variables(text: str) -> dict[str, str]:
    result = {}
    for line in text.splitlines():
        match = re.match(r'^\s*\$(\w+)\s*=\s*(.*)$', without_comment(line))
        if match:
            result[match[1]] = match[2].strip()
    return result


def expand(text: str, values: dict[str, str]) -> str:
    for _ in range(10):
        updated = re.sub(r'\$(\w+)', lambda m: values.get(m[1], m[0]), text)
        if updated == text:
            break
        text = updated
    return text


def category(dispatcher: str, args: str, key: str) -> str:
    if 'workspace' in dispatcher:
        return 'Workspaces'
    if key.startswith('XF86') or any(x in args for x in ('wpctl ', 'playerctl ', 'brightnessctl ')):
        return 'Media & Devices'
    if dispatcher in ('exit', 'submap') or any(x in args for x in ('hyprlock', 'screenshot', 'control-center')):
        return 'System'
    return 'Applications' if dispatcher == 'exec' else 'Window hover'


def default_label(dispatcher: str, args: str) -> str:
    labels = {'killactive': 'Close window', 'togglefloating': 'Toggle floating',
              'fullscreen': 'Toggle fullscreen', 'pseudo': 'Toggle pseudotiling',
              'exit': 'Log out of Hyprland', 'movewindow': 'Drag window',
              'resizewindow': 'Resize window', 'layoutmsg': 'Change tiling split'}
    commands = {'$terminal': 'Open terminal', '$menu': 'Open application launcher',
                '$fileManager': 'Open file manager'}
    if args in commands:
        return commands[args]
    if 'hyprlock' in args:
        return 'Lock screen'
    if 'screenshot.sh' in args:
        return 'Screenshot: ' + args.split()[-1]
    if 'control-center' in args:
        return 'Open Hyprland Control'
    if dispatcher in labels:
        return labels[dispatcher]
    return (dispatcher.replace('movetoworkspace', 'Move to workspace').replace('workspace', 'Workspace') + ' ' + args).strip()


@dataclass
class Binding:
    id: str
    label: str
    category: str
    enabled: bool
    mods: str
    key: str
    dispatcher: str
    args: str = ''
    flags: str = ''
    submap: str = 'reset'
    protected: bool = False

    def shortcut(self, values=None):
        mods = expand(self.mods, values or {'mainMod': 'SUPER'})
        display_key = {'code:61': '/', 'mouse:272': 'Left drag', 'mouse:273': 'Right drag',
                       'mouse_down': 'Wheel down', 'mouse_up': 'Wheel up'}.get(self.key, self.key)
        return ' + '.join([*mods.split(), display_key])

    def line(self):
        fields = [self.mods, self.key]
        if 'd' in self.flags:
            fields.append(self.label.replace(',', ' '))
        if 'm' in self.flags:
            fields.append(self.dispatcher + (' ' + self.args if self.args else ''))
        else:
            fields += [self.dispatcher, self.args]
        return 'bind' + self.flags + ' = ' + ', '.join(fields)


def parse(text: str) -> list[Binding]:
    result, meta, submap = [], {}, 'reset'
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if line.startswith('# @hotkey '):
            try:
                meta = json.loads(line[len('# @hotkey '):])
            except (ValueError, TypeError) as exc:
                raise ConfigError(f'Invalid metadata on line {number}: {exc}') from exc
            continue
        enabled = True
        if line.startswith('# disabled: '):
            line = line[len('# disabled: '):]
            enabled = False
        elif not line or line.startswith('#'):
            continue
        line = without_comment(line)
        if line.startswith('submap'):
            match = re.fullmatch(r'submap\s*=\s*([\w-]+)', line)
            if not match:
                raise ConfigError(f'Unsupported submap on line {number}')
            submap = match[1]
            continue
        match = re.fullmatch(r'bind([a-z]*)\s*=\s*(.*)', line)
        if not match:
            raise ConfigError(f'Line {number} is not a binding. Keep other settings in hyprland.conf.')
        flags, fields = match[1], match[2].split(',', 4 if 'd' in match[1] else 3)
        fields = [field.strip() for field in fields]
        minimum = 4 if 'd' in flags else 3
        if len(fields) < minimum:
            raise ConfigError(f'Incomplete binding on line {number}')
        if len(fields) == minimum:
            fields.append('')
        mods, key = fields[:2]
        dispatch, args = fields[-2:]
        if 'm' in flags and not args and ' ' in dispatch:
            dispatch, args = dispatch.split(' ', 1)
        label = fields[2] if 'd' in flags else default_label(dispatch, args)
        result.append(Binding(
            id=meta.get('id', uuid.uuid4().hex), label=meta.get('label', label),
            category=('Window hover' if meta.get('category') == 'Windows' else meta.get('category', category(dispatch, args, key))),
            enabled=enabled, mods=mods, key=key, dispatcher=dispatch, args=args,
            flags=flags, submap=submap, protected=bool(meta.get('protected', False))))
        meta = {}
    ids = [b.id for b in result]
    if len(ids) != len(set(ids)):
        raise ConfigError('Duplicate binding IDs in keybindings.conf.')
    return result


def serialize(bindings: list[Binding]) -> str:
    lines = ['# Managed by Hyprland Control. Only Hyprland reads this file.',
             '# Changes are validated before saving; previous versions are backed up.', '']
    submap = 'reset'
    for b in bindings:
        if b.submap != submap:
            lines += [f'submap = {b.submap}', '']
            submap = b.submap
        metadata = {k: getattr(b, k) for k in ('id', 'label', 'category', 'protected')}
        lines += ['# @hotkey ' + json.dumps(metadata, ensure_ascii=True),
                  ('' if b.enabled else '# disabled: ') + b.line(), '']
    if submap != 'reset':
        lines.append('submap = reset')
    return '\n'.join(lines) + '\n'


def trigger(binding: Binding, values: dict[str, str]):
    aliases = {'WIN': 'SUPER', 'META': 'SUPER', 'MOD4': 'SUPER', 'CONTROL': 'CTRL', 'MOD1': 'ALT'}
    mods = tuple(sorted({aliases.get(x.upper(), x.upper()) for x in expand(binding.mods, values).split()}))
    return mods, binding.key.lower(), 'r' in binding.flags, binding.submap


def conflicts(bindings: list[Binding], values: dict[str, str]) -> list[str]:
    seen, errors = {}, []
    for b in bindings:
        if not b.enabled:
            continue
        key = trigger(b, values)
        if key in seen:
            errors.append(f'{b.shortcut(values)}: "{seen[key].label}" and "{b.label}" use the same shortcut.')
        else:
            seen[key] = b
    return errors


def protect_typing(bindings, values):
    """Keep normal typing and application Ctrl/Shift shortcuts out of global grabs."""
    for b in bindings:
        if not b.enabled or b.submap != 'reset':
            continue
        mods = trigger(b, values)[0]
        dedicated = b.key.startswith('XF86') or b.key.lower() in ('print', 'pause')
        dedicated = dedicated or bool(re.fullmatch(r'F([1-9]|[12][0-9]|3[0-5])', b.key, re.I))
        if 'SUPER' not in mods and not dedicated:
            raise ConfigError(f'"{b.label}": use SUPER for global shortcuts. '
                              'Plain keys and Ctrl/Shift combinations are reserved for applications; '
                              'media, Print Screen and function keys are exempt.')


def validate_fields(bindings):
    for b in bindings:
        if not b.key or not b.dispatcher:
            raise ConfigError(f'"{b.label}": key and action are required.')
        for field in ('mods', 'key', 'dispatcher', 'args', 'flags', 'submap'):
            value = getattr(b, field)
            if any(c in value for c in '\r\n\x00'):
                raise ConfigError(f'"{b.label}": {field} must be a single line.')
        if not re.fullmatch(r'[\w$\s]*', b.mods):
            raise ConfigError(f'"{b.label}": invalid modifiers.')
        if ',' in b.key or '#' in b.key:
            raise ConfigError('Use a keysym such as comma or numbersign, not a literal separator.')
        if not re.fullmatch(r'[\w.]+', b.dispatcher):
            raise ConfigError(f'"{b.label}": invalid action name.')
        if not re.fullmatch(r'[a-z]*', b.flags) or not re.fullmatch(r'[\w-]+', b.submap):
            raise ConfigError(f'"{b.label}": invalid flags or submap.')
        if re.search(r'(?<!#)#(?!#)', b.args):
            raise ConfigError('Escape literal # characters in commands as ## (Hyprland syntax).')


def command(argv, timeout=15):
    return subprocess.run(argv, text=True, capture_output=True, timeout=timeout)


def atomic_write(path: Path, content: bytes):
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class Store:
    def __init__(self, root=ROOT, state=STATE, runner=command):
        self.root, self.state, self.run = Path(root), Path(state), runner
        self.path, self.main = self.root / 'keybindings.conf', self.root / 'hyprland.conf'
        self.defaults = self.root / 'control_center' / 'keybindings-defaults.conf'

    def load(self):
        data = self.path.read_bytes()
        return parse(data.decode()), digest(data)

    def read_preset(self, path, baseline):
        """Read a binding-only draft, retaining this installation's recovery key."""
        try:
            with Path(path).open('rb') as stream:
                data = stream.read(2 * 1024 * 1024 + 1)
            if len(data) > 2 * 1024 * 1024:
                raise ConfigError('This preset is too large (maximum 2 MiB).')
            records = parse(data.decode('utf-8-sig'))
            self.validate_preset(records)
        except (UnicodeError, ValueError, TypeError, AttributeError) as exc:
            raise ConfigError(f'Not a valid UTF-8 hotkey preset: {exc}') from exc
        values = variables(self.main.read_text())
        recovery = [b for b in baseline if b.protected]
        result, retained = [], set()
        for binding in records:
            reserved = next((b for b in recovery if b.id == binding.id
                             or trigger(b, values) == trigger(binding, values)), None)
            if reserved:
                if reserved.id not in retained:
                    result.append(replace(reserved))
                    retained.add(reserved.id)
            else:
                # Imported metadata must not make ordinary bindings uneditable.
                result.append(replace(binding, protected=False))
        result.extend(replace(b) for b in recovery if b.id not in retained)
        return result

    @staticmethod
    def validate_preset(records):
        if not records:
            raise ConfigError('This preset contains no hotkey bindings.')
        for b in records:
            if not all(isinstance(getattr(b, field), str) for field in
                       ('id', 'label', 'category', 'mods', 'key', 'dispatcher', 'args', 'flags', 'submap')):
                raise ConfigError('Preset names, IDs, categories and binding fields must be text.')
            if not b.id:
                raise ConfigError('A preset binding has an empty ID.')
            if 'd' in b.flags and any(c in b.label for c in '\r\n\x00'):
                raise ConfigError('A binding description must be a single line.')
        validate_fields(records)

    def save_preset(self, path, records):
        """Export the complete editor draft without applying it or reloading."""
        path = Path(path)
        if path.resolve() in {self.path.resolve(), self.main.resolve(), self.defaults.resolve()}:
            raise ConfigError('Choose a separate preset file. Use Apply changes to update active hotkeys; '
                              'the saved defaults are kept unchanged.')
        self.validate_preset(records)
        content = serialize(records).encode('utf-8')
        parse(content.decode('utf-8'))  # Refuse an export that cannot be read back.
        atomic_write(path, content)

    def check(self, bindings, main_text):
        validate_fields(bindings)
        protect_typing(bindings, variables(main_text))
        problems = conflicts(bindings, variables(main_text))
        if problems:
            raise ConfigError('\n'.join(problems))
        if main_text.count(SOURCE) != 1:
            raise ConfigError('Expected one managed keybindings source in hyprland.conf; nothing was changed.')
        with tempfile.TemporaryDirectory(prefix='.hotkey-check-', dir=self.root) as temporary:
            test_keys = Path(temporary) / 'keybindings.conf'
            test_main = Path(temporary) / 'hyprland.conf'
            test_keys.write_text(serialize(bindings))
            test_main.write_text(main_text.replace(SOURCE, f'source = {test_keys}'))
            result = self.run(['Hyprland', '--verify-config', '--config', str(test_main)])
            output = re.sub(r'\x1b\[[0-9;]*m', '', result.stdout + result.stderr)
            if result.returncode or 'config ok' not in output:
                raise ConfigError('Hyprland rejected these changes:\n' + output[-6000:])

    def apply(self, bindings, expected):
        if self.root.is_symlink() or self.path.is_symlink() or self.main.is_symlink():
            raise ConfigError('Refusing to write through a configuration symlink.')
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (self.state / 'apply.lock').open('w') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ConfigError('Another save is in progress.') from exc
            old = self.path.read_bytes()
            if digest(old) != expected:
                raise ConfigError('The file changed outside this window. Reload before saving to avoid overwriting those edits.')
            old_bindings = parse(old.decode())
            for protected in (b for b in old_bindings if b.protected):
                current = next((b for b in bindings if b.id == protected.id), None)
                if current != protected:
                    raise ConfigError('The recovery shortcut cannot be changed or removed.')
            main_text = self.main.read_text()
            self.check(bindings, main_text)
            if self.path.read_bytes() != old or self.main.read_text() != main_text:
                raise ConfigError('The configuration changed during validation. Reload and try again.')
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
            backup = self.state / ('keybindings-' + stamp + '.conf')
            backup.write_bytes(old)
            backup.chmod(0o600)
            new = serialize(bindings).encode()
            atomic_write(self.path, new)
            try:
                reloaded = self.run(['hyprctl', 'reload'])
                if reloaded.returncode or reloaded.stdout.strip() != 'ok':
                    raise ConfigError('Hyprland could not reload: ' + reloaded.stdout + reloaded.stderr)
                checked = self.run(['hyprctl', 'configerrors'])
                if checked.returncode or checked.stdout.strip():
                    raise ConfigError('Hyprland reported errors: ' + checked.stdout + checked.stderr)
            except Exception as exc:
                if self.path.read_bytes() == new:
                    atomic_write(self.path, old)
                    self.run(['hyprctl', 'reload'])
                    raise ConfigError(f'Changes were rolled back. {exc}') from exc
                raise ConfigError(f'An external edit prevented rollback. Backup: {backup}. {exc}') from exc
            return digest(new), backup
