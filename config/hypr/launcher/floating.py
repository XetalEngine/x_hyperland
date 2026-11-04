"""Session-owned floating placement and per-shortcut size memory."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import select
import signal
import socket
import subprocess
import sys
import tempfile
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from window_rules.model import launch_managed
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'compat'))
from hypr_compat import ipc as compatible_ipc
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from session_logging import log_path

STATE = Path(__file__).resolve().parent / 'floating-sizes.json'
TAG = re.compile(r'^xetal-(float|tile)-([0-9a-f]{24})-[0-9a-f]{12}\*?$')


def runtime(environment=None):
    env = os.environ if environment is None else environment
    return Path(env['XDG_RUNTIME_DIR']) / 'hypr' / env['HYPRLAND_INSTANCE_SIGNATURE']


def valid_size(value):
    return (isinstance(value, list) and len(value) == 2
            and all(type(n) is int and 1 <= n <= 32768 for n in value))


def valid_position(value):
    return (isinstance(value, list) and len(value) == 2
            and all(type(n) is int and -32768 <= n <= 32768 for n in value))


class Store:
    def __init__(self, path=None):
        self.path = Path(path or STATE)

    def document(self):
        if not self.path.exists():return {'version':1,'sizes':{},'positions':{}}
        data = json.loads(self.path.read_text())
        if (not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('sizes'), dict)
                or any(not re.fullmatch(r'[0-9a-f]{24}', key) or not valid_size(value)
                       for key, value in data['sizes'].items())):
            raise ValueError('Invalid floating window sizes; existing settings were left untouched.')
        if (not isinstance(data.get('positions',{}),dict)
                or any(not re.fullmatch(r'[0-9a-f]{24}',key) or not valid_position(value)
                       for key,value in data.get('positions',{}).items())):
            raise ValueError('Invalid floating window positions; existing settings were left untouched.')
        return data

    def read(self):return self.document()['sizes']

    def positions(self):return self.document().get('positions',{})

    def save(self, changes, positions=None):
        positions=positions or {}
        if not changes and not positions:return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            data=self.document();sizes=data['sizes'];places=data.get('positions',{})
            if (all(sizes.get(key) == value for key, value in changes.items())
                    and all(places.get(key)==value for key,value in positions.items())):return
            sizes.update(changes)
            places.update(positions)
            fd, name = tempfile.mkstemp(prefix='.floating-sizes-', dir=self.path.parent)
            try:
                with os.fdopen(fd, 'w') as out:
                    json.dump({'version': 1, 'sizes': sizes, 'positions':places}, out, indent=2)
                    out.write('\n'); out.flush(); os.fsync(out.fileno())
                os.replace(name, self.path)
            finally:
                if os.path.exists(name):os.unlink(name)


def window_key(client):
    for tag in client.get('tags', []):
        match = TAG.fullmatch(tag)
        if match:return match[2]


def eligible(client):
    return (client.get('mapped') and client.get('floating')
            and normalized(client.get('class', '')) != 'xetalauth'
            and not client.get('fullscreen') and not client.get('fullscreenClient')
            and valid_size(client.get('size')))


def normalized(value):
    return re.sub(r'[^a-z0-9]', '', value.casefold())


def process_stamp(pid):
    try:
        fields = Path(f'/proc/{int(pid)}/stat').read_text().rsplit(') ', 1)[1].split()
        return fields[19] if fields[0] != 'Z' else None
    except (OSError, ValueError, IndexError):return None


def descendant(pid, ancestor, proc=Path('/proc')):
    """Follow real process parents, including sudo/AppImage wrappers, without
    trusting an application's title or accidentally matching a reused PID."""
    root_pid, root_stamp = ancestor
    if not root_stamp:return False
    seen = set()
    while pid and pid not in seen and len(seen) < 64:
        seen.add(pid)
        try:
            fields = (proc / str(int(pid)) / 'stat').read_text().rsplit(') ', 1)[1].split()
            if fields[0] == 'Z':return False
            if int(pid) == root_pid:return fields[19] == root_stamp
            pid = int(fields[1])
        except (OSError, ValueError, IndexError):return False
    return False


def matches(client, request):
    if window_key(client) == request['key']:return True
    if request['terminal']:
        return (normalized(client.get('initialClass', '')) == 'kitty'
                and client.get('initialTitle') == request['name'])
    classes = {normalized(client.get(name, '')) for name in ('class', 'initialClass')}
    return bool((classes - {''}) & set(request['classes']))


