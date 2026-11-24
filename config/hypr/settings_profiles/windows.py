"""Portable per-window overrides, matched by application, role and occurrence.

Compositor stable IDs are session-only. Never reuse one from another login.
"""
from pathlib import Path
import json
import os

from . import archive

FILE = 'effects/window_close/saved-windows.json'


def geometry(client, previous=None):
    value = dict(previous or {})
    value.update({k:client[k] for k in ('at', 'size', 'floating')})
    value.update(fullscreen=client.get('fullscreen', 0), client_fullscreen=client.get('fullscreenClient', 0))
    if client['floating'] and not value['fullscreen'] and not value['client_fullscreen']:
        value.update(normal_at=client['at'], normal_size=client['size'])
    return value


def key(client, metadata):
    return (str(client.get('initialClass') or client.get('class') or ''),
            str(metadata.get('role', 'main')), str(client.get('initialTitle') or client.get('title') or ''))


def identities(clients, metadata, assignments=None):
    assignments = assignments if assignments is not None else {}
    live = {c.get('stableId') for c in clients if c.get('mapped')}
    for ident in set(assignments) - live: assignments.pop(ident)
    # Hyprland exposes stableId in hexadecimal; the controls API uses decimal.
    for client in sorted(clients, key=lambda c: int(c.get('stableId', '0') or '0', 16)):
        if not client.get('mapped') or not client.get('stableId'): continue
        meta = metadata.get(client['address'], {})
        if meta.get('stableId') != client['stableId']: continue
        identity = key(client, meta)
        if not identity[0]: continue
        stable = client['stableId']; saved = assignments.get(stable)
        if saved and (saved['app'], saved['role'], saved['title']) == identity: match = saved
        else:
            used = {m['occurrence'] for m in assignments.values() if (m['app'],m['role'],m['title']) == identity}
            occurrence = next(n for n in range(10000) if n not in used)
            match = dict(app=identity[0], role=identity[1], title=identity[2], occurrence=occurrence)
            assignments[stable] = match
        yield client, dict(match)


def controls_id(client): return str(int(client['stableId'], 16))


def capture(hypr, instance, previous=None):
    clients = hypr.query('clients'); metadata = hypr.query('xetal-windows')
    documents = {}
    for profile, name in (('standard', 'xetal-windowbuttons-rules.json'), ('kde', 'xetal-windowbuttons-kde-rules.json')):
        path = Path(instance)/name
        documents[profile] = json.loads(path.read_text()).get('windows', {}) if path.exists() else {}
    records = []
    assignments = dict((previous or {}).get('live_matches', {})) if (previous or {}).get('session') == Path(instance).name else {}
    for client, match in identities(clients, metadata, assignments):
        ident = controls_id(client)
        rules = {p:d[ident] for p,d in documents.items() if ident in d}
        row = {'match': match, 'rules': rules}
        from window_rules.window_types import geometry_managed
        if geometry_managed(client, metadata.get(client['address'], {})):
            old = next((r for r in (previous or {}).get('windows', []) if r['match'] == match), {})
            row['geometry'] = geometry(client, old.get('geometry'))
        if rules or 'geometry' in row: records.append(row)
    return {'version': 1, 'windows': records, 'session':Path(instance).name, 'live_matches':assignments}


def validate(value):
    from effects.window_close import rules
    if not isinstance(value, dict) or value.get('version') != 1 or not isinstance(value.get('windows'), list) or len(value['windows']) > 10000:
        raise ValueError('Invalid saved individual window settings.')
    def validate_match(match):
        if not isinstance(match, dict): raise ValueError('Invalid window match.')
        if any(not isinstance(match.get(k), str) or len(match[k]) > 8192 for k in ('app', 'role', 'title')):
            raise ValueError('Invalid window match.')
        if type(match.get('occurrence')) is not int or not 0 <= match['occurrence'] < 10000: raise ValueError('Invalid window occurrence.')
    if 'live_matches' in value:
        import re
        if not isinstance(value.get('session'), str) or len(value['session']) > 512 or not isinstance(value['live_matches'], dict) or len(value['live_matches']) > 10000:
            raise ValueError('Invalid live window map.')
        for ident, match in value['live_matches'].items():
            if not isinstance(ident, str) or not re.fullmatch('[0-9a-fA-F]+', ident): raise ValueError('Invalid live window identity.')
            validate_match(match)
    for row in value['windows']:
        match = row['match']; validate_match(match)
        if not isinstance(row.get('rules'), dict) or set(row['rules']) - {'standard', 'kde'}: raise ValueError('Invalid window profile.')
        for rule in row['rules'].values(): rules.validate(rule)
        if 'geometry' in row:
            geometry = row['geometry']
            for name in ('at', 'size', *[n for n in ('normal_at', 'normal_size') if n in geometry]):
                vector = geometry.get(name)
                if not isinstance(vector, list) or len(vector) != 2 or any(type(n) is not int or not -32768 <= n <= 32768 for n in vector):
                    raise ValueError('Invalid saved window geometry.')
                if name.endswith('size') and min(vector) < 1: raise ValueError('Invalid saved window size.')
            if type(geometry.get('floating')) is not bool or any(type(geometry.get(k)) is not int or geometry[k] not in (0, 1, 2) for k in ('fullscreen', 'client_fullscreen')):
                raise ValueError('Invalid saved window mode.')
    return value


