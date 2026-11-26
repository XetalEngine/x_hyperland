"""Configure the popup's next map, before Wayland can display its first frame."""
import json
from pathlib import Path
import re
import subprocess
import sys

sys.path.append(str(Path(__file__).resolve().parents[1] / 'control_center'))
import audio_layout

RULE = 'fusion-quick-panel'


def prepare(request, *, rule=RULE):
    # Only numeric geometry and a fixed animation choice enter compositor IPC.
    if rule not in (RULE, 'fusion-clipboard-history'):
        raise ValueError('Unknown taskbar popup.')
    monitor = int(request['monitor'])
    width, height = int(request['width']), int(request['height'])
    x, y = int(request['relative_x']), int(request['relative_y'])
    max_width = audio_layout.MAX_WIDTH if rule == RULE and request.get('kind') == 'audio' else 600
    if monitor < 0 or not (1 <= width <= max_width and 1 <= height <= 1200):
        raise ValueError('Invalid popup geometry.')
    edge = 'bottom' if request.get('edge') == 'bottom' else 'top'
    values = {'monitor': str(monitor), 'size': f'{width} {height}',
              'move': f'{x} {y}', 'animation': 'slide ' + edge}
    result = subprocess.run(['hyprctl', '--batch', ';'.join(
        f'keyword windowrule[{rule}]:{key} {value}' for key, value in values.items())],
        capture_output=True, text=True, timeout=2)
    replies = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if result.returncode or len(replies) != len(values) or any(reply != 'ok' for reply in replies):
        raise RuntimeError('Could not prepare the taskbar popup: ' + (result.stderr or result.stdout).strip())
    return width, height


def resize_mapped(request, pid, cancelled):
    """Resize only this process's mapped popup, without changing focus or stacking."""
    width,height=int(request['width']),int(request['height'])
    x,y=int(request['x']),int(request['y'])
    if not 1<=width<=audio_layout.MAX_WIDTH or not 1<=height<=1200:
        raise ValueError('Invalid mixer geometry.')
    result=subprocess.run(['hyprctl','-j','clients'],capture_output=True,text=True,timeout=1)
    if result.returncode:raise RuntimeError('Could not locate the mixer window.')
    clients=json.loads(result.stdout)
    client=next((c for c in clients if c.get('pid')==pid and c.get('mapped') and
                 c.get('title')=='Hyper Fusion quick panel' and c.get('class')=='fusion-quick-panel'),None)
    if cancelled.is_set() or not client:return False
    address=client.get('address','')
    if not re.fullmatch(r'0x[0-9a-fA-F]+',address):raise ValueError('Invalid mixer address.')
    result=subprocess.run(['hyprctl','--batch',
        f'dispatch resizewindowpixel exact {width} {height},address:{address};'
        f'dispatch movewindowpixel exact {x} {y},address:{address}'],capture_output=True,text=True,timeout=1)
    replies=[line.strip() for line in result.stdout.splitlines() if line.strip()]
    if result.returncode or replies!=['ok','ok']:
        raise RuntimeError('Could not resize the mixer: '+(result.stderr or result.stdout).strip())
    return True
