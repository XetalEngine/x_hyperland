"""Small, consistent outline icons for desktop tools and navigation."""
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QIcon, QPainter, QPainterPath, QPen, QPixmap, QColor


def icon(name, color, size=24):
    pixmap=QPixmap(size*2,size*2);pixmap.fill(Qt.GlobalColor.transparent);pixmap.setDevicePixelRatio(2)
    p=QPainter(pixmap);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.scale(size/24,size/24)
    p.setPen(QPen(QColor(color),1.7,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)
    def line(x,y,a,b):p.drawLine(QPointF(x,y),QPointF(a,b))
    if name=='home':
        line(3,10,12,3);line(12,3,21,10);line(5,9,5,21);line(19,9,19,21);line(5,21,19,21)
        p.drawRoundedRect(QRectF(9,13,6,8),1,1)
    elif name=='hotkeys':
        p.drawRoundedRect(QRectF(2,5,20,14),3,3)
        for y in (9,12):
            for x in (6,10,14,18):line(x,y,x+.4,y)
        line(7,16,17,16)
    elif name=='audio':
        path=QPainterPath(QPointF(3,9));path.lineTo(7,9);path.lineTo(12,5);path.lineTo(12,19);path.lineTo(7,15);path.lineTo(3,15);path.closeSubpath();p.drawPath(path)
        p.drawArc(QRectF(10,7,9,10),-65*16,130*16);p.drawArc(QRectF(10,3,14,18),-55*16,110*16)
    elif name=='network':
        p.drawArc(QRectF(1,5,22,20),48*16,84*16);p.drawArc(QRectF(5,10,14,13),42*16,96*16)
        p.drawArc(QRectF(9,15,6,5),30*16,120*16);p.drawEllipse(QPointF(12,20),.7,.7)
    elif name=='bluetooth':
        path=QPainterPath(QPointF(11,2));path.lineTo(18,8);path.lineTo(6,18);path.moveTo(11,2);path.lineTo(11,22);path.lineTo(18,16);path.lineTo(6,6);p.drawPath(path)
    elif name=='displays':
        p.drawRoundedRect(QRectF(2,3,20,14),2,2);line(12,17,12,21);line(8,21,16,21)
    elif name=='fusion-settings':
        p.drawRoundedRect(QRectF(2,3,20,14),2,2);line(12,17,12,21);line(8,21,16,21)
        for x,y in ((7,9),(12,12),(17,8)):
            line(x,6,x,y-1.4);line(x,y+1.4,x,14)
            p.drawEllipse(QPointF(x,y),1.4,1.4)
    elif name=='input':
        p.drawRoundedRect(QRectF(6,2,12,20),6,6);line(12,5,12,9);line(6,11,18,11)
    elif name=='theme':
        for x,y in ((6,6),(18,6),(6,18),(18,18)):p.drawEllipse(QPointF(x,y),3.6,3.6)
        p.setBrush(QColor(color));p.drawEllipse(QPointF(18,6),1.7,1.7)
    elif name=='context-menu':
        p.drawRoundedRect(QRectF(3,3,18,18),3,3)
        for y in (8,12,16):line(7,y,7.5,y);line(11,y,17,y)
    elif name=='calendar':
        p.drawRoundedRect(QRectF(3,5,18,17),2,2);line(3,10,21,10);line(8,2,8,7);line(16,2,16,7)
        for x in (8,12,16):p.drawPoint(QPointF(x,15))
    elif name=='terminal':
        p.drawRoundedRect(QRectF(2,4,20,16),2,2);line(6,8,10,12);line(10,12,6,16);line(13,16,18,16)
    elif name=='system':
        line(12,2,12,11);p.drawArc(QRectF(3,4,18,18),125*16,290*16)
    elif name=='microphone':
        p.drawRoundedRect(QRectF(9,2,6,13),3,3);p.drawArc(QRectF(5,6,14,14),180*16,180*16);line(12,20,12,23)
    else:
        p.drawEllipse(QRectF(4,4,16,16));p.drawEllipse(QRectF(9,9,6,6))
    p.end();return QIcon(pixmap)
