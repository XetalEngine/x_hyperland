#!/usr/bin/env python3
"""Local cube faces with ordinary Hyprland fallback when its adapter is absent."""
import subprocess
import sys
import os
import re
from pathlib import Path

def cube_faces():
    runtime=os.environ.get('XDG_RUNTIME_DIR','');signature=os.environ.get('HYPRLAND_INSTANCE_SIGNATURE','')
    if not runtime or not signature or '/' in signature:return None
    try:lines=(Path(runtime)/'hypr'/signature/'xetal-cube-faces').read_text().splitlines()
    except OSError:return None
    if not lines or lines[0]!='enabled':return None
    return {int(parts[0]) for line in lines[1:] if len(parts:=line.split())>=2
            and parts[0].lstrip('-').isdigit() and parts[1].isdigit() and 1<=int(parts[1])<=10}


def cube_enabled():
    return cube_faces() is not None


def monitor_faces(workspaces, monitor):
    faces=cube_faces()
    return None if faces is None else sorted(w['id'] for w in workspaces
                                             if w['monitor']==monitor and w.get('id',0) in faces and w.get('id',0)>0)


def keep_faces(content, numbers, monitor):
    """Save session-created cube sides too, so adding a fifth survives login."""
    for number in numbers:
        pattern=rf'^\s*workspace\s*=\s*{number}\s*,([^#\n]*)'
        rules=re.findall(pattern,content,re.M)
        if rules and 'persistent:true' in rules[-1].replace(' ',''):continue
        content=content.rstrip()+f'\nworkspace = {number}, monitor:{monitor}, persistent:true\n'
    return content


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
