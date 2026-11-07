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


def tray(painter, width, style, colors, phase):
    """Draw a horizontal tray in a width × 96 coordinate space."""
    if style == 'hyperfusionblue':
        blue_vault(painter,width,colors,phase);return
    if style == 'midnighttransit':
        platform_twelve(painter,width,colors,phase);return
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
            radius = 2 if style == 'raw' else 6 if style == 'midnighttransit' else 10 if style in ('gildedhollow','hyperfusionblue') else 8 if style in ('breakpoint', 'binaryknife', 'obsidianforge', 'shadowedge') else 16
            p.drawRoundedRect(rect, radius, radius)
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
