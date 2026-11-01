#!/usr/bin/env python3
"""Keep three private UIs ready, and stop only our own children on logout."""
import fcntl
import os
from pathlib import Path
import select
import signal
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from session_logging import log_path


def alive(path):
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
            peer.settimeout(.1); peer.connect(str(path))
        return True
    except OSError: return False


def main():
    if not os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'): return 1
    instance = Path(os.environ['XDG_RUNTIME_DIR']) / 'hypr' / os.environ['HYPRLAND_INSTANCE_SIGNATURE']
    lock = (instance / 'session-ui-preload.lock').open('a')
    try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError: return 0
    stop = False
    def shutdown(*_):
        nonlocal stop
        stop = True
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP): signal.signal(sig, shutdown)
    tools = [('apps', 'xetal-launcher.sock', ROOT / 'scripts/launcher.sh'),
             ('settings', 'control-center.sock', ROOT / 'scripts/control-center.sh'),
             ('panel', '.xpanel.sock', ROOT / 'scripts/control-panel.sh')]
    children, logs, retry = {}, {}, {}
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as lifetime:
            lifetime.connect(str(instance / '.socket2.sock'))
            while not stop:
                for name, endpoint, command in tools:
                    child = children.get(name)
                    if child and child.poll() is None: continue
                    if time.monotonic() < retry.get(name, 0): continue
                    retry[name] = time.monotonic() + 5
                    if alive(instance / endpoint): continue
                    if name not in logs: logs[name] = log_path(instance, 'cached-' + name + '.log').open('a')
                    children[name] = subprocess.Popen([str(command), '--preload'], stdout=logs[name], stderr=logs[name])
                readable, _, _ = select.select([lifetime], [], [], 1)
                if readable and not lifetime.recv(65536): break
    finally:
        for child in children.values():
            if child.poll() is None: child.terminate()
        for child in children.values():
            try: child.wait(timeout=3)
            except subprocess.TimeoutExpired: child.kill(); child.wait()
        for log in logs.values(): log.close()
    return 0


if __name__ == '__main__': raise SystemExit(main())
