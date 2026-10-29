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
