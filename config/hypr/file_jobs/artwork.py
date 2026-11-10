"""Original transfer scenes; phase is a repeating 0..1 animation cycle."""
import math
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient


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


def leviathan(p, box, accent, surface, phase, count, trails, glow, archive, extracting, result):
    """Documents and puzzle cubes pass between brass labyrinth gateways.

    A phase is a whole journey. Packets and their entire trails fade together
    before each wrap, while gateway lights use complete periodic revolutions.
    """
    from leviathan import puzzle_cube
    p.save();p.setClipRect(box,Qt.ClipOperation.IntersectClip)
    mid=box.center();left=box.left()+29;right=box.right()-29
    brass=QColor('#dac09a' if surface.lightnessF()<.5 else '#76562e')
    for x,zipped in ((left,extracting),(right,archive)):
        portal=QPainterPath(QPointF(x-19,mid.y()+23));portal.lineTo(x-19,mid.y()-13)
        portal.lineTo(x,mid.y()-27);portal.lineTo(x+19,mid.y()-13);portal.lineTo(x+19,mid.y()+23);portal.closeSubpath()
        p.setBrush(surface);p.setPen(QPen(brass,1.2));p.drawPath(portal)
        p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(alpha(brass,100),.8))
        p.drawRect(QRectF(x-15,mid.y()-11,30,30))
        if zipped:puzzle_cube(p,QPointF(x,mid.y()+3),21,brass,accent,surface)
        else:
            p.save();p.translate(x,mid.y()+3);p.scale(.7,.7);paper(p,brass,technical=True);p.restore()
        intensity=155+65*math.sin(phase*math.tau)
        p.setBrush(alpha(accent,intensity));p.setPen(QPen(brass,.7))
        jewel=QPainterPath(QPointF(x,mid.y()-23));jewel.lineTo(x+3,mid.y()-19);jewel.lineTo(x,mid.y()-15);jewel.lineTo(x-3,mid.y()-19);jewel.closeSubpath();p.drawPath(jewel)
    start,end=left+28,right-28
    p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(alpha(brass,90),.8))
    for y in (mid.y()+19,mid.y()+23):p.drawLine(QPointF(start,y),QPointF(end,y))
    for i in range(10):
        x=start+(end-start)*(i+.5)/10
        p.drawLine(QPointF(x-4,mid.y()+19),QPointF(x,mid.y()+23))
    if result:
        if result=='done':success(p,mid,accent)
        p.restore();return
    for index in range(max(1,count)):
        t=(phase+index/max(1,count))%1
        fade=min(1.,t/.14,(1-t)/.14);fade=fade*fade*(3-2*fade)
        travel=1-t if extracting else t;direction=-1 if extracting else 1
        x=start+(end-start)*travel;y=mid.y()-5-7*math.sin(travel*math.pi)
        p.save();p.setOpacity(p.opacity()*fade)
        if glow:
            halo=QRadialGradient(QPointF(x,y),23);halo.setColorAt(0,alpha(accent,glow));halo.setColorAt(1,alpha(accent,0))
            p.setBrush(halo);p.setPen(Qt.PenStyle.NoPen);p.drawEllipse(QPointF(x,y),23,23)
        if trails:
            for n in range(1,4):
                tx=x-direction*(10+n*7);ty=y+math.sin(t*math.tau+n)*2
                p.setPen(QPen(alpha(brass,130/n),.8));p.setBrush(alpha(accent,70/n))
                shard=QPainterPath(QPointF(tx,ty-2));shard.lineTo(tx+2,ty);shard.lineTo(tx,ty+2);shard.lineTo(tx-2,ty);shard.closeSubpath();p.drawPath(shard)
        if archive or extracting:puzzle_cube(p,QPointF(x,y),25,brass,accent,surface)
        else:
            p.translate(x,y);p.rotate(4*math.sin(t*math.tau));paper(p,brass,technical=True)
            p.setPen(QPen(accent,1.4));p.drawLine(QPointF(-4,7),QPointF(4,7))
        p.restore()
    p.restore()


