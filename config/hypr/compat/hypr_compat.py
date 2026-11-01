"""Translate Xetal's managed settings/actions to Hyprland 0.57's Lua API.

The editors retain their readable .conf data, metadata and rollback format.
Only the compositor entry point and IPC boundary vary by Hyprland version.
Unknown syntax is an error, never a silently discarded setting.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys


def lua(value):
    if isinstance(value, dict):
        return '{' + ', '.join('['+lua(k)+']='+lua(v) for k, v in value.items()) + '}'
    if isinstance(value, (list, tuple)):
        return '{' + ', '.join(map(lua, value)) + '}'
    if value is None: return 'nil'
    # JSON escapes for control characters other than these aren't Lua escapes.
    result = json.dumps(value, ensure_ascii=False, allow_nan=False)
    return re.sub(r'\\u00([0-9a-f]{2})', lambda m: '\\'+str(int(m[1], 16)).zfill(3), result)


def call(name, *args):
    return 'hl.' + name + '(' + ', '.join(map(lua, args)) + ')'


def scalar(value):
    value = value.strip()
    if value.lower() in ('true', 'yes', 'on', 'yes, please :)'): return True
    if value.lower() in ('false', 'no', 'off'): return False
    if re.fullmatch(r'[+-]?\d+', value): return int(value)
    if re.fullmatch(r'[+-]?(?:\d+\.\d*|\.\d+)', value): return float(value)
    colors = re.findall(r'rgba?\([\da-fA-F]+\)', value)
    if len(colors) > 1:
        angle = re.search(r'([+-]?\d+)deg$', value)
        return {'colors': colors, 'angle': int(angle[1]) if angle else 0}
    return value


def parts(value, separator=','):
    """Split config fields, respecting regex groups, quotes and inline rules."""
    result, start, nesting, quote, escaped = [], 0, [], '', False
    for i, c in enumerate(value):
        if escaped: escaped = False; continue
        if c == '\\': escaped = True; continue
        if quote:
            if c == quote: quote = ''
            continue
        if c in "\"'": quote = c
        elif c in '([{': nesting.append(c)
        elif c in ')]}' and nesting: nesting.pop()
        elif c == separator and not nesting:
            result.append(value[start:i].strip()); start = i+1
    result.append(value[start:].strip())
    return result


def window_rule(fields):
    result, match = {}, {}
    string_keys = {'name', 'monitor', 'workspace', 'animation', 'group', 'content', 'tag', 'suppress_event'}
    for key, value in fields:
        if key.startswith('match:'):
            match[key[6:]] = scalar(value) if key[6:] in {'float', 'fullscreen', 'pin', 'xwayland', 'focus'} else value
        else:
            result[key] = value if key in string_keys else scalar(value)
    if match: result['match'] = match
    return result


def rule_fields(text):
    fields = []
    for item in parts(text):
        key, _, value = item.partition(' ')
        fields.append((key, value.strip() or 'on'))
    return fields


def session_command(command):
    """Scope the IPC adapter to our apps, not D-Bus/systemd's activation env."""
    rules = ''
    if command.startswith('['):
        end = command.find(']')
        if end < 0: raise ValueError('Unclosed launch rules')
        rules, command = command[:end+1]+' ', command[end+1:].lstrip()
    return rules + 'env PATH="$HOME/.config/hypr/compat/bin:$PATH" XETAL_HYPRLAND_LUA=1 /bin/sh -c ' + shlex.quote(command)


