"""Cursor gallery with a local, interactive effect preview."""
from copy import deepcopy
import math
import time
from PyQt6.QtCore import Qt,QTimer,QRectF,QByteArray,QPointF,QSize
from PyQt6.QtGui import QPainter,QColor,QPen,QPixmap,QIcon
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QPushButton,
    QGroupBox,QFormLayout,QComboBox,QSpinBox,QCheckBox,QColorDialog,QScrollArea)
from . import model,art,controller


class Preview(QWidget):
    def __init__(self):
        super().__init__();self.values=deepcopy(model.DEFAULTS);self.points=[];self.ripples=[]
        self.setMinimumHeight(135);self.setMouseTracking(True)
        self.timer=QTimer(self);self.timer.timeout.connect(self.advance);self.timer.setInterval(16)
    def mouseMoveEvent(self,event):
        if self.values['trail']!='none':self.points.append((event.position(),time.monotonic()));self.points=self.points[-64:];self.timer.start()
    def mousePressEvent(self,event):
        if self.values['click_ripple']:self.ripples.append((event.position(),time.monotonic()));self.timer.start()
    def advance(self):
        cutoff=time.monotonic()-self.values['duration']/1000
        self.points=[p for p in self.points if p[1]>cutoff];self.ripples=[p for p in self.ripples if p[1]>cutoff]
        self.update()
        if not self.points and not self.ripples:self.timer.stop()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        now=time.monotonic();color=QColor(self.values['color']);lifetime=self.values['duration']/1000
        for point,born in self.points:
            fade=max(0,1-(now-born)/lifetime);color.setAlphaF(fade*self.values['intensity']/100)
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(color);radius=(10 if self.values['trail']=='glow' else 4)*fade
            if self.values['trail']=='sparkle':
                p.setPen(QPen(color,2));p.drawLine(QPointF(point.x()-radius,point.y()),QPointF(point.x()+radius,point.y()));p.drawLine(QPointF(point.x(),point.y()-radius),QPointF(point.x(),point.y()+radius))
            else:p.drawEllipse(point,radius,radius)
        for point,born in self.ripples:
            age=(now-born)/lifetime;color.setAlphaF(max(0,1-age));p.setPen(QPen(color,2));p.setBrush(Qt.BrushStyle.NoBrush);p.drawEllipse(point,6+age*27,6+age*27)
        for index,shape in enumerate(('left_ptr','hand2','xterm','sb_h_double_arrow','watch')):
            renderer=QSvgRenderer(QByteArray(art.svg(self.values['style'],shape)[0].encode()))
            renderer.render(p,QRectF(22+index*72,22,46,46))
        p.setPen(self.palette().color(self.foregroundRole()));p.drawText(22,109,'Move and click here to preview your effects')


