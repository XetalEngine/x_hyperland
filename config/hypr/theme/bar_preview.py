"""Visual taskbar variations shared by every theme and palette."""
from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QSizePolicy, QWidget
import bar_styles
import runtime


class VariationCard(QPushButton):
    def __init__(self, variation):
        super().__init__();self.variation=variation;self.design=runtime.design()
        self.setCheckable(True);self.setMinimumSize(105,82)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
        self.setAccessibleName(bar_styles.VARIANTS[variation]);self.setToolTip(bar_styles.VARIANTS[variation])
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c=runtime.colors();a=QColor(c['Accent'])
        if not self.isEnabled():p.setOpacity(.5)
        p.setPen(QPen(a if self.isChecked() else QColor(c['Midlight']),2 if self.isChecked() else 1))
        p.setBrush(QColor(c['AlternateBase'] if self.isChecked() else c['Window']))
        p.drawRoundedRect(QRectF(1,1,self.width()-2,self.height()-2),10,10)
        p.setPen(QColor(c['Text']))
        p.drawText(QRectF(4,6,self.width()-8,22),Qt.AlignmentFlag.AlignCenter,
                   {'full':'Full','partial':'Partial','centered':'Centered'}[self.variation])
        p.translate(10,37);w=self.width()-20
        radius={'raw':1,'breakpoint':3,'binaryknife':2,'porcelainink':2,'obsidianforge':3,'shadowedge':2}.get(self.design,10)
        gradient=QLinearGradient(0,0,0,24);gradient.setColorAt(0,QColor(c['Button']));gradient.setColorAt(1,QColor(c['Base']))
        p.setBrush(gradient);p.setPen(QPen(a,.8))
        if self.variation=='partial':
            for x,length in ((0,w*.44),(w*.48,w*.17),(w*.69,w*.31)):
                p.drawRoundedRect(QRectF(x,0,length,23),radius,radius)
        else:p.drawRoundedRect(QRectF(0,0,w,23),radius,radius)
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(a)
        p.drawRoundedRect(QRectF(5,8,8,7),2,2)
        start=w*.41 if self.variation=='centered' else 19
        size=min(5.,w*.035)
        for i in range(3):
            p.setOpacity(.95 if i==1 else .35);p.drawRoundedRect(QRectF(start+i*(size+3),8,size,7),radius/3,radius/3)
        p.setOpacity(.7);p.setBrush(QColor(c['Text']))
        for i in range(3):p.drawRoundedRect(QRectF(w-7-i*5,9,2,5),1,1)
        if self.design in ('hollowgrove','gildedhollow'):
            p.setPen(QPen(a,.7));p.drawLine(5,19,int(w-5),19)


class VariationPicker(QWidget):
    valueChanged=pyqtSignal(str)
    def __init__(self):
        super().__init__();self.cards={};self._value='full'
        row=QHBoxLayout(self);row.setContentsMargins(0,0,0,0);row.setSpacing(6)
        for value in bar_styles.VARIANTS:
            card=VariationCard(value);card.clicked.connect(lambda _,v=value:self.setValue(v))
            row.addWidget(card);self.cards[value]=card
        self.setValue('full')
    def value(self):return self._value
    def setValue(self,value):
        if value not in self.cards:raise ValueError('Unknown taskbar variation.')
        changed=value!=self._value;self._value=value
        for key,card in self.cards.items():card.setChecked(key==value)
        if changed:self.valueChanged.emit(value)
    def setDesign(self,value):
        for card in self.cards.values():card.design=value;card.update()
