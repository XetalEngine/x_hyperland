"""Software previews of the materials in native/dock_shader.hpp.

Keep the silhouettes and ornaments aligned with the compositor materials. Qt
painting also works without an OpenGL context (including VM settings windows).
"""
import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient


def alpha(color, amount):
    value = QColor(color); value.setAlphaF(max(0., min(1., amount))); return value


def blend(a, b, amount):
    a, b = QColor(a), QColor(b)
    return QColor.fromRgbF(*(a.getRgbF()[i]*(1-amount)+b.getRgbF()[i]*amount for i in range(3)))


def line(painter, x1, y1, x2, y2):
    painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))


def blue_vault(p, width, colors, phase):
    """Silver end caps and a dark glass bay, mirrored by native style 11."""
    from hyperfusionblue import paint_surface
    box=QRectF(8,8,width-16,80);paint_surface(p,box,colors,12,100)
    p.save();p.setRenderHint(QPainter.RenderHint.Antialiasing)
    accent=QColor(colors['Accent']);silver=QColor(colors['Light'])
    for x in (10,width-26):
        cap=QLinearGradient(x,10,x+16,86)
        cap.setColorAt(0,silver);cap.setColorAt(.16,QColor(colors['Button']));cap.setColorAt(.52,QColor(colors['Base']));cap.setColorAt(1,silver)
        p.setBrush(cap);p.setPen(QPen(silver,.7));p.drawRoundedRect(QRectF(x,11,16,74),5,5)
        for y in (18,78):
            p.setBrush(QColor(colors['Base']));p.drawEllipse(QPointF(x+8,y),1.6,1.6)
        p.setPen(QPen(accent,2));line(p,x+8,34,x+8,62)
    p.setPen(QPen(alpha(silver,.7),1));line(p,29,12,width-29,12)
    p.setPen(QPen(accent,2));line(p,29,83,width-29,83)
    shine=QLinearGradient(26,0,width-26,0)
    shine.setColorAt(0,alpha(accent,0));shine.setColorAt(.5+.3*math.sin(phase*.45),alpha(silver,.7));shine.setColorAt(1,alpha(accent,0))
    p.setPen(QPen(shine,1.5));line(p,29,15,width-29,15)
    p.restore()


def platform_twelve(p,width,colors,phase):
    """An enamel station platform, cream rails and paired signal lanterns."""
    from midnighttransit import paint_surface
    paint_surface(p,QRectF(8,8,width-16,80),colors,9,100)
    p.save();cream=QColor(colors['Light']);accent=QColor(colors['Accent'])
    p.setPen(QPen(cream,1.4))
    for y in (16,80):line(p,31,y,width-31,y)
    p.setPen(QPen(alpha(cream,.35),.8))
    for x in range(35,int(width-30),11):line(p,x,80,x+2,84)
    for x in (21,width-21):
        p.setBrush(QColor(colors['Base']));p.setPen(QPen(cream,1))
        p.drawRoundedRect(QRectF(x-7,24,14,48),7,7)
        for y in (34,61):
            p.setBrush(alpha(accent,.75+.2*math.sin(phase*.6)));p.drawEllipse(QPointF(x,y),3,3)
        p.setPen(QPen(cream,.8));line(p,x-3,46,x+3,46);line(p,x-3,50,x+3,50)
    p.restore()


def harbour_cabinet(p,width,colors,phase):
    """Walnut drawer cabinet with brass straps, corner screws and sage inlay."""
    from blackwood import paint_surface
    paint_surface(p,QRectF(8,8,width-16,80),colors,5,100)
    p.save();brass=QColor(colors['Light']);accent=QColor(colors['Accent'])
    for x in (9,width-23):
        metal=QLinearGradient(0,9,0,87);metal.setColorAt(0,alpha(brass,.6));metal.setColorAt(.5,alpha(brass,.18));metal.setColorAt(1,alpha(brass,.42))
        p.setPen(QPen(brass,.7));p.setBrush(metal);p.drawRoundedRect(QRectF(x,10,14,76),2,2)
        for y in (18,78):
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(brass);p.drawEllipse(QPointF(x+7,y),2,2)
            p.setPen(QPen(QColor(colors['Base']),.7));line(p,x+5.8,y,x+8.2,y)
        gem=QPainterPath();gem.moveTo(x+7,43);gem.lineTo(x+11,48);gem.lineTo(x+7,53);gem.lineTo(x+3,48);gem.closeSubpath()
        p.fillPath(gem,accent)
    p.setPen(QPen(alpha(brass,.8),.8))
    for y in (11,85):line(p,25,y,width-25,y)
    p.setPen(QPen(alpha(accent,.3),1));line(p,29,81,width-29,81)
    p.restore()


def containment_bay(p, width, colors, phase):
    """Riveted instrument rack, vented end caps and a phosphor conduit."""
    from atomicafterglow import paint_surface
    paint_surface(p,QRectF(8,8,width-16,80),colors,5,100)
    p.save(); brass=QColor(colors['Light']); accent=QColor(colors['Accent'])
    for x in (11,width-27):
        cap=QRectF(x,12,16,72)
        p.setBrush(QColor(colors['Button']));p.setPen(QPen(brass,.7));p.drawRoundedRect(cap,2,2)
        for y in range(30,68,5):
            p.setPen(QPen(QColor(colors['Base']),2));line(p,x+4,y,x+12,y)
        for y in (19,77):
            p.setBrush(brass);p.setPen(Qt.PenStyle.NoPen);p.drawEllipse(QPointF(x+8,y),2,2)
            p.setPen(QPen(QColor(colors['Base']),.7));line(p,x+7,y,x+9,y)
        p.setPen(QPen(accent,2))
        for dx in (2,7,12):line(p,x+dx,26,x+dx+3,22)
    p.setPen(QPen(alpha(brass,.65),1));line(p,31,15,width-31,15)
    p.setPen(QPen(alpha(accent,.3),4));line(p,31,81,width-31,81)
    p.setPen(QPen(alpha(accent,.9),1.5));line(p,31,81,width-31,81)
    for x in range(38,int(width-31),13):
        p.setPen(QPen(alpha(accent,.5+.3*math.sin(phase+x*.025)),1))
        line(p,x,84,x+4,84)
    p.restore()


