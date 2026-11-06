#!/usr/bin/env python3
"""Remember ordinary window modes/sizes, without moving existing windows at startup."""
import fcntl
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import select
import signal
import socket
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from effects.session import initialize
sys.path.insert(0, str(ROOT/'launcher'))
from floating import Hypr, valid_size, window_key, workarea


def identity(client, metadata):
    app = client.get('initialClass') or client.get('class')
    if not app: return None
    role = metadata.get('role', 'main')
    value = app.casefold() + (':picker' if is_picker(client) else ':' + ('dialog:' if metadata.get('dialog') else 'window:') + str(role))
    return hashlib.sha256(value.encode()).hexdigest()[:32]


def is_picker(client):
    return client.get('class', '').startswith('xetal-file-picker')


def eligible(client):
    return (client.get('mapped') and not client.get('hidden') and valid_size(client.get('size'))
            and client.get('workspace', {}).get('id', 0) >= 0)


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.data = {}
        if self.path.exists():
            document = json.loads(self.path.read_text())
            if document.get('version') != 1 or not isinstance(document.get('windows'), dict):
                raise ValueError('Invalid window memory file; existing state was left untouched.')
            for key, value in document['windows'].items():
                if not re.fullmatch('[a-f0-9]{32}', key) or not isinstance(value, dict):
                    raise ValueError('Invalid window memory entry')
                if not all(valid_size(value[name]) for name in ('size', 'area')):
                    raise ValueError('Invalid saved window size')
                for name in ('floating_size', 'tiled_size'):
                    if name in value and not valid_size(value[name]): raise ValueError('Invalid saved window size')
                if (type(value.get('floating')) is not bool or value.get('fullscreen') not in (0, 1, 2)
                        or value.get('client_fullscreen') not in (0, 1, 2)):
                    raise ValueError('Invalid saved window mode')
            self.data = document['windows']
        self.dirty = False

    def put(self, key, value):
        if self.data.get(key) != value:
            self.data[key] = value
            self.dirty = True

    def save(self):
        if not self.dirty: return
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, temporary = tempfile.mkstemp(prefix='.windows-', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump({'version': 1, 'windows': self.data}, stream, indent=2)
                stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            self.dirty = False
        finally:
            Path(temporary).unlink(missing_ok=True)


class Tracker:
    def __init__(self, hypr, store):
        self.hypr, self.store = hypr, store
        self.known, self.samples, self.pending = set(), {}, {}
        self.keys, self.owners = {}, set()
        self.initialized = False

    def restore(self, client, meta, saved, monitor, phase=0):
        if meta.get('workspace_layout', 'off') != 'off': return False
        address = client['address']
        # Fusion Files chooses its mode at launch: ordinary windows tile,
        # external requests use a first-map floating rule and their own size,
        # and Ctrl-click uses the launcher's exec rules. A later generic restore
        # would visibly switch modes and mix these independent workflows.
        if client.get('class') in ('xetal-files', 'xetal-files-external') and not meta.get('dialog'):
            return False
        picker = is_picker(client)
        # Fusion's chooser saves its actual size synchronously at acceptance /
        # cancellation. It is more recent than a polling sample on a quick close.
        if picker and client.get('floating') and not client.get('fullscreen') and not client.get('fullscreenClient'):
            return False
        if picker: saved = None
        # Both launcher modes are explicit first-map choices. Reapplying the
        # app's previous mode here would cause tile → float/maximize → tile
        # jumps. Still observe these windows below to preserve normal sizes.
        if window_key(client) or any(tag.removesuffix('*') == 'fusion-managed-rule' for tag in client.get('tags', [])): return False
        floating = True if picker else saved['floating'] if saved else client.get('floating', False)
        fullscreen = 0 if picker else saved['fullscreen'] if saved else client.get('fullscreen', 0)
        client_fs = 0 if picker else saved['client_fullscreen'] if saved else client.get('fullscreenClient', 0)
        if not saved and not picker: return False
        if phase == 0:
            current_fs = client.get('fullscreen', 0), client.get('fullscreenClient', 0)
            if current_fs != (0, 0):
                self.hypr.command(f'xetal-window-state {address} 0 0')
            if bool(client.get('floating')) != floating:
                self.hypr.dispatch('setfloating' if floating else 'settiled', 'address:'+address)
            # The layout target changes on the next compositor frame. Resizing
            # in the same turn can otherwise resize the old tiled target.
            return True
        # A tiled window's pixel size describes one position in a shared
        # layout, not a reusable app preference. Restoring it changes sibling
        # splits: reopening two full-area windows can crush one into a strip.
        # Also require the live target to be floating before resizing it.
        if phase == 1 and floating and client.get('floating') and monitor and not meta.get('fixed'):
            x, y, width, height = workarea(monitor)
            size = saved.get('floating_size', saved['size']) if saved else client['size']
            w, h = max(1, min(size[0], width-16)), max(1, min(size[1], height-16))
            self.hypr.dispatch('resizewindowpixel', f'exact {w} {h},address:{address}')
            left, top = client.get('at', [x, y])
            if picker: left, top = x+(width-w)//2, y+(height-h)//2
            else: left, top = min(max(left, x), x+width-w), min(max(top, y), y+height-h)
            self.hypr.dispatch('movewindowpixel', f'exact {left} {top},address:{address}')
        if phase == 2 and (fullscreen or client_fs):
            self.hypr.command(f'xetal-window-state {address} {fullscreen} {client_fs}')
        return True

    def update(self, now):
        clients = self.hypr.query('clients')
        metadata = self.hypr.query('xetal-windows')
        monitors = {m['id']: m for m in self.hypr.query('monitors')}
        current = {(c['address'], c.get('pid')) for c in clients if c.get('mapped')}
        for client in clients:
            token = client['address'], client.get('pid')
            if not eligible(client): continue
            meta = metadata.get(client['address'], {})
            if meta.get('workspace_layout', 'off') != 'off':
                # Workspace choices override remembered app modes, without
                # replacing those preferences when this window later closes.
                self.pending.pop(token, None); self.samples.pop(token, None)
                self.owners.discard(token)
                continue
            key = identity(client, meta)
            if key is None: continue
            self.keys[token] = key
            monitor = monitors.get(client.get('monitor'))
            if monitor is None: continue
            if self.initialized and token not in self.known:
                self.pending[token] = {'at': now + .2, 'phase': 0}
            if token in self.pending:
                pending = self.pending[token]
                if now < pending['at']: continue
                if pending['phase'] == 0: pending['saved'] = self.store.data.get(key)
                try:
                    restoring = self.restore(client, meta, pending['saved'], monitor, pending['phase'])
                except ValueError:
                    # A short-lived dialog can close between enumeration and an
                    # addressed dispatch. Do not stop memory for every other app.
                    self.pending.pop(token, None)
                    self.samples.pop(token, None)
                    continue
                if restoring and pending['phase'] < 2:
                    pending['phase'] += 1
                    pending['at'] = now + .2
                    continue
                self.pending.pop(token)
                self.samples[token] = (None, now + .65)
                continue
            previous, changed = self.samples.get(token, (None, now))
            if previous is None and changed > now: continue
            value = dict(self.store.data.get(key, {}))
            fullscreen = min(2, client.get('fullscreen', 0))
            client_fs = min(2, client.get('fullscreenClient', 0))
            floating = bool(client.get('floating'))
            value.update(floating=floating, fullscreen=fullscreen, client_fullscreen=client_fs,
                         size=list(client['size']), area=list(workarea(monitor)[2:]))
            if not fullscreen and not client_fs:
                value['floating_size' if floating else 'tiled_size'] = list(client['size'])
            if value != previous:
                self.samples[token] = value, now
            # The most recently focused sibling is the app's next-window default.
            siblings = [c for c in clients if eligible(c) and identity(c, metadata.get(c['address'], {})) == key]
            if min(siblings, key=lambda c: c.get('focusHistoryID', 999))['address'] == client['address']:
                self.owners.add(token)
                if value == previous and now-changed >= .45:
                    self.store.put(key, value)
            else: self.owners.discard(token)
        closed = self.known-current
        for token in closed:
            previous, _ = self.samples.get(token, (None, 0))
            if previous and token in self.owners: self.store.put(self.keys[token], previous)
            self.keys.pop(token, None)
            self.owners.discard(token)
            self.pending.pop(token, None)
            self.samples.pop(token, None)
        self.known = current
        self.initialized = True


def ensure_plugin(hypr):
    if any(plugin.get('name') == 'Xetal Window Memory' for plugin in hypr.query('plugin list')): return
    manifest = json.loads((ROOT/'runtime/manifest.json').read_text())
    if hypr.query('version').get('commit') != manifest['commit']:
        raise RuntimeError('Window memory needs the supported Hyprland runtime.')
    path = runpy.run_path(str(ROOT/'runtime/window_memory/build.py'))['build']()
    response = hypr.command('plugin load '+str(path)).strip()
    if response != 'ok': raise RuntimeError(response)


def main():
    if not os.environ.get('HYPRLAND_INSTANCE_SIGNATURE') or not os.environ.get('XDG_RUNTIME_DIR'): return 1
    instance = Path(os.environ['XDG_RUNTIME_DIR'])/'hypr'/os.environ['HYPRLAND_INSTANCE_SIGNATURE']
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, default=ROOT/'runtime/window_memory/state/windows.json')
    state = parser.parse_args().state
    with (instance/'window-memory.lock').open('a') as lock, socket.socket(socket.AF_UNIX) as events:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return 0
        events.connect(str(instance/'.socket2.sock'))
        hypr = Hypr(instance)
        def startup_cancel(*_): raise SystemExit(0)
        for number in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP): signal.signal(number, startup_cancel)
        if not initialize('window_memory', lambda: ensure_plugin(hypr), instance, threading.Event()): return 1
        tracker = Tracker(hypr, Store(state))
        stopping = False
        def stop(*_):
            nonlocal stopping
            stopping = True
        for number in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP): signal.signal(number, stop)
        last_save = last_update = 0
        try:
            while not stopping:
                if select.select([events], [], [], .2)[0] and not events.recv(65536): break
                now = time.monotonic()
                if now-last_update < .15: continue
                tracker.update(now)
                last_update = now
                if now-last_save > 2:
                    tracker.store.save(); last_save = now
        finally:
            tracker.store.save()
    return 0


if __name__ == '__main__':
    try: raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as error:
        print('Window memory: '+str(error), file=sys.stderr)
        raise SystemExit(1)
