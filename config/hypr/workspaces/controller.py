#!/usr/bin/env python3
"""Atomic workspace changes shared by the taskbar, gear editor and compositor."""
import argparse
import fcntl
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workspaces import model
from effects.window_close import controller as buttons, model as button_settings, rules


def display_number(workspace):
    key=model.identity(workspace)
    try:
        lines=(buttons.instance_dir()/'xetal-cube-faces').read_text().splitlines()
        if lines and lines[0]=='enabled':
            for line in lines[1:]:
                fields=line.split('\t',1)[0].split()
                if len(fields)==2 and fields[0]==key and fields[1] in ('1','2','3','4'):return fields[1]
    except (OSError,RuntimeError):pass
    return key


def activate():
    plugins = json.loads(buttons.hypr('-j', 'plugin', 'list'))
    if not any(p.get('name') == 'Xetal Window Memory' for p in plugins):
        raise RuntimeError('The window behavior service is not running.')
    # Load both readers before applying layout changes, keeping failed saves reversible.
    if any(p.get('name') == 'Xetal Window Close' for p in plugins):
        answer=buttons.hypr('dispatch', 'xetalwindowclose:reload')
        if answer!='ok':raise RuntimeError(answer)
    else:
        settings, _ = button_settings.load()
        buttons.activate(settings)
    answer=buttons.hypr('dispatch', 'xetalworkspaces:reload')
    if answer!='ok':raise RuntimeError(answer)


def save(workspace, *, layout=None, controls=None, rule=None, token=None, path=None, window_id=None):
    key = model.identity(workspace); path = model.PATH if path is None else path
    if layout is not None and layout not in model.LAYOUTS: raise ValueError('Unknown workspace layout.')
    if controls is not None and controls not in model.CONTROLS: raise ValueError('Unknown workspace button mode.')
    if rule is not None: rule = rules.validate(dict(rule, mode='always'))
    buttons.instance_dir(); path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        document, current = model.load(path)
        if token is not None and token != current: raise ValueError('Workspace settings changed elsewhere. Reload before applying.')
        if window_id is not None:
            info = buttons.window_info(window_id)
            if str(info.get('workspace')) != key or info.get('workspace_controls') != 'on':
                raise ValueError('This window’s workspace settings changed. Reload before applying.')
        old = path.read_bytes() if path.exists() else None
        value = model.effective(document, key)
        if key not in document['workspaces']:
            settings, _ = button_settings.load()
            value['rule'] = dict(rules.effective(settings), mode='always')
        if layout is not None: value['layout'] = layout
        if controls is not None: value['controls'] = controls
        if rule is not None: value['rule'] = rule
        document['workspaces'][key] = value
        encoded = model.encode(document).encode()
        try:
            buttons.atomic(path, encoded); activate()
        except Exception:
            if old is None: path.unlink(missing_ok=True)
            else: buttons.atomic(path, old)
            try: activate()
            except Exception: pass
            raise
    return model.load(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--layout', choices=model.LAYOUTS)
    parser.add_argument('--controls', choices=model.CONTROLS)
    args = parser.parse_args()
    save(args.workspace, layout=args.layout, controls=args.controls)


if __name__ == '__main__':
    try: main()
    except Exception as error: print(str(error), file=sys.stderr); sys.exit(1)