def spore_cradle(p,width,colors,phase):
    """Plum cradle, branching ivory roots and paired mushroom lanterns (ID 15)."""
    from mycelium import paint_surface,mushroom
    paint_surface(p,QRectF(8,8,width-16,80),colors,20,100)
    p.save();accent=QColor(colors['Accent']);ivory=QColor(colors['Light'])
    for x in (23,width-23):
        halo=QRadialGradient(QPointF(x,48),23)
        halo.setColorAt(0,alpha(accent,.22+.04*math.sin(phase*.6)));halo.setColorAt(1,alpha(accent,0))
        p.setBrush(halo);p.setPen(Qt.PenStyle.NoPen);p.drawEllipse(QPointF(x,48),22,29)
        mushroom(p,x,43,.64,accent,ivory)
    p.setBrush(Qt.BrushStyle.NoBrush)
    for offset,opacity in ((0,.55),(4,.22)):
        root=QPainterPath();root.moveTo(35,81-offset)
        root.cubicTo(width*.32,73-offset,width*.67,86-offset,width-35,79-offset)
        p.setPen(QPen(alpha(ivory,opacity),.8));p.drawPath(root)
    for x in range(42,int(width-35),23):
        p.setPen(QPen(alpha(ivory,.4),.6));line(p,x,80,x+7,74);line(p,x+4,76,x+3,72)
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(alpha(accent,.6+.2*math.sin(phase*.6+x*.07)))
        p.drawEllipse(QPointF(x,83),1.3,1.3)
    p.restore()


def parcel_bevel(p,box,colors,inset=False):
    light=blend(colors['Window'],'#ffffff',.65);dark=blend(colors['Window'],'#000000',.7)
    if inset:light,dark=dark,light
    p.setPen(QPen(light,2));p.drawLine(box.bottomLeft(),box.topLeft());p.drawLine(box.topLeft(),box.topRight())
    p.setPen(QPen(dark,2));p.drawLine(box.topRight(),box.bottomRight());p.drawLine(box.bottomRight(),box.bottomLeft())


def parcel_shelf(p,width,colors,phase):
    """Raised ivory/espresso casework and brass handles, mirrored by native ID 16."""
    p.save();box=QRectF(8,8,width-16,80)
    p.fillRect(box,QColor(colors['Window']))
    for x in (9,width-26):
        p.fillRect(QRectF(x,9,17,78),blend(colors['Window'],colors['Accent'],.18))
        p.setPen(QPen(blend(colors['Window'],colors['WindowText'],.45),1.5));p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(x+5.5,31,7,34),1,1)
    p.setPen(QPen(alpha(colors['Accent'],.6),1.5));line(p,31,82,width-31,82)
    p.setPen(QPen(alpha(colors['WindowText'],.18),1));line(p,31,13,width-31,13)
    parcel_bevel(p,box.adjusted(1,1,-1,-1),colors);p.restore()


def neon_pit_lane(p,width,colors,phase):
    """Lacquer, twin neon rails and light fins, mirrored by native ID 17."""
    p.save();box=QRectF(8,8,width-16,80)
    accent=QColor(colors['Accent']);ink=QColor(colors['WindowText'])
    pink=QColor.fromRgbF(accent.blueF(),accent.redF(),accent.greenF())
    surface=QLinearGradient(box.topLeft(),box.bottomLeft())
    surface.setColorAt(0,blend(colors['Window'],ink,.10));surface.setColorAt(1,blend(colors['Window'],accent,.04))
    p.setBrush(surface);p.setPen(QPen(alpha(accent,.42),1));p.drawRoundedRect(box,7,7)
    p.setPen(QPen(alpha(accent,.8),1.4));line(p,31,14,width-31,14)
    p.setPen(QPen(alpha(pink,.8),1.4));line(p,31,82,width-31,82)
    p.setPen(QPen(alpha(ink,.16),1))
    for x in range(35,int(width-31),19):line(p,x,85,min(x+6,width-31),85)
    for x,direction in ((8,1),(width-8,-1)):
        for i,color in enumerate((accent,pink)):
            p.setPen(QPen(alpha(color,.8),1.6));dx=8+i*5
            line(p,x+direction*dx,55,x+direction*(dx+4),41)
    p.restore()