def polaris(p, box, accent, surface, phase, count, trails, glow, archive, extracting, result):
    """Glass document capsules cross a polar arc between orbital gateways.

    Phase is one complete cycle. Each capsule, trail and halo fades together
    before its own wrap; the secondary orbit makes one complete revolution.
    """
    p.save(); mid=box.center(); left=box.left()+31; right=box.right()-31
    ice=QColor('#def8ff' if surface.lightnessF()<.5 else '#25466a')
    violet=QColor('#aa98ee' if surface.lightnessF()<.5 else '#65529b')
    route=QPainterPath(QPointF(left+25,mid.y()+7))
    route.cubicTo(left+95,mid.y()-23,right-95,mid.y()-23,right-25,mid.y()+7)
    p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(alpha(accent,55),1));p.drawPath(route)
    for x,zipped in ((left,extracting),(right,archive)):
        folder(p,QPointF(x,mid.y()),accent,surface,zipped,True)
        p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(alpha(violet,150),1))
        p.drawEllipse(QRectF(x-24,mid.y()-8,48,16))
        angle=phase*math.tau
        dot=QPointF(x+24*math.cos(angle),mid.y()+8*math.sin(angle))
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(ice);p.drawEllipse(dot,1.6,1.6)
    if result:
        if result=='done':success(p,mid,accent)
        p.restore();return
    start,end=left+31,right-31
    for index in range(max(1,count)):
        t=(phase+index/max(1,count))%1
        fade=min(1.,t/.13,(1-t)/.13);fade=fade*fade*(3-2*fade)
        travel=1-t if extracting else t
        x=start+(end-start)*travel;y=mid.y()+7-22*math.sin(travel*math.pi)
        p.save();p.setOpacity(p.opacity()*fade)
        if glow:
            halo=QRadialGradient(QPointF(x,y),23)
            halo.setColorAt(0,alpha(accent,glow));halo.setColorAt(1,alpha(accent,0))
            p.setBrush(halo);p.setPen(Qt.PenStyle.NoPen);p.drawEllipse(QPointF(x,y),23,23)
        if trails:
            for n in range(1,5):
                trail=travel+(1 if extracting else -1)*n*.018
                tx=start+(end-start)*trail;ty=mid.y()+7-22*math.sin(trail*math.pi)
                p.setPen(Qt.PenStyle.NoPen);p.setBrush(alpha(violet,110/n));p.drawEllipse(QPointF(tx,ty),2,2)
        p.translate(x,y)
        glass=QLinearGradient(0,-16,0,16);glass.setColorAt(0,alpha(ice,90));glass.setColorAt(.45,surface);glass.setColorAt(1,alpha(violet,100))
        p.setBrush(glass);p.setPen(QPen(accent,1));p.drawRoundedRect(QRectF(-12,-16,24,32),8,8)
        p.scale(.75,.75);paper(p,accent,technical=True)
        if archive or extracting:
            p.setPen(QPen(violet,1.5))
            for py in (-6,-2,2,6):p.drawLine(QPointF(-1,py),QPointF(2,py))
        p.restore()
    p.restore()


def infernalencore(p, box, accent, surface, phase, count, trails, glow, archive, extracting, result):
    """Documents ride a sound wave between two brass amplifier cabinets.

    Each document, halo and note trail fades as one at its own route wrap.
    The wave and tilt use whole periods so phase zero and one render alike.
    """
    p.save();mid=box.center();left=box.left()+31;right=box.right()-31
    ink=QColor('#f4dfbd' if surface.lightnessF()<.5 else '#503329')
    for x,zipped in ((left,extracting),(right,archive)):
        case=QRectF(x-21,mid.y()-27,42,54)
        p.setBrush(surface);p.setPen(QPen(ink,1.3));p.drawRoundedRect(case,3,3)
        p.setPen(QPen(alpha(ink,180),1));p.drawLine(case.topLeft()+QPointF(3,9),case.topRight()+QPointF(-3,9))
        for dx in (-12,-5,2):
            p.setBrush(ink);p.setPen(Qt.PenStyle.NoPen);p.drawEllipse(QPointF(x+dx,mid.y()-22),1.3,1.3)
        p.setBrush(accent);p.drawEllipse(QPointF(x+13,mid.y()-22),1.8,1.8)
        for y in (-8,13):
            p.setBrush(alpha(ink,22));p.setPen(QPen(alpha(ink,150),1));p.drawEllipse(QPointF(x,mid.y()+y),8,8)
            p.setBrush(alpha(accent,110));p.drawEllipse(QPointF(x,mid.y()+y),2,2)
        for dx in (-17,17):
            for dy in (-24,24):
                p.setBrush(ink);p.setPen(Qt.PenStyle.NoPen);p.drawEllipse(QPointF(x+dx,mid.y()+dy),.9,.9)
        if zipped:
            p.setPen(QPen(accent,1.5))
            for dy in range(-14,23,5):p.drawLine(QPointF(x+14,mid.y()+dy),QPointF(x+17,mid.y()+dy))
    if result:
        if result=='done':success(p,mid,accent)
        p.restore();return
    start,end=left+27,right-27
    wave=QPainterPath()
    for i in range(81):
        t=i/80;x=start+(end-start)*t
        y=mid.y()+15+math.sin(t*math.tau*2+phase*math.tau)*3*math.sin(t*math.pi)
        if i==0:wave.moveTo(x,y)
        else:wave.lineTo(x,y)
    p.setPen(QPen(alpha(accent,95),1));p.setBrush(Qt.BrushStyle.NoBrush);p.drawPath(wave)
    for index in range(count):
        t=(phase+index/count)%1
        fade=min(1.,t/.12,(1-t)/.12);fade=fade*fade*(3-2*fade)
        travel=1-t if extracting else t;direction=-1 if extracting else 1
        x=start+(end-start)*travel;y=mid.y()-7-math.sin(travel*math.pi)*8
        p.save();p.setOpacity(p.opacity()*fade)
        if trails:
            p.setPen(QPen(alpha(ink,110),1));p.setBrush(alpha(accent,115))
            for n in range(1,4):
                nx=x-direction*(12+n*9);ny=y+4+math.sin(t*math.tau+n)*3
                p.drawEllipse(QPointF(nx,ny),2,1.4);p.drawLine(QPointF(nx+2,ny),QPointF(nx+2,ny-6))
        if glow:
            halo=QRadialGradient(QPointF(x,y),22);halo.setColorAt(0,alpha(accent,glow));halo.setColorAt(1,alpha(accent,0))
            p.setBrush(halo);p.setPen(Qt.PenStyle.NoPen);p.drawEllipse(QPointF(x,y),22,18)
        p.translate(x,y);p.rotate(math.sin(t*math.tau)*9);paper(p,ink,technical=True)
        p.setPen(QPen(accent,1.8));p.drawLine(QPointF(-5,7),QPointF(5,7))
        if archive or extracting:
            for dy in range(-6,6,4):p.drawLine(QPointF(-1,dy),QPointF(2,dy))
        p.restore()
    p.restore()