def workarea(monitor):
    scale = monitor.get('scale', 1) or 1
    width, height = monitor['width'], monitor['height']
    if monitor.get('transform', 0) % 2:width, height = height, width
    left, top, right, bottom = monitor.get('reserved', [0, 0, 0, 0])
    return (monitor['x'] + left, monitor['y'] + top,
            max(1, round(width / scale) - left - right),
            max(1, round(height / scale) - top - bottom))


class Hypr:
    def __init__(self, root):self.root = root

    def command(self, command):
        if os.environ.get('XETAL_HYPRLAND_LUA') == '1':
            command = compatible_ipc(command)
        with socket.socket(socket.AF_UNIX) as stream:
            stream.settimeout(2)
            stream.connect(str(self.root / '.socket.sock'))
            stream.sendall(command.encode())
            chunks = []
            while chunk := stream.recv(65536):chunks.append(chunk)
        return b''.join(chunks).decode()

    def query(self, what):return json.loads(self.command('j/' + what))

    def dispatch(self, what, args):
        answer = self.command('dispatch ' + what + ' ' + args).strip()
        if answer != 'ok':raise ValueError(answer)


class Tracker:
    def __init__(self, hypr, store):
        self.hypr, self.store = hypr, store
        self.pending, self.samples = {}, {}
        self.positions = {}

    def prepare(self, request, now):
        clients = self.hypr.query('clients')
        saved = self.store.read().get(request['key'])
        current = sorted((c for c in clients if eligible(c) and matches(c, request)),
                         key=lambda c: c.get('focusHistoryID', 999))
        if current:
            saved = current[0]['size']
            self.store.save({request['key']: saved})
        token = uuid.uuid4().hex[:12]
        floating = request.get('floating', True)
        position = self.store.positions().get(request['key'])
        monitor = None
        if floating or current and valid_position(current[0].get('at')):
            monitors = [m for m in self.hypr.query('monitors') if 'width' in m and 'height' in m]
            monitor = next((m for m in monitors if m.get('focused')), monitors[0] if monitors else None)
            if current and valid_position(current[0].get('at')):
                old_monitor=next((m for m in monitors if m['id']==current[0].get('monitor')),None)
                if old_monitor:
                    x,y,_,_=workarea(old_monitor)
                    position=[current[0]['at'][0]-x,current[0]['at'][1]-y]
                    self.store.save({}, {request['key']:position})
            if monitor and saved:
                _,_,width,height=workarea(monitor)
                saved=[min(saved[0],max(1,width-32)),min(saved[1],max(1,height-32))]
        tag = ('xetal-float-' if floating else 'xetal-tile-') + request['key'] + '-' + token
        self.pending[token] = dict(request, tag=tag, size=saved, position=position, created=now, committed=None,
                                   existing={c['address'] for c in clients if matches(c, request)},
                                   before={c['address'] for c in clients})
        # These are first-map rules. Ordinary launches must never briefly
        # restore a maximized/floating preference before entering the layout.
        rules = ['float on' if floating else 'float off']
        if floating:
            if monitor and saved and position:
                x,y,width,height=workarea(monitor)
                dx=max(16,min(position[0],width-saved[0]-16));dy=max(16,min(position[1],height-saved[1]-16))
                rules.append(f'move {x-monitor["x"]+dx} {y-monitor["y"]+dy}')
            else:rules.append('center on')
        rules += ['tag +' + tag, 'fullscreen_state 0 0']
        if floating and saved:rules.append(f'size {saved[0]} {saved[1]}')
        if launch_managed(request.get('classes', [])):
            rules = ['tag +' + tag]
        return {'token': token, 'rules': '; '.join(rules)}

    def finish(self, token, success, now):
        if token not in self.pending:return
        if success:self.pending[token]['committed'] = now
        else:self.pending.pop(token)

    def started(self, token, pid):
        if token in self.pending:
            self.pending[token]['process'] = (pid, process_stamp(pid))

    def place_reused(self, client, request):
        if any(tag.removesuffix('*') == 'fusion-managed-rule' for tag in client.get('tags', [])):
            self.tag(client, request); return
        address = 'address:' + client['address']
        if client.get('fullscreen') or client.get('fullscreenClient'):
            answer=self.hypr.command(f"xetal-window-state {client['address']} 0 0").strip()
            if answer != 'ok':raise ValueError(answer)
        if not request.get('floating', True):
            self.hypr.dispatch('settiled', address)
            self.tag(client, request)
            return
        self.hypr.dispatch('setfloating', address)
        current = next((c for c in self.hypr.query('clients') if c['address'] == client['address']), None)
        if not current:return
        if not current.get('floating'):
            # A forced-tiled workspace may refuse the floating request. Never
            # resize its shared layout as though this were a floating window.
            self.tag(current, request)
            return
        if request['size']:
            width, height = request['size']
            self.hypr.dispatch('resizewindowpixel', f'exact {width} {height},' + address)
        # Read the resulting size: toggling from tiled restores Hyprland's
        # natural floating geometry when we have no saved floating size yet.
        current = next((c for c in self.hypr.query('clients') if c['address'] == client['address']), None)
        if not current:return
        monitor = next((m for m in self.hypr.query('monitors') if m['id'] == current['monitor']), None)
        if monitor:
            x, y, width, height = workarea(monitor)
            w, h = current['size']
            w,h=min(w,max(1,width-32)),min(h,max(1,height-32))
            if [w,h]!=current['size']:self.hypr.dispatch('resizewindowpixel',f'exact {w} {h},'+address)
            dx,dy=request.get('position') or [round((width-w)/2),round((height-h)/2)]
            self.hypr.dispatch('movewindowpixel', f'exact {x+max(16,min(dx,width-w-16))} {y+max(16,min(dy,height-h-16))},' + address)
        self.tag(current, request)

    def tag(self, client, request):
        address = 'address:' + client['address']
        for tag in client.get('tags', []):
            if TAG.fullmatch(tag):self.hypr.dispatch('tagwindow', '-' + tag.removesuffix('*') + ' ' + address)
        self.hypr.dispatch('tagwindow', '+' + request['tag'] + ' ' + address)

    def update(self, clients, now):
        for token, request in list(self.pending.items()):
            if any(request['tag'] in [tag.removesuffix('*') for tag in c.get('tags', [])]
                   and normalized(c.get('class', '')) != 'xetalauth' for c in clients):
                del self.pending[token]
                continue
            if now - request['created'] > 120:
                del self.pending[token]
                continue
            if request['committed'] is None or now - request['committed'] < 1:continue
            launched = request.get('process')
            # Hyprland's exec rules can lose the app after an elevation or
            # wrapper boundary. Claim only a newly mapped window descended
            # from this exact launch; never guess by class or current focus.
            largest_first = sorted(clients, key=lambda c: c.get('size', [0, 0])[0] * c.get('size', [0, 0])[1], reverse=True)
            child = next((c for c in largest_first if c['address'] not in request['before']
                          and normalized(c.get('class', '')) != 'xetalauth'
                          and c.get('mapped') and not c.get('fullscreen') and not c.get('fullscreenClient')
                          and launched and descendant(c.get('pid', 0), launched)), None)
            if child:
                self.place_reused(child, request)
                del self.pending[token]
                continue
            if not launched or not launched[1] or process_stamp(launched[0]) == launched[1]:continue
            # An app may activate its existing window instead of making one.
            # Wait for the new invocation to exit; a slow new window must not
            # cause us to change a different instance which is already open.
            active = next((c for c in clients if c.get('focusHistoryID') == 0
                           and c['address'] in request['existing'] and c.get('mapped')
                           and not c.get('fullscreen') and not c.get('fullscreenClient')), None)
            if active:
                self.place_reused(active, request)
                del self.pending[token]

        changes, positions, present, settled = {}, {}, set(), []
        monitors = None
        # If several windows settle together, the most recently focused wins.
        for client in sorted(clients, key=lambda c: c.get('focusHistoryID', 999), reverse=True):
            key, address = window_key(client), client['address']
            if not key or not eligible(client):continue
            present.add(address)
            size = client['size'][:]
            place=None
            if valid_position(client.get('at')):
                if monitors is None:monitors={m['id']:m for m in self.hypr.query('monitors')}
                if monitor:=monitors.get(client.get('monitor')):
                    x,y,_,_=workarea(monitor)
                    place=[client['at'][0]-x,client['at'][1]-y]
            previous = self.samples.get(address)
            if previous is None or previous[0] != size or self.positions.get(address)!=place:
                self.samples[address] = (size, now, False, key)
                self.positions[address]=place
            elif not previous[2] and now - previous[1] >= .5:
                changes[key] = size
                if place is not None:positions[key]=place
                settled.append(address)
        for address, sample in self.samples.items():
            # A quick tile/maximize is just as final as closing the normal
            # rectangle. Save its last floating sample before dropping it.
            if address not in present and not sample[2]:
                changes.setdefault(sample[3], sample[0])
                if self.positions.get(address) is not None:positions.setdefault(sample[3],self.positions[address])
        self.store.save(changes,positions)
        for address in settled:
            size, since, _, key = self.samples[address]
            self.samples[address] = (size, since, True, key)
        self.samples = {address: sample for address, sample in self.samples.items() if address in present}
        self.positions = {address:position for address,position in self.positions.items() if address in present}


