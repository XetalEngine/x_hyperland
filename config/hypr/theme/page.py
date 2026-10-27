"""Theme controls with a wallpaper preview for every physical display."""
import copy
from pathlib import Path
import sys
from PyQt6.QtCore import Qt,QRectF,pyqtSignal
from PyQt6.QtGui import QPixmap,QImageReader,QPainter,QPainterPath,QColor,QPen,QFont
from PyQt6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QPushButton,QFileDialog,QTabWidget,QMessageBox)
sys.path.insert(0,str(Path(__file__).resolve().parent))
import backend
import runtime
from image_picker import ImagePicker
import desktop_settings as settings
from preferences_page import PreferencesPage


def label(text,name=''):
    result=QLabel(text); result.setObjectName(name); result.setWordWrap(True); return result


def button(text,callback,primary=False):
    result=QPushButton(text); result.clicked.connect(callback)
    if primary: result.setObjectName('primary')
    return result


class MonitorPictures(QWidget):
    selected=pyqtSignal(str)
    def __init__(self):
        super().__init__(); self.models=[]; self.wallpapers={}; self.current=''; self.boxes={}; self.pixmaps={}
        self.setMinimumHeight(265); self.setCursor(Qt.CursorShape.PointingHandCursor)
    def pixmap(self,path):
        if path not in self.pixmaps:
            reader=QImageReader(path); size=reader.size()
            if size.width()>1600 or size.height()>1600: reader.setScaledSize(size.scaled(1600,1600,Qt.AspectRatioMode.KeepAspectRatio))
            reader.setAutoTransform(True); self.pixmaps[path]=QPixmap.fromImage(reader.read())
        return self.pixmaps[path]
    def paintEvent(self,event):
        painter=QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing); painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setBrush(QColor('#0b121d')); painter.setPen(QPen(QColor('#344859'))); painter.drawRoundedRect(QRectF(self.rect()).adjusted(1,1,-1,-1),14,14)
        self.boxes={}; models=[m for m in self.models if m['enabled'] and not m['mirror']]
        if not models:
            painter.setPen(QColor('#afbed0')); painter.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'Connect a display to preview its wallpaper'); return
        left=min(m['x'] for m in models); top=min(m['y'] for m in models)
        right=max(m['x']+settings.logical_size(m)[0] for m in models); bottom=max(m['y']+settings.logical_size(m)[1] for m in models)
        scale=min((self.width()-64)/(right-left),(self.height()-96)/(bottom-top))
        ox=(self.width()-(right-left)*scale)/2; oy=(self.height()-(bottom-top)*scale)/2-10
        for m in models:
            width,height=settings.logical_size(m)
            box=QRectF(ox+(m['x']-left)*scale+3,oy+(m['y']-top)*scale,width*scale-6,height*scale-6)
            self.boxes[m['name']]=box; selected=not self.current or self.current==m['name']
            path=QPainterPath(); path.addRoundedRect(box,8,8); painter.save(); painter.setClipPath(path); painter.fillRect(box,QColor('#080c12'))
            item=self.wallpapers.get(m['name'],{}); image=self.pixmap(item.get('path',''))
            if not image.isNull():
                fit=item.get('fit','cover')
                if fit=='tile': painter.drawTiledPixmap(box,image)
                elif fit=='fill': painter.drawPixmap(box,image,QRectF(image.rect()))
                else:
                    ratio=max(box.width()/image.width(),box.height()/image.height()) if fit=='cover' else min(box.width()/image.width(),box.height()/image.height())
                    target=QRectF(0,0,image.width()*ratio,image.height()*ratio); target.moveCenter(box.center()); painter.drawPixmap(target,image,QRectF(image.rect()))
            else:
                painter.setPen(QColor('#acbed1')); painter.drawText(box,Qt.AlignmentFlag.AlignCenter,'No saved wallpaper')
            painter.setBrush(QColor(7,18,29,210)); painter.setPen(Qt.PenStyle.NoPen)
            badge=QRectF(box.x()+8,box.y()+8,30,28); painter.drawRoundedRect(badge,7,7)
            painter.setPen(QColor('#ffffff')); painter.setFont(QFont('Noto Sans',12,QFont.Weight.Bold)); painter.drawText(badge,Qt.AlignmentFlag.AlignCenter,str(m['number']))
            painter.restore(); painter.setBrush(Qt.BrushStyle.NoBrush); painter.setPen(QPen(QColor('#7ce8d6' if selected else '#506379'),2.5 if selected else 1))
            painter.drawRoundedRect(box,8,8)
            painter.setFont(QFont('Noto Sans',10,QFont.Weight.DemiBold)); painter.setPen(QColor('#d4e8f4'))
            painter.drawText(QRectF(box.x()-8,box.bottom()+8,box.width()+16,25),Qt.AlignmentFlag.AlignCenter,m['name'])
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            for name,rect in self.boxes.items():
                if rect.contains(event.position()): self.selected.emit(name); break


