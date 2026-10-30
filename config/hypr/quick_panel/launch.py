#!/usr/bin/env python3
"""Place a taskbar popup on the clicked output before its first frame."""
import argparse
import json
import os
from pathlib import Path
import shlex
import socket
import subprocess
import sys
import model

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('kind', choices=['clock', 'power']); args = parser.parse_args()
    request = {'kind': args.kind}
    try:
        query = lambda key: json.loads(subprocess.check_output(['hyprctl', '-j', key], text=True, timeout=1))
        monitor = model.monitor_at(query('monitors'), query('cursorpos'))
        options = json.loads((ROOT / 'waybar/options.json').read_text())
        if monitor: request.update(model.placement(monitor, args.kind, options.get('position', 'top')))
    except (OSError, ValueError, KeyError, subprocess.SubprocessError): pass
    signature = os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'); directory = os.environ.get('XDG_RUNTIME_DIR')
    if not signature or not directory: return 1
    address = Path(directory) / 'hypr' / signature / 'fusion-quick-panel.sock'
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
            peer.settimeout(.15); peer.connect(str(address)); peer.sendall(json.dumps(request).encode() + b'\n'); return 0
    except OSError: pass
    command = ['python3', str(ROOT / 'theme/run.py'), 'python3', str(ROOT / 'quick_panel/app.py'), '--kind', args.kind, '--request', json.dumps(request)]
    if 'monitor' in request:
        rules = f"[float;noborder;monitor {request['monitor']};size {request['width']} {request['height']};move {request['relative_x']} {request['relative_y']}]"
        result = subprocess.run(['hyprctl', 'dispatch', 'exec', rules + ' ' + shlex.join(command)], capture_output=True, text=True, timeout=2)
        if not result.returncode and result.stdout.strip() == 'ok': return 0
    os.execvp(command[0], command)


if __name__ == '__main__': raise SystemExit(main())
