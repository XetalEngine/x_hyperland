"""Mix-and-match layouts, a component chooser, and the saved preset gallery."""
from pathlib import Path
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QPixmap
from PyQt6.QtWidgets import (QWidget, QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QCheckBox, QDialogButtonBox, QScrollArea, QFrame, QInputDialog, QMessageBox, QComboBox, QSizePolicy)
import runtime
import layouts
import presets
import selection_marker


def label(text, name=''):
    widget=QLabel(text);widget.setTextFormat(Qt.TextFormat.PlainText);widget.setWordWrap(True);widget.setObjectName(name);return widget


class ComponentDialog(QDialog):
    def __init__(self, name, target, parent=None, selected=None):
        super().__init__(parent);self.setWindowTitle('Apply '+name);self.resize(540,610)
        root=QVBoxLayout(self);root.setContentsMargins(22,20,22,20)
        root.addWidget(label('What would you like to apply?','brand'))
        root.addWidget(label('Choose the parts of '+name+' to use. Everything left unchecked keeps its current appearance.','muted'))
        self.checks={}
        for key,(title,description) in presets.COMPONENTS.items():
            box=QCheckBox(title);box.setToolTip(description);box.setChecked(selected is None or key in selected)
            if key in ('transfer','switcher','terminal') and key not in target:box.setEnabled(False);box.setChecked(False)
            root.addWidget(box);note=label(description,'muted');note.setContentsMargins(25,0,0,3);root.addWidget(note)
            self.checks[key]=box
        row=QHBoxLayout()
        for title,checked in [('Select all',True),('Clear selection',False)]:
            button=QPushButton(title);button.clicked.connect(lambda _,v=checked:self.select(v));row.addWidget(button)
        row.addStretch();root.addLayout(row)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Apply|QDialogButtonBox.StandardButton.Cancel)
        self.apply=buttons.button(QDialogButtonBox.StandardButton.Apply);self.apply.clicked.connect(self.accept)
        buttons.rejected.connect(self.reject);root.addWidget(buttons)
        for box in self.checks.values():box.toggled.connect(lambda:self.apply.setEnabled(bool(self.selection())))
        self.apply.setEnabled(bool(self.selection()))
    def selection(self):return {key for key,box in self.checks.items() if box.isChecked()}
    def select(self,enabled):
        for box in self.checks.values():
            if box.isEnabled():box.setChecked(enabled)