class WallpapersPage(QWidget):
    def __init__(self,async_run,filename=''):
        super().__init__(); self.async_run=async_run; self.filename=filename; self.models=[]; self.baseline={}; self.draft={}
        self.busy=False; self.loading=False; self.dirty=False
        root=QVBoxLayout(self); root.setContentsMargins(16,16,16,16)
        root.addWidget(label('Your screens, your backdrop','brand'))
        root.addWidget(label('Click a screen to set its wallpaper, or choose All displays. The preview follows your monitor arrangement.','muted'))
        self.canvas=MonitorPictures(); self.canvas.selected.connect(self.select); root.addWidget(self.canvas,1)
        self.filename_label=label('Current wallpapers appear on each display.','muted'); root.addWidget(self.filename_label)
        row=QHBoxLayout(); self.choose=button('Choose image…',self.choose_image); row.addWidget(self.choose)
        self.monitor=QComboBox(); self.monitor.currentIndexChanged.connect(self.sync); row.addWidget(self.monitor,1)
        self.fit=QComboBox()
        for title,value in [('Fill screen','cover'),('Fit whole image','contain'),('Stretch','fill'),('Tile','tile')]: self.fit.addItem(title,value)
        self.fit.currentIndexChanged.connect(self.change_fit); row.addWidget(self.fit); root.addLayout(row)
        self.pending=label('','status'); self.pending.hide(); root.addWidget(self.pending)
        bottom=QHBoxLayout(); self.status=label('','muted'); bottom.addWidget(self.status,1)
        self.reload=button('Reload',lambda:self.refresh(True)); bottom.addWidget(self.reload)
        self.discard=button('Discard',self.reset); bottom.addWidget(self.discard)
        self.apply=button('Apply wallpaper',self.save,True); bottom.addWidget(self.apply); root.addLayout(bottom); self.update_state()
    def refresh(self,force=False):
        if self.busy or (self.dirty and not force): return
        if self.dirty and QMessageBox.question(self,'Discard wallpaper edits?','Discard the wallpaper preview and reload?',
            QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)!=QMessageBox.StandardButton.Discard: return
        self.busy=True; self.update_state(); self.status.setText('Reading current wallpapers…')
        self.async_run(lambda:(settings.display_models(settings.monitors()),backend.read_wallpapers()),self.loaded,self.failed)
    def loaded(self,result):
        self.models,self.baseline=result; self.draft={}; self.busy=False; self.loading=True
        selected=self.monitor.currentData(); self.monitor.clear(); self.monitor.addItem('All displays','')
        for m in self.models:
            if m['enabled']: self.monitor.addItem(f"{m['number']} · {m['name']} · {m['label']}",m['name'])
        self.monitor.setCurrentIndex(max(0,self.monitor.findData(selected))); self.loading=False
        self.canvas.models=self.models; self.sync(); self.update_state(); self.status.setText('Wallpapers stay separate for each monitor and are restored at login.')
        if self.filename:
            filename,self.filename=self.filename,''; self.stage_image(filename)
    def targets(self):
        name=self.monitor.currentData()
        return [name] if name else [m['name'] for m in self.models if m['enabled']]
    def effective(self): return {**self.baseline,**self.draft}
    def select(self,name): self.monitor.setCurrentIndex(self.monitor.findData(name))
    def sync(self,*_):
        if self.loading:return
        self.loading=True; self.canvas.current=self.monitor.currentData() or ''; data=self.effective(); targets=self.targets()
        item=data.get(targets[0],{}) if targets else {}; self.fit.setCurrentIndex(max(0,self.fit.findData(item.get('fit','cover'))))
        if len(targets)==1:
            path=item.get('original') or item.get('path',''); self.filename_label.setText(Path(path).name if path else 'Choose an image for this display.'); self.filename_label.setToolTip(path)
        else: self.filename_label.setText('Each screen shows its current wallpaper. Choosing an image here will preview it on all displays.')
        self.loading=False; self.canvas.wallpapers=data; self.canvas.update()
    def choose_image(self):
        filename=ImagePicker.choose(self,'Choose a wallpaper',str(Path.home()/'Pictures'),'Images (*.png *.jpg *.jpeg *.webp *.bmp)',self.async_run)
        if filename:self.stage_image(filename)
    def stage_image(self,filename):
        try:
            if self.canvas.pixmap(filename).isNull(): raise ValueError('This image could not be read.')
            for target in self.targets(): self.draft[target]={'path':str(Path(filename).resolve()),'original':str(Path(filename).resolve()),'fit':self.fit.currentData()}
            self.sync(); self.update_state()
        except Exception as exc:self.status.setText(str(exc))
    def change_fit(self,*_):
        if self.loading or self.busy:return
        effective=self.effective()
        for target in self.targets():
            if target in effective:self.draft[target]={**effective[target],'fit':self.fit.currentData()}
        self.sync(); self.update_state()
    def update_state(self):
        self.draft={k:v for k,v in self.draft.items() if v!=self.baseline.get(k)}
        self.dirty=bool(self.draft); self.pending.setVisible(self.dirty)
        self.pending.setText('WALLPAPER PREVIEW  ·  '+', '.join(self.draft)+'\nApply keeps these choices. Discard returns to your current wallpapers.')
        for w in [self.choose,self.monitor,self.fit,self.reload,self.canvas]: w.setEnabled(not self.busy)
        self.apply.setEnabled(self.dirty and not self.busy); self.discard.setEnabled(self.dirty and not self.busy)
    def reset(self):self.draft={};self.sync();self.update_state()
    def save(self):
        if self.busy or not self.dirty:return
        draft,expected=copy.deepcopy(self.draft),copy.deepcopy(self.baseline)
        self.busy=True;self.update_state();self.status.setText('Applying wallpapers…')
        self.async_run(lambda:backend.apply_wallpapers(draft,expected),self.saved,self.failed)
    def saved(self,state):self.baseline=state;self.busy=False;self.reset();self.status.setText('Wallpapers applied and saved for future logins.')
    def failed(self,message):self.busy=False;self.update_state();self.status.setText(message)