def midnightrun(p, box, accent, surface, phase, count, trails, glow, archive, extracting, result):
    """Neon couriers carry documents between two illuminated garages.

    Each car, its lights, and its trail disappear together at its route wrap.
    Wheel spokes complete eight full turns; the road itself stays still.
    """
    p.save(); mid=box.center(); left=box.left()+31; right=box.right()-31
    pink=QColor.fromRgbF(accent.blueF(),accent.redF(),accent.greenF())
    ink=QColor('#d7f6ff' if surface.lightnessF()<.5 else '#1b3046')
    road=mid.y()+20
    p.setPen(QPen(alpha(accent,120),1));p.drawLine(QPointF(left,road-1),QPointF(right,road-1))
    p.setPen(QPen(alpha(pink,120),1));p.drawLine(QPointF(left,road+6),QPointF(right,road+6))
    p.setPen(QPen(alpha(ink,65),1))
    for x in range(int(left),int(right-4),17):p.drawLine(QPointF(x,road+3),QPointF(x+6,road+3))
    for x,zipped in ((left,extracting),(right,archive)):
        case=QRectF(x-22,mid.y()-25,44,48)
        p.setBrush(surface);p.setPen(QPen(accent,1.2));p.drawRoundedRect(case,4,4)
        p.setPen(QPen(pink,2));p.drawLine(case.topLeft()+QPointF(5,5),case.topRight()+QPointF(-5,5))
        p.setPen(QPen(alpha(ink,95),.8))
        for y in range(-13,18,6):p.drawLine(QPointF(x-16,mid.y()+y),QPointF(x+16,mid.y()+y))
        p.save();p.translate(x,mid.y()+2);p.scale(.85,.85)
        paper(p,accent,technical=True)
        if zipped:
            p.setPen(QPen(pink,1.5))
            for y in range(-6,9,4):p.drawLine(QPointF(-1,y),QPointF(2,y))
        p.restore()
    if result:
        if result=='done':success(p,mid,accent)
        p.restore();return
    start,end=left+27,right-27
    for index in range(count):
        t=(phase+index/count)%1
        fade=min(1.,t/.12,(1-t)/.12);fade=fade*fade*(3-2*fade)
        travel=1-t if extracting else t
        x=start+(end-start)*travel
        direction=-1 if extracting else 1
        p.save();p.setOpacity(p.opacity()*fade)
        if trails:
            for n in range(1,5):
                p.setPen(QPen(alpha(pink,70/n),1.5))
                dx=-direction*(14+n*5)
                p.drawLine(QPointF(x+dx,mid.y()+14),QPointF(x+dx-direction*3,mid.y()+14))
        if glow:
            halo=QRadialGradient(QPointF(x,road),23)
            halo.setColorAt(0,alpha(pink,glow));halo.setColorAt(1,alpha(accent,0))
            p.setBrush(halo);p.setPen(Qt.PenStyle.NoPen);p.drawEllipse(QPointF(x,road),23,9)
        p.translate(x,mid.y());p.scale(direction,1)
        body=QPainterPath(QPointF(-17,14));body.lineTo(-16,7);body.lineTo(-9,5)
        body.lineTo(-5,-3);body.lineTo(7,-3);body.lineTo(12,5);body.lineTo(18,7)
        body.lineTo(18,14);body.closeSubpath()
        p.setBrush(surface);p.setPen(QPen(ink,1));p.drawPath(body)
        p.setPen(QPen(accent,1.4));p.drawLine(QPointF(-8,5),QPointF(11,5))
        p.setPen(QPen(pink,1.6));p.drawLine(QPointF(-14,13),QPointF(13,13))
        p.setPen(QPen(accent,2));p.drawLine(QPointF(14,8),QPointF(18,8))
        p.setPen(QPen(pink,2));p.drawLine(QPointF(-17,8),QPointF(-14,8))
        p.save();p.translate(0,-8);p.scale(.58,.58);paper(p,accent,technical=True)
        if archive or extracting:
            p.setPen(QPen(pink,1.7))
            for y in range(-6,9,4):p.drawLine(QPointF(-1,y),QPointF(2,y))
        p.restore()
        for dx in (-10,11):
            center=QPointF(dx,16)
            p.setBrush(surface);p.setPen(QPen(ink,1.2));p.drawEllipse(center,3,3)
            angle=travel*math.tau*8
            spoke=QPointF(math.cos(angle)*2.1,math.sin(angle)*2.1)
            p.drawLine(center-spoke,center+spoke)
        p.restore()
    p.restore()


