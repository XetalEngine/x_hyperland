"""Persistent favorite groups and tile packing, independent of menu dimensions."""
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
import uuid

STATE = Path(__file__).with_name('favorite-layout.json')
MEDIUM_WIDTH, MEDIUM_HEIGHT = 142, 112
COLUMN_WIDTH = MEDIUM_WIDTH * 3
COLUMN_GAP = 24
CELL_WIDTH, CELL_HEIGHT = MEDIUM_WIDTH // 2, MEDIUM_HEIGHT // 2


def footprint(tile, cell):
    size = 1 if tile['size'] == 'small' else 2
    x, y = cell
    return {(x + dx, y + dy) for dx in range(size) for dy in range(size)}


def valid_cell(tile, cell):
    size = 1 if tile['size'] == 'small' else 2
    return (isinstance(cell, (list, tuple)) and len(cell) == 2
            and all(type(value) is int for value in cell)
            and 0 <= cell[0] <= 6 - size and 0 <= cell[1] <= 4096 - size)


def group(title='Pinned apps', column=0):
    return {'id': uuid.uuid4().hex, 'title': title, 'column': column, 'tiles': []}


def validate(data):
    if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('groups'), list):
        raise ValueError('The saved favorite layout is not supported.')
    groups, apps = set(), set()
    for item in data['groups']:
        if (not isinstance(item, dict) or not isinstance(item.get('id'), str) or not item['id']
                or item['id'] in groups or not isinstance(item.get('title'), str)
                or not item['title'].strip() or len(item['title']) > 80
                or type(item.get('column')) is not int or not 0 <= item['column'] < 64
                or not isinstance(item.get('tiles'), list)):
            raise ValueError('A saved favorite group is invalid.')
        groups.add(item['id'])
        occupied = set()
        for tile in item['tiles']:
            if (not isinstance(tile, dict) or not isinstance(tile.get('app'), str) or not tile['app']
                    or tile['app'] in apps or tile.get('size') not in ('small', 'medium')):
                raise ValueError('A saved favorite tile is invalid or duplicated.')
            apps.add(tile['app'])
            if 'cell' in tile:
                if not valid_cell(tile, tile['cell']) or occupied.intersection(footprint(tile, tile['cell'])):
                    raise ValueError('A saved tile position is invalid or overlaps another tile.')
                occupied.update(footprint(tile, tile['cell']))
    return data


def reconcile(data, favorites):
    """Keep local order; new pins join the first group, unpins disappear."""
    data = copy.deepcopy(data)
    favorites = list(dict.fromkeys(favorites))
    present = set()
    for item in data['groups']:
        item['tiles'] = [tile for tile in item['tiles'] if tile['app'] in favorites]
        present.update(tile['app'] for tile in item['tiles'])
    additions = [app for app in favorites if app not in present]
    if additions and not data['groups']:
        data['groups'].append(group())
    if additions:
        data['groups'][0]['tiles'].extend({'app': app, 'size': 'medium'} for app in additions)
    return data