class LayoutCard(QPushButton):
    def __init__(self,kind):
        super().__init__();self.kind=kind;self.setCheckable(True);self.setMinimumSize(260,190)
        self.setAccessibleName(layouts.LAYOUTS[kind]);self.setToolTip(layouts.DESCRIPTIONS[kind])
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);c=runtime.colors()
        rect=QRectF(self.rect()).adjusted(2,2,-2,-2);p.setBrush(QColor(c['AlternateBase']));p.setPen(QPen(QColor(c['Accent'] if self.isChecked() else c['Midlight']),2 if self.isChecked() else 1));p.drawRoundedRect(rect,12,12)
        preview=rect.adjusted(14,14,-14,-65);p.setBrush(QColor(c['Base']));p.setPen(Qt.PenStyle.NoPen);p.drawRoundedRect(preview,7,7)
        rail=self.kind in ('modern','sidebar');wide=self.kind=='sidebar';navwidth=preview.width()*.34 if wide else 34
        if rail:
            nav=QRectF(preview.x()+5,preview.y()+5,navwidth,preview.height()-10);p.setBrush(QColor(c['Button']));p.drawRoundedRect(nav,9,9)
            for i in range(4):
                y=nav.y()+9+i*21;p.setBrush(QColor(c['Highlight'] if i==1 else c['Midlight']));p.drawRoundedRect(QRectF(nav.x()+6,y,nav.width()-12,16),8 if wide else 4,8 if wide else 4)
                p.setBrush(QColor(c['Accent']));p.drawEllipse(QRectF(nav.x()+10,y+4,7,7))
            left=nav.right()+9;top=preview.top()+12
        else:
            for i in range(4):
                p.setBrush(QColor(c['Highlight'] if i==1 else c['Button']))
                p.drawRoundedRect(QRectF(preview.x()+6+i*(preview.width()-12)/4,preview.y()+6,(preview.width()-18)/4,30 if self.kind=='ribbon' else 16),3,3)
                if self.kind=='ribbon':p.setBrush(QColor(c['Accent']));p.drawEllipse(QRectF(preview.x()+18+i*(preview.width()-12)/4,preview.y()+11,8,8))
            left=preview.x()+12;top=preview.y()+(47 if self.kind=='ribbon' else 35)
        p.setBrush(QColor(c['Midlight']));p.drawRoundedRect(QRectF(left,top,preview.right()-left-12,5),2,2)
        p.setBrush(QColor(c['Button']));p.drawRoundedRect(QRectF(left,top+16,preview.right()-left-12,max(15,preview.bottom()-top-28)),10 if rail else 3,10 if rail else 3)
        p.setPen(QColor(c['Text']));p.setFont(QFont(runtime.ui_font(),12,QFont.Weight.DemiBold));p.drawText(rect.adjusted(16,rect.height()-53,-10,-28),layouts.LAYOUTS[self.kind])
        p.setPen(QColor(c['PlaceholderText']));p.setFont(QFont(runtime.ui_font(),9));p.drawText(rect.adjusted(16,rect.height()-27,-10,-4),layouts.DESCRIPTIONS[self.kind])