def dispatcher(name, args=''):
    args = args.strip()
    direction = {'l': 'left', 'r': 'right', 'u': 'up', 'd': 'down'}.get(args, args)
    simple = {'exec': 'exec_cmd', 'execr': 'exec_raw', 'event': 'event', 'submap': 'submap',
              'layoutmsg': 'layout', 'togglespecialworkspace': 'workspace.toggle_special', 'global': 'global'}
    if name in simple: return call('dsp.'+simple[name], session_command(args) if name in ('exec', 'execr') else args)
    empty = {'exit': 'exit', 'killactive': 'window.close', 'forcekillactive': 'window.kill',
             'pseudo': 'window.pseudo', 'resizewindow': 'window.resize', 'bringactivetotop': 'window.bring_to_top',
             'pin': 'window.pin', 'togglegroup': 'group.toggle'}
    if name in empty and not args: return call('dsp.'+empty[name])
    if name == 'resizewindow' and args in ('1', '2'):
        return call('dsp.window.resize', {'keep_aspect_ratio': args == '1'})
    if name in ('workspace', 'focusmonitor', 'focuswindow', 'movefocus'):
        key = {'workspace': 'workspace', 'focusmonitor': 'monitor', 'focuswindow': 'window', 'movefocus': 'direction'}[name]
        return call('dsp.focus', {key: direction if name == 'movefocus' else args})
    if name in ('togglefloating', 'setfloating', 'settiled'):
        options = {'action': {'togglefloating': 'toggle', 'setfloating': 'set', 'settiled': 'unset'}[name]}
        if args: options['window'] = args
        return call('dsp.window.float', options)
    if name in ('closewindow', 'killwindow'):
        return call('dsp.window.'+('close' if name == 'closewindow' else 'kill'), {'window': args})
    if name == 'alterzorder':
        values = args.split(',', 1)
        options = {'mode': values[0].strip()}
        if len(values)>1 and values[1].strip(): options['window'] = values[1].strip()
        return call('dsp.window.alter_zorder', options)
    if name == 'fullscreen':
        values = args.split()
        return call('dsp.window.fullscreen', {'mode': 'maximized' if values and values[0] == '1' else 'fullscreen',
                    'action': {'0': 'toggle', '1': 'set', '2': 'unset'}.get(values[1], 'toggle') if len(values)>1 else 'toggle'})
    if name == 'movewindow':
        if not args: return call('dsp.window.drag')
        return call('dsp.window.move', {'monitor': args[4:], 'follow': True} if args.startswith('mon:') else {'direction': direction})
    if name in ('movetoworkspace', 'movetoworkspacesilent'):
        values = args.split(',', 1)
        options = {'workspace': values[0], 'follow': name == 'movetoworkspace'}
        if len(values)>1: options['window'] = values[1].strip()
        return call('dsp.window.move', options)
    if name in ('movewindowpixel', 'resizewindowpixel', 'resizeactive', 'moveactive'):
        values = args.split(',', 1); position = values[0].split(); relative = position[0] != 'exact'
        if not relative: position = position[1:]
        if len(position) != 2: raise ValueError('Expected x and y for '+name)
        options = {'x': float(position[0]), 'y': float(position[1]), 'relative': relative}
        if len(values)>1: options['window'] = values[1].strip()
        return call('dsp.window.'+('resize' if name.startswith('resize') else 'move'), options)
    if name == 'tagwindow':
        values = re.split(r'[,\s]+', args, maxsplit=1)
        options = {'tag': values[0]}
        if len(values)>1: options['window'] = values[1]
        return call('dsp.window.tag', options)
    if name == 'signalwindow':
        window, signal = args.rsplit(',', 1)
        return call('dsp.window.signal', {'window': window, 'signal': int(signal)})
    if name == 'dpms':
        values = args.split(); options = {'action': {'on': 'set', 'off': 'unset', 'toggle': 'toggle'}[values[0]]}
        if len(values)>1: options['monitor'] = values[1]
        return call('dsp.dpms', options)
    raise ValueError('Invalid dispatcher for Hyprland Lua: '+name)


FLAGS = {'e': 'repeating', 'l': 'locked', 'r': 'release', 'n': 'non_consuming', 't': 'transparent',
         'i': 'ignore_mods', 'p': 'dont_inhibit', 'o': 'long_press', 'u': 'submap_universal',
         'm': 'mouse', 'c': 'click', 'g': 'drag'}


def binding(key, value):
    flags = key[4:]
    if set(flags) - set(FLAGS) - {'d'}: raise ValueError('Unsupported binding flags: '+flags)
    # Only the first fields are structural. The command can contain commas.
    fields = [v.strip() for v in value.split(',', 3 if 'd' in flags else 2)]
    mods, button = fields[:2]; remaining = fields[-1]
    options = {FLAGS[f]: True for f in flags if f in FLAGS}
    if 'd' in flags: options['description'] = fields[2]
    if 'm' in flags: name, _, args = remaining.partition(' ')
    else: name, _, args = remaining.partition(',')
    shortcut = ' + '.join([*mods.split(), button])
    return 'hl.bind('+lua(shortcut)+', '+dispatcher(name.strip(), args)+', '+lua(options)+')'


