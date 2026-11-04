"""Desktop icon preferences and monitor-aware layouts, independent of GTK."""
from __future__ import annotations
import copy
import fcntl
import json
import math
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def defaults():
    return dict(version=1, enabled=False, auto_align=True, auto_arrange=False,
                flow='columns', size=56, positions={})


def valid_name(name):
    return isinstance(name, str) and name not in ('', '.', '..') and '/' not in name and '\0' not in name


def validate(value):
    if not isinstance(value, dict) or value.get('version') != 1:
        raise ValueError('Invalid desktop icon settings. The existing file was kept.')
    result = defaults()
    result.update(value)
    if (type(result['enabled']) is not bool or type(result['auto_align']) is not bool
            or type(result['auto_arrange']) is not bool
            or result['flow'] not in ('columns', 'rows') or result['size'] not in (40, 56, 72)
            or not isinstance(result['positions'], dict) or len(result['positions']) > 50000):
        raise ValueError('Invalid desktop icon layout. The existing file was kept.')
    for name, position in result['positions'].items():
        if (not valid_name(name) or not isinstance(position, dict)
                or not isinstance(position.get('monitor'), str) or len(position['monitor']) > 256
                or type(position.get('order')) is not int or not 0 <= position['order'] <= 100000
                or any(type(position.get(key)) not in (float, int) or not math.isfinite(position[key])
                       or not 0 <= position[key] <= 1 for key in ('x', 'y'))):
            raise ValueError('Invalid saved desktop icon position. The existing file was kept.')
    return copy.deepcopy(result)


class Store:
    def __init__(self, path=None):
        self.path = Path(path) if path else ROOT/'desktop_menu/icons.json'

    def load(self):
        try:
            with self.path.open('rb') as stream:
                data = stream.read(8*1024*1024+1)
        except FileNotFoundError:
            return defaults()
        if len(data) > 8*1024*1024:
            raise ValueError('Desktop icon settings are too large.')
        return validate(json.loads(data))

    def change(self, update):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            current = self.load()
            before = copy.deepcopy(current)
            update(current)
            current = validate(current)
            if current == before:
                return current
            descriptor, temporary = tempfile.mkstemp(prefix='.icons-', dir=self.path.parent)
            try:
                with os.fdopen(descriptor, 'w') as stream:
                    json.dump(current, stream, ensure_ascii=True, indent=2)
                    stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
                os.replace(temporary, self.path)
            finally:
                Path(temporary).unlink(missing_ok=True)
            return current


def cell(settings):
    return settings['size']+56, settings['size']+58


