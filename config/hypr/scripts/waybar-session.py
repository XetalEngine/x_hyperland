#!/usr/bin/env python3
"""Recover this session's taskbar without restarting the compositor or apps."""
import fcntl
import os
from pathlib import Path
import select
import signal
import socket
import subprocess
import time


def stop_child(child):
    # A click on the bar may have launched an application. Never kill a process
    # group or search for other Waybar instances: only this exact owned child.
    if child is None or child.poll() is not None:
        return
    child.terminate()
    try:
        child.wait(timeout=2)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()


def supervise(instance, command, *, interval=.25, delays=(1, 2, 4, 8, 15, 30), stable_after=30):
    """The IPC connection, not the continued existence of a socket file, owns us."""
    with (instance/'waybar-supervisor.lock').open('a') as lock, \
            socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as events:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        events.connect(str(instance/'.socket2.sock'))
        events.setblocking(False)
        stopping = False

        def stop(*_):
            nonlocal stopping
            stopping = True

        previous = {number: signal.signal(number, stop)
                    for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
        child = None
        failures = 0
        next_start = time.monotonic()
        started = next_start
        try:
            while not stopping:
                # Check for logout before spawning or respawning anything.
                if select.select([events], [], [], interval)[0]:
                    try:
                        if not events.recv(65536):
                            break
                    except BlockingIOError:
                        pass
                if stopping:
                    break
                now = time.monotonic()
                if child is not None and child.poll() is not None:
                    code = child.returncode
                    child = None
                    if now-started >= stable_after:
                        failures = 0
                    delay = delays[min(failures, len(delays)-1)]
                    failures += 1
                    next_start = now+delay
                    print(f'Waybar exited ({code}); restarting in {delay:g}s.', flush=True)
                if child is None and now >= next_start:
                    try:
                        log_path = instance/'waybar.log'
                        if log_path.exists() and log_path.stat().st_size > 5*1024*1024:
                            os.replace(log_path, instance/'waybar.log.1')
                        with log_path.open('ab') as log:
                            child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
                        started = now
                        print(f'Waybar started: {child.pid}.', flush=True)
                    except OSError as error:
                        delay = delays[min(failures, len(delays)-1)]
                        failures += 1
                        next_start = now+delay
                        print(f'Waybar could not start: {error}; retrying in {delay:g}s.', flush=True)
        except ConnectionError:
            pass
        finally:
            stop_child(child)
            for number, handler in previous.items():
                signal.signal(number, handler)
    return 0


def main():
    runtime = os.environ.get('XDG_RUNTIME_DIR')
    signature = os.environ.get('HYPRLAND_INSTANCE_SIGNATURE')
    if not runtime or not signature:
        return 1
    instance = Path(runtime)/'hypr'/signature
    root = Path(__file__).resolve().parents[1]
    try:
        return supervise(instance, ['waybar', '--config', str(root/'waybar/config.json'),
                                    '--style', str(root/'waybar/style.css')])
    except OSError as error:
        print(f'Taskbar session ended: {error}', flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
