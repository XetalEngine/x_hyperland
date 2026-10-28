"""Place Apps beside the taskbar before its first Wayland frame."""
import json
import os
from pathlib import Path
import shlex
import socket
import subprocess
import sys

import geometry
import bar_toggle
from floating import workarea

ROOT = Path(__file__).resolve().parents[1]


def bar_edge(path=None):
    try:
        value = json.loads((path or ROOT/'waybar/options.json').read_text())
        if value.get('version') == 1 and value.get('position') == 'bottom':
            return 'bottom'
    except (OSError, ValueError, AttributeError):
        pass
    return 'top'


def bounds(monitor, preferred, edge):
    x, y, available_width, available_height = workarea(monitor)
    width = max(1, min(preferred[0], available_width - 48))
    height = max(1, min(preferred[1], available_height - 28))
    left = x + min(24, max(0, (available_width - width) // 2))
    gap = min(14, max(0, (available_height - height) // 2))
    top = y + gap if edge == 'top' else y + available_height - gap - height
    return tuple(round(v) for v in (left - monitor['x'], top - monitor['y'], width, height))


def selected_monitor(monitors, cursor):
    # A bar click can be on an output that has no focused application.
    for monitor in monitors:
        scale = monitor.get('scale', 1) or 1
        width, height = monitor['width'], monitor['height']
        if monitor.get('transform', 0) % 2: width, height = height, width
        if (monitor['x'] <= cursor['x'] < monitor['x'] + width/scale
                and monitor['y'] <= cursor['y'] < monitor['y'] + height/scale):
            return monitor
    return next((m for m in monitors if m.get('focused')), monitors[0])


def main():
    command = ['python3', str(ROOT/'theme/run.py'), 'python3', str(ROOT/'launcher/app.py'), *sys.argv[1:]]
    if not any(arg == '--preview' or arg.startswith('--preview=') for arg in sys.argv) and os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'):
        if contact_existing(sys.argv[1:]):return 0
        if '--from-bar' in sys.argv and '--edit' not in sys.argv and bar_toggle.consume():return 0
        try:
            def query(name):
                return json.loads(subprocess.check_output(['hyprctl', '-j', name], text=True, timeout=1))
            monitor = selected_monitor(query('monitors'), query('cursorpos'))
            x, y, width, height = bounds(monitor, geometry.size(), bar_edge())
            command += ['--initial-size', str(width), str(height)]
            rules = f"[float;monitor {int(monitor['id'])};size {width} {height};move {x} {y}]"
            result = subprocess.run(['hyprctl', 'dispatch', 'exec', rules + ' ' + shlex.join(command)],
                                    capture_output=True, text=True, timeout=2)
            if result.returncode == 0 and result.stdout.strip() == 'ok': return 0
        except (OSError, ValueError, KeyError, TypeError, IndexError, subprocess.SubprocessError):
            pass
    os.execvp(command[0], command)


def contact_existing(arguments):
    """Toggle an open menu immediately, before starting Python/Qt a second time."""
    runtime=os.environ.get('XDG_RUNTIME_DIR');signature=os.environ.get('HYPRLAND_INSTANCE_SIGNATURE')
    if not runtime or not signature:return False
    edit=None
    for index,value in enumerate(arguments):
        if value=='--edit' and index+1<len(arguments):edit=arguments[index+1]
        elif value.startswith('--edit='):edit=value.partition('=')[2]
    message=(json.dumps({'edit':edit})+'\n').encode() if edit else b'toggle\n'
    try:
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as peer:
            peer.settimeout(.1);peer.connect(str(Path(runtime)/'hypr'/signature/'xetal-launcher.sock'))
            peer.sendall(message)
        bar_toggle.clear();return True
    except OSError:return False


if __name__ == '__main__': raise SystemExit(main())
