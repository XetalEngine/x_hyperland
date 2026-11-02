"""Theme → Window effects → Mouse effects, sharing the cursor preference store."""
from copy import deepcopy
import math
from PyQt6.QtCore import Qt,QPointF,QSize
from PyQt6.QtGui import QPainter,QPixmap,QIcon,QColor
from PyQt6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QPushButton,
    QGroupBox,QFormLayout,QComboBox,QSpinBox,QCheckBox,QColorDialog,QScrollArea,QMessageBox)
from . import model,effects,controller
from .mouse_preview import MousePreview,paint_trail


class MouseEffectsPage(QWidget):
    def __init__(self,async_run):
        super().__init__();self.async_run=async_run;self.busy=self.dirty=self.loading=False
        error=''
        try:self.baseline,self.token=model.load()
        except (ValueError,OSError) as exc:self.baseline,self.token=dict(model.DEFAULTS),None;error=str(exc)
        self.draft=deepcopy(self.baseline)
        root=QVBoxLayout(self);root.setContentsMargins(16,12,16,12)
        title=QLabel('Mouse effects');title.setObjectName('brand');root.addWidget(title)
        intro=QLabel('Six different ways to leave your mark. Follow your desktop theme, or choose any effect to make it your own.');intro.setWordWrap(True);intro.setObjectName('muted');root.addWidget(intro)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.body=QWidget();layout=QVBoxLayout(self.body)
        row=QHBoxLayout();row.addWidget(QLabel('Mouse trail'));self.trail=QComboBox()
        for key,label in model.TRAILS.items():self.trail.addItem(label,key)
        self.trail.currentIndexChanged.connect(self.choose);row.addWidget(self.trail,1);layout.addLayout(row)
        self.preview=MousePreview();layout.addWidget(self.preview)
        grid=QGridLayout();self.cards={}
        from theme.designs import DESIGNS
        for i,(key,(design,name,accent,_,description)) in enumerate(effects.STYLES.items()):
            button=QPushButton(name+'\n'+DESIGNS[design]);button.setCheckable(True);button.setMinimumHeight(82)
            button.setToolTip(description);button.clicked.connect(lambda _,k=key:self.select(k));button.setAccessibleName(name+' — '+DESIGNS[design])
            pixmap=QPixmap(116,56);pixmap.fill(Qt.GlobalColor.transparent);p=QPainter(pixmap);p.setRenderHint(QPainter.RenderHint.Antialiasing)
            marks=[(QPointF(10+j*2.7,28+math.sin(j*.2)*12),1-j*.009,j,False) for j in range(35)]
            paint_trail(p,dict(model.DEFAULTS,trail=key,color=accent,duration=700),marks,1.1);p.end()
            button.setIcon(QIcon(pixmap));button.setIconSize(QSize(116,56));grid.addWidget(button,i//3,i%3);self.cards[key]=button
        layout.addLayout(grid)
        self.description=QLabel();self.description.setWordWrap(True);self.description.setObjectName('muted');layout.addWidget(self.description)
        options=QGroupBox('Motion & feedback');form=QFormLayout(options);self.fields={}
        for key,label,lo,hi,suffix in [('duration','Trail lifetime',100,1000,' ms'),('intensity','Opacity',10,100,'%')]:
            field=QSpinBox();field.setRange(lo,hi);field.setSuffix(suffix);field.setKeyboardTracking(False)
            field.valueChanged.connect(lambda value,k=key:self.edit(k,value));self.fields[key]=field;form.addRow(label,field)
        self.color=QPushButton();self.color.clicked.connect(self.choose_color);form.addRow('Accent color',self.color)
        ripple=QCheckBox('Ripple when I click');ripple.toggled.connect(lambda value:self.edit('click_ripple',value));self.fields['click_ripple']=ripple;form.addRow(ripple)
        layout.addWidget(options);layout.addStretch();scroll.setWidget(self.body);root.addWidget(scroll,1)
        self.status=QLabel(error or 'Trails follow each display’s frames and stop drawing after they fade. Choose Off to disable the trail.');self.status.setWordWrap(True);self.status.setObjectName('muted');root.addWidget(self.status)
        row=QHBoxLayout();self.defaults=QPushButton('System defaults');self.defaults.clicked.connect(self.reset_defaults);row.addWidget(self.defaults);row.addStretch()
        self.reload=QPushButton('Reload');self.reload.clicked.connect(lambda:self.refresh(True));row.addWidget(self.reload)
        self.discard=QPushButton('Discard');self.discard.clicked.connect(lambda:self.fill(self.baseline));row.addWidget(self.discard)
        self.apply=QPushButton('Apply mouse effects');self.apply.setObjectName('primary');self.apply.clicked.connect(self.save);row.addWidget(self.apply);root.addLayout(row)
        self.fill(self.baseline)
    def fill(self,values):
        self.loading=True;self.draft=deepcopy(values);self.trail.setCurrentIndex(self.trail.findData(values['trail']))
        for key,field in self.fields.items():
            if isinstance(field,QCheckBox):field.setChecked(values[key])
            else:field.setValue(values[key])
        self.loading=False;self.changed()
    def choose(self):
        if self.loading:return
        self.select(self.trail.currentData())
    def select(self,key):
        values=dict(self.draft,trail=key)
        if key in effects.STYLES:values['color']=effects.STYLES[key][2]
        self.fill(values)
    def edit(self,key,value):
        if not self.loading:self.draft[key]=value;self.changed()
    def choose_color(self):
        chosen=QColorDialog.getColor(QColor(self.draft['color']),self,'Mouse effect accent')
        if chosen.isValid():self.edit('color',chosen.name())
    def reset_defaults(self):
        values=dict(self.draft)
        for key in ('trail','click_ripple','duration','intensity','color'):values[key]=model.DEFAULTS[key]
        self.fill(values)
    def changed(self):
        self.dirty=self.draft!=self.baseline;self.preview.values=deepcopy(self.draft);self.preview.update()
        active=effects.resolve(self.draft['trail']);entry=effects.STYLES.get(active)
        for key,button in self.cards.items():button.setChecked(key==active)
        self.description.setText(entry[4] if entry else ('The trail is off. Click feedback can still be used.' if active=='none' else model.TRAILS[active]))
        follow=self.draft['trail']=='follow';self.color.setText('From the effect’s palette' if follow else self.draft['color'])
        self.color.setEnabled(not follow);self.body.setEnabled(not self.busy)
        self.apply.setEnabled(self.dirty and not self.busy);self.discard.setEnabled(self.dirty and not self.busy)
        self.reload.setEnabled(not self.busy);self.defaults.setEnabled(not self.busy)
    def refresh(self,force=False):
        if self.busy or self.dirty and not force:return
        if self.dirty and QMessageBox.question(self,'Discard mouse-effect edits?','Reload saved settings and discard these edits?',QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)!=QMessageBox.StandardButton.Discard:return
        try:self.baseline,self.token=model.load();self.fill(self.baseline)
        except (OSError,ValueError) as exc:self.failed(str(exc))
    def save(self):
        if self.busy or not self.dirty:return
        self.busy=True;self.changed();self.status.setText('Applying mouse effects…')
        self.async_run(lambda:controller.save(self.draft,self.token),self.saved,self.failed)
    def saved(self,result):
        self.baseline,self.token=result;self.busy=False;self.fill(self.baseline);self.status.setText('Mouse effects saved and active.')
    def failed(self,error):self.busy=False;self.changed();self.status.setText(str(error))