def exchange(root, payload):
    with socket.socket(socket.AF_UNIX) as stream:
        stream.settimeout(3)
        stream.connect(str(root / 'floating-geometry.sock'))
        stream.sendall(json.dumps(payload).encode() + b'\n')
        with stream.makefile('rb') as reader:reply = json.loads(reader.readline(65536))
    if 'error' in reply:raise ValueError(reply['error'])
    return reply


def prepare(entry, terminal, environment, *, floating=True):
    root = runtime(environment)
    identity = entry.get_id() + ('\0terminal' if terminal else '\0application')
    classes = [entry.origin.removesuffix('.desktop'), Path(entry.argv()[0]).name]
    if entry.base:
        wm_class = entry.base.get_startup_wm_class()
        if wm_class:classes.append(wm_class)
    request = {'action': 'prepare', 'key': hashlib.sha256(identity.encode()).hexdigest()[:24],
               'classes': [normalized(value) for value in classes], 'terminal': bool(terminal),
               'name': entry.get_display_name(), 'floating': bool(floating)}
    try:return exchange(root, request)
    except (FileNotFoundError, ConnectionRefusedError):pass
    destination = log_path(root, 'floating-geometry.log')
    with destination.open('a') as log:
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--watch'], env=environment,
                         stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        try:return exchange(root, request)
        except (FileNotFoundError, ConnectionRefusedError):time.sleep(.03)
    raise ValueError('Floating window size memory could not start.' +
                     (' File logging is disabled.' if destination == Path(os.devnull) else ' Check floating-geometry.log.'))