def packed(tiles):
    """Keep saved cells; only automatically place tiles without a position."""
    occupied = {cell for tile in tiles if 'cell' in tile for cell in footprint(tile, tile['cell'])}
    result = []
    for tile in tiles:
        small = tile['size'] == 'small'
        if 'cell' in tile:
            x, y = tile['cell']
            size = 1 if small else 2
            result.append((tile['app'], x * CELL_WIDTH, y * CELL_HEIGHT, size * CELL_WIDTH, size * CELL_HEIGHT))
            continue
        slot = 0
        while True:
            x, y = (slot % 3) * 2, (slot // 3) * 2
            cells = [(x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1)]
            if small:
                cell = next((cell for cell in cells if cell not in occupied), None)
                if cell is not None:
                    occupied.add(cell)
                    result.append((tile['app'], cell[0] * MEDIUM_WIDTH // 2,
                                   cell[1] * MEDIUM_HEIGHT // 2, MEDIUM_WIDTH // 2, MEDIUM_HEIGHT // 2))
                    break
            elif not occupied.intersection(cells):
                occupied.update(cells)
                result.append((tile['app'], x * MEDIUM_WIDTH // 2, y * MEDIUM_HEIGHT // 2,
                               MEDIUM_WIDTH, MEDIUM_HEIGHT))
                break
            slot += 1
    return result


def freeze(item):
    positions = {app: [x // CELL_WIDTH, y // CELL_HEIGHT] for app, x, y, _, _ in packed(item['tiles'])}
    for tile in item['tiles']:
        tile['cell'] = positions[tile['app']]


def settle(item, moving, preferred=None):
    """The chosen tile keeps its cell; only overlapping tiles make room."""
    taken = footprint(moving, moving['cell'])
    displaced = []
    for tile in item['tiles']:
        if tile is moving:
            continue
        if taken.intersection(footprint(tile, tile['cell'])):
            displaced.append(tile)
        else:
            taken.update(footprint(tile, tile['cell']))
    for tile in displaced:
        tile.pop('cell')
        if preferred is not None and valid_cell(tile, preferred) and not taken.intersection(footprint(tile, preferred)):
            tile['cell'] = list(preferred)
            taken.update(footprint(tile, preferred))
    freeze(item)


def place_tile(data, app, destination, cell):
    source, tile = find_tile(data, app)
    target = find_group(data, destination)
    if not valid_cell(tile, cell):
        raise ValueError('Drop the tile inside the group grid.')
    freeze(source)
    if target is not source:
        freeze(target)
    previous = tile['cell']
    source['tiles'].remove(tile)
    target['tiles'].append(tile)
    tile['cell'] = list(cell)
    settle(target, tile, previous if source is target else None)
    target['tiles'].sort(key=lambda t: (t['cell'][1], t['cell'][0]))


def resize_tile(data, app, size):
    if size not in ('small', 'medium'):
        raise ValueError('Choose Small or Medium.')
    item, tile = find_tile(data, app)
    if tile['size'] == size:
        return
    freeze(item)
    tile['size'] = size
    tile['cell'][0] = min(tile['cell'][0], 5 if size == 'small' else 4)
    tile['cell'][1] = min(tile['cell'][1], 4095 if size == 'small' else 4094)
    settle(item, tile)


def find_group(data, ident):
    return next(item for item in data['groups'] if item['id'] == ident)


def find_tile(data, app):
    return next((item, tile) for item in data['groups'] for tile in item['tiles'] if tile['app'] == app)


def move_tile(data, app, destination, before=None):
    source, tile = find_tile(data, app)
    target = find_group(data, destination)
    if before == app:
        return
    if source is target and before is None:
        return
    if any('cell' in t for t in source['tiles']):
        freeze(source)
    if any('cell' in t for t in target['tiles']):
        freeze(target)
    source['tiles'].remove(tile)
    tile.pop('cell', None)
    index = next((i for i, existing in enumerate(target['tiles']) if existing['app'] == before), len(target['tiles']))
    target['tiles'].insert(index, tile)


def move_group(data, ident, column, before=None):
    if before == ident:
        return
    item = find_group(data, ident)
    data['groups'].remove(item)
    item['column'] = column
    index = next((i for i, existing in enumerate(data['groups']) if existing['id'] == before), len(data['groups']))
    data['groups'].insert(index, item)


def remove_group(data, ident):
    item = find_group(data, ident)
    others = [g for g in data['groups'] if g is not item]
    if item['tiles'] and not others:
        raise ValueError('Keep one group for your pinned apps, or create another group first.')
    if item['tiles']:
        for tile in item['tiles']:
            tile.pop('cell', None)
        others[0]['tiles'].extend(item['tiles'])
    data['groups'].remove(item)


class Store:
    def __init__(self, path=None):
        self.path = Path(path) if path else STATE

    def raw(self):
        try:
            return self.path.read_bytes()
        except FileNotFoundError:
            return b''

    def load(self, favorites):
        raw = self.raw()
        data = validate(json.loads(raw)) if raw else {'version': 1, 'groups': []}
        if not raw:
            # On first use, keep My Computer ahead of inherited KDE favorites.
            # A saved layout retains the user's own groups and tile positions.
            favorites = sorted(favorites, key=lambda ident: ident != 'xetal-files-computer.desktop')
        return reconcile(data, favorites), hashlib.sha256(raw).hexdigest()

    def save(self, data, expected):
        validate(data)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if hashlib.sha256(self.raw()).hexdigest() != expected:
                raise ValueError('The layout changed outside this menu. Reopen Favorites to load the latest layout.')
            content = (json.dumps(data, indent=2, ensure_ascii=False) + '\n').encode()
            fd, name = tempfile.mkstemp(prefix='.favorites-', dir=self.path.parent)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(name, self.path)
            finally:
                if os.path.exists(name):
                    os.unlink(name)
            return hashlib.sha256(content).hexdigest()
