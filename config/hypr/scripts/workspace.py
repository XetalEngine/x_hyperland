#!/usr/bin/env python3
"""Local cube faces with ordinary Hyprland fallback when its adapter is absent."""
import subprocess
import sys
import os
from pathlib import Path

def cube_enabled():
    runtime=os.environ.get('XDG_RUNTIME_DIR','');signature=os.environ.get('HYPRLAND_INSTANCE_SIGNATURE','')
    if not runtime or not signature or '/' in signature:return False
    try:return (Path(runtime)/'hypr'/signature/'xetal-cube-faces').read_text().startswith('enabled\n')
    except OSError:return False


def dispatch(action, target, run=subprocess.run):
    if action not in ('switch', 'move') or target not in tuple(map(str, range(1, 11))) + ('e+1', 'e-1'):
        raise ValueError('Unsupported workspace shortcut')
    command = ['hyprctl', 'dispatch', 'xetalcube:workspace', action+' '+target]
    result = run(command, capture_output=True, text=True)
    if result.returncode or 'Invalid dispatcher' in result.stdout or 'invalid dispatcher' in result.stdout.lower():
        # No native adapter (unsupported compositor or disabled plugin): retain
        # the exact original global workspace semantics, including 5–0.
        if 'dispatcher' not in (result.stdout+result.stderr).lower():
            raise RuntimeError(result.stderr or result.stdout)
        result = run(['hyprctl', 'dispatch', 'movetoworkspace' if action == 'move' else 'workspace', target],
                     capture_output=True, text=True)
    if result.returncode: raise RuntimeError(result.stderr or result.stdout)


if __name__ == '__main__':
    try: dispatch(*sys.argv[1:])
    except (ValueError, RuntimeError, TypeError) as error:
        print(error, file=sys.stderr); sys.exit(1)
