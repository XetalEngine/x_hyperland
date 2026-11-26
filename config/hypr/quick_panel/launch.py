#!/usr/bin/env python3
"""Place a taskbar popup on the clicked output before its first frame."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import model

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('kind', choices=list(model.PANEL_SIZES)); args = parser.parse_args()
    request = {'kind': args.kind}
    app_count = None
    if args.kind == 'audio':
        # Fit the first frame; the popup follows live app changes after mapping.
        sys.path.append(str(ROOT / 'control_center'))
        import audio_backend
        try:
            streams=json.loads(subprocess.check_output(['pactl','-f','json','list','sink-inputs'],text=True,timeout=.5,stderr=subprocess.DEVNULL))
            app_count=len(audio_backend.groups(streams,'playback'))
        except (OSError,ValueError,TypeError,KeyError,subprocess.SubprocessError): pass
    try:
        query = lambda key: json.loads(subprocess.check_output(['hyprctl', '-j', key], text=True, timeout=1))
        monitor = model.monitor_at(query('monitors'), query('cursorpos'))
        options = json.loads((ROOT / 'waybar/options.json').read_text())
        if monitor: request.update(model.placement(monitor, args.kind, options.get('position', 'top'), app_count=app_count))
    except (OSError, ValueError, KeyError, subprocess.SubprocessError): pass
    signature = os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'); directory = os.environ.get('XDG_RUNTIME_DIR')
    if not signature or not directory: return 1
    address = Path(directory) / 'hypr' / signature / 'fusion-quick-panel.sock'
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
            peer.settimeout(.15); peer.connect(str(address)); peer.sendall(json.dumps(request).encode() + b'\n'); return 0
    except OSError: pass
    command = ['python3', str(ROOT / 'theme/run.py'), 'python3', str(ROOT / 'quick_panel/app.py'), '--kind', args.kind, '--request', json.dumps(request)]
    os.execvp(command[0], command)


if __name__ == '__main__': raise SystemExit(main())