class ThemePage(QWidget):
    def __init__(self,async_run,filename=''):
        super().__init__(); self.async_run=async_run; self.applying=False; self.token=None; self.baseline=runtime.mode()
        root=QVBoxLayout(self);root.setContentsMargins(18,16,18,16)
        heading=QHBoxLayout();brand=label('Theme & wallpaper','brand');brand.setWordWrap(False);heading.addWidget(brand);heading.addStretch();heading.addWidget(label('Appearance','muted'))
        self.mode=QComboBox()
        for value,title in runtime.MODES.items():self.mode.addItem(title,value)
        self.mode.setCurrentIndex(self.mode.findData(self.baseline));self.mode.currentIndexChanged.connect(self.changed);heading.addWidget(self.mode)
        self.apply=button('Apply theme',self.save_mode,True);heading.addWidget(self.apply);root.addLayout(heading)
        self.status=label('A complete palette for Qt, GTK and this desktop. Apps with their own forced themes keep those choices.','muted');root.addWidget(self.status)
        self.tabs=QTabWidget();self.wallpapers=WallpapersPage(async_run,filename);self.appearance=PreferencesPage('appearance',async_run)
        self.tabs.addTab(self.wallpapers,'Wallpapers');self.tabs.addTab(self.appearance,'Window effects');root.addWidget(self.tabs,1)
        self.tabs.currentChanged.connect(lambda _:self.tabs.currentWidget().refresh());self.changed()
    @property
    def dirty(self):return self.wallpapers.dirty or self.appearance.dirty or self.mode.currentData()!=self.baseline
    @property
    def busy(self):return self.applying or self.wallpapers.busy or self.appearance.busy
    def refresh(self):
        if not self.applying and self.mode.currentData()==self.baseline:
            self.baseline=runtime.mode();self.mode.setCurrentIndex(self.mode.findData(self.baseline));self.token=backend.theme_token();self.changed()
        self.tabs.currentWidget().refresh()
    def changed(self,*_):self.apply.setEnabled(not self.applying and self.mode.currentData()!=self.baseline);self.mode.setEnabled(not self.applying)
    def save_mode(self):
        if self.applying or not self.token:return
        value=self.mode.currentData();token=self.token;self.applying=True;self.changed();self.status.setText('Applying the desktop palette…')
        self.async_run(lambda:backend.apply_mode(value,token),lambda token:self.saved(value,token),self.failed)
    def saved(self,value,token):
        self.baseline=value;self.token=token;self.applying=False;self.changed()
        self.status.setText('Theme applied. Qt apps opened with this theme update live; reopen older apps and GTK apps to pick it up.')
    def failed(self,message):self.applying=False;self.changed();self.status.setText(message)