def grid(area, settings, index):
    width, height = cell(settings)
    columns = max(1, int(area[2])//width)
    rows = max(1, int(area[3])//height)
    col, row = (divmod(index, rows) if settings['flow'] == 'columns'
                else (index % columns, index // columns))
    return area[0]+col*width, area[1]+row*height


def index_at(area, settings, x, y):
    width, height = cell(settings)
    col, row = max(0, int((x-area[0])//width)), max(0, int((y-area[1])//height))
    if settings['flow'] == 'columns':
        rows = max(1, int(area[3])//height)
        return col*rows+min(row, rows-1)
    columns = max(1, int(area[2])//width)
    return row*columns+min(col, columns-1)


def available(point, occupied, settings):
    width, height = cell(settings)
    return not any(abs(point[0]-p[0]) < width and abs(point[1]-p[1]) < height for p in occupied)


def first_free(area, settings, occupied):
    index = 0
    while not available(point := grid(area, settings, index), occupied, settings):
        index += 1
    return point


def snap(area, settings, point, occupied=()):
    """Nearest empty grid cell, leaving every other icon in its chosen cell."""
    width, height = cell(settings)
    columns, rows = max(1, int(area[2])//width), max(1, int(area[3])//height)
    col = min(columns-1, max(0, round((point[0]-area[0])/width)))
    row = min(rows-1, max(0, round((point[1]-area[1])/height)))
    target = (area[0]+col*width, area[1]+row*height)
    if available(target, occupied, settings): return target
    candidates = (grid(area, settings, index) for index in range(columns*rows))
    vacant = [p for p in candidates if available(p, occupied, settings)]
    return min(vacant, key=lambda p: (p[0]-target[0])**2+(p[1]-target[1])**2) if vacant else first_free(area, settings, occupied)


def layout(names, areas, settings):
    """Missing outputs fall back without discarding their saved positions."""
    result = {monitor: {} for monitor in areas}
    if not areas:
        return result
    primary = next(iter(areas))
    saved = settings['positions']
    ordered = sorted(names, key=lambda name: (saved.get(name, {}).get('order', 100001), name.casefold(), name))
    if not settings['auto_arrange']:
        # Reserve remembered cells before placing new files or icons from a
        # disconnected output. They must not displace the existing layout.
        ordered.sort(key=lambda name: saved.get(name, {}).get('monitor') not in areas)
    width, height = cell(settings)
    for name in ordered:
        position = saved.get(name, {})
        monitor = position.get('monitor', primary)
        missing = monitor not in areas
        if missing:
            monitor = primary
        area = areas[monitor]
        point = grid(area, settings, len(result[monitor]))
        if not settings['auto_arrange'] and position and not missing:
            point = (round(area[0]+position['x']*max(0, area[2]-width)),
                     round(area[1]+position['y']*max(0, area[3]-height)))
            if settings['auto_align']:
                point = snap(area, settings, point, result[monitor].values())
        elif not settings['auto_arrange']:
            point = first_free(area, settings, result[monitor].values())
        result[monitor][name] = point
    return result


def remember(settings, monitor, area, name, point, order):
    width, height = cell(settings)
    settings['positions'][name] = dict(monitor=monitor, order=order,
        x=max(0., min(1., (point[0]-area[0])/max(1, area[2]-width))),
        y=max(0., min(1., (point[1]-area[1])/max(1, area[3]-height))))


def capture(settings, names, areas, only_new=False):
    """Keep visible placement when switching modes and remember new icons."""
    for monitor, positions in layout(names, areas, settings).items():
        for index, (name, point) in enumerate(positions.items()):
            saved = settings['positions'].get(name)
            if saved and (only_new or saved['monitor'] not in areas): continue
            remember(settings, monitor, areas[monitor], name, point, index)


def move(settings, names, areas, monitor, selected, point, anchor=None):
    selected = [name for name in selected if name in names]
    if not selected or monitor not in areas:
        return
    positions = layout(names, areas, settings)
    target = positions[monitor]
    area = areas[monitor]
    if settings['auto_arrange']:
        ordered = [name for name in target if name not in selected]
        index = min(len(ordered), index_at(area, settings, *point))
        ordered[index:index] = selected
        for index, name in enumerate(ordered):
            remember(settings, monitor, area, name, grid(area, settings, index), index)
    else:
        capture(settings, names, areas)
        original = {name: pos for group in positions.values() for name, pos in group.items()}
        start = original.get(anchor or selected[0], (0, 0))
        occupied = [pos for name, pos in target.items() if name not in selected]
        if settings['auto_align']:
            point = snap(area, settings, point, occupied)
            if anchor in selected: selected = [anchor, *[name for name in selected if name != anchor]]
        order = max((p['order'] for p in settings['positions'].values()), default=-1)+1
        for index, name in enumerate(selected):
            old = original.get(name, start)
            destination = (point[0]+old[0]-start[0], point[1]+old[1]-start[1])
            if settings['auto_align']: destination = snap(area, settings, destination, occupied)
            remember(settings, monitor, area, name, destination, order+index)
            occupied.append(destination)


def align(settings, names, areas):
    capture(dict(settings, auto_align=True), names, areas)


def arrange(settings, names, areas):
    capture(dict(settings, auto_arrange=True), names, areas)
