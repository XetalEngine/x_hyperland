"""The upstream XDPH picker contract, with separate preview and selection IDs."""
import re


def portal_windows(value):
    result = []
    pattern = r'(\d+)\[HC>\](.*?)\[HT>\](.*?)\[HE>\](\d+)\[HA>\]'
    seen = set()
    for handle, app, title, address in re.findall(pattern, value, re.S):
        handle, address = int(handle), int(address)
        if not 0 < handle <= 0xffffffff or handle in seen:
            continue
        seen.add(handle)
        result.append({'kind':'window', 'id':str(handle), 'address':hex(address) if address else '',
                       'app':app, 'title':title or app, 'name':title or app})
    return result


def logical_size(monitor):
    width, height = monitor['width'], monitor['height']
    if monitor.get('transform', 0) % 2:
        width, height = height, width
    return width / monitor.get('scale', 1), height / monitor.get('scale', 1)


def match_windows(sources, clients):
    """Keep the portal's own handles: compositor addresses are ONLY for previews."""
    by_address = {int(c['address'], 16):c for c in clients if c.get('mapped')}
    result = []
    for original in sources:
        source = dict(original)
        client = by_address.get(int(source['address'], 16)) if source.get('address') else None
        if client is None and not source.get('address'):
            candidates = [c for c in clients if c.get('mapped') and c.get('class') == source['app']
                          and c.get('title') == source['title']]
            if len(candidates) == 1:
                client = candidates[0]
        source['available'] = client is not None or not source.get('address')
        if client:
            source.update(address=client['address'], title=client['title'] or source['title'],
                          workspace=client.get('workspace', {}).get('name', ''), monitor=client.get('monitor'))
        result.append(source)
    return result


def selection(source, remember=False):
    kind = source['kind']
    if kind == 'window':
        ident = str(source['id'])
        if not ident.isdecimal() or not 0 < int(ident) <= 0xffffffff:
            raise ValueError('This window is no longer available.')
        target = 'window:' + ident
    elif kind in ('screen', 'region'):
        name = source['name']
        if not re.fullmatch(r'[A-Za-z0-9_.:-]+', name):
            raise ValueError('Invalid monitor name.')
        target = kind + ':' + name
        if kind == 'region':
            x, y, w, h = source['rect']
            if any(type(n) is not int for n in (x,y,w,h)) or min(x,y) < 0 or min(w,h) <= 0:
                raise ValueError('Draw a region inside one screen.')
            target += f'@{x},{y},{w},{h}'
    else:
        raise ValueError('Select a screen or window first.')
    return '[SELECTION]' + ('r' if remember else '') + '/' + target + '\n'