def platform95(p, box, accent, surface, phase, count, trails, glow, archive, extracting, result):
    """Brass parcel trolleys roll between two classic filing cabinets.

    Each trolley and its entire trail fade together at its own wrap point.
    Wheel rotation makes eight whole turns per route, including reverse travel.
    """
    p.save(); mid=box.center(); left=box.left()+31; right=box.right()-31
    ink=QColor('#f5ecda' if surface.lightnessF()<.5 else '#392619')
    rail_y=mid.y()+19
    p.setPen(QPen(alpha(ink,65),1))
    for y in (rail_y,rail_y+4):p.drawLine(QPointF(left,y),QPointF(right,y))
    for x in range(int(left),int(right),13):p.drawLine(QPointF(x,rail_y),QPointF(x+2,rail_y+4))
    for x,zipped in ((left,extracting),(right,archive)):
        case=QRectF(x-20,mid.y()-25,40,51)
        p.setBrush(surface);p.setPen(QPen(ink,1.2));p.drawRect(case)
        p.setPen(QPen(alpha(ink,95),1));p.drawLine(case.topLeft()+QPointF(2,2),case.topRight()+QPointF(-2,2))
        for y in (-19,1):
            drawer=QRectF(x-15,mid.y()+y,30,17)
            p.setBrush(alpha(accent,38));p.setPen(QPen(alpha(ink,155),.8));p.drawRect(drawer)
            p.setPen(QPen(accent,2));p.drawLine(QPointF(x-4,drawer.center().y()),QPointF(x+4,drawer.center().y()))
        if zipped:
            p.setPen(QPen(accent,2))
            for y in range(-19,20,5):p.drawLine(QPointF(x+11,mid.y()+y),QPointF(x+15,mid.y()+y))
    if result:
        if result=='done':success(p,mid,accent)
        p.restore();return
    start,end=left+26,right-26
    for index in range(count):
        t=(phase+index/count)%1
        visibility=min(1.,t/.12,(1-t)/.12)
        visibility=visibility*visibility*(3-2*visibility)
        travel=1-t if extracting else t
        x=start+(end-start)*travel
        p.save();p.setOpacity(p.opacity()*visibility)
        if trails:
            direction=1 if extracting else -1
            for n in range(1,5):
                p.setPen(QPen(alpha(accent,55/n),1.4))
                dx=direction*n*6
                p.drawLine(QPointF(x+dx,mid.y()+6),QPointF(x+dx+direction*3,mid.y()+6))
        if glow:
            halo=QRadialGradient(QPointF(x,mid.y()+9),18)
            halo.setColorAt(0,alpha(accent,glow*.8));halo.setColorAt(1,alpha(accent,0))
            p.setBrush(halo);p.setPen(Qt.PenStyle.NoPen);p.drawEllipse(QPointF(x,mid.y()+9),18,12)
        # A folder sits on the luggage cart; archive jobs carry a tied parcel.
        p.setPen(QPen(ink,1));p.setBrush(accent)
        cargo=QPainterPath();cargo.moveTo(x-10,mid.y()+9);cargo.lineTo(x-10,mid.y()-10)
        cargo.lineTo(x-3,mid.y()-10);cargo.lineTo(x,mid.y()-6);cargo.lineTo(x+10,mid.y()-6)
        cargo.lineTo(x+10,mid.y()+9);cargo.closeSubpath();p.drawPath(cargo)
        p.setPen(QPen(accent.lighter(170),1));p.drawLine(QPointF(x-8,mid.y()-3),QPointF(x+8,mid.y()-3))
        if archive or extracting:
            p.setPen(QPen(ink,1));p.drawLine(QPointF(x,mid.y()-6),QPointF(x,mid.y()+9))
            p.drawLine(QPointF(x-10,mid.y()+2),QPointF(x+10,mid.y()+2))
        p.setPen(QPen(ink,1.6));p.drawLine(QPointF(x-13,mid.y()+11),QPointF(x+13,mid.y()+11))
        p.drawLine(QPointF(x-13,mid.y()+11),QPointF(x-13,mid.y()-5))
        p.drawLine(QPointF(x-13,mid.y()-5),QPointF(x-17,mid.y()-5))
        for dx in (-8,8):
            center=QPointF(x+dx,rail_y-3)
            p.setBrush(surface);p.setPen(QPen(ink,1.1));p.drawEllipse(center,3,3)
            angle=travel*math.tau*8
            spoke=QPointF(math.cos(angle)*2.3,math.sin(angle)*2.3)
            p.drawLine(center-spoke,center+spoke)
        p.restore()
    p.restore()


