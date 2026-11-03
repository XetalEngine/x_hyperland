"""Original vector scenes for the Modern and BreakPoint transfer cards."""
import math
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QLinearGradient, QPainterPath, QPen, QRadialGradient


def alpha(color, opacity):
    value = QColor(color); value.setAlpha(round(max(0, min(255, opacity)))); return value


def paper(p, accent, *, technical=False):
    page = QPainterPath(); page.moveTo(-7, -10); page.lineTo(2, -10)
    page.lineTo(8, -4); page.lineTo(8, 10); page.lineTo(-7, 10); page.closeSubpath()
    p.setPen(QPen(accent.lighter(135), 1))
    p.setBrush(alpha(accent, 40) if technical else accent.lighter(180)); p.drawPath(page)
    p.setPen(QPen(accent if technical else accent.darker(175), 1))
    p.drawLine(QPointF(2, -10), QPointF(2, -4)); p.drawLine(QPointF(2, -4), QPointF(8, -4))
    for row in (-1, 3, 7): p.drawLine(QPointF(-4, row), QPointF(4, row))


def folder(p, center, accent, surface, archive=False, technical=False):
    p.save(); p.translate(center)
    p.setPen(QPen(alpha(accent, 85), 1)); p.setBrush(surface)
    p.drawRoundedRect(QRectF(-28, -23, 56, 46), 8 if technical else 15, 8 if technical else 15)
    if archive:
        p.setPen(QPen(accent.lighter(125), 1.2)); p.setBrush(alpha(accent, 25))
        p.drawRoundedRect(QRectF(-13, -15, 26, 30), 3, 3)
        p.setPen(QPen(accent, 2))
        for y in range(-11, 12, 4): p.drawLine(QPointF(-2, y), QPointF(2, y))
    else:
        shape = QPainterPath(); shape.moveTo(-16, 11); shape.lineTo(-16, -12)
        shape.lineTo(-5, -12); shape.lineTo(-1, -7); shape.lineTo(16, -7)
        shape.lineTo(16, 11); shape.closeSubpath()
        fill = QLinearGradient(0, -12, 0, 12)
        fill.setColorAt(0, alpha(accent.lighter(120), 95 if technical else 220))
        fill.setColorAt(1, alpha(accent, 25 if technical else 135))
        p.setPen(QPen(accent.lighter(135), 1)); p.setBrush(fill); p.drawPath(shape)
        p.setPen(QPen(alpha(accent.lighter(160), 150), 1)); p.drawLine(QPointF(-13, -3), QPointF(13, -3))
    p.restore()


