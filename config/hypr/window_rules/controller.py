"""Validate the whole profile before atomically activating window rules."""
import fcntl
import json
import tempfile
from . import model
from effects.window_close import controller as buttons


def refresh_buttons():
    if any(p.get('name') == 'Xetal Window Close' for p in json.loads(buttons.hypr('-j', 'plugin', 'list'))):
        buttons.hypr('dispatch', 'xetalwindowclose:reload')


def save(document, expected):
    document = model.validate(document)
    buttons.instance_dir()
    with (model.ROOT/'.rules.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if model.load()[1] != expected: raise ValueError('Window rules changed elsewhere. Reload before saving.')
        content = model.render(document)
        root = model.ROOT.parent
        main = (root/'hyprland.conf').read_text()
        previous_config = model.CONFIG.read_bytes() if model.CONFIG.exists() else None
        source = 'source = ~/.config/hypr/window_rules/rules.conf'
        if main.count(source) != 1: raise ValueError('The Window Rules configuration source is missing or duplicated.')
        import sys
        sys.path.insert(0, str(root/'control_center'))
        from keys import hypr_compat
        import subprocess
        with tempfile.TemporaryDirectory(prefix='.window-rules-', dir=root) as directory:
            candidate = model.Path(directory)/'rules.conf'; candidate.write_text(content)
            check = hypr_compat.candidate(root, directory, main.replace(source, 'source = '+str(candidate)))
            result = subprocess.run(['Hyprland','--verify-config','--config',str(check)], capture_output=True, text=True, timeout=30)
            if result.returncode or 'config ok' not in result.stdout.lower()+result.stderr.lower():
                raise ValueError('Hyprland rejected these rules:\n'+(result.stdout+result.stderr)[-3000:])
        if model.load()[1] != expected: raise ValueError('Window rules changed during validation. Reload before saving.')
        if (root/'hyprland.conf').read_text() != main or (model.CONFIG.read_bytes() if model.CONFIG.exists() else None) != previous_config:
            raise ValueError('The Hyprland configuration changed during validation. Reload before saving.')
        previous = {path: path.read_bytes() if path.exists() else None for path in (model.PATH, model.CONFIG)}
        try:
            buttons.atomic(model.CONFIG, content.encode())
            buttons.atomic(model.PATH, (json.dumps(document, indent=2)+'\n').encode())
            buttons.hypr('reload')
            errors = buttons.hypr('configerrors')
            if errors: raise ValueError(errors)
            refresh_buttons()
        except Exception:
            for path, data in previous.items():
                if data is None: path.unlink(missing_ok=True)
                else: buttons.atomic(path, data)
            try:
                buttons.hypr('reload'); refresh_buttons()
            except Exception: pass
            raise
    return model.load()