def mycelium(p, box, accent, surface, phase, count, trails, glow, archive, extracting, result):
    """Documents drift like spores between caps; every wrap fades fully out.

    The clock supplies one complete cycle. Opacity covers the document AND its
    glow/trail; secondary cap breathing uses one whole periodic turn too.
    """
    from mycelium import mushroom
    p.save();mid=box.center();left=box.left()+38;right=box.right()-38
    ivory=QColor('#f2dfc5' if surface.lightnessF()<.5 else '#72546f')
    p.setBrush(Qt.BrushStyle.NoBrush)
    root=QPainterPath(QPointF(left,mid.y()+23))
    root.cubicTo(left+50,mid.y()+34,right-50,mid.y()+30,right,mid.y()+23)
    p.setPen(QPen(alpha(ivory,85),1));p.drawPath(root)
    for x in range(int(left+18),int(right-12),29):
        branch=QPainterPath(QPointF(x,mid.y()+28));branch.quadTo(x+5,mid.y()+21,x+13,mid.y()+20)
        p.setPen(QPen(alpha(ivory,45),.7));p.drawPath(branch)
    for x,zipped in ((left,extracting),(right,archive)):
        halo=QRadialGradient(QPointF(x,mid.y()),32)
        halo.setColorAt(0,alpha(accent,glow*(1.1+.2*math.sin(phase*math.tau))))
        halo.setColorAt(1,alpha(accent,0));p.setPen(Qt.PenStyle.NoPen);p.setBrush(halo)
        p.drawEllipse(QPointF(x,mid.y()),33,31)
        mushroom(p,x,mid.y()+3,1.1,accent,ivory)
        if zipped:
            p.setPen(QPen(accent.darker(170),1.4))
            for y in range(8,22,4):p.drawLine(QPointF(x-1,mid.y()+y),QPointF(x+2,mid.y()+y))
    if result=='done':
        success(p,mid,accent);p.restore();return
    start,end=(right-17,left+17) if extracting else (left+17,right-17)
    def location(t):return QPointF(start+(end-start)*t,mid.y()-9-15*math.sin(t*math.pi))
    for i in range(max(1,count)):
        t=(phase+i/max(1,count))%1
        fade=min(1,t/.16,(1-t)/.16);fade=fade*fade*(3-2*fade)
        p.save();p.setOpacity(p.opacity()*fade)
        spot=location(t)
        if trails:
            for j in range(1,6):
                trail=location(max(0,t-j*.018))
                p.setPen(Qt.PenStyle.NoPen);p.setBrush(alpha(accent,(65-j*9)*fade))
                p.drawEllipse(trail,2.7-j*.3,2.7-j*.3)
        halo=QRadialGradient(spot,15);halo.setColorAt(0,alpha(accent,glow*1.8));halo.setColorAt(1,alpha(accent,0))
        p.setBrush(halo);p.setPen(Qt.PenStyle.NoPen);p.drawEllipse(spot,15,15)
        p.translate(spot);p.rotate(8*math.sin(t*math.tau+i))
        p.scale(.55,.55);paper(p,accent);p.restore()
    p.restore()