def amplifier_rack(p,width,colors,phase):
    """Brass guards and twin-speaker end caps, mirrored by native ID 18."""
    p.save();box=QRectF(8,8,width-16,80)
    accent=QColor(colors['Accent']);ink=QColor(colors['WindowText']);brass=blend(accent,ink,.65)
    surface=QLinearGradient(box.topLeft(),box.bottomLeft())
    surface.setColorAt(0,blend(colors['Window'],ink,.07));surface.setColorAt(1,QColor(colors['Window']))
    p.setBrush(surface);p.setPen(QPen(alpha(accent,.2),1));p.drawRoundedRect(box,5,5)
    for x,direction in ((8,1),(width-8,-1)):
        p.setPen(QPen(alpha(ink,.08),1))
        for dx in range(3,24,3):
            for y in range(15,83,3):p.drawPoint(QPointF(x+direction*dx,y))
        for y in (37,59):
            p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(alpha(brass,.65),1));p.drawEllipse(QPointF(x+direction*12,y),6,6)
            p.setBrush(alpha(accent,.45));p.setPen(Qt.PenStyle.NoPen);p.drawEllipse(QPointF(x+direction*12,y),1.5,1.5)
        p.setPen(QPen(alpha(brass,.8),1.5))
        for y,dy in ((11,1),(85,-1)):
            line(p,x+direction*3,y,x+direction*18,y)
            line(p,x+direction*3,y,x+direction*3,y+dy*11)
    p.setPen(QPen(alpha(brass,.5),1));line(p,33,12,width-33,12)
    p.setPen(QPen(alpha(accent,.55),1.3));line(p,33,84,width-33,84)
    p.restore()


def orbital_glass(p, width, colors, phase):
    """Inset optical rim and orbiting end lights, mirrored by native ID 19."""
    p.save();box=QRectF(8,8,width-16,80)
    accent=QColor(colors['Accent']);ink=QColor(colors['WindowText'])
    surface=QLinearGradient(box.topLeft(),box.bottomLeft())
    surface.setColorAt(0,blend(colors['Window'],ink,.14))
    surface.setColorAt(.35,blend(colors['Window'],accent,.04))
    surface.setColorAt(1,QColor(colors['Window']))
    p.setBrush(surface);p.setPen(QPen(alpha(accent,.55),1));p.drawRoundedRect(box,14,14)
    p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(alpha(accent,.18),1))
    p.drawRoundedRect(box.adjusted(3,3,-3,-3),11,11)
    p.setPen(QPen(alpha(ink,.55),1));line(p,34,11,width-34,11)
    p.setPen(QPen(alpha(accent,.65),1.4));line(p,34,82,width-34,82)
    for x in (23,width-23):
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(alpha(accent,.65),1));p.drawEllipse(QPointF(x,48),8,18)
        dot=QPointF(x+8*math.cos(phase*.7),48+18*math.sin(phase*.7))
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(ink);p.drawEllipse(dot,2,2)
        star=QPainterPath(QPointF(x,42));star.lineTo(x+1.5,46.5);star.lineTo(x+6,48)
        star.lineTo(x+1.5,49.5);star.lineTo(x,54);star.lineTo(x-1.5,49.5)
        star.lineTo(x-6,48);star.lineTo(x-1.5,46.5);star.closeSubpath()
        p.fillPath(star,alpha(accent,.8))
    p.restore()


def puzzle_reliquary(p, width, colors, phase):
    """Engraved brass double rim and faceted end seals; native material 20."""
    p.save();accent=QColor(colors['Accent']);ink=QColor(colors['WindowText'])
    brass=blend(ink,'#c79b61',.65);base=QColor(colors['Window'])
    box=QRectF(8,8,width-16,80)
    surface=QLinearGradient(box.topLeft(),box.bottomLeft())
    surface.setColorAt(0,blend(base,ink,.075));surface.setColorAt(.3,blend(base,accent,.04));surface.setColorAt(1,base)
    p.setBrush(surface);p.setPen(QPen(alpha(brass,.85),1));p.drawRoundedRect(box,6,6)
    p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(alpha(brass,.35),.8));p.drawRoundedRect(box.adjusted(4,4,-4,-4),3,3)
    for x in (23,width-23):
        diamond=QPainterPath(QPointF(x,29));diamond.lineTo(x+10,48);diamond.lineTo(x,67);diamond.lineTo(x-10,48);diamond.closeSubpath()
        p.setBrush(base);p.setPen(QPen(alpha(brass,.85),1));p.drawPath(diamond)
        line(p,x,29,x,67);line(p,x-10,48,x+10,48)
        p.setPen(QPen(alpha(brass,.4),.7));p.drawEllipse(QPointF(x,48),6,6)
        p.setBrush(alpha(accent,.65+.2*math.sin(phase)));p.setPen(Qt.PenStyle.NoPen);p.drawEllipse(QPointF(x,48),2,2)
    p.setPen(QPen(alpha(brass,.55),.8))
    for y in (15,81):line(p,37,y,width-37,y)
    p.restore()


def ghost_trap(p, width, colors, phase):
    """Enamel trap rail, striped end guards and a living ectoplasm lip."""
    accent,ink,base=(QColor(colors[k]) for k in ('Accent','WindowText','Window'))
    p.save();bounds=QRectF(8,8,width-16,80)
    shape=QPainterPath();shape.addRoundedRect(bounds,10,10)
    fill=QLinearGradient(0,8,0,88)
    fill.setColorAt(0,blend(base,ink,.12));fill.setColorAt(1,base)
    p.setBrush(fill);p.setPen(QPen(accent,1.5));p.drawPath(shape);p.setClipPath(shape,Qt.ClipOperation.IntersectClip)
    for x,sx in ((8,1),(width-8,-1)):
        p.save();p.translate(x,8);p.scale(sx,1)
        p.fillRect(QRectF(2,8,18,64),blend(base,'#000000',.2))
        warm=blend(ink,'#ffc229',.75);p.setPen(QPen(warm,3))
        for y in (15,26,37,48,59):line(p,5,y,16,y-7)
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(alpha(accent,.75+.15*math.sin(phase)))
        p.drawEllipse(QPointF(11,70),2.5,2.5);p.restore()
    p.setPen(QPen(alpha(accent,.8),2));line(p,32,81,width-32,81)
    lip=QPainterPath(QPointF(32,10));lip.lineTo(width-32,10);lip.lineTo(width-32,13)
    for i in range(30,-1,-1):
        x=32+(width-64)*i/30
        lip.lineTo(x,14+2*math.sin(x*.1+phase)+1.5*math.sin(x*.21-phase))
    lip.closeSubpath();p.fillPath(lip,accent);p.restore()


