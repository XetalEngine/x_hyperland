"""Interactive previews of the procedural mouse trails."""
import math
import time
from PyQt6.QtCore import Qt,QPointF,QRectF,QTimer
from PyQt6.QtGui import QColor,QPainter,QPen,QPolygonF,QRadialGradient
from PyQt6.QtWidgets import QWidget
from . import model,effects

def paint_trail(p,values,marks,now,design=None):
    style=effects.resolve(values['trail'],design)
    accent,secondary=effects.colors(values,design)
    colors=[QColor(accent),QColor(secondary),QColor('#20252b' if style=='ink' else '#ffe1a3' if style=='cinder' else '#fff0d9' if style=='cloud' else '#f4f6f9' if style=='blade' else '#f2ffff')]
    duration=values['duration']/1000;opacity=values['intensity']/100
    def color(index,alpha):
        c=QColor(colors[index]);c.setAlphaF(max(0,min(1,alpha*opacity)));return c
    def line(a,b,width,alpha,index=0):
        p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(color(index,alpha),width,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap));p.drawLine(a,b)
    def disc(at,r,alpha,index=0,glow=False):
        c=color(index,alpha);p.setPen(Qt.PenStyle.NoPen)
        if glow:
            gradient=QRadialGradient(at,r);gradient.setColorAt(0,c);c.setAlpha(0);gradient.setColorAt(1,c);p.setBrush(gradient)
        else:p.setBrush(c)
        p.drawEllipse(at,r,r)
    def ring(at,r,alpha,index=0,tilt=1,angle=0):
        p.save();p.translate(at);p.rotate(math.degrees(angle));p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(color(index,alpha),1.25));p.drawEllipse(QRectF(-r,-r*tilt,2*r,2*r*tilt));p.restore()
    def polar(a,r):return QPointF(math.cos(a)*r,math.sin(a)*r)
    for i,(at,born,seed,click) in enumerate(marks):
        age=max(0,min(1,(now-born)/duration));fade=(1-age)**2
        if not fade:continue
        if click:ring(at,6+age*34,fade,1);continue
        if style=='none':continue
        previous=marks[i-1][0] if i else at;delta=at-previous;distance=math.hypot(delta.x(),delta.y())
        d=delta/distance if distance>.01 else QPointF(1,0);n=QPointF(-d.y(),d.x());angle=math.atan2(d.y(),d.x())
        joined=i>0 and not marks[i-1][3] and distance<64;random=seed*.61803398875
        if style=='plasma':
            if joined:
                for sign,index in ((1,0),(-1,1)):
                    offset=n*(math.sin(born*24+age*8)*7*sign);old=previous+n*(math.sin(marks[i-1][1]*24+(now-marks[i-1][1])/duration*8)*7*sign)
                    line(old,at+offset,7,fade*.18);line(old,at+offset,1.5,fade,index)
            if seed%4==0:disc(at,10,fade*.3,glow=True);disc(at,1.8,fade,2)
        elif style=='orbit':
            if seed%3:continue
            rotation=random+age*3;r=4+age*15
            disc(at,r*1.5,fade*.18,glow=True);ring(at,r,fade,0,.55,rotation);ring(at,r*.75,fade*.7,1,.55,-rotation);disc(at+polar(rotation,r),2.1,fade,2)
        elif style=='fracture':
            if seed%2:continue
            side=1 if seed%4 else -1;at=at+n*(side*age*26)-d*(age*10);a=angle+random+age*side*4;size=2+seed%5
            tip=at+polar(a,size*1.6);left=at+polar(a+2.5,size);right=at+polar(a-2.5,size*.6)
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(color(1 if seed%3==0 else 0,fade));p.drawPolygon(QPolygonF([tip,left,right]));line(tip,left,.8,fade*.8,2)
        elif style=='circuit':
            if joined:
                elbow=QPointF(at.x(),previous.y());line(previous,elbow,1.4,fade);line(elbow,at,1.4,fade)
            if seed%5:continue
            point=at+n*(age*18)+QPointF(0,age*18)
            if seed%2:line(point+QPointF(0,-5),point+QPointF(0,5),1.2,fade,1);line(point+QPointF(-2,-3),point+QPointF(0,-5),1.2,fade,1)
            else:
                corners=[point+QPointF(x,y) for x,y in ((-3,-5),(3,-5),(3,5),(-3,5),(-3,-5))]
                for a,b in zip(corners,corners[1:]):line(a,b,1.2,fade,1)
            disc(at,1.5,fade,2)
        elif style=='tidal':
            if joined:line(previous,at,5,fade*.17)
            if seed%3:continue
            at=at+QPointF(math.sin(random+age*4)*age*13,-age*28);r=2+seed%6+age*5
            disc(at,r*2,fade*.22,glow=True);ring(at,r,fade*.8);disc(at+QPointF(-r*.35,-r*.45),1.4,fade,2);disc(at+n*12,1.1,fade*.7,1)
        elif style=='ink':
            if joined:line(previous,at,5*fade+.7,fade*.5,1);line(previous,at,3.6*fade+.4,fade,2)
            if seed%4:continue
            at=at+n*(math.sin(random)*age*24)+QPointF(age*8,age*14);a=random+age*2;tip=polar(a,4);side=polar(a+math.pi/2,1.8)
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(color(0,fade));p.drawPolygon(QPolygonF([at+tip,at+side,at-tip,at-side]));disc(at+n*6,1.1,fade,2)
        elif style=='blade':
            if joined:line(previous,at,4,fade*.12);line(previous,at,.9,fade*.85,2)
            if seed%6:continue
            side=1 if seed%12 else -1
            center=at+n*(side*age*14)-d*(age*14);r=3+age*13;rotation=angle+side*age*1.7
            for j in range(8):
                a=rotation+side*(-.8+j*1.5/8)
                line(center+polar(a,r),center+polar(a+side*1.5/8,r),.4+math.sin(j*math.pi/8)*2*(1-age),fade*.8)
            needle=at+n*(side*(4+age*24))+d*(age*6)
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(color(1,fade))
            p.drawPolygon(QPolygonF([needle+d*5,needle-d*3+n*1.2,needle-d*3-n*1.2]))
        elif style=='cloud':
            if joined:line(previous,at,5,fade*.16,1);line(previous,at,1.3,fade*.7)
            if seed%5:continue
            at+=QPointF(math.sin(random+age*2)*age*12,-age*22);r=3.5+age*3
            disc(at+QPointF(0,1),r*2.5,fade*.22,1,True)
            disc(at+QPointF(-r*.8,r*.35),r*.75,fade*.7)
            disc(at+QPointF(r*.85,r*.35),r*.8,fade*.7)
            disc(at+QPointF(0,-r*.1),r,fade*.82)
            line(at+QPointF(-r*.3,-r*.7),at+QPointF(r*.25,-r*.7),.9,fade*.8,2)
            star=at+QPointF(math.sin(random)*15,9+age*13);rotation=random+age*1.8;size=2+math.sin(age*math.pi)*2
            points=[star+polar(rotation+arm*math.pi/4,size if arm%2==0 else size*.26) for arm in range(8)]
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(color(2,fade));p.drawPolygon(QPolygonF(points))
        elif style=='cinder':
            if joined:
                line(previous,at,8,fade*.18);line(previous,at,3,fade,1);line(previous,at,1.1,fade*(1-age),2)
            if seed%4:continue
            side=1 if seed%8 else -1
            crack=at+n*(side*7)+d*3
            line(at,crack,1.2,fade*.6,1);line(crack,crack+n*(side*4)-d*4,.8,fade*.4)
            ember=at+QPointF(math.sin(random)*age*22,-age*(22+seed%14))
            disc(ember,6*(1-age)+1,fade*.45,glow=True)
            line(ember+QPointF(-age*2,3+age*3),ember,1.4,fade)
            disc(ember,1.3*(1-age)+.3,fade,2)
        elif style=='sparkle':line(at+QPointF(-4*fade,0),at+QPointF(4*fade,0),1.4,fade);line(at+QPointF(0,-4*fade),at+QPointF(0,4*fade),1.4,fade)
        else:disc(at,(12 if style=='glow' else 4)*fade,fade,glow=style=='glow')


