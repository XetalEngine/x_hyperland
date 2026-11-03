#!/usr/bin/env python3
"""Focus and raise exactly the window clicked in the workspace taskbar."""
import os
from pathlib import Path
import re
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'launcher'))
from floating import Hypr, runtime


def activate(hypr, address):
    if not re.fullmatch(r'(?:0x)?[0-9a-fA-F]+', address):
        raise ValueError('Invalid window address')
    address = '0x'+address.removeprefix('0x')
    client = next((w for w in hypr.query('clients') if w['address']==address and w.get('mapped')), None)
    if not client: return
    pid = client.get('pid')
    selector = 'address:'+address
    hypr.dispatch('focuswindow', selector)
    # Minimize restores asynchronously. Wait for this same window to leave
    # its stash, then use the same ordering operation as Super+F.
    for _ in range(80):
        current = next((w for w in hypr.query('clients') if w['address']==address and w.get('pid')==pid), None)
        if not current or not current.get('mapped'): return
        if not current.get('hidden') and not current.get('workspace', {}).get('name', '').startswith('special:xetal-minimized-'):
            try:hypr.dispatch('alterzorder', 'top,'+selector)
            except ValueError as error:
                if 'Restore the minimized window first' not in str(error):raise
            else:return
        time.sleep(.025)


if __name__ == '__main__':
    try:
        if len(sys.argv)!=2:raise ValueError('A window address is required')
        activate(Hypr(runtime(os.environ)), sys.argv[1])
    except (OSError,ValueError,KeyError) as error:
        print('Activate window:', error, file=sys.stderr)
        raise SystemExit(1)