def keyword(key, value):
    if key.startswith('bind'): return binding(key, value)
    if key == 'plugin': return call('plugin.load', value)
    if key in ('env', 'envd'):
        name, value = value.split(',', 1)
        return call('env', name.strip(), value.strip(), key == 'envd')
    if key == 'monitor':
        values = parts(value); options = {'output': values[0]}
        if values[1] == 'disable': options['disabled'] = True
        else:
            if len(values)<4: raise ValueError('Monitor needs mode, position and scale')
            options.update(zip(('mode', 'position', 'scale'), values[1:4]))
            if len(values[4:]) % 2: raise ValueError('Monitor option needs a value')
            for name, data in zip(values[4::2], values[5::2]): options[name] = scalar(data)
        return call('monitor', options)
    if key == 'workspace':
        values = parts(value); options = {'workspace': values[0]}
        for item in values[1:]:
            name, data = item.split(':', 1)
            options[name] = data if name in ('monitor', 'on-created-empty') else scalar(data)
        return call('workspace_rule', options)
    if key == 'bezier':
        name, *values = parts(value)
        if len(values)!=4: raise ValueError('Bezier needs four control values')
        return call('curve', name, {'type': 'bezier', 'points': [[float(v) for v in values[:2]], [float(v) for v in values[2:]]]})
    if key == 'animation':
        values = parts(value)
        options = dict(zip(('leaf', 'enabled', 'speed', 'bezier', 'style'), values))
        options['enabled'] = bool(scalar(values[1])); options['speed'] = float(values[2])
        return call('animation', options)
    if key == 'windowrule': return call('window_rule', window_rule(rule_fields(value)))
    match = re.fullmatch(r'windowrule\[(.+)\]:(\w+)', key)
    if match: return call('window_rule', window_rule([('name', match[1]), (match[2], value)]))
    if key == 'exec-once': return 'hl.on("hyprland.start", function() '+call('exec_cmd', session_command(value))+' end)'
    if key == 'exec': return call('exec_cmd', session_command(value))
    if ':' not in key and '.' not in key: raise ValueError('Unsupported managed setting: '+key)
    return call('config', {key.replace(':', '.'): scalar(value)})


class Renderer:
    def __init__(self, root, overrides=None):
        self.root = Path(root).resolve()
        self.overrides = {Path(k).resolve(): v for k, v in (overrides or {}).items()}
        self.variables = {}; self.stack = []; self.submap = 'reset'

    def expand(self, value):
        for _ in range(20):
            updated = re.sub(r'\$(\w+)', lambda m: self.variables.get(m[1], m[0]), value)
            if updated == value: return value
            value = updated
        raise ValueError('Recursive configuration variable')

    def source_path(self, value, parent):
        prefix = '~/.config/hypr/'
        if value.startswith(prefix): return self.root/value[len(prefix):]
        path = Path(os.path.expanduser(value))
        return path if path.is_absolute() else parent/path

    def render(self, path=None):
        path = Path(path or self.root/'hyprland.conf').resolve()
        if path in self.stack: raise ValueError('Recursive source: '+str(path))
        self.stack.append(path); output, sections, block = ['-- Source: '+lua(str(path))], [], []
        text = self.overrides[path] if path in self.overrides else path.read_text()
        for number, raw in enumerate(text.splitlines(), 1):
            if raw.lstrip().startswith('#'): continue
            line = raw.replace('##', '\x00').split('#', 1)[0].replace('\x00', '#').strip()
            if not line: continue
            try:
                if re.fullmatch(r'[\w:.-]+\s*\{', line): sections.append(line[:-1].strip()); continue
                if line == '}':
                    if not sections: raise ValueError('Unmatched closing brace')
                    name = sections.pop()
                    if name in ('windowrule', 'device'):
                        output.append(call('window_rule', window_rule(block)) if name=='windowrule' else call('device', {k: scalar(v) for k,v in block}))
                        block = []
                    continue
                if '=' not in line: raise ValueError('Expected a setting assignment')
                key, value = (v.strip() for v in line.split('=', 1))
                value = self.expand(value)
                if key.startswith('$'): self.variables[key[1:]] = value; continue
                if sections and sections[0] in ('windowrule', 'device'):
                    block.append((key, value)); continue
                if key == 'source':
                    source = self.source_path(value, path.parent)
                    matches = sorted(source.parent.glob(source.name)) if any(c in source.name for c in '*?[') else [source]
                    if not matches: raise ValueError('Source not found: '+value)
                    for source in matches: output.append(self.render(source))
                elif key == 'submap':
                    if self.submap != 'reset': output.append('end)')
                    self.submap = value
                    if value != 'reset': output.append('hl.define_submap('+lua(value)+', function()')
                elif key == 'exec' and not sections:
                    # Lua executes top-level code during --verify-config too.
                    # Keep startup/reload actions out of validation entirely.
                    action = call('exec_cmd', session_command(value))
                    output.append('hl.on("hyprland.start", function() '+action+' end)')
                    output.append('hl.on("config.reloaded", function() if #hl.get_monitors() > 0 then '+action+' end end)')
                else:
                    full_key = ':'.join([*sections, key]) if sections and key not in ('animation', 'bezier') else key
                    output.append(keyword(full_key, value))
            except (ValueError, IndexError, KeyError, OSError) as error:
                raise ValueError(f'{path}:{number}: {error}') from error
        if sections: raise ValueError(f'{path}: unclosed {sections[-1]} block')
        self.stack.pop()
        if not self.stack and self.submap != 'reset': output.append('end)'); self.submap = 'reset'
        return '\n'.join(output)+'\n'