class MousePreview(QWidget):
    def __init__(self):
        super().__init__();self.values=dict(model.DEFAULTS);self.marks=[];self.serial=0;self.hovered=False;self.point=None
        self.setMinimumHeight(160);self.setMouseTracking(True);self.setAccessibleName('Mouse effect preview')
        self.timer=QTimer(self);self.timer.timeout.connect(self.advance)
    def showEvent(self,event):
        rate=self.screen().refreshRate() if self.screen() else 60
        self.timer.start(max(4,round(1000/max(30,rate))));super().showEvent(event)
    def hideEvent(self,event):self.timer.stop();self.marks.clear();super().hideEvent(event)
    def enterEvent(self,event):self.hovered=True;super().enterEvent(event)
    def leaveEvent(self,event):self.hovered=False;self.point=None;super().leaveEvent(event)
    def append(self,point,click=False):
        if self.values['trail']=='none' and not click:return
        self.serial+=1;self.marks.append((point,time.monotonic(),self.serial,click));self.marks=self.marks[-160:];self.point=point
    def mouseMoveEvent(self,event):self.append(event.position())
    def mousePressEvent(self,event):
        if self.values['click_ripple']:self.append(event.position(),True)
    def advance(self):
        now=time.monotonic();self.marks=[m for m in self.marks if now-m[1]<self.values['duration']/1000]
        if not self.hovered and self.values['trail']!='none':
            self.append(QPointF(self.width()/2+math.sin(now*2.3)*self.width()*.33,65+math.sin(now*4.6)*25))
        self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(),self.palette().base());paint_trail(p,self.values,self.marks,time.monotonic())
        p.setPen(self.palette().text().color())
        if self.point:
            p.setBrush(self.palette().text());at=self.point
            p.drawPolygon(QPolygonF([at,at+QPointF(0,13),at+QPointF(4,9),at+QPointF(10,9)]))
        p.drawText(QRectF(10,self.height()-30,self.width()-20,24),Qt.AlignmentFlag.AlignCenter,
                   'Move here to steer the preview · Click to try ripple feedback')