def atomicafterglow(p, box, accent, surface, phase, count, trails, glow, archive, extracting, result):
    """A closed phosphor orbit transports documents between instrument bays.

    All motion uses whole turns of the supplied phase. Packet trails follow
    the same closed ellipse, including when an individual packet wraps.
    """
    p.save()
    center = box.center()
    rx, ry = max(18., box.width()/2-77), min(23., box.height()/2-12)
    brass = QColor('#d3cba2' if surface.lightnessF() < .5 else '#686c3d')
    p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(alpha(brass, 80), 1))
    orbit = QRectF(center.x()-rx, center.y()-ry, 2*rx, 2*ry)
    p.drawEllipse(orbit)
    p.setPen(QPen(alpha(accent, 35), 3)); p.drawEllipse(orbit.adjusted(-3, -3, 3, 3))
    for x, zipped in ((box.left()+31, extracting), (box.right()-31, archive)):
        bay = QRectF(x-23, center.y()-27, 46, 54)
        body = QLinearGradient(bay.topLeft(), bay.bottomLeft())
        body.setColorAt(0, surface.lighter(125)); body.setColorAt(.4, surface); body.setColorAt(1, surface.darker(125))
        p.setBrush(body); p.setPen(QPen(brass, 1)); p.drawRoundedRect(bay, 3, 3)
        for dx in (-18, 18):
            for dy in (-22, 22):
                p.setBrush(brass); p.drawEllipse(QPointF(x+dx, center.y()+dy), 1, 1)
        folder(p, QPointF(x, center.y()-1), accent, surface, zipped, True)
        p.setPen(QPen(accent, 2)); p.drawLine(QPointF(x-13, center.y()+22), QPointF(x+13, center.y()+22))
    # Stationary atom with a softly breathing core; sin(tau*phase) closes.
    p.save(); p.translate(center); p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(alpha(brass, 100), .8))
    for angle in (0, 60, 120):
        p.save(); p.rotate(angle); p.drawEllipse(QRectF(-16, -6, 32, 12)); p.restore()
    p.setPen(Qt.PenStyle.NoPen); p.setBrush(alpha(accent, 170+35*math.sin(phase*math.tau)))
    p.drawEllipse(QPointF(), 3, 3); p.restore()
    if result == 'done':
        p.fillRect(QRectF(center.x()-18, center.y()-13, 36, 26), surface)
        success(p, center, accent)
    elif not result:
        for i in range(count):
            t = (phase+i/count) % 1
            def point(turn):
                angle = turn*math.tau
                return center+QPointF(rx*math.cos(angle), ry*math.sin(angle))
            if trails:
                for j in range(1, 7):
                    p.setPen(Qt.PenStyle.NoPen); p.setBrush(alpha(accent, 85*(1-j/7)))
                    p.drawEllipse(point(t-j*.012), 2.4, 2.4)
            pos = point(t)
            p.save(); p.translate(pos)
            if glow:
                bloom = QRadialGradient(QPointF(), 18)
                bloom.setColorAt(0, alpha(accent, glow)); bloom.setColorAt(1, alpha(accent, 0))
                p.setBrush(bloom); p.setPen(Qt.PenStyle.NoPen); p.drawEllipse(QPointF(), 18, 18)
            p.scale(.67, .67); p.rotate(8*math.sin(t*math.tau))
            paper(p, accent, technical=True); p.restore()
    p.restore()


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


def shadowedge(p, box, accent, surface, phase, count, trails, glow, archive, extracting, result):
    """Sealed dispatches cross a silver cutting arc in a quiet rain of sparks."""
    left=QPointF(box.left()+32,box.center().y());right=QPointF(box.right()-32,box.center().y())
    start,end=left+QPointF(35,0),right-QPointF(35,0)
    silver=QColor('#c9cfd8') if surface.lightnessF()<.5 else QColor('#515b69')
    p.setPen(QPen(alpha(silver,45),1));p.drawLine(start,end)
    folder(p,left,silver,surface,extracting,True);folder(p,right,silver,surface,archive,True)
    if result=='done':success(p,box.center(),accent);return
    if result:return
    center=box.center()
    arc=QPainterPath(center+QPointF(-15,22))
    arc.cubicTo(center+QPointF(19,8),center+QPointF(27,-8),center+QPointF(14,-24))
    p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(alpha(accent,75),3));p.drawPath(arc)
    p.setPen(QPen(alpha(silver,210),1));p.drawPath(arc)
    for i in range(count):
        t=(phase+i/count)%1
        pos=start+(end-start)*t+QPointF(0,-math.sin(t*math.pi)*5)
        p.save();p.setOpacity(min(1,t*8,(1-t)*8));p.translate(pos)
        if trails:
            for dy,length in ((-7,22),(0,32),(7,17)):
                p.setPen(QPen(alpha(accent,85 if dy==0 else 35),1))
                p.drawLine(QPointF(-length,dy),QPointF(-10,dy))
        p.rotate(-16+math.sin(t*math.pi)*25)
        p.setPen(QPen(silver,1));p.setBrush(surface)
        p.drawRect(QRectF(-9,-7,18,14))
        p.drawLine(QPointF(-9,-7),QPointF(0,1));p.drawLine(QPointF(9,-7),QPointF(0,1))
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(accent);p.drawRect(QRectF(-2,-1,4,4))
        p.restore()
    if glow:
        glint=QPointF(center.x()+8,center.y()-4)
        shine=QRadialGradient(glint,12);shine.setColorAt(0,alpha(silver,glow));shine.setColorAt(1,alpha(silver,0))
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(shine);p.drawEllipse(glint,12,12)


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