def uses_lua(binary='Hyprland'):
    result = subprocess.run([binary, '--version'], capture_output=True, text=True, timeout=10, check=True)
    match = re.search(r'Hyprland\s+(\d+)\.(\d+)', result.stdout)
    if not match: raise ValueError('Could not determine the installed Hyprland configuration format')
    return tuple(map(int, match.groups())) >= (0, 57)


def install_entry(root, binary='Hyprland'):
    """Render into a staging tree only; never change the running session."""
    root = Path(root)
    if uses_lua(binary):
        (root/'hyprland.lua').write_text((root/'compat/entry.lua').read_text())


def candidate(root, directory, main_text=None, overrides=None, modern=None):
    root, directory = Path(root), Path(directory)
    if modern is None: modern = uses_lua()
    text = main_text if main_text is not None else (root/'hyprland.conf').read_text()
    path = directory/('hyprland.lua' if modern else 'hyprland.conf')
    if modern:
        if main_text is None and not overrides and (root/'hyprland.lua').is_file():
            return root/'hyprland.lua'
        overrides = {**(overrides or {}), root/'hyprland.conf': text}
        path.write_text(Renderer(root, overrides).render())
    else:
        path.write_text(text.replace('~/.config/hypr/', str(root)+'/').replace('@HYPR@', str(root)))
    return path


def ipc(command):
    name, _, rest = command.partition(' ')
    if name == 'dispatch':
        if rest.startswith('hl.'): return command
        action, _, args = rest.partition(' ')
        return 'dispatch '+dispatcher(action, args)
    if name == 'keyword':
        key, _, value = rest.partition(' ')
        return 'eval '+keyword(key, value)
    return command


def cli(argv, native='/usr/bin/hyprctl'):
    if argv and argv[0] == 'render':
        source = Renderer(Path(argv[1])).render()
        print('-- Xetal settings rendered successfully\n'+source); return 0
    # This wrapper lives only on the PATH inherited by our Lua session.
    if '--batch' in argv:
        index = argv.index('--batch')+1
        # Socket1 splits on semicolons even inside Lua strings. Escape each
        # translated request before adding the real batch separators.
        argv[index] = ';'.join(ipc(item).replace('\\', '\\\\').replace(';', '\\;')
                               for item in parts(argv[index], ';') if item)
    else:
        index = 0
        while index < len(argv) and argv[index].startswith('-'):
            index += 2 if argv[index] in ('-i', '--instance') else 1
        if index < len(argv) and argv[index] in ('dispatch', 'keyword'):
            argv[index:] = ipc(' '.join(argv[index:])).split(' ', 1)
    result = subprocess.run([native, *argv], capture_output=True, text=True)
    print(result.stdout, end=''); print(result.stderr, end='', file=sys.stderr)
    return result.returncode or (1 if re.search(r'(^|\n)(?:error:|Error:|Invalid dispatcher)', result.stdout) else 0)


if __name__ == '__main__':
    try: sys.exit(cli(sys.argv[1:]))
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr); sys.exit(1)