def tray(painter, width, style, colors, phase):
    """Draw a horizontal tray in a width × 96 coordinate space."""
    if style == 'ghostbusters':
        ghost_trap(painter,width,colors,phase);return
    if style == 'leviathan':
        puzzle_reliquary(painter,width,colors,phase);return
    if style == 'polaris':
        orbital_glass(painter,width,colors,phase);return
    if style == 'infernalencore':
        amplifier_rack(painter,width,colors,phase);return
    if style == 'midnightrun':
        neon_pit_lane(painter,width,colors,phase);return
    if style == 'platform95':
        parcel_shelf(painter,width,colors,phase);return
    if style == 'mycelium':
        spore_cradle(painter,width,colors,phase);return
    if style == 'hyperfusionblue':
        blue_vault(painter,width,colors,phase);return
    if style == 'midnighttransit':
        platform_twelve(painter,width,colors,phase);return
    if style == 'blackwood':
        harbour_cabinet(painter,width,colors,phase);return
    if style == 'atomicafterglow':
        containment_bay(painter,width,colors,phase);return
    p = painter; accent, ink, base = (QColor(colors[k]) for k in ('Accent', 'WindowText', 'Window'))
    bounds = QRectF(8, 8, width-16, 80)
    radius = {'raw': 3, 'breakpoint': 10, 'binaryknife': 5, 'porcelainink': 5,
              'obsidianforge': 9, 'shadowedge': 4}.get(style, 40)
    shape = QPainterPath()
    if style in ('breakpoint', 'binaryknife', 'shadowedge'):
        x, y, right, bottom = bounds.left(), bounds.top(), bounds.right(), bounds.bottom()
        shape.moveTo(x+10, y); shape.lineTo(right-10, y); shape.lineTo(right, y+10)
        shape.lineTo(right, bottom-10); shape.lineTo(right-10, bottom)
        shape.lineTo(x+10, bottom); shape.lineTo(x, bottom-10); shape.lineTo(x, y+10); shape.closeSubpath()
    else:
        shape.addRoundedRect(bounds, radius, radius)
    p.save(); p.setPen(Qt.PenStyle.NoPen)
    for spread in (6, 3):
        p.setPen(QPen(alpha(colors['Shadow'], .15), spread)); p.setBrush(Qt.BrushStyle.NoBrush); p.drawPath(shape)
    gradient = QLinearGradient(0, 8, 0, 88)
    gradient.setColorAt(0, blend(base, ink, .12 if style == 'candycloud' else .09))
    gradient.setColorAt(.42, blend(base, accent, .055)); gradient.setColorAt(1, base)
    p.setBrush(gradient); p.setPen(QPen(alpha(blend(accent, ink, .3), .5), 1.2)); p.drawPath(shape)
    p.setClipPath(shape); p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(alpha(accent, .65), 1))
    if style == 'raw':
        line(p, 10, 82, width-10, 82)
        for x in range(16, int(width-12), 14): line(p, x, 14, x+2, 14)
    elif style == 'modern':
        gleam = QLinearGradient(0, 0, width, 0)
        gleam.setColorAt(0, alpha(ink, 0)); gleam.setColorAt(.5+.15*math.sin(phase*.6), alpha(ink, .55)); gleam.setColorAt(1, alpha(ink, 0))
        p.setPen(QPen(gleam, 1.2)); line(p, 36, 11, width-36, 11)
    elif style == 'breakpoint':
        line(p, 20, 82, width-20, 82)
        for x in (15, 23, width-23, width-15): line(p, x-4, 61, x+4, 35)
    elif style == 'binaryknife':
        for x, direction in ((13, 1), (width-13, -1)):
            line(p, x, 27, x+direction*14, 13); line(p, x, 69, x+direction*14, 83)
        p.setPen(QPen(alpha(ink, .05), 8)); line(p, width*.3, 10, width*.6, 86)
    elif style == 'tidalglass':
        for offset, opacity in ((0, .6), (5, .2)):
            wave = QPainterPath()
            for x in range(10, int(width-9), 2):
                y = 79-offset+math.sin(x*.025+phase*.7)*3+math.sin(x*.06-phase*.4)*2
                if x == 10: wave.moveTo(x, y)
                else: wave.lineTo(x, y)
            p.setPen(QPen(alpha(accent, opacity), 1.2)); p.drawPath(wave)
    elif style == 'porcelainink':
        p.setPen(QPen(alpha(ink, .04), .6))
        for x in range(15, int(width), 7): line(p, x, 10, x-3, 86)
        p.setPen(QPen(alpha(accent, .55), 1)); line(p, 16, 82, width-16, 82)
        p.drawEllipse(QPointF(width-25, 48), 7, 7)
    elif style == 'obsidianforge':
        p.setPen(QPen(alpha(ink, .045), .6))
        for y in range(12, 87, 3): line(p, 10, y, width-10, y)
        p.setPen(QPen(alpha(accent, .7+.1*math.sin(phase)), 1.5)); line(p, 18, 82, width-18, 82)
        p.setPen(QPen(alpha(ink, .3), 1)); p.setBrush(alpha(ink, .12))
        for x in (21, width-21):
            for y in (21, 75): p.drawEllipse(QPointF(x, y), 2, 2)
    elif style == 'candycloud':
        p.setPen(QPen(alpha(ink, .65), 1))
        for x in range(32, int(width-25), 47):
            length = 2.5+math.sin(phase*1.4+x)*1.5
            line(p, x-length, 77, x+length, 77); line(p, x, 77-length, x, 77+length)
    elif style == 'shadowedge':
        p.setPen(QPen(alpha(ink, .045), 1))
        for x in range(-80, int(width), 12): line(p, x, 8, x+80, 88)
        p.setPen(QPen(alpha(accent, .5), 1)); line(p, 21, 12, width-21, 12); line(p, 21, 83, width-21, 83)
    elif style == 'gildedhollow':
        from gildedhollow import diamond, scrollwork
        # The same brass caps and lantern jewel as the native dock material.
        cap = QLinearGradient(0, 8, 0, 88)
        cap.setColorAt(0, blend(accent, ink, .38)); cap.setColorAt(.3, blend(base, accent, .25))
        cap.setColorAt(.66, blend(base, accent, .1)); cap.setColorAt(1, blend(base, accent, .35))
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(cap)
        p.drawRect(QRectF(8, 8, 24, 80)); p.drawRect(QRectF(width-32, 8, 24, 80))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(alpha(accent, .65), 1.3)); p.drawPath(shape)
        p.setPen(QPen(alpha(accent, .28), .8)); p.drawRoundedRect(bounds.adjusted(4,4,-4,-4),36,36)
        for mirror in (False, True):
            scrollwork(p, width-11 if mirror else 11, 21, colors, mirror, .77)
            p.setPen(QPen(alpha(ink,.55),.6)); p.setBrush(blend(base,accent,.5))
            p.drawEllipse(QPointF(width-24 if mirror else 24, 71),1.7,1.7)
        sweep = -55+(width+110)*((phase*.105) % 1)
        glint = QLinearGradient(sweep-35,0,sweep+35,0)
        glint.setColorAt(0,alpha(ink,0)); glint.setColorAt(.5,alpha(ink,.95)); glint.setColorAt(1,alpha(ink,0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(glint,2)); p.drawPath(shape)
        gleam = QLinearGradient(32,0,width-32,0)
        gleam.setColorAt(0,alpha(accent,0)); gleam.setColorAt(.5,alpha(accent,.55)); gleam.setColorAt(1,alpha(accent,0))
        p.setPen(QPen(gleam,.8)); line(p,32,83,width-32,83)
        diamond(p,QPointF(width/2,83),colors,4.4,True)
    elif style == 'hollowgrove':
        for end in (False, True):
            p.save()
            if end: p.translate(width, 0); p.scale(-1, 1)
            p.setPen(QPen(alpha(accent, .6), 1)); line(p, 20, 17, 38, 79)
            for i in range(4):
                p.save(); p.translate(24+i*4+(-4 if i % 2 == 0 else 5), 22+i*13)
                p.rotate(-37); p.setBrush(alpha(accent, .36)); p.drawEllipse(QRectF(-5.5, -2.2, 11, 4.4)); p.restore()
            p.restore()
    # Each material has a distinct edge construction in addition to its color.
    p.setBrush(Qt.BrushStyle.NoBrush)
    if style == 'raw':
        p.setPen(QPen(alpha(accent,.75),1))
        for end in (False,True):
            p.save()
            if end:p.translate(width,0);p.scale(-1,1)
            line(p,17,20,33,48);line(p,33,48,17,76);p.drawEllipse(QPointF(33,48),3,3);p.restore()
        pulse=8+(width-16)*((phase*.18)%1)
        p.setPen(QPen(alpha(ink,.9),2));line(p,pulse-4,82,pulse+4,82)
    elif style == 'modern':
        sheen=QLinearGradient(0,10,0,55);sheen.setColorAt(0,alpha(ink,.12));sheen.setColorAt(1,alpha(ink,0))
        p.setBrush(sheen);p.setPen(Qt.PenStyle.NoPen);p.drawRoundedRect(bounds.adjusted(5,4,-5,-30),25,25)
        p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(alpha(accent,.22),1));p.drawRoundedRect(bounds.adjusted(5,5,-5,-5),35,35)
    elif style == 'breakpoint':
        p.setPen(QPen(alpha(accent,.48),1.1));p.drawRoundedRect(bounds.adjusted(4,4,-4,-4),6,6)
        for x in (21,width-21):
            for y in range(25,74,10):
                p.setPen(QPen(alpha(accent,.4+.2*math.sin(phase+y)),2));line(p,x-4,y,x+4,y)
        p.setPen(QPen(alpha(ink,.65),1));p.drawEllipse(QPointF(21,21),2,2);p.drawEllipse(QPointF(width-21,75),2,2)
    elif style == 'binaryknife':
        for x,d in ((14,1),(width-14,-1)):
            p.setPen(QPen(alpha(accent,.75),1.2));line(p,x,37,x+d*25,12);line(p,x,60,x+d*25,85)
        p.setPen(QPen(alpha(ink,.35),1));line(p,35,12,width-35,12)
    elif style == 'tidalglass':
        for x,d in ((22,1),(width-22,-1)):
            for i in range(3):
                p.setPen(QPen(alpha(accent,.45),1));p.drawEllipse(QPointF(x+d*i*5,32+i*13),2+i,2+i)
        p.setPen(QPen(alpha(ink,.3),1));p.drawRoundedRect(bounds.adjusted(4,4,-4,-4),36,36)
    elif style == 'porcelainink':
        for x in (17,width-17):
            p.setPen(QPen(alpha(ink,.18),4));line(p,x,16,x,80)
            p.setPen(QPen(alpha(accent,.4),.8));line(p,x+5,12,x+5,84)
        p.setPen(QPen(alpha(accent,.6),.8));p.drawRect(QRectF(width-30,43,10,10))
    elif style == 'obsidianforge':
        p.setPen(QPen(alpha(accent,.38),1.2));p.drawRoundedRect(bounds.adjusted(5,5,-5,-5),4,4)
        for x in (24,width-24):
            for y in range(29,69,8):
                p.setPen(QPen(alpha(colors['Shadow'],.75),4));line(p,x-5,y,x+5,y)
                p.setPen(QPen(alpha(accent,.3+.1*math.sin(phase*2+y)),1));line(p,x-4,y+1,x+4,y+1)
    elif style == 'candycloud':
        p.setPen(QPen(alpha(ink,.28),1.4));p.drawRoundedRect(bounds.adjusted(4,4,-4,-4),36,36)
        p.setBrush(alpha(ink,.15));p.setPen(QPen(alpha(accent,.3),.8))
        for x in (25,width-25):p.drawEllipse(QPointF(x,48),6,6)
    elif style == 'shadowedge':
        p.setPen(QPen(alpha(ink,.25),1))
        for x,d in ((15,1),(width-15,-1)):
            line(p,x,30,x+d*18,12);line(p,x,66,x+d*18,84)
        sweep=(math.sin(phase*.22)+1)*width/2
        gleam=QLinearGradient(sweep-40,0,sweep+40,0);gleam.setColorAt(0,alpha(ink,0));gleam.setColorAt(.5,alpha(ink,.55));gleam.setColorAt(1,alpha(ink,0))
        p.setPen(QPen(gleam,1.4));line(p,24,12,width-24,12)
    elif style == 'hollowgrove':
        p.setPen(QPen(alpha(accent,.24),.9));p.drawRoundedRect(bounds.adjusted(4,4,-4,-4),36,36)
        moon=QPainterPath();moon.addEllipse(QPointF(width/2,80),4,4)
        cut=QPainterPath();cut.addEllipse(QPointF(width/2+2,79),3.8,3.8)
        p.setBrush(alpha(accent,.65));p.setPen(Qt.PenStyle.NoPen);p.drawPath(moon.subtracted(cut))
        for end in (22,width-22):
            for i in range(3):
                p.setBrush(alpha(accent,.3));p.drawEllipse(QPointF(end+i*3,48+math.sin(phase*.5+i*2)*22),1.2,1.2)
    elif style == 'gildedhollow':
        p.setPen(QPen(alpha(accent,.3),1))
        for x in range(38,int(width-35),7):line(p,x,15,x+1,15)
    p.restore()