def gildedhollow(p, box, accent, surface, phase, count, trails, glow, archive, extracting, result):
    """Little brass minecarts carry documents along a lantern-lit rail."""
    p.save()
    left,right=QPointF(box.left()+32,box.center().y()),QPointF(box.right()-32,box.center().y())
    start,end=left.x()+33,right.x()-33
    p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(alpha(accent,60),1))
    for offset in (10,14):p.drawLine(QPointF(start,left.y()+offset),QPointF(end,left.y()+offset))
    for x in range(round(start),round(end),14):p.drawLine(QPointF(x,left.y()+9),QPointF(x+2,left.y()+16))
    folder(p,left,accent,surface,extracting,True);folder(p,right,accent,surface,archive,True)
    if result=='done':success(p,box.center(),accent)
    elif not result:
        for index in range(count):
            t=(phase+index/count)%1;point=QPointF(start+(end-start)*t,left.y())
            p.save();p.translate(point);p.setOpacity(min(1,t*8,(1-t)*8))
            if glow:
                light=QRadialGradient(QPointF(0,-5),22);light.setColorAt(0,alpha(accent,glow*1.4));light.setColorAt(1,alpha(accent,0))
                p.setBrush(light);p.setPen(Qt.PenStyle.NoPen);p.drawEllipse(QPointF(0,-5),22,22)
            fill=QLinearGradient(0,-11,0,8);fill.setColorAt(0,accent.lighter(160));fill.setColorAt(.25,accent);fill.setColorAt(1,accent.darker(250))
            p.setPen(QPen(accent.lighter(130),.8));p.setBrush(fill)
            cart=QPainterPath(QPointF(-10,-5));cart.lineTo(10,-5);cart.lineTo(7,7);cart.lineTo(-7,7);cart.closeSubpath();p.drawPath(cart)
            p.setBrush(surface);p.drawEllipse(QPointF(-6,10),2.5,2.5);p.drawEllipse(QPointF(6,10),2.5,2.5)
            p.setBrush(accent.lighter(140));p.drawRoundedRect(QRectF(-5,-14,10,9),1,1)
            p.setPen(QPen(surface,.8));p.drawLine(QPointF(-3,-11),QPointF(2,-11));p.drawLine(QPointF(-3,-8),QPointF(1,-8))
            if trails:
                spark=QPointF(-12,-11-4*math.sin(t*math.tau));p.setPen(QPen(alpha(accent.lighter(170),170),1))
                p.drawLine(spark-QPointF(2,0),spark+QPointF(2,0));p.drawLine(spark-QPointF(0,2),spark+QPointF(0,2))
            p.restore()
    p.restore()


def hollowgrove(p, box, accent, surface, phase, count, trails, glow, archive, extracting, result):
    """Leaf letters drift between folders along a gently curving branch."""
    left=QPointF(box.left()+32,box.center().y());right=QPointF(box.right()-32,box.center().y())
    folder(p,left,accent,surface,extracting,True);folder(p,right,accent,surface,archive,True)
    if result=='done':success(p,box.center(),accent);return
    if result:return
    route=QPainterPath(left+QPointF(34,0));route.cubicTo(box.center()+QPointF(-35,-16),box.center()+QPointF(35,16),right-QPointF(34,0))
    p.setPen(QPen(alpha(accent,55),1));p.drawPath(route)
    for index in range(count):
        t=(phase+index/count)%1
        p.save();p.translate(route.pointAtPercent(t));p.rotate(math.sin(t*math.tau)*18-12)
        p.setOpacity(min(1,t*9,(1-t)*9));leaf=QPainterPath(QPointF(-9,5));leaf.cubicTo(-10,-8,5,-11,10,-7);leaf.cubicTo(12,5,-1,12,-9,5)
        p.setBrush(alpha(accent,100));p.setPen(QPen(accent,1));p.drawPath(leaf);p.drawLine(QPointF(-8,6),QPointF(8,-6))
        if trails:
            p.setPen(QPen(alpha(accent,70),1));p.drawLine(QPointF(-17,6),QPointF(-23,6))
        p.restore()


def hyperfusionblue(p, box, accent, surface, phase, count, trails, glow, archive, extracting, result):
    p.save();p.setRenderHint(QPainter.RenderHint.Antialiasing)
    c=QColor(accent);base=QColor(surface);ink=QColor('#d7edfa')
    y=box.center().y();left=box.left()+22;right=box.right()-22
    rail=QLinearGradient(left,y-5,left,y+5);rail.setColorAt(0,ink);rail.setColorAt(.25,base);rail.setColorAt(1,c)
    p.setPen(Qt.PenStyle.NoPen);p.setBrush(rail);p.drawRoundedRect(QRectF(left,y-4,right-left,8),4,4)
    for x in (left,right):
        bay=QLinearGradient(x-12,y-20,x+12,y+20);bay.setColorAt(0,ink);bay.setColorAt(.12,c);bay.setColorAt(.5,base);bay.setColorAt(1,c.darker(160))
        p.setBrush(bay);p.setPen(QPen(ink,1));p.drawRoundedRect(QRectF(x-13,y-21,26,42),5,5)
        p.setPen(QPen(c,2));p.drawLine(QPointF(x-7,y+15),QPointF(x+7,y+15))
    for i in range(max(1,count)):
        t=(phase+i/max(1,count))%1.;x=left+20+t*max(1,right-left-40)
        if extracting:x=right-20-t*max(1,right-left-40)
        p.save();p.setOpacity(min(1,t*10,(1-t)*10))
        if trails:
            tail=QColor(c);tail.setAlpha(55);p.setPen(QPen(tail,3));p.drawLine(QPointF(x-14,y),QPointF(x,y))
        p.setBrush(c);p.setPen(QPen(ink,1));p.drawRoundedRect(QRectF(x-5,y-7,10,14),2,2)
        p.setPen(QPen(ink,.6));p.drawLine(QPointF(x-2,y-3),QPointF(x+2,y-3))
        p.restore()
    p.restore()


