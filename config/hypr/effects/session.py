"""Start native effects reliably, with ownership limited to one compositor login."""
import fcntl
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time

DELAYS = (0, 1, 2, 4, 8, 15, 30)


def instance_path():
    runtime = os.environ.get('XDG_RUNTIME_DIR', '')
    signature = os.environ.get('HYPRLAND_INSTANCE_SIGNATURE', '')
    if not runtime or not signature or Path(signature).name != signature or signature in ('.', '..'):
        raise RuntimeError('Open these controls inside the Hyprland session.')
    return Path(runtime)/'hypr'/signature


def record(instance, name, state, attempt, error='', previous=''):
    """One small current-status file; never grow an unattended failure log."""
    data = dict(state=state, attempt=attempt, error=str(error)[-4000:],
                previous_error=str(previous)[-4000:], updated=time.time())
    temporary = None
    try:
        fd, temporary = tempfile.mkstemp(prefix='.plugin-startup-', dir=instance)
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream); stream.write('\n')
        os.replace(temporary, instance/('plugin-startup-'+name+'.json'))
    except OSError:
        pass  # A full runtime directory must not prevent the effect starting.
    finally:
        if temporary:
            try: Path(temporary).unlink(missing_ok=True)
            except OSError: pass


def python_executable():
    # sys.executable can be empty when Python cannot resolve argv[0] in the
    # display manager's environment. Setup verifies the system interpreter.
    for candidate in (sys.executable, '/usr/bin/python3'):
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise RuntimeError('The dock icon helper needs /usr/bin/python3. Run Setup to repair Python dependencies.')


def ready():
    # IPC can exist before an output/renderer is ready on the first login.
    result = subprocess.run(['hyprctl', '-j', 'monitors'], capture_output=True,
                            text=True, timeout=10)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or 'Hyprland IPC is not ready.')
    monitors = json.loads(result.stdout)
    if not isinstance(monitors, list) or not any(isinstance(m, dict) and m.get('width', 0) > 0 and m.get('height', 0) > 0 for m in monitors):
        raise RuntimeError('Waiting for a connected monitor and the compositor renderer.')


def initialize(name, start, instance, stopped, *, delays=DELAYS, probe=ready):
    """Serialize cold-start builds/loads and retry transient login failures."""
    previous = ''
    for attempt, delay in enumerate(delays, 1):
        if stopped.wait(delay): return False
        record(instance, name, 'starting', attempt, previous, previous)
        try:
            # Loading shaders and building adapters in parallel can overwhelm a
            # fresh VM and make another loader's short IPC deadline expire.
            with (instance/'plugin-startup.lock').open('a') as lock:
                while True:
                    try:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        if stopped.wait(.1): return False
                if stopped.is_set(): return False
                probe()
                start()
            record(instance, name, 'ready', attempt, previous=previous)
            if previous: print(f'{name}: startup recovered on attempt {attempt}.', flush=True)
            return True
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            previous = str(error)
            final = attempt == len(delays)
            record(instance, name, 'failed' if final else 'retrying', attempt, previous)
            print(f'{name}: {previous}\n'+('Run fusion-check for details.' if final else 'Retrying startup…'),
                  file=sys.stderr, flush=True)
    return False


def connect_events(instance, stopped, *, delays=DELAYS):
    previous = None
    for delay in delays:
        if stopped.wait(delay): return None
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            connection.settimeout(2)
            connection.connect(str(instance/'.socket2.sock'))
            connection.settimeout(None)
            return connection
        except OSError as error:
            connection.close(); previous = error
    raise RuntimeError('Could not connect to Hyprland startup events: '+str(previous))


def run(name, start, *, auxiliary=None):
    instance = instance_path()
    stopped = threading.Event()
    connection = child = watcher = child_watcher = None
    previous_handlers = {}
    def stop(*_):
        stopped.set()
        # Native builders catch SystemExit and stop only their own compiler.
        raise SystemExit(0)
    for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        previous_handlers[number] = signal.signal(number, stop)
    try:
        # A second launcher must not create duplicate icon workers or retries.
        with (instance/('plugin-session-'+name+'.lock')).open('a') as lock:
            try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: return
            record(instance, name, 'waiting', 0)
            connection = connect_events(instance, stopped)
            if connection is None: return
            def watch():
                try:
                    while connection.recv(65536): pass
                except OSError: pass
                finally:
                    if not stopped.is_set():
                        stopped.set()
                        os.kill(os.getpid(), signal.SIGTERM)
            watcher = threading.Thread(target=watch, daemon=True); watcher.start()
            if initialize(name, start, instance, stopped) and auxiliary and not stopped.is_set():
                # Decorations must never prevent the native minimize handler
                # from loading. Report icon-worker failure separately.
                helper_name = name+'-icons'
                try:
                    child = subprocess.Popen([python_executable(), str(auxiliary)],
                                             env=dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_QPA_PLATFORMTHEME=''))
                except (OSError, RuntimeError) as error:
                    record(instance, helper_name, 'failed', 1, error)
                    print(f'{helper_name}: {error}\nRun fusion-check for details.', file=sys.stderr, flush=True)
                else:
                    record(instance, helper_name, 'ready', 1)
                    def watch_child():
                        code = child.wait()
                        if not stopped.is_set():
                            message = f'Dock icon helper exited with status {code}; minimizing remains available.'
                            record(instance, helper_name, 'failed', 1, message)
                            print(message, file=sys.stderr, flush=True)
                    child_watcher = threading.Thread(target=watch_child, daemon=True); child_watcher.start()
            watcher.join()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        record(instance, name, 'failed', 0, error)
        raise
    finally:
        stopped.set()
        if child and child.poll() is None:
            child.terminate()
            try: child.wait(timeout=3)
            except subprocess.TimeoutExpired: child.kill(); child.wait()
        if connection:
            try: connection.shutdown(socket.SHUT_RDWR)
            except OSError: pass
            connection.close()
        if watcher: watcher.join(timeout=3)
        if child_watcher: child_watcher.join(timeout=3)
        for number, handler in previous_handlers.items(): signal.signal(number, handler)
