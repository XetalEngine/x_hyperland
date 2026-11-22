#!/usr/bin/env python3
"""Boot selection preferences; fixed file targets, syntax checks and undo.

Do not regenerate the menu: doing so would discard the user's entry edits.
The defaults file and a final generator also preserve preferences on the next
normal grub-mkconfig. No kernel, theme or firmware settings are changed here.
"""
from pathlib import Path
import json
import re
import shlex
import stat
import subprocess
import tempfile
import grub_editor as grub

GENERATOR = '/etc/grub.d/99_zz_hyper_fusion_boot_options'
SIGNATURE = '# Hyper Fusion boot preferences v1'
BEGIN = '### BEGIN '+GENERATOR+' ###'
END = '### END '+GENERATOR+' ###'
CALL = '    if [ "${fusion_remember}" = true ]; then savedefault; fi # Fusion remember selection'
KEYS = ('GRUB_DEFAULT', 'GRUB_SAVEDEFAULT', 'GRUB_TIMEOUT', 'GRUB_TIMEOUT_STYLE')


def defaults_values(text):
    values = {}
    for line in text.splitlines():
        match = re.fullmatch(r'\s*(?:export\s+)?(GRUB_[A-Z_]+)=(.*)', line)
        if not match or match[1] not in KEYS: continue
        try: value = shlex.split(match[2], comments=True)
        except ValueError: continue
        if len(value) == 1: values[match[1]] = value[0]
    return values


def update_defaults(text, values):
    # Do not erase another assignment/command on a shared line, or half of a
    # multiline shell value. Such custom defaults need an explicit manual edit.
    for line in text.splitlines():
        match = re.match(r'^\s*(?:export\s+)?('+'|'.join(KEYS)+r')=(.*)', line)
        if not match: continue
        lexer = shlex.shlex(match[2], posix=True, punctuation_chars=';|&()<>')
        lexer.whitespace_split = True
        try: tokens = list(lexer)
        except ValueError: raise ValueError('GRUB preferences contain a multiline value. Put each setting on its own line first.') from None
        if len(tokens) > 1:
            raise ValueError('GRUB preferences share a line with other shell commands. Put each setting on its own line first.')
    lines = [line for line in text.splitlines() if not re.match(
        r'^\s*(?:export\s+)?(?:'+ '|'.join(KEYS)+r')=', line)]
    return '\n'.join(lines).rstrip()+'\n'+ '\n'.join(k+'='+shlex.quote(str(v)) for k, v in values.items())+'\n'


def boot_choices(text):
    entries = grub.menu_entries(text)
    by_id = {e['id']: e for e in entries}
    choices = []
    for entry in entries:
        if entry['kind'] != 'menuentry' or not entry['editable']: continue
        lineage = [entry]
        while lineage[0]['parent_id']: lineage.insert(0, by_id[lineage[0]['parent_id']])
        # IDs survive title edits and reordering; use numeric paths only where
        # the original generator did not provide IDs.
        selector = '>'.join(e['menu_id'] or str(e['index_path'][-1]) for e in lineage)
        choices.append({'value': selector, 'name': ' → '.join(e['name'] for e in lineage),
                        'index': '>'.join(map(str, entry['index_path']))})
    return choices


def options_script(options):
    default = grub.quote(options['default'])
    remember = 'true' if options['remember'] else 'false'
    return f'''{SIGNATURE}
set fusion_remember={remember}
export fusion_remember
function savedefault {{
  if [ "${{fusion_remember}}" = true -a -z "${{boot_once}}" ]; then
    set saved_entry="${{chosen}}"
    if [ "${{env_block}}" ]; then
      save_env -f "${{env_block}}" saved_entry
    else
      save_env saved_entry
    fi
  fi
}}
if [ -z "${{boot_once}}" ]; then
  set default={default}
  if [ "${{fusion_remember}}" = true -a -n "${{saved_entry}}" ]; then
    set default="${{saved_entry}}"
  fi
fi
set timeout_style={options['style']}
set timeout={options['timeout']}
'''


def apply_to_menu(text, options):
    matches = list(re.finditer(r'^'+re.escape(BEGIN)+r'\n.*?^'+re.escape(END)+r'(?:\n|$)', text, re.M | re.S))
    if len(matches) > 1 or (not matches and (BEGIN in text or END in text)):
        raise ValueError('The boot preference block is damaged. Restore its backup first.')
    if matches: text = text[:matches[0].start()]+text[matches[0].end():]
    text = text.replace(CALL+'\n', '')
    if options['remember']:
        for entry in reversed(grub.menu_entries(text)):
            if entry['kind'] == 'menuentry' and entry['bootable']:
                start, end = entry['body_start'], entry['body_end']
                body = text[start:end].lstrip('\n')
                text = text[:start]+'\n'+CALL+'\n'+body+text[end:]
    return text.rstrip()+'\n\n'+BEGIN+'\n'+options_script(options)+END+'\n'