def fire(p, center, size, accent, phase):
    """A deterministic, continuously rising particle preview, without assets."""
    p.save(); p.setPen(Qt.PenStyle.NoPen)
    glow = QRadialGradient(center, size*.52)
    glow.setColorAt(0, alpha(accent, .5)); glow.setColorAt(1, alpha(accent, 0))
    p.setBrush(glow); p.drawEllipse(center, size*.52, size*.52)
    for i in range(26):
        age = (phase*(.4+(i % 5)*.04)+i*.6180339) % 1
        sway = math.sin(i*7.21+age*4)*size*(.21-.13*age)
        point = center+QPointF(sway, size*(.27-age*.77))
        radius = size*(.09+.06*math.sin(i*4)**2)*(1-age*.8)
        particle = QRadialGradient(point, radius)
        particle.setColorAt(0, alpha(blend(accent, '#ffffff', .4), (1-age)*.65))
        particle.setColorAt(.35, alpha(accent, (1-age)*.48)); particle.setColorAt(1, alpha(accent, 0))
        p.setBrush(particle); p.drawEllipse(point, radius, radius)
    p.restore()


def app_icon(p, rect, index, colors):
    """Neutral sample apps, so previews do not depend on installed icon packs."""
    p.save(); p.translate(rect.center()); p.scale(rect.width()/32, rect.height()/32)
    p.setPen(QPen(alpha(colors['WindowText'], .9), 1.3)); p.setBrush(alpha(colors['Window'], .85))
    if index % 3 == 0:
        p.drawRoundedRect(QRectF(-14, -11, 28, 22), 3, 3)
        line(p, -8, -5, -3, 0); line(p, -3, 0, -8, 5); line(p, 1, 5, 8, 5)
    elif index % 3 == 1:
        folder = QPainterPath(); folder.moveTo(-14, -7); folder.lineTo(-14, -11); folder.lineTo(-3, -11)
        folder.lineTo(1, -7); folder.lineTo(14, -7); folder.lineTo(14, 12); folder.lineTo(-14, 12); folder.closeSubpath()
        p.drawPath(folder); line(p, -12, -3, 12, -3)
    else:
        p.drawEllipse(QRectF(-13, -13, 26, 26)); p.drawEllipse(QRectF(-6, -13, 12, 26))
        line(p, -12, -5, 12, -5); line(p, -12, 5, 12, 5)
    p.restore()