class CursorsPage(QWidget):
    def __init__(self,async_run):
        super().__init__();self.async_run=async_run;self.busy=self.dirty=self.loading=False
        self.baseline,self.token=model.load();self.draft=deepcopy(self.baseline)
        root=QVBoxLayout(self);title=QLabel('Cursors');title.setObjectName('brand');root.addWidget(title)
        root.addWidget(QLabel('A finishing touch for your desktop. Cursor style, trails and click feedback are independent.'))
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body=QWidget();layout=QVBoxLayout(body)
        self.preview=Preview();layout.addWidget(self.preview)
        gallery=QHBoxLayout();self.styles={}
        for key,(name,*_) in art.STYLES.items():
            button=QPushButton(name);button.setCheckable(True);button.clicked.connect(lambda _,k=key:self.choose_style(k))
            pixmap=QPixmap(42,42);pixmap.fill(Qt.GlobalColor.transparent);painter=QPainter(pixmap)
            QSvgRenderer(QByteArray(art.svg(key)[0].encode())).render(painter);painter.end()
            button.setIcon(QIcon(pixmap));button.setIconSize(QSize(42,42))
            button.setMinimumHeight(65);button.setAccessibleName(name+' cursor');self.styles[key]=button;gallery.addWidget(button)
        layout.addLayout(gallery)
        group=QGroupBox('Pointer & effects');form=QFormLayout(group);self.fields={}
        for key,title,lo,hi,suffix in [('size','Cursor size',20,64,' px'),('duration','Trail lifetime',100,1000,' ms'),('intensity','Effect opacity',10,100,'%')]:
            spin=QSpinBox();spin.setRange(lo,hi);spin.setSuffix(suffix);spin.valueChanged.connect(lambda value,k=key:self.edit(k,value));self.fields[key]=spin;form.addRow(title,spin)
        trail=QComboBox()
        for key,title in model.TRAILS.items():trail.addItem(title,key)
        trail.currentIndexChanged.connect(lambda:self.edit('trail',trail.currentData()));self.fields['trail']=trail;form.insertRow(1,'Mouse trail',trail)
        ripple=QCheckBox('Ripple when I click');ripple.toggled.connect(lambda value:self.edit('click_ripple',value));self.fields['click_ripple']=ripple;form.addRow(ripple)
        self.color=QPushButton('Effect color');self.color.clicked.connect(self.choose_color);form.addRow('Color',self.color);layout.addWidget(group);layout.addStretch()
        scroll.setWidget(body);root.addWidget(scroll,1)
        self.status=QLabel('Effects are optional. Your other desktop sessions keep their own cursors.');self.status.setWordWrap(True);root.addWidget(self.status)
        row=QHBoxLayout();defaults=QPushButton('Defaults');defaults.clicked.connect(lambda:self.fill(model.DEFAULTS));row.addWidget(defaults);row.addStretch()
        self.reload=QPushButton('Reload');self.reload.clicked.connect(lambda:self.refresh(True));row.addWidget(self.reload)
        self.discard=QPushButton('Discard');self.discard.clicked.connect(lambda:self.fill(self.baseline));row.addWidget(self.discard)
        self.apply=QPushButton('Apply cursors');self.apply.setObjectName('primary');self.apply.clicked.connect(self.save);row.addWidget(self.apply);root.addLayout(row)
        self.body=body;self.fill(self.baseline)
    def fill(self,values):
        self.loading=True;self.draft=deepcopy(values)
        for key,field in self.fields.items():
            if isinstance(field,QSpinBox):field.setValue(values[key])
            elif isinstance(field,QComboBox):field.setCurrentIndex(field.findData(values[key]))
            else:field.setChecked(values[key])
        self.loading=False;self.changed()
    def edit(self,key,value):
        if self.loading:return
        self.draft[key]=value;self.changed()
    def choose_style(self,key):self.edit('style',key)
    def choose_color(self):
        color=QColorDialog.getColor(QColor(self.draft['color']),self,'Pointer effect color')
        if color.isValid():self.edit('color',color.name())
    def changed(self):
        self.dirty=self.draft!=self.baseline;self.preview.values=deepcopy(self.draft);self.preview.update()
        for key,button in self.styles.items():button.setChecked(key==self.draft['style'])
        self.color.setText(self.draft['color']);self.body.setEnabled(not self.busy)
        self.apply.setEnabled(self.dirty and not self.busy);self.discard.setEnabled(self.dirty and not self.busy);self.reload.setEnabled(not self.busy)
    def refresh(self,force=False):
        if self.busy or (self.dirty and not force):return
        try:self.baseline,self.token=model.load();self.fill(self.baseline)
        except (OSError,ValueError) as error:self.failed(str(error))
    def save(self):
        self.busy=True;self.changed();self.status.setText('Applying cursor style and effects…')
        self.async_run(lambda:controller.save(self.draft,self.token),self.saved,self.failed)
    def saved(self,result):
        self.baseline,self.token=result;self.busy=False;self.fill(self.baseline);self.status.setText('Saved. Cursor style and effects are active.')
    def failed(self,error):self.busy=False;self.changed();self.status.setText(str(error))