class Preferences(grub.Store):
    def __init__(self, root=Path('/'), checker=None):
        super().__init__(root, checker)
        self.state = root/'var/lib/hyper-fusion/grub-preferences'
        self.generator = root/GENERATOR.lstrip('/')
        self.defaults = root/'etc/default/grub'

    def files(self):
        return {'config': self.config, 'generator': self.generator, 'entries': self.state/'options.json',
                'defaults': self.defaults}

    def safe_paths(self):
        super().safe_paths()
        for path in (self.defaults, *self.defaults.parents):
            if path == self.root: break
            if path.is_symlink(): raise RuntimeError('The GRUB defaults path must not contain symbolic links.')
            if path.exists() and self.root == Path('/'):
                info = path.stat()
                if info.st_uid != 0 or info.st_mode & 0o022: raise RuntimeError('GRUB defaults must be writable only by root.')

    def remember_support(self):
        env = self.config.parent/'grubenv'
        try:
            data = env.read_bytes()
            if env.is_symlink() or not data.startswith(b'# GRUB Environment Block\n') or len(data) != 1024:
                raise ValueError('GRUB has no standard environment block for saving the last selection.')
            probe = grub.executable('grub-probe', 'grub2-probe')
            filesystem = grub.command([probe, '--target=fs', env]).decode().strip()
            abstraction = grub.command([probe, '--target=abstraction', env]).decode().strip()
            if abstraction: raise ValueError('Remembering the last entry is unavailable on this RAID, encrypted or LVM boot volume.')
            if filesystem == 'btrfs':
                # Recent GRUB can use a reserved Btrfs header area. Never create
                # or alter that raw disk area here; accept an existing setup.
                if not re.search(rb'(?m)^env_block=\d+\+\d+$', data) or 'load_env -f "${env_block}"' not in self.config.read_text():
                    raise ValueError('This Btrfs boot volume needs a GRUB reserved environment block before it can remember selections.')
            elif filesystem not in ('ext2', 'fat'):
                raise ValueError('Remembering the last entry has not been verified for this boot filesystem ('+filesystem+').')
            if 'load_env' not in self.config.read_text(): raise ValueError('The current GRUB menu does not load its saved environment.')
            return True, 'The last selected operating system becomes the default at the following boot.'
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            return False, str(error)

    def options_status(self):
        text = self.config.read_text(); choices = boot_choices(text)
        values = defaults_values((grub.read_optional(self.defaults) or b'').decode())
        options = {'default': values.get('GRUB_DEFAULT', '0'), 'remember': values.get('GRUB_SAVEDEFAULT') == 'true',
                   'style': values.get('GRUB_TIMEOUT_STYLE', 'menu'), 'timeout': 5}
        try: options['timeout'] = max(-1, min(3600, int(values.get('GRUB_TIMEOUT', '5'))))
        except ValueError: pass
        if options['style'] not in ('menu', 'countdown', 'hidden'): options['style'] = 'menu'
        saved = grub.read_optional(self.state/'options.json')
        if saved and BEGIN in text: options.update(json.loads(saved))
        for choice in choices:
            if options['default'] in (choice['value'], choice['index'], choice['name']):
                options['default'] = choice['value']; break
        else: options['default'] = choices[0]['value'] if choices else ''
        supported, reason = self.remember_support()
        return {'options': options, 'choices': choices, 'revision': self.revision(),
                'remember_supported': supported, 'remember_reason': reason,
                'can_undo': (self.state/'last.json').exists()}

    def save(self, request, alive=lambda: None):
        if request.get('options_revision') != self.revision() or request.get('menu_revision') != grub.digest(self.config.read_bytes()):
            raise RuntimeError('GRUB changed. Reload boot preferences before saving.')
        o = request.get('options')
        if not isinstance(o, dict) or set(o) != {'default', 'remember', 'timeout', 'style'}:
            raise ValueError('Invalid boot preferences.')
        if o['default'] not in {c['value'] for c in boot_choices(self.config.read_text())}: raise ValueError('Select an existing default entry.')
        if type(o['remember']) is not bool or type(o['timeout']) is not int or not -1 <= o['timeout'] <= 3600:
            raise ValueError('Timeout must be between -1 and 3600 seconds.')
        if o['style'] not in ('menu', 'countdown', 'hidden'): raise ValueError('Select a supported menu style.')
        if o['remember']:
            okay, reason = self.remember_support()
            if not okay: raise ValueError(reason)
        old_generator = grub.read_optional(self.generator)
        if old_generator and SIGNATURE.encode() not in old_generator: raise ValueError('Another tool owns the boot preference generator.')
        revised = apply_to_menu(self.config.read_text(), o); self.check(revised)
        targets = {k: (grub.read_optional(p), stat.S_IMODE(p.stat().st_mode) if p.exists() else 0o600)
                   for k, p in self.files().items()}
        targets['config'] = (revised.encode(), targets['config'][1])
        targets['generator'] = (('#!/bin/sh\nexec tail -n +3 "$0"\n'+options_script(o)).encode(), 0o755)
        targets['entries'] = (grub.encoded(o), 0o600)
        values = {'GRUB_DEFAULT': 'saved' if o['remember'] else o['default'], 'GRUB_SAVEDEFAULT': str(o['remember']).lower(),
                  'GRUB_TIMEOUT': str(o['timeout']), 'GRUB_TIMEOUT_STYLE': o['style']}
        updated_defaults = update_defaults((targets['defaults'][0] or b'').decode(), values).encode()
        with tempfile.NamedTemporaryFile(prefix='fusion-grub-defaults-') as script:
            script.write(updated_defaults); script.flush()
            grub.command(['/bin/sh', '-n', script.name])
        targets['defaults'] = (updated_defaults,
                               targets['defaults'][1] if self.defaults.exists() else 0o644)
        self.defaults.parent.mkdir(parents=True, exist_ok=True)
        return self.publish(targets, request['options_revision'], alive)