def finish(ticket, success, environment):
    exchange(runtime(environment), {'action': 'finish', 'token': ticket['token'], 'success': success})


def watch(root, store):
    with (root / 'floating-geometry.lock').open('a') as lock:
        try:fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:return
        endpoint = root / 'floating-geometry.sock'
        with socket.socket(socket.AF_UNIX) as events, socket.socket(socket.AF_UNIX) as server:
            events.connect(str(root / '.socket2.sock'))
            endpoint.unlink(missing_ok=True)
            server.bind(str(endpoint)); endpoint.chmod(0o600); server.listen(8)
            tracker = Tracker(Hypr(root), store)
            try:
                while True:
                    readable, _, _ = select.select([events, server], [], [], .25)
                    if events in readable and not events.recv(65536):return
                    if server in readable:
                        connection, _ = server.accept()
                        with connection:
                            connection.settimeout(2)
                            try:
                                with connection.makefile('rb') as reader:request = json.loads(reader.readline(65536))
                                now = time.monotonic()
                                if request['action'] == 'prepare':reply = tracker.prepare(request, now)
                                elif request['action'] == 'finish':
                                    tracker.finish(request['token'], request['success'], now);reply = {'ok': True}
                                elif request['action'] == 'started':
                                    tracker.started(request['token'], request['pid']);reply = {'ok': True}
                                else:raise ValueError('Unknown floating window request.')
                            except Exception as error:reply = {'error': str(error)}
                            try:connection.sendall(json.dumps(reply).encode() + b'\n')
                            except (BrokenPipeError, ConnectionResetError):pass
                    if readable or tracker.pending or tracker.samples:
                        try:tracker.update(tracker.hypr.query('clients'), time.monotonic())
                        except (OSError, ValueError) as error:print('Floating size memory:', error, flush=True)
            finally:endpoint.unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser();parser.add_argument('--watch', action='store_true')
    parser.add_argument('--state', type=Path);parser.add_argument('--exec-token')
    parser.add_argument('command', nargs=argparse.REMAINDER);args = parser.parse_args()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    if args.watch:watch(runtime(), Store(args.state))
    elif args.exec_token:
        command = args.command[1:] if args.command[:1] == ['--'] else args.command
        if not command:parser.error('A program to launch is required.')
        try:exchange(runtime(), {'action': 'started', 'token': args.exec_token, 'pid': os.getpid()})
        except (OSError, ValueError) as error:print('Floating size memory:', error, file=sys.stderr)
        os.execvpe(command[0], command, os.environ)
