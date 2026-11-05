#!/usr/bin/env python3
"""Play one short, allowlisted sound inside the current Hyprland session."""
import argparse
import fcntl
import os
from pathlib import Path
import re
import select
import shutil
import signal
import socket
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sounds import model


def notification_event(env):
    """Respect notification hints. Never interpret notification text as a command."""
    hints = {k.lower().replace('_', '-'): str(v).strip().lower() for k,v in env.items()}
    if hints.get('swaync-hint-suppress-sound') in ('true', '1', 'yes'): return None
    if str(env.get('SWAYNC_REPLACES_ID', '0')) not in ('', '0'): return None
    name = env.get('SWAYNC_SOUND_NAME', '').lower()
    category = env.get('SWAYNC_CATEGORY', '').lower()
    urgency = env.get('SWAYNC_URGENCY', '').lower()
    if urgency in ('critical', '2') or name in ('dialog-error', 'dialog-error-serious'): return 'error'
    if name in ('dialog-warning', 'battery-low', 'battery-caution') or category.endswith('.warning'): return 'warning'
    if name == 'dialog-question': return 'question'
    if name in ('complete', 'dialog-success') or category in ('transfer.complete', 'device.added'): return 'success'
    if name == 'dialog-information': return 'info'
    return 'notification'


def do_not_disturb():
    client = shutil.which('swaync-client')
    if not client: return False
    try:
        result = subprocess.run([client, '--get-dnd'], capture_output=True, text=True, timeout=.45)
        return result.returncode == 0 and result.stdout.strip().lower() == 'true'
    except (OSError, subprocess.SubprocessError): return False


def session_directory(env=os.environ):
    signature = env.get('HYPRLAND_INSTANCE_SIGNATURE', '')
    directory = env.get('XDG_RUNTIME_DIR', '')
    if not directory or not re.fullmatch(r'[A-Za-z0-9_.-]+', signature): return None
    instance = Path(directory) / 'hypr' / signature
    return instance if (instance / '.socket2.sock').is_socket() else None


def command(path, volume):
    if player := shutil.which('pw-play'):
        return [player, '--media-role', 'Notification', '--volume', str(volume/100), str(path)]
    if player := shutil.which('paplay'):
        return [player, '--property=media.role=event', '--volume='+str(round(65536*volume/100)), str(path)]
    raise RuntimeError('Install PipeWire audio tools or paplay to preview sounds.')


def play(event, *, preview=False, pack=None, volume=None, once=False):
    config, _ = model.load()
    instance = session_directory()
    if not instance:
        if preview: raise RuntimeError('Preview sounds from your Hyprland session.')
        return 0
    # The connection also proves that this is a live session, not a stale socket.
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as lifetime:
        lifetime.settimeout(.4); lifetime.connect(str(instance / '.socket2.sock'))
        if once:
            try: fd = os.open(instance / 'fusion-startup-sound.done', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError: return 0
            os.close(fd)
        if not preview and (not config['enabled'] or not config['events'][event]): return 0
        level = config['volume'] if volume is None else volume
        if level == 0: return 0
        if not preview and config['respect_dnd'] and do_not_disturb(): return 0
        path = model.asset(pack or config['pack'], event)
        if not path.is_file(): raise RuntimeError('This sound pack is incomplete. Reinstall the desktop sound assets.')
        args = command(path, level)
        channel = 'preview' if preview else 'session' if event in ('startup', 'shutdown') else 'alerts'
        with (instance / ('fusion-sound-'+channel+'.lock')).open('a+') as lock:
            try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: return 0
            # Repeated short alerts should not chatter as a burst finishes.
            lock.seek(0)
            try: previous = float(lock.read() or '0')
            except ValueError: previous = 0
            if channel == 'alerts' and time.monotonic()-previous < 1.1: return 0
            lock.seek(0); lock.truncate(); lock.write(str(time.monotonic())); lock.flush()
            stopped = False
            def stop(*_):
                nonlocal stopped
                stopped = True
            old = {sig: signal.signal(sig, stop) for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
            child = None
            try:
                child = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                deadline = time.monotonic()+4.8
                while not stopped and child.poll() is None and time.monotonic() < deadline:
                    readable, _, _ = select.select([lifetime], [], [], .05)
                    if readable and not lifetime.recv(65536): break
                if child.poll() is None:
                    child.terminate()
                    try: child.wait(timeout=.2)
                    except subprocess.TimeoutExpired: child.kill(); child.wait()
                if preview and child.returncode: raise RuntimeError('Audio playback was unavailable. Check your output device.')
            finally:
                if child and child.poll() is None:
                    child.kill(); child.wait()
                for sig,handler in old.items(): signal.signal(sig, handler)
    return 0


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('event', nargs='?', choices=model.EVENTS)
    parser.add_argument('--notification', action='store_true')
    parser.add_argument('--startup', action='store_true')
    parser.add_argument('--preview', action='store_true')
    parser.add_argument('--pack', choices=model.STYLES)
    parser.add_argument('--volume', type=int, choices=range(101), metavar='0–100')
    args=parser.parse_args()
    if args.notification and args.startup: parser.error('Choose one sound source.')
    event='startup' if args.startup else notification_event(os.environ) if args.notification else args.event
    if not event: return 0
    try: return play(event, preview=args.preview, pack=args.pack, volume=args.volume, once=args.startup)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        # A sound must never interrupt a notification or a session action.
        if args.preview: print(str(exc), file=sys.stderr); return 1
        return 0


if __name__=='__main__': raise SystemExit(main())