class LayoutPage(QWidget):
    def __init__(self,owner):
        super().__init__();self.owner=owner;outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame)
        body=QWidget();root=QVBoxLayout(body);scroll.setWidget(body);outer.addWidget(scroll)
        root.addWidget(label('Navigation & controls','section'))
        root.addWidget(label('Choose the structure independently of your colors. These shapes also carry through dialogs and Control Panel controls.','muted'))
        self.choice=QComboBox()
        for key,title in layouts.LAYOUTS.items():self.choice.addItem(title,key)
        self.choice.setCurrentIndex(self.choice.findData(runtime.layout()));root.addWidget(self.choice)
        grid=QGridLayout();grid.setSpacing(14);self.cards={}
        for i,key in enumerate(layouts.LAYOUTS):
            card=LayoutCard(key);card.clicked.connect(lambda _,k=key:self.choice.setCurrentIndex(self.choice.findData(k)));self.cards[key]=card;grid.addWidget(card,i//2,i%2)
        root.addLayout(grid,1)
        row=QHBoxLayout();row.addWidget(label('Fusion Files selection marker','section'))
        self.marker=QComboBox();self.marker.setAccessibleName('Fusion Files selection marker');self.marker.setMaximumWidth(360)
        for key,title in selection_marker.STYLES.items():self.marker.addItem(title,key)
        self.marker.setCurrentIndex(self.marker.findData(runtime.selection_marker()))
        row.addWidget(self.marker,1);root.addLayout(row)
        root.addWidget(label('An optional accent edge beside the selected folder. Off is the default in every theme. Apply theme to keep your choice.','muted'))
        self.marker_preview=selection_marker.preview();root.addWidget(self.marker_preview);root.addStretch()
        self.marker.currentIndexChanged.connect(lambda:(self.refresh(),owner.changed()))
        self.choice.currentIndexChanged.connect(lambda: (self.refresh(),owner.changed()))
        self.refresh()
    def refresh(self):
        for key,card in self.cards.items():card.setChecked(key==self.choice.currentData());card.update()
        selection_marker.style_preview(self.marker_preview,self.marker.currentData())


class CustomPage(QWidget):
    def __init__(self,owner):
        super().__init__();self.owner=owner;root=QVBoxLayout(self)
        row=QHBoxLayout();row.addWidget(label('Your custom presets','section'));row.addStretch()
        save=QPushButton('＋ Save current mix…');save.clicked.connect(self.save_current);row.addWidget(save);root.addLayout(row)
        root.addWidget(label('Save the appearance currently applied to your desktop, including each screen’s wallpaper. Apply pending edits before saving.','muted'))
        self.scroll=QScrollArea();self.scroll.setWidgetResizable(True);self.scroll.setFrameShape(QFrame.Shape.NoFrame);root.addWidget(self.scroll,1)
        self.note=label('','muted');root.addWidget(self.note)
    def refresh(self):
        try:items=presets.library()['presets']
        except (OSError,ValueError) as error:self.note.setText(str(error));return
        body=QWidget();grid=QGridLayout(body);grid.setSpacing(16);grid.setColumnStretch(0,1);grid.setColumnStretch(1,1)
        for i,item in enumerate(items):
            frame=QFrame();frame.setObjectName('presetCard');box=QVBoxLayout(frame);box.setContentsMargins(14,12,14,12)
            box.addWidget(label(item['name'],'section'));config=item['config'];theme=config['theme']
            preview=QLabel();preview.setFixedHeight(135);preview.setAlignment(Qt.AlignmentFlag.AlignCenter);preview.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
            choices=config.get('wallpapers',{});path=next((entry['path'] for entry in choices.values() if Path(entry['path']).is_file()),'')
            image=QPixmap(path)
            if not image.isNull():preview.setPixmap(image.scaled(520,135,Qt.AspectRatioMode.KeepAspectRatioByExpanding,Qt.TransformationMode.SmoothTransformation));preview.setMaximumWidth(520)
            else:preview.setText(runtime.DESIGNS[theme['design']]);preview.setStyleSheet('background:'+runtime.colors(theme['mode'],theme['design'])['Highlight'])
            box.addWidget(preview)
            box.addWidget(label(runtime.DESIGNS[theme['design']]+' · '+layouts.LAYOUTS[theme['layout']],'muted'))
            row=QHBoxLayout()
            for caption,action in [('Rename',lambda _,p=item:self.rename(p)),('Remove',lambda _,p=item:self.remove(p)),('Apply…',lambda _,p=item:self.owner.apply_custom(p))]:
                control=QPushButton(caption);control.clicked.connect(action);row.addWidget(control)
            box.addLayout(row);grid.addWidget(frame,i//2,i%2)
        if not items:grid.addWidget(label('Your saved combinations will appear here.','muted'),0,0,1,2)
        grid.setRowStretch((len(items)+1)//2,1);old=self.scroll.takeWidget();self.scroll.setWidget(body)
        if old:old.deleteLater()
        self.note.setText(f'{len(items)} saved preset'+('s' if len(items)!=1 else ''))
    def save_current(self):
        if self.owner.dirty:self.note.setText('Apply your pending changes first, then save this mix.');return
        name,ok=QInputDialog.getText(self,'Save custom preset','Preset name:')
        if not ok:return
        try:
            import backend
            token=backend.theme_token();value=presets.current()
            if token!=backend.theme_token():raise ValueError('Appearance changed while saving. Try again with the new choices.')
            presets.save(name,value);self.refresh()
        except (OSError,ValueError) as error:self.note.setText(str(error))
    def rename(self,item):
        name,ok=QInputDialog.getText(self,'Rename preset','Preset name:',text=item['name'])
        if not ok:return
        try:presets.save(name,item['config'],item['id']);self.refresh()
        except (OSError,ValueError) as error:self.note.setText(str(error))
    def remove(self,item):
        if QMessageBox.question(self,'Remove preset','Remove “'+item['name']+'” from Custom?',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)!=QMessageBox.StandardButton.Yes:return
        try:presets.remove(item['id']);self.refresh()
        except (OSError,ValueError) as error:self.note.setText(str(error))
