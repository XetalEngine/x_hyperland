"""Configure the popup's next map, before Wayland can display its first frame."""
import subprocess

RULE = 'fusion-quick-panel'


def prepare(request):
    # Only numeric geometry and a fixed animation choice enter compositor IPC.
    monitor = int(request['monitor'])
    width, height = int(request['width']), int(request['height'])
    x, y = int(request['relative_x']), int(request['relative_y'])
    if monitor < 0 or not (1 <= width <= 600 and 1 <= height <= 1200):
        raise ValueError('Invalid popup geometry.')
    edge = 'bottom' if request.get('edge') == 'bottom' else 'top'
    values = {'monitor': str(monitor), 'size': f'{width} {height}',
              'move': f'{x} {y}', 'animation': 'slide ' + edge}
    result = subprocess.run(['hyprctl', '--batch', ';'.join(
        f'keyword windowrule[{RULE}]:{key} {value}' for key, value in values.items())],
        capture_output=True, text=True, timeout=2)
    replies = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if result.returncode or len(replies) != len(values) or any(reply != 'ok' for reply in replies):
        raise RuntimeError('Could not prepare the taskbar popup: ' + (result.stderr or result.stdout).strip())
    return width, height