def remember(root, instance, hypr=None):
    """Keep individual choices after their windows close, ready for Save."""
    from launcher.floating import Hypr
    path = Path(root)/FILE
    previous = validate(json.loads(path.read_text())) if path.exists() else {'windows':[]}
    current = capture(hypr or Hypr(instance), instance, previous)
    if previous['windows']:
        matches = [r['match'] for r in current['windows']]
        current['windows'] += [r for r in previous['windows'] if r['match'] not in matches]
    archive.atomic(path, archive.encode(validate(current)))


class Restore:
    """One application per mapped window; later user edits take precedence."""
    def __init__(self, root, instance, hypr):
        self.root, self.instance, self.hypr = Path(root), Path(instance), hypr
        self.applied = set(); path = self.root/FILE
        self.geometry_pending = {}
        self.dirty = False
        self.assignments = {}
        self.value = validate(json.loads(path.read_text())) if path.exists() else {'windows': []}
        self.value['version'] = 1

    def update(self, clients, metadata):
        from effects.window_close import rules
        changed = False
        for client, match in identities(clients, metadata, self.assignments):
            stable = client['stableId']
            ident = controls_id(client)
            if stable in self.applied: continue
            row = next((r for r in self.value['windows'] if r['match'] == match), None)
            if row is None:
                self.applied.add(stable)
                continue
            for profile, value in row['rules'].items():
                name = 'xetal-windowbuttons-kde-rules.json' if profile == 'kde' else 'xetal-windowbuttons-rules.json'
                path = self.instance/name
                with archive.locked(self.instance/('settings-' + profile)):
                    document, _ = rules.load(path, 'windows')
                    # A rule created in this session already belongs to its user.
                    if ident not in document['windows']:
                        document['windows'][ident] = value
                        archive.atomic(path, rules.encode(document, 'windows').encode()); changed = True
            self.applied.add(stable)
            if row.get('geometry'):
                # Apply over compositor frames, just like the existing geometry
                # tracker; never resize the previous tiled target in the same IPC.
                from launcher.floating import window_key
                meta = metadata.get(client['address'], {})
                mode_allowed = (meta.get('workspace_layout', 'off') == 'off' and not window_key(client)
                                and not any(t.removesuffix('*') == 'fusion-managed-rule' for t in client.get('tags', [])))
                if mode_allowed or (client.get('floating') and not client.get('fullscreen') and not client.get('fullscreenClient')):
                    self.geometry_pending[stable] = (row['geometry'], 0, mode_allowed)
        if changed: self.hypr.dispatch('xetalwindowclose:reload', '')
        if self.geometry_pending:
            from launcher.floating import workarea
            monitors = {m['id']:m for m in self.hypr.query('monitors')}
            from window_rules.window_types import geometry_managed
            alive = {c.get('stableId') for c in clients}
            for stable in set(self.geometry_pending) - alive: self.geometry_pending.pop(stable, None)
            for client in clients:
                stable = client.get('stableId')
                if stable not in self.geometry_pending: continue
                if not geometry_managed(client, metadata.get(client['address'], {})): continue
                value, phase, mode_allowed = self.geometry_pending[stable]; address = client['address']
                if metadata.get(client['address'], {}).get('workspace_layout', 'off') == 'tile':
                    self.geometry_pending.pop(stable); continue
                if phase == 0 and mode_allowed:
                    self.hypr.command(f'xetal-window-state {address} 0 0')
                    self.hypr.dispatch('setfloating' if value['floating'] else 'settiled', 'address:' + address)
                elif phase == 1 and value['floating'] and client.get('floating'):
                    monitor = monitors.get(client.get('monitor'))
                    if monitor:
                        x, y, width, height = workarea(monitor)
                        size = value.get('normal_size', value['size']); position = value.get('normal_at', value['at'])
                        w, h = min(size[0], max(1, width-16)), min(size[1], max(1, height-16))
                        left = max(x, min(position[0], x + width-w))
                        top = max(y, min(position[1], y + height-h))
                        self.hypr.dispatch('resizewindowpixel', f'exact {w} {h},address:{address}')
                        self.hypr.dispatch('movewindowpixel', f'exact {left} {top},address:{address}')
                elif phase == 2:
                    if mode_allowed: self.hypr.command(f"xetal-window-state {address} {value['fullscreen']} {value['client_fullscreen']}")
                    self.geometry_pending.pop(stable); continue
                self.geometry_pending[stable] = value, phase + 1, mode_allowed
        # Preserve each sibling separately, including the normal rectangle
        # beneath maximization. Capture before close; the owner flushes on exit.
        from window_rules.window_types import geometry_managed
        live_rules = {}
        for profile, name in (('standard','xetal-windowbuttons-rules.json'), ('kde','xetal-windowbuttons-kde-rules.json')):
            live_rules[profile] = rules.load(self.instance/name, 'windows')[0]['windows']
        for client, match in identities(clients, metadata, self.assignments):
            if client['stableId'] in self.geometry_pending: continue
            row = next((r for r in self.value['windows'] if r['match'] == match), None)
            ident = controls_id(client)
            current = dict(match=match, rules={p:values[ident] for p,values in live_rules.items() if ident in values})
            if geometry_managed(client, metadata.get(client['address'], {})):
                current['geometry'] = geometry(client, row.get('geometry') if row else None)
            if not current['rules'] and 'geometry' not in current: continue
            if current != row:
                if row is not None: self.value['windows'].remove(row)
                self.value['windows'].append(current); self.dirty = True

    def flush(self):
        if self.dirty:
            self.value.update(session=self.instance.name, live_matches=self.assignments)
            archive.atomic(self.root/FILE, archive.encode(validate(self.value)))
            self.dirty = False