def success(p, center, accent):
    p.setPen(QPen(accent, 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(center+QPointF(-7, 0), center+QPointF(-1, 6))
    p.drawLine(center+QPointF(-1, 6), center+QPointF(11, -7))


def modern(p, box, accent, surface, phase, count, trails, glow, archive, extracting, result):
    left = QPointF(box.left()+38, box.center().y())
    right = QPointF(box.right()-38, box.center().y())
    start, end = left+QPointF(36, 0), right-QPointF(36, 0)
    line = QPainterPath(start); line.cubicTo(start+QPointF(50, -9), end-QPointF(50, -9), end)
    p.setPen(QPen(alpha(accent, 30), 2, Qt.PenStyle.DotLine)); p.setBrush(Qt.BrushStyle.NoBrush); p.drawPath(line)
    for center in (left, right):
        bloom = QRadialGradient(center, 42)
        bloom.setColorAt(0, alpha(accent, glow*.65)); bloom.setColorAt(1, alpha(accent, 0))
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(bloom); p.drawEllipse(center, 42, 30)
    folder(p, left, accent, surface, extracting)
    folder(p, right, accent, surface, archive)
    if result == 'done': success(p, box.center(), accent); return
    if result: return
    for i in range(count):
        t = (phase+i/count) % 1
        point = line.pointAtPercent(t)
        p.save(); p.setOpacity(min(1, t*8, (1-t)*8)); p.translate(point)
        if trails:
            for offset in (12, 6):
                p.setPen(Qt.PenStyle.NoPen); p.setBrush(alpha(accent, 24 if offset == 6 else 12))
                p.drawRoundedRect(QRectF(-8-offset, -10+offset*.15, 16, 20), 4, 4)
        p.rotate(math.sin(t*math.pi*2)*7)
        paper(p, accent); p.restore()


def tidalglass(p, box, accent, surface, phase, count, trails, glow, archive, extracting, result):
    """Pages drift along an illuminated current between two glass folders."""
    p.save()
    left, right=QPointF(box.left()+38,box.center().y()),QPointF(box.right()-38,box.center().y())
    for offset in (-7,7):
        wave=QPainterPath(left+QPointF(31,offset))
        wave.cubicTo(QPointF(box.center().x()-40,left.y()+offset-14),
                     QPointF(box.center().x()+40,right.y()+offset+14),right+QPointF(-31,offset))
        p.setPen(QPen(alpha(accent,28),1));p.setBrush(Qt.BrushStyle.NoBrush);p.drawPath(wave)
    modern(p,box,accent,surface,phase,count,trails,glow,archive,extracting,result)
    if not result:
        for index in range(count+2):
            t=(phase*.7+index/(count+2))%1
            center=QPointF(left.x()+48+t*(right.x()-left.x()-96),left.y()+12*math.sin(t*math.pi*2))
            radius=2+(index%3)*.7
            p.setPen(QPen(alpha(accent,80),.7));p.setBrush(alpha(surface,130));p.drawEllipse(center,radius,radius)
    p.restore()


def porcelainink(p, box, accent, surface, phase, count, trails, glow, archive, extracting, result):
    """Folded sheets follow a brushstroke between two outlined document trays."""
    p.save()
    left,right=QPointF(box.left()+32,box.center().y()),QPointF(box.right()-32,box.center().y())
    ink=QColor('#292521' if surface.lightness()>128 else '#e8dfd1')
    start,end=left+QPointF(30,0),right-QPointF(30,0)
    route=QPainterPath(start);route.cubicTo(start+QPointF(40,-9),end-QPointF(40,-9),end)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(alpha(ink,35),1));p.drawPath(route)
    for center,zipped in ((left,extracting),(right,archive)):
        p.save();p.translate(center)
        tray=QPainterPath();tray.moveTo(-21,14);tray.lineTo(-21,-12)
        tray.lineTo(-5,-12);tray.lineTo(0,-7);tray.lineTo(21,-7);tray.lineTo(21,14);tray.closeSubpath()
        p.setBrush(surface);p.setPen(QPen(ink,1.2));p.drawPath(tray)
        p.setPen(QPen(accent,2));p.drawLine(QPointF(-17,9),QPointF(17,9))
        if zipped:
            p.setPen(QPen(ink,1.5))
            for y in range(-4,8,4):p.drawLine(QPointF(-2,y),QPointF(2,y))
        p.restore()
    if result=='done':success(p,box.center(),accent)
    elif not result:
        for index in range(count):
            t=(phase+index/count)%1
            p.save();p.setOpacity(min(1,t*8,(1-t)*8));p.translate(route.pointAtPercent(t))
            if trails:
                p.setPen(QPen(alpha(ink,45),.7));p.drawLine(QPointF(-19,0),QPointF(-11,0))
            p.rotate(math.sin(t*math.pi)*-5)
            page=QPainterPath();page.moveTo(-7,-10);page.lineTo(2,-10);page.lineTo(8,-4);page.lineTo(8,10);page.lineTo(-7,10);page.closeSubpath()
            p.setBrush(surface);p.setPen(QPen(ink,1));p.drawPath(page)
            p.drawLine(QPointF(2,-10),QPointF(2,-4));p.drawLine(QPointF(2,-4),QPointF(8,-4))
            for y in (-1,3):p.drawLine(QPointF(-4,y),QPointF(4,y))
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(accent);p.drawRect(QRectF(1,5,4,3))
            p.restore()
    p.restore()


def candycloud(p, box, accent, surface, phase, count, trails, glow, archive, extracting, result):
    """Cloud couriers float envelopes along a satin ribbon between soft docks."""
    p.save()
    left,right=QPointF(box.left()+35,box.center().y()),QPointF(box.right()-35,box.center().y())
    pearl=accent.lighter(155)
    route=QPainterPath(left+QPointF(30,0))
    route.cubicTo(left+QPointF(75,-28),right-QPointF(75,-18),right-QPointF(30,0))
    p.setBrush(Qt.BrushStyle.NoBrush)
    ribbon=QLinearGradient(left,right);ribbon.setColorAt(0,alpha(accent,75));ribbon.setColorAt(.5,alpha(pearl,110));ribbon.setColorAt(1,alpha(accent,75))
    p.setPen(QPen(ribbon,6,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap));p.drawPath(route)
    p.setPen(QPen(alpha(pearl,140),1));p.drawPath(route)
    for center,zipped in ((left,extracting),(right,archive)):
        p.setPen(Qt.PenStyle.NoPen)
        for dx,dy,radius in ((-15,11,14),(0,7,19),(16,12,13)):
            p.setBrush(alpha(accent,65));p.drawEllipse(center+QPointF(dx,dy),radius,radius*.6)
        folder(p,center-QPointF(0,4),accent,surface,zipped)
    if result=='done':success(p,box.center(),accent)
    elif not result:
        for index in range(count):
            t=(phase+index/count)%1
            point=route.pointAtPercent(t)+QPointF(0,math.sin(t*math.tau+index)*3)
            p.save();p.setOpacity(min(1,t*8,(1-t)*8));p.translate(point)
            if glow:
                light=QRadialGradient(QPointF(0,-7),22);light.setColorAt(0,alpha(accent,glow));light.setColorAt(1,alpha(accent,0))
                p.setPen(Qt.PenStyle.NoPen);p.setBrush(light);p.drawEllipse(QPointF(0,-7),22,22)
            # A rounded envelope is suspended from a tiny three-lobed cloud.
            p.setPen(QPen(alpha(pearl,130),.8))
            p.drawLine(QPointF(-6,-7),QPointF(-5,3));p.drawLine(QPointF(6,-7),QPointF(5,3))
            p.setPen(Qt.PenStyle.NoPen)
            for dx,dy,radius in ((-6,-10,5),(0,-13,6),(6,-10,5)):
                fill=QLinearGradient(0,-19,0,-5);fill.setColorAt(0,pearl);fill.setColorAt(1,accent)
                p.setBrush(fill);p.drawEllipse(QPointF(dx,dy),radius,radius)
            p.setBrush(surface);p.setPen(QPen(accent,1.1));p.drawRoundedRect(QRectF(-9,2,18,13),4,4)
            p.drawLine(QPointF(-8,4),QPointF(0,10));p.drawLine(QPointF(0,10),QPointF(8,4))
            if trails:
                p.setPen(QPen(alpha(pearl,160),1))
                star=QPointF(-17,4+math.sin(t*math.tau)*4)
                p.drawLine(star-QPointF(2,0),star+QPointF(2,0));p.drawLine(star-QPointF(0,3),star+QPointF(0,3))
            p.restore()
    p.restore()


def obsidianforge(p, box, accent, surface, phase, count, trails, glow, archive, extracting, result):
    """Documents travel as hot metal plates through a pair of basalt presses."""
    p.save()
    left,right=QPointF(box.left()+31,box.center().y()),QPointF(box.right()-31,box.center().y())
    start,end=left.x()+29,right.x()-29
    p.setBrush(Qt.BrushStyle.NoBrush)
    for offset in (-14,14):
        p.setPen(QPen(alpha(accent,55),1));p.drawLine(QPointF(start,left.y()+offset),QPointF(end,right.y()+offset))
    for center,zipped in ((left,extracting),(right,archive)):
        p.save();p.translate(center)
        mold=QPainterPath();mold.moveTo(-23,-19);mold.lineTo(17,-19);mold.lineTo(23,-13)
        mold.lineTo(23,19);mold.lineTo(-17,19);mold.lineTo(-23,13);mold.closeSubpath()
        p.setBrush(surface);p.setPen(QPen(alpha(accent,130),1));p.drawPath(mold)
        p.setPen(QPen(accent,2));p.drawLine(QPointF(-18,14),QPointF(18,14))
        p.setPen(QPen(accent.lighter(145),1));p.drawLine(QPointF(-12,-10),QPointF(12,-10))
        if zipped:
            for y in (-5,0,5):p.drawLine(QPointF(-3,y),QPointF(3,y))
        else:
            p.drawLine(QPointF(-12,-10),QPointF(-12,7));p.drawLine(QPointF(12,-10),QPointF(12,7))
        p.restore()
    if result=='done':success(p,box.center(),accent)
    elif not result:
        for index in range(count):
            t=(phase+index/count)%1;x=start+(end-start)*t;y=left.y()
            p.save();p.setOpacity(min(1,t*8,(1-t)*8))
            if glow:
                heat=QRadialGradient(QPointF(x,y),24);heat.setColorAt(0,alpha(accent,glow*1.4));heat.setColorAt(1,alpha(accent,0))
                p.setBrush(heat);p.setPen(Qt.PenStyle.NoPen);p.drawEllipse(QPointF(x,y),24,20)
            if trails:
                for spark in range(3):
                    age=(phase*2+index*.23+spark*.3)%1
                    ember=QPointF(x-age*15,y-7-age*14)
                    p.setPen(QPen(alpha(accent.lighter(150),210*(1-age)),1.3))
                    p.drawLine(ember,ember+QPointF(2,3))
            p.translate(x,y)
            page=QPainterPath();page.moveTo(-7,-10);page.lineTo(2,-10);page.lineTo(8,-4);page.lineTo(8,10);page.lineTo(-7,10);page.closeSubpath()
            fill=QLinearGradient(0,-10,0,10);fill.setColorAt(0,accent.lighter(135));fill.setColorAt(1,accent.darker(170))
            p.setBrush(fill);p.setPen(QPen(accent.lighter(170),1));p.drawPath(page)
            p.setPen(QPen(surface,1));p.drawLine(QPointF(-4,0),QPointF(4,0));p.drawLine(QPointF(-4,4),QPointF(2,4))
            p.restore()
    p.restore()


def breakpoint(p, box, accent, surface, phase, count, trails, glow, archive, extracting, result):
    left, right = QPointF(box.left()+36, box.center().y()), QPointF(box.right()-36, box.center().y())
    start, end = left.x()+38, right.x()-38
    p.setPen(QPen(alpha(accent, 20), 1))
    for row in (-16, 0, 16):
        p.drawLine(QPointF(start, left.y()+row), QPointF(end, left.y()+row))
    for x in range(round(start), round(end), 16):
        p.drawLine(QPointF(x, left.y()-20), QPointF(x, left.y()+20))
    p.setPen(QPen(alpha(accent, 95), 1))
    for row in (-11, 11):
        p.drawLine(QPointF(start, left.y()+row), QPointF(end, left.y()+row))
    folder(p, left, accent, surface, extracting, True)
    folder(p, right, accent, surface, archive, True)
    p.setPen(QPen(accent, 2))
    for point in (left, right):
        p.drawLine(point+QPointF(-28, -16), point+QPointF(-28, -23))
        p.drawLine(point+QPointF(-28, -23), point+QPointF(-18, -23))
    if result == 'done': success(p, box.center(), accent); return
    if result: return
    for i in range(count):
        t = (phase+i/count) % 1
        x = start+(end-start)*t
        p.save(); p.setOpacity(min(1, t*9, (1-t)*9))
        if glow:
            bloom = QRadialGradient(QPointF(x, left.y()), 24)
            bloom.setColorAt(0, alpha(accent, glow)); bloom.setColorAt(1, alpha(accent, 0))
            p.setBrush(bloom); p.setPen(Qt.PenStyle.NoPen); p.drawEllipse(QPointF(x, left.y()), 24, 20)
        if trails:
            for offset in range(4, 0, -1):
                p.setPen(Qt.PenStyle.NoPen); p.setBrush(alpha(accent, 55-offset*10))
                p.drawRect(QRectF(x-10-offset*6, left.y()-5, 3, 10))
        p.translate(x, left.y()); paper(p, accent, technical=True); p.restore()


def binaryknife(p, box, accent, surface, phase, count, trails, glow, archive, extracting, result):
    """Documents follow angular control-flow traces through a scanning gate."""
    left, right = QPointF(box.left()+32, box.center().y()), QPointF(box.right()-32, box.center().y())
    start, end = left.x()+32, right.x()-32
    center = box.center()
    routes = []
    for offset in (-12, 12):
        route = QPainterPath(QPointF(start, left.y()))
        route.lineTo(start+18, left.y()); route.lineTo(start+30, left.y()+offset)
        route.lineTo(end-30, left.y()+offset); route.lineTo(end-18, left.y()); route.lineTo(end, left.y())
        p.setPen(QPen(alpha(accent, 60), 1)); p.setBrush(Qt.BrushStyle.NoBrush); p.drawPath(route)
        routes.append(route)
    folder(p, left, accent, surface, extracting, True)
    folder(p, right, accent, surface, archive, True)
    if result == 'done': success(p, center, accent); return
    if result: return
    scan = center.x()+math.sin(phase*math.tau)*8
    beam = QLinearGradient(scan-9, 0, scan+9, 0)
    beam.setColorAt(0, alpha(accent, 0)); beam.setColorAt(.5, alpha(accent, glow*1.5)); beam.setColorAt(1, alpha(accent, 0))
    p.setPen(Qt.PenStyle.NoPen); p.setBrush(beam)
    p.drawRect(QRectF(scan-9, center.y()-21, 18, 42))
    p.setPen(QPen(alpha(accent.lighter(150), 170), 1))
    p.drawLine(QPointF(scan, center.y()-19), QPointF(scan, center.y()+19))
    for index in range(count):
        t = (phase+index/count) % 1
        route = routes[index%2]
        point = route.pointAtPercent(t)
        p.save(); p.setOpacity(min(1, t*8, (1-t)*8))
        if trails:
            for distance in (0.045, 0.09, 0.135):
                trail = route.pointAtPercent(max(0, t-distance))
                p.setPen(Qt.PenStyle.NoPen); p.setBrush(alpha(accent, 80-distance*400))
                p.drawRect(QRectF(trail.x()-2, trail.y()-2, 4, 4))
        p.translate(point); p.scale(.78, .78); paper(p, accent.lighter(115), technical=True); p.restore()
    p.setBrush(accent.lighter(150)); p.setPen(Qt.PenStyle.NoPen)
    for point in (QPointF(start, center.y()), QPointF(end, center.y())):
        p.drawRect(QRectF(point.x()-2, point.y()-2, 4, 4))
