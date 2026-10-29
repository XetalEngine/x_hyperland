# SPDX-License-Identifier: GPL-2.0-or-later
"""Compiz switcher layout equations, adapted for independent Wayland previews.

Ring/Shift/Stack origins and original sources are recorded in compiz/NOTICE.md.
Coordinates use a 1000 × 480 stage, fitted to the actual monitor by the renderer.
No client window is moved, resized, reparented, or hidden by these layouts.
"""
from dataclasses import dataclass
import math


@dataclass
class Tile:
    index: int
    x: float
    y: float
    width: float
    height: float
    depth: float = 0.
    rotate_y: float = 0.
    rotate_x: float = 0.
    brightness: float = 1.
    opacity: float = 1.

    def polygon(self):
        ay, ax = math.radians(self.rotate_y), math.radians(self.rotate_x)
        result = []
        for x, y in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            x, y = x*self.width/2, y*self.height/2
            z = -x*math.sin(ay) + y*math.sin(ax)
            perspective = 1000/max(120., 1000-z)
            result.append((self.x+x*math.cos(ay)*perspective, self.y+y*math.cos(ax)*perspective))
        return result


def distance(index, position, count):
    """Nearest cyclic distance; continuous through first/last transitions."""
    return (index-position+count/2) % count-count/2 if count else 0.


def dimensions(client, width, height):
    size = client.get('size', [960, 600])
    if not isinstance(size, (list, tuple)) or len(size) != 2:
        size = [960, 600]
    try:
        w, h = (max(1., float(n)) for n in size)
        if not math.isfinite(w+h): w, h = 960., 600.
    except (TypeError, ValueError): w, h = 960., 600.
    factor = min(width/w, height/h)
    return w*factor, h*factor


def layout(clients, position, selected, options):
    count = len(clients)
    if not count: return []
    selected %= count
    style = options['style']; cfg = options['profiles'][style]
    tiles = []
    if style in ('fusion', 'static', 'scale'):
        columns = cfg.get('columns', min(5, max(2, math.ceil(math.sqrt(count*1.6)))))
        capacity = columns*(2 if style == 'fusion' else 3)
        start = selected//capacity*capacity
        visible = min(capacity, count-start)
        rows = math.ceil(visible/columns)
        gap = cfg.get('spacing', 16)
        cw, ch = 960/columns, 430/rows
        for offset in range(visible):
            i = start+offset; row, col = divmod(offset, columns)
            row_count = min(columns, visible-row*columns)
            w, h = (min(212, cw-16), min(180, ch-16)) if style == 'fusion' else dimensions(
                clients[i], min(cw-gap, cfg.get('thumb_width', cw)), min(ch-gap, cfg.get('thumb_height', ch)))
            tiles.append(Tile(i, 500+(col-(row_count-1)/2)*cw, 240+(row-(rows-1)/2)*ch, w, h))
    elif style == 'application':
        for i, client in enumerate(clients):
            d = distance(i, position, count)
            if abs(d) > 3.5: continue
            w, h = dimensions(client, cfg['thumb_width'], cfg['thumb_height'])
            tiles.append(Tile(i, 500+d*(cfg['thumb_width']+20), 240, w, h, -abs(d),
                              opacity=min(1., max(0., 3.5-abs(d)))))
    elif style == 'ring':
        a, b = 1000*cfg['ring_width']/200, 480*cfg['ring_height']/200
        for i, client in enumerate(clients):
            angle = distance(i, position, count)*2*math.pi/count
            # Compiz ring.c: ellipse, then linear interpolation by depth on Y.
            depth = (math.cos(angle)+1)/2
            factor = cfg['min_scale']/100+(1-cfg['min_scale']/100)*depth
            w, h = dimensions(client, cfg['thumb_width'], cfg['thumb_height'])
            tiles.append(Tile(i, 500+(-1 if cfg['clockwise'] else 1)*a*math.sin(angle),
                              220+b*math.cos(angle), w*factor, h*factor, depth,
                              brightness=cfg['min_brightness']/100+(1-cfg['min_brightness']/100)*depth))
    elif style in ('cover', 'flip'):
        thumb_w, thumb_h = 1000*cfg['size']/100, 480*cfg['size']/100
        space = thumb_w*math.cos(math.sin(math.pi/4)*math.pi/3)
        for i, client in enumerate(clients):
            d = distance(i, position, count)
            if abs(d) > 5.5: continue
            w, h = dimensions(client, thumb_w, thumb_h)
            if style == 'cover':
                pos = max(-1, min(1, d))
                if abs(d) < 1:
                    x = math.sin(pos*math.pi/2)*space
                    z = -abs(d)*thumb_w/2000
                    angle = -math.sin(pos*math.pi/2)*60
                else:
                    rad = (space/1000)/math.sin(math.pi/6)
                    ang = math.pi/max(72, count*2)*(d-pos)+pos*math.pi/6
                    x = math.sin(ang)*rad*1000
                    z = -thumb_w/2000-math.cos(math.pi/6)*rad+math.cos(ang)*rad
                    angle = (90-abs(ang)*180/math.pi)*-pos
                scale = 1/(1-z)
                # Shift's cover offset raises/lowers the baseline of the covers.
                tiles.append(Tile(i, 500+x*scale, 285-h*scale/2+cfg['cover_offset']*2,
                                  w*scale, h*scale, z, rotate_y=angle,
                                  opacity=min(1., max(0., 5.5-abs(d)))))
            else:
                # Shift Flip keeps the trailing deck visible; the front cover
                # fades as it leaves the stack, exactly as Compiz's distance > 0 path.
                d = (position-i+count-1) % count-(count-1)
                angle = math.radians(cfg['flip_rotation'])
                z = math.cos(angle)*d*thumb_w/2000
                scale = 1/(1-z) if d <= 0 else 1+min(d, 1)*.18
                opacity = max(0., 1-d) if d > 0 else min(1., max(0., 5.5+d))
                tiles.append(Tile(i, 500+math.sin(angle)*d*thumb_w/2*scale,
                                  280-h*scale/2, w*scale, h*scale, d,
                                  rotate_y=cfg['flip_rotation'], opacity=opacity))
    elif style == 'stack':
        # Aspect-aware rows and bottom-aligned, lifted selection from Stack.
        aspects = [dimensions(c, 900, 900) for c in clients]
        columns = max(1, math.ceil(math.sqrt(sum(w/h for w, h in aspects)*900/480)))
        groups, group, total = [], [], 0.
        for i, (w, h) in enumerate(aspects):
            if group and total+w/h > columns:
                groups.append(group); group, total = [], 0.
            group.append(i); total += w/h
        if group: groups.append(group)
        for row, group in enumerate(groups):
            sizes = [dimensions(clients[i], 900/len(group)-24, min(300, 900/columns)) for i in group]
            gap = (1000-sum(w for w, h in sizes))/(len(group)+1)
            x = gap; baseline = 440-row*360/max(1, len(groups))
            for i, (w, h) in zip(group, sizes):
                active = i == selected
                tilt = cfg['tilt'] if (cfg['inactive_rotate'] or active) else 0
                tiles.append(Tile(i, x+w/2, baseline-h/2-(24 if active else 0), w, h,
                                  10000 if active else baseline, rotate_x=tilt))
                x += w+gap
    return sorted((t for t in tiles if t.opacity > .005), key=lambda t: (t.depth, t.index == selected))