def dock(p, area, style, colors, *, phase=0., weights=(1., 1., 1.), zoom=(), vertical=False, stack=False):
    """Paint a fitted dock and return slot hit boxes in widget coordinates."""
    count = sum(weights)
    if count < .005: return []
    length = 48+count*74
    scale = min(area.width()/(96 if vertical else length), area.height()/(length if vertical else 96), 1.5)
    center = area.center(); slots = []
    p.save(); p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.translate(center); p.scale(scale, scale)
    if not stack:
        p.save()
        if vertical: p.rotate(90)
        p.translate(-length/2, -48); p.setOpacity(p.opacity()*min(1., count)); tray(p, length, style, colors, phase); p.restore()
    cursor = -count*74/2
    for index, weight in enumerate(weights):
        offset = cursor+weight*37; cursor += weight*74
        spot = QPointF(0, offset) if vertical else QPointF(offset, 0)
        z = zoom[index] if index < len(zoom) else 1.
        size = 60*z
        rect = QRectF(spot.x()-size/2, spot.y()-size/2, size, size)
        slots.append(QRectF(center.x()+rect.x()*scale, center.y()+rect.y()*scale, size*scale, size*scale))
        p.save(); p.setOpacity(p.opacity()*max(0., min(1., weight)))
        if not stack:
            p.setPen(QPen(alpha(colors['Accent'], .12+(z-1)), .8)); p.setBrush(alpha(colors['Accent'], .035+(z-1)*.1))
            radius = 8 if style == 'ghostbusters' else 4 if style == 'leviathan' else 11 if style == 'polaris' else 4 if style == 'infernalencore' else 1 if style == 'platform95' else 2 if style == 'raw' else 3 if style == 'atomicafterglow' else 4 if style == 'blackwood' else 6 if style in ('midnighttransit','midnightrun') else 10 if style in ('gildedhollow','hyperfusionblue') else 8 if style in ('breakpoint', 'binaryknife', 'obsidianforge', 'shadowedge') else 16
            p.drawRoundedRect(rect, radius, radius)
        if style == 'ghostbusters' and not stack:
            accent=QColor(colors['Accent'])
            p.setBrush(blend(colors['Window'],accent,.06+(z-1)*.12))
            p.setPen(QPen(alpha(accent,min(1,.5+(z-1)*.5)),1));p.drawRoundedRect(rect,8,8)
            p.setPen(QPen(alpha(accent,.8),1.8));line(p,rect.left()+8,rect.bottom()-5,rect.right()-8,rect.bottom()-5)
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(alpha(accent,.5))
            for dx in (-5,5):p.drawEllipse(QPointF(rect.center().x()+dx,rect.top()+5),1.2,1.2)
        if style == 'leviathan' and not stack:
            brass=blend(colors['WindowText'],'#c79b61',.65);accent=QColor(colors['Accent'])
            p.setBrush(blend(colors['Window'],accent,.04+(z-1)*.1));p.setPen(QPen(alpha(brass,min(1,.4+(z-1)*.5)),.8));p.drawRoundedRect(rect,4,4)
            p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(alpha(brass,.2),.6));p.drawRoundedRect(rect.adjusted(3,3,-3,-3),2,2)
            p.setPen(QPen(alpha(accent,min(1,.6+(z-1)*.4)),1.2));line(p,rect.left()+9,rect.bottom()-5,rect.right()-9,rect.bottom()-5)
        if style == 'polaris' and not stack:
            accent=QColor(colors['Accent']);ink=QColor(colors['WindowText'])
            pane=QLinearGradient(rect.topLeft(),rect.bottomLeft())
            pane.setColorAt(0,blend(colors['Window'],ink,.13))
            pane.setColorAt(1,blend(colors['Window'],accent,.06+(z-1)*.1))
            p.setBrush(pane);p.setPen(QPen(alpha(accent,min(1,.4+(z-1)*.4)),.9));p.drawRoundedRect(rect,11,11)
            p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(alpha(ink,.18),.8));p.drawRoundedRect(rect.adjusted(3,3,-3,-3),8,8)
            p.setPen(QPen(alpha(accent,min(1,.45+(z-1)*.4)),1.4));line(p,rect.left()+10,rect.bottom()-5,rect.right()-10,rect.bottom()-5)
        if style == 'infernalencore' and not stack:
            accent=QColor(colors['Accent']);brass=blend(accent,colors['WindowText'],.65)
            pane=QLinearGradient(rect.topLeft(),rect.bottomLeft())
            pane.setColorAt(0,blend(colors['Window'],colors['WindowText'],.06));pane.setColorAt(1,blend(colors['Window'],accent,.035+(z-1)*.09))
            p.setBrush(pane);p.setPen(QPen(alpha(accent,min(1,.2+(z-1)*.35)),.8));p.drawRoundedRect(rect,4,4)
            p.setPen(QPen(alpha(brass,.45),1));line(p,rect.left()+5,rect.top()+3,rect.right()-5,rect.top()+3)
            p.fillRect(QRectF(rect.left()+5,rect.bottom()-12,rect.width()-10,8),blend(colors['Window'],'#000000',.35))
            p.setBrush(alpha(brass,.7));p.setPen(Qt.PenStyle.NoPen)
            for dx in (-6,0,6):p.drawEllipse(QPointF(rect.center().x()+dx,rect.bottom()-8),1.4,1.4)
            p.setBrush(alpha(accent,min(1,.6+(z-1)*.3)));p.drawEllipse(QPointF(rect.right()-8,rect.bottom()-8),1.6,1.6)
        if style == 'midnightrun' and not stack:
            accent=QColor(colors['Accent']);pink=QColor.fromRgbF(accent.blueF(),accent.redF(),accent.greenF())
            pane=QLinearGradient(rect.topLeft(),rect.bottomLeft())
            pane.setColorAt(0,blend(colors['Window'],colors['WindowText'],.07));pane.setColorAt(1,blend(colors['Window'],accent,.04+(z-1)*.08))
            p.setBrush(pane);p.setPen(QPen(alpha(accent,min(1,.25+(z-1)*.4)),.8));p.drawRoundedRect(rect,6,6)
            p.setPen(QPen(alpha(accent,min(1,.35+(z-1)*.35)),1.3));line(p,rect.left()+8,rect.top()+5,rect.right()-8,rect.top()+5)
            p.setPen(QPen(alpha(pink,min(1,.45+(z-1)*.4)),1.3));line(p,rect.left()+8,rect.bottom()-5,rect.right()-8,rect.bottom()-5)
            p.setPen(QPen(alpha(pink,.35),1))
            for i in range(2):
                x=rect.right()-10-i*4;line(p,x-2,rect.bottom()-10,x,rect.bottom()-15)
        if style == 'platform95' and not stack:
            p.fillRect(rect,blend(colors['Window'],colors['Accent'],.035+(z-1)*.12))
            parcel_bevel(p,rect.adjusted(1,1,-1,-1),colors,True)
            p.setPen(QPen(alpha(colors['Accent'],min(1,.4+(z-1)*.55)),1.5))
            line(p,rect.left()+7,rect.bottom()-6,rect.right()-7,rect.bottom()-6)
        if style == 'mycelium' and not stack:
            pane=QLinearGradient(rect.topLeft(),rect.bottomRight());pane.setColorAt(0,QColor(colors['Button']));pane.setColorAt(1,QColor(colors['Base']))
            p.setBrush(pane);p.setPen(QPen(alpha(colors['Light'],.45),.8));p.drawRoundedRect(rect,16,16)
            p.setPen(QPen(alpha(colors['Accent'],.7),.8));p.setBrush(Qt.BrushStyle.NoBrush)
            path=QPainterPath(QPointF(rect.left()+9,rect.bottom()-9))
            path.quadTo(rect.center().x(),rect.bottom()-3,rect.right()-9,rect.bottom()-9);p.drawPath(path)
            for dx in (-5,0,5):
                p.setPen(Qt.PenStyle.NoPen);p.setBrush(alpha(colors['Accent'],.55+(z-1)*.3));p.drawEllipse(QPointF(rect.center().x()+dx,rect.bottom()-8),1,1)
        if style == 'atomicafterglow' and not stack:
            pane=QLinearGradient(rect.topLeft(),rect.bottomLeft());pane.setColorAt(0,QColor(colors['Button']));pane.setColorAt(1,QColor(colors['Base']))
            p.setBrush(pane);p.setPen(QPen(alpha(colors['Light'],.65),.8));p.drawRoundedRect(rect,3,3)
            p.setBrush(QColor(colors['Base']));p.setPen(QPen(alpha(colors['Accent'],.6),.6))
            p.drawRoundedRect(QRectF(rect.left()+9,rect.bottom()-12,rect.width()-18,7),1,1)
            p.setPen(QPen(QColor(colors['Accent']),2))
            for i in range(4):line(p,rect.left()+13+i*8,rect.bottom()-8,rect.left()+17+i*8,rect.bottom()-8)
        if style == 'blackwood' and not stack:
            pane=QLinearGradient(rect.topLeft(),rect.bottomRight());pane.setColorAt(0,QColor(colors['Button']));pane.setColorAt(1,QColor(colors['Base']))
            p.setBrush(pane);p.setPen(QPen(alpha(colors['Light'],.65),.8));p.drawRoundedRect(rect,4,4)
            p.setPen(QPen(alpha(colors['Midlight'],.6),.6));p.setBrush(Qt.BrushStyle.NoBrush);p.drawRoundedRect(rect.adjusted(3,3,-3,-3),2,2)
            p.setPen(QPen(QColor(colors['Light']),2));line(p,rect.center().x()-5,rect.bottom()-7,rect.center().x()+5,rect.bottom()-7)
        if style == 'midnighttransit' and not stack:
            pane=QLinearGradient(rect.topLeft(),rect.bottomRight())
            pane.setColorAt(0,QColor(colors['Button']));pane.setColorAt(.65,QColor(colors['Base']));pane.setColorAt(1,QColor(colors['Window']))
            p.setBrush(pane);p.setPen(QPen(alpha(colors['Light'],.75),1));p.drawRoundedRect(rect,6,6)
            p.setPen(QPen(alpha(colors['Accent'],.75),2));line(p,rect.left()+8,rect.bottom()-5,rect.right()-8,rect.bottom()-5)
        if style == 'hyperfusionblue' and not stack:
            glass=QLinearGradient(rect.topLeft(),rect.bottomLeft())
            glass.setColorAt(0,alpha(colors['Light'],.24));glass.setColorAt(.45,alpha(colors['Accent'],.06));glass.setColorAt(.5,alpha(colors['Base'],.6));glass.setColorAt(1,alpha(colors['Accent'],.16))
            p.setBrush(glass);p.setPen(QPen(alpha(colors['Light'],.65),.8));p.drawRoundedRect(rect,10,10)
            p.setPen(QPen(alpha(colors['Accent'],.8),2));line(p,rect.left()+9,rect.bottom()-4,rect.right()-9,rect.bottom()-4)
        fire(p, spot, size, QColor(colors['Accent']), phase+index*.7)
        app_icon(p, QRectF(spot.x()-size*.20, spot.y()-size*.16, size*.4, size*.4), index, colors)
        p.restore()
    p.restore(); return slots