def blackwood(p, box, accent, surface, phase, count, trails, glow, archive, extracting, result):
    """Sealed document boats cross a quiet cove between two brass beacons."""
    p.save();p.setRenderHint(QPainter.RenderHint.Antialiasing)
    left=box.left()+25;right=box.right()-25;y=box.center().y()+4
    brass=QColor(accent).lighter(145);base=QColor(surface)
    for row in (10,15):
        wave=QPainterPath();wave.moveTo(left,y+row)
        for x in range(int(left),int(right)+1,4):wave.lineTo(x,y+row+math.sin(x*.08-phase*math.tau)*1.7)
        p.setPen(QPen(alpha(accent,65),.8));p.drawPath(wave)
    for x in (left,right):
        tower=QPainterPath();tower.moveTo(x-7,y+10);tower.lineTo(x-4,y-21);tower.lineTo(x+4,y-21);tower.lineTo(x+7,y+10);tower.closeSubpath()
        p.setBrush(base);p.setPen(QPen(brass,1));p.drawPath(tower)
        p.setBrush(brass);p.drawRect(QRectF(x-4,y-23,8,7));p.drawLine(QPointF(x-7,y-25),QPointF(x+7,y-25))
        if glow:
            beam=QPainterPath(QPointF(x,y-20));beam.lineTo(x+(25 if x==left else -25),y-29);beam.lineTo(x+(25 if x==left else -25),y-16);beam.closeSubpath()
            p.fillPath(beam,alpha(brass,18+int(12*math.sin(phase*math.tau))))
    if result=='done':success(p,box.center(),accent);p.restore();return
    if result:p.restore();return
    for index in range(max(1,count)):
        t=(phase+index/max(1,count))%1
        x=left+20+t*max(1,right-left-40)
        if extracting:x=right-20-t*max(1,right-left-40)
        p.save();p.translate(x,y+math.sin((t+phase)*math.tau)*1.3);p.setOpacity(min(1,t*10,(1-t)*10))
        p.setPen(QPen(brass,1));p.setBrush(base)
        p.drawRoundedRect(QRectF(-7,-16,14,15),1,1)
        p.drawLine(QPointF(-4,-12),QPointF(4,-12));p.drawLine(QPointF(-4,-9),QPointF(2,-9))
        hull=QPainterPath();hull.moveTo(-14,-1);hull.lineTo(14,-1);hull.lineTo(9,7);hull.lineTo(-9,7);hull.closeSubpath();p.setBrush(accent);p.drawPath(hull)
        if archive:p.setBrush(brass);p.drawRect(QRectF(-1,-16,2,15))
        if trails:p.setPen(QPen(alpha(accent,70),.8));p.drawLine(QPointF(-22,7),QPointF(-16,7))
        p.restore()
    p.restore()


def midnighttransit(p, box, accent, surface, phase, count, trails, glow, archive, extracting, result):
    """Small document carriages travel between station platforms."""
    p.save();p.setRenderHint(QPainter.RenderHint.Antialiasing)
    left=box.left()+27;right=box.right()-27;y=box.center().y()
    ink=QColor(accent).lighter(145);base=QColor(surface)
    p.setPen(QPen(alpha(ink,95),1))
    for x in range(int(left),int(right),10):p.drawLine(QPointF(x,y+11),QPointF(x+3,y+17))
    for offset in (10,16):p.drawLine(QPointF(left,y+offset),QPointF(right,y+offset))
    for x in (left,right):
        p.setBrush(base);p.setPen(QPen(ink,1));p.drawRoundedRect(QRectF(x-10,y-22,20,39),4,4)
        p.setBrush(accent);p.drawEllipse(QPointF(x,y-13),3,3)
        p.drawLine(QPointF(x-5,y+8),QPointF(x+5,y+8))
    if result=='done':success(p,box.center(),accent);p.restore();return
    if result:p.restore();return
    for index in range(max(1,count)):
        t=(phase+index/max(1,count))%1
        x=left+23+t*max(1,right-left-46)
        if extracting:x=right-23-t*max(1,right-left-46)
        p.setOpacity(min(1,t*10,(1-t)*10))
        p.setBrush(base);p.setPen(QPen(ink,1));p.drawRoundedRect(QRectF(x-12,y-9,24,18),3,3)
        p.setBrush(accent);p.setPen(Qt.PenStyle.NoPen)
        for offset in (-7,1):p.drawRoundedRect(QRectF(x+offset,y-5,6,6),1,1)
        p.setBrush(ink)
        for offset in (-7,7):p.drawEllipse(QPointF(x+offset,y+10),2,2)
        if archive:
            p.setPen(QPen(accent,1.2));p.drawLine(QPointF(x,y-8),QPointF(x,y+8))
        if trails:
            p.setPen(QPen(alpha(accent,65),1));p.drawLine(QPointF(x-20,y+1),QPointF(x-15,y+1))
    p.restore()
