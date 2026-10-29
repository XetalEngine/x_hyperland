"""Theme controls with a wallpaper preview for every physical display."""
import copy
from pathlib import Path
import sys
from PyQt6.QtCore import Qt,QRectF,pyqtSignal
from PyQt6.QtGui import QPixmap,QImageReader,QPainter,QPainterPath,QColor,QPen,QFont
from PyQt6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLayout,QLabel,QComboBox,QPushButton,QFileDialog,QTabWidget,QMessageBox,QFrame,QScrollArea,QCheckBox,QSlider)
sys.path.insert(0,str(Path(__file__).resolve().parent))
import backend
import runtime
import draft as theme_draft
from image_picker import ImagePicker
import desktop_settings as settings
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from effects.burn.page import WindowEffectsPage
from file_jobs.page import FileTransferPage
from identity import ProfileCard,launcher_background_path
from design_preview import DesktopPreview
from launcher_surfaces import DEFAULTS,StripImage,paint_group,paint_tile
from launcher_labels import positions as label_positions


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
        painter.setBrush(runtime.qcolor('#0b121d')); painter.setPen(QPen(runtime.qcolor('#344859'))); painter.drawRoundedRect(QRectF(self.rect()).adjusted(1,1,-1,-1),14,14)
        self.boxes={}; models=[m for m in self.models if m['enabled'] and not m['mirror']]
        if not models:
            painter.setPen(runtime.qcolor('#afbed0')); painter.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'Connect a display to preview its wallpaper'); return
        left=min(m['x'] for m in models); top=min(m['y'] for m in models)
        right=max(m['x']+settings.logical_size(m)[0] for m in models); bottom=max(m['y']+settings.logical_size(m)[1] for m in models)
        scale=min((self.width()-64)/(right-left),(self.height()-96)/(bottom-top))
        ox=(self.width()-(right-left)*scale)/2; oy=(self.height()-(bottom-top)*scale)/2-10
        for m in models:
            width,height=settings.logical_size(m)
            box=QRectF(ox+(m['x']-left)*scale+3,oy+(m['y']-top)*scale,width*scale-6,height*scale-6)
            self.boxes[m['name']]=box; selected=not self.current or self.current==m['name']
            path=QPainterPath(); path.addRoundedRect(box,8,8); painter.save(); painter.setClipPath(path); painter.fillRect(box,runtime.qcolor('#080c12'))
            item=self.wallpapers.get(m['name'],{}); image=self.pixmap(item.get('path',''))
            if not image.isNull():
                fit=item.get('fit','cover')
                if fit=='tile': painter.drawTiledPixmap(box,image)
                elif fit=='fill': painter.drawPixmap(box,image,QRectF(image.rect()))
                else:
                    ratio=max(box.width()/image.width(),box.height()/image.height()) if fit=='cover' else min(box.width()/image.width(),box.height()/image.height())
                    target=QRectF(0,0,image.width()*ratio,image.height()*ratio); target.moveCenter(box.center()); painter.drawPixmap(target,image,QRectF(image.rect()))
            else:
                painter.setPen(runtime.qcolor('#acbed1')); painter.drawText(box,Qt.AlignmentFlag.AlignCenter,'No saved wallpaper')
            painter.setBrush(runtime.qcolor(7,18,29,210)); painter.setPen(Qt.PenStyle.NoPen)
            badge=QRectF(box.x()+8,box.y()+8,30,28); painter.drawRoundedRect(badge,7,7)
            painter.setPen(runtime.qcolor('#ffffff')); painter.setFont(QFont(runtime.ui_font(),12,QFont.Weight.Bold)); painter.drawText(badge,Qt.AlignmentFlag.AlignCenter,str(m['number']))
            painter.restore(); painter.setBrush(Qt.BrushStyle.NoBrush); painter.setPen(QPen(runtime.qcolor('#7ce8d6' if selected else '#506379'),2.5 if selected else 1))
            painter.drawRoundedRect(box,8,8)
            painter.setFont(QFont(runtime.ui_font(),10,QFont.Weight.DemiBold)); painter.setPen(runtime.qcolor('#d4e8f4'))
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
        self.breakpoint_set=button('BreakPoint set',self.stage_breakpoint);row.addWidget(self.breakpoint_set)
        self.breakpoint_set.setToolTip('Preview the three included wallpapers across your displays, from left to right. Apply to keep them.')
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
    def stage_breakpoint(self):
        if self.busy:return
        screens=sorted((m for m in self.models if m['enabled'] and not m['mirror']),key=lambda m:(m['x'],m['y'],m['name']))
        choices={}
        for index,monitor in enumerate(screens):
            path=runtime.ROOT.parent/'wallpaper/breakpoint'/f'workstation-{index%3+1}.png'
            if self.canvas.pixmap(str(path)).isNull():
                self.status.setText('A BreakPoint wallpaper is missing. Reinstall the included artwork.');return
            choices[monitor['name']]={'path':str(path),'original':str(path),'fit':'cover'}
        self.draft.update(choices);self.sync();self.update_state()
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
        for w in [self.choose,self.breakpoint_set,self.monitor,self.fit,self.reload,self.canvas]: w.setEnabled(not self.busy)
        self.apply.setEnabled(self.dirty and not self.busy); self.discard.setEnabled(self.dirty and not self.busy)
    def reset(self):self.draft={};self.sync();self.update_state()
    def save(self):
        if self.busy or not self.dirty:return
        draft,expected=copy.deepcopy(self.draft),copy.deepcopy(self.baseline)
        self.busy=True;self.update_state();self.status.setText('Applying wallpapers…')
        self.async_run(lambda:backend.apply_wallpapers(draft,expected),self.saved,self.failed)
    def saved(self,state):self.baseline=state;self.busy=False;self.reset();self.status.setText('Wallpapers applied and saved for future logins.')
    def failed(self,message):self.busy=False;self.update_state();self.status.setText(message)


class DesignCard(QPushButton):
    def __init__(self,style,parent=None):
        super().__init__(parent);self.design=style;self.mode='dark';self.setCheckable(True);self.setMinimumSize(245,224)
        self.artwork=DesktopPreview();self.launcher_design=style
        self.surfaces=runtime.launcher_surfaces()[style]
        self.strip_image=StripImage(self);self.strip_image.changed.connect(self.update)
        self.setAccessibleName(runtime.DESIGNS[style]);self.setCursor(Qt.CursorShape.PointingHandCursor)
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        modern=self.design=='modern';colors=runtime.colors(self.mode,self.design)
        box=QRectF(self.rect()).adjusted(2,2,-2,-2)
        p.setBrush(QColor(colors['Window']));p.setPen(QPen(QColor(colors['Accent'] if self.isChecked() else colors['Midlight']),2 if self.isChecked() else 1))
        p.drawRoundedRect(box,16,16)
        self.artwork.paint(p,box.adjusted(14,14,-14,-58),self.design,self.mode,self.surfaces,self.strip_image.frame,self.launcher_design)
        p.setPen(QColor(colors['Text']));p.setFont(QFont(runtime.ui_font(),12,QFont.Weight.DemiBold))
        p.drawText(QRectF(box.x()+16,box.bottom()-49,box.width()-32,23),Qt.AlignmentFlag.AlignVCenter,runtime.DESIGNS[self.design])
        p.setPen(QColor(colors['PlaceholderText']));p.setFont(QFont(runtime.ui_font(),9))
        p.drawText(QRectF(box.x()+16,box.bottom()-25,box.width()-32,20),Qt.AlignmentFlag.AlignVCenter,'Charcoal glass · crimson focus' if self.design=='breakpoint' else 'Soft cards · blue accents' if modern else 'Original layout · cyan accents')


class BackgroundPreview(QWidget):
    def __init__(self):
        super().__init__();self.setFixedSize(144,92);self.path=None;self.picture=QPixmap();self.enabled=False
    def refresh(self,choice,enabled):
        path=launcher_background_path(choice=choice) if enabled else None
        self.enabled=enabled
        if path!=self.path:
            self.path=path;self.picture=QPixmap()
            if path:
                reader=QImageReader(str(path));reader.setAutoTransform(True)
                size=reader.size()
                if size.isValid():reader.setScaledSize(size.scaled(288,184,Qt.AspectRatioMode.KeepAspectRatio))
                self.picture=QPixmap.fromImage(reader.read())
        self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        box=QRectF(self.rect()).adjusted(.5,.5,-.5,-.5);colors=runtime.colors()
        p.setBrush(QColor(colors['Base']));p.setPen(Qt.PenStyle.NoPen);p.drawRoundedRect(box,10,10)
        if not self.picture.isNull():DesktopPreview.picture(p,self.picture,box,10)
        else:
            p.setPen(QColor(colors['PlaceholderText']));p.drawText(box,Qt.AlignmentFlag.AlignCenter,'No preview' if self.enabled else 'Theme background')
        p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(QColor(colors['Midlight']),1));p.drawRoundedRect(box,10,10)


class SurfacePreview(QWidget):
    def __init__(self):
        super().__init__();self.setMinimumSize(270,188);self.setMaximumWidth(426)
        self.artwork=DesktopPreview();self.options=dict(DEFAULTS['modern']);self.design='modern';self.mode='dark'
        self.labels=runtime.launcher_labels();self.visibility=runtime.launcher_background_visibility()
        self.strip_image=StripImage(self);self.strip_image.changed.connect(self.update)
    def refresh(self,style,mode,options,background,backdrop,labels=None,visibility=None):
        self.design=style;self.mode=mode;self.options=dict(options)
        self.labels=labels if labels is not None else runtime.launcher_labels()
        self.visibility=visibility if visibility is not None else runtime.launcher_background_visibility()
        self.artwork.refresh(background=background,enabled=backdrop)
        self.strip_image.load(options['group_image']);self.strip_image.set_enabled(options['group_opacity']>0)
        self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        colors=runtime.colors(self.mode,self.design);box=QRectF(self.rect()).adjusted(1,1,-1,-1)
        p.setBrush(QColor(colors['Window']));p.setPen(QPen(QColor(colors['Midlight']),1));p.drawRoundedRect(box,12,12)
        if self.artwork.show_background and not self.artwork.background.isNull():
            DesktopPreview.picture(p,self.artwork.background,box,12)
            shade=QColor(colors['Window']);shade.setAlpha(round(255*(1-self.visibility/100)))
            p.setBrush(shade);p.drawRoundedRect(box,12,12)
        strip=QRectF(10,12,self.width()-20,34)
        paint_group(p,strip,colors,self.design,self.options['group_opacity'],self.strip_image.frame)
        p.setFont(QFont(runtime.ui_font(),10,QFont.Weight.DemiBold));p.setPen(QColor(colors['Text']))
        p.drawText(strip.adjusted(8,0,-8,0),Qt.AlignmentFlag.AlignVCenter,'⠿  Favorites')
        p.drawText(strip.adjusted(8,0,-8,0),Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,'⋯')
        width=(self.width()-40)/3
        for index,title in enumerate(('Files','Browser','Terminal')):
            tile=QRectF(10+index*(width+10),54,width,118)
            paint_tile(p,tile,colors,self.design,self.mode,self.options['tile_opacity'],selected=index==0)
            picture=self.artwork.icons[index]
            p.setFont(QFont(runtime.ui_font(),9))
            icon_y,name_y,hotkey_y=label_positions(tile.height(),self.labels['names'],self.labels['hotkeys'],p.fontMetrics().height())
            if not picture.isNull():p.drawPixmap(QRectF(tile.center().x()-19,tile.y()+icon_y,38,38),picture,QRectF(picture.rect()))
            p.setPen(QColor(colors['Text']));p.setFont(QFont(runtime.ui_font(),9))
            if name_y is not None:p.drawText(QRectF(tile.x()+3,tile.y()+name_y,tile.width()-6,31),Qt.AlignmentFlag.AlignHCenter|Qt.AlignmentFlag.AlignTop,title)
            p.setPen(QColor(colors['PlaceholderText']));p.setFont(QFont(runtime.ui_font(),8))
            if hotkey_y is not None:p.drawText(QRectF(tile.x()+3,tile.y()+hotkey_y,tile.width()-6,16),Qt.AlignmentFlag.AlignHCenter|Qt.AlignmentFlag.AlignTop,'No hotkey')


class DesignPage(QWidget):
    def __init__(self,owner):
        super().__init__();self.owner=owner
        outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);outer.addWidget(scroll)
        body=QWidget();scroll.setWidget(body)
        root=QVBoxLayout(body);root.setContentsMargins(6,12,6,6);root.setSpacing(16)
        root.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        root.addWidget(label('Desktop theme','section'))
        self.cards={};row=QHBoxLayout();row.setSpacing(16)
        for style in runtime.DESIGNS:
            card=DesignCard(style);card.clicked.connect(lambda _,s=style:owner.design.setCurrentIndex(owner.design.findData(s)))
            self.cards[style]=card;row.addWidget(card,1)
        root.addLayout(row);root.addStretch()
    def refresh(self):
        style=self.owner.menu_design()
        for name,card in self.cards.items():
            card.mode=self.owner.mode.currentData();card.setChecked(name==self.owner.design.currentData())
            card.artwork.labels=dict(self.owner.labels);card.artwork.visibility=self.owner.visibility
            card.artwork.refresh(self.owner.avatar,self.owner.background,self.owner.backdrop)
            card.launcher_design=name if self.owner.launcher_style.currentData()=='follow' else style
            card.surfaces=dict(self.owner.surfaces[card.launcher_design]);card.strip_image.load(card.surfaces['group_image'])
            card.strip_image.set_enabled(card.surfaces['group_opacity']>0);card.update()


class StartMenuPage(QWidget):
    def __init__(self,owner):
        super().__init__();self.owner=owner
        outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);outer.addWidget(scroll)
        body=QWidget();scroll.setWidget(body)
        root=QVBoxLayout(body);root.setContentsMargins(6,12,6,6);root.setSpacing(16)
        root.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        menu=QHBoxLayout();menu.addWidget(label('Start menu style','section'));menu.addStretch()
        owner.launcher_style=QComboBox();owner.launcher_style.setAccessibleName('Start menu style')
        for value,title in runtime.LAUNCHER_STYLES.items():owner.launcher_style.addItem(title,value)
        owner.launcher_style.setCurrentIndex(owner.launcher_style.findData(owner.baseline[-1]))
        owner.launcher_style.setMinimumWidth(220);menu.addWidget(owner.launcher_style);root.addLayout(menu)
        root.addWidget(label('Mix any Start menu with your desktop theme. Follow desktop theme keeps them matched.','muted'))
        background=QHBoxLayout();background.setSpacing(16)
        self.background_preview=BackgroundPreview();background.addWidget(self.background_preview)
        background_controls=QVBoxLayout();background_controls.setSpacing(5)
        title=QHBoxLayout();title.addWidget(label('Apps background','section'))
        self.background_source=label('','muted');title.addWidget(self.background_source);title.addStretch();background_controls.addLayout(title)
        self.wallpaper=QCheckBox('Show background image');self.wallpaper.setChecked(owner.backdrop)
        self.wallpaper.setToolTip('Show your chosen image behind the entire Apps menu in any design.')
        self.wallpaper.toggled.connect(owner.set_backdrop);background_controls.addWidget(self.wallpaper)
        actions=QHBoxLayout();actions.addWidget(button('Choose image…',owner.choose_background))
        actions.addWidget(button('Use desktop wallpaper',lambda:owner.set_background('')));actions.addStretch()
        background_controls.addLayout(actions)
        visibility_row=QHBoxLayout();visibility_row.addWidget(label('Background visibility'))
        self.visibility=QSlider(Qt.Orientation.Horizontal);self.visibility.setRange(0,100);self.visibility.setValue(owner.visibility)
        self.visibility.setAccessibleName('Background visibility');self.visibility.setToolTip('Bring out the image behind Apps. 0% hides the image; 100% shows its full colors.')
        self.visibility.valueChanged.connect(owner.set_visibility);visibility_row.addWidget(self.visibility,1)
        self.visibility_value=QLabel();self.visibility_value.setFixedWidth(40);visibility_row.addWidget(self.visibility_value)
        background_controls.addLayout(visibility_row);background.addLayout(background_controls,1);root.addLayout(background)
        labels=QHBoxLayout();labels.addWidget(label('Shortcut labels','section'));labels.addStretch()
        self.label_controls={}
        for key,title in [('names','Show shortcut names'),('hotkeys','Show hotkeys')]:
            check=QCheckBox(title);check.setChecked(owner.labels[key])
            check.toggled.connect(lambda enabled,k=key:owner.set_label(k,enabled));labels.addWidget(check);self.label_controls[key]=check
        root.addLayout(labels)
        root.addWidget(label('Applies to every Start menu style. Small tiles always show only their icon.','muted'))
        surface_heading=QHBoxLayout();surface_heading.addWidget(label('Apps tiles & groups','section'))
        self.surface_style=label('','muted');self.surface_style.setWordWrap(False)
        self.surface_style.setToolTip('Each design remembers its own opacity and group-strip artwork.')
        surface_heading.addWidget(self.surface_style);surface_heading.addStretch()
        surface_heading.addWidget(button('Reset surfaces',owner.reset_surfaces));root.addLayout(surface_heading)
        surfaces=QHBoxLayout();surfaces.setSpacing(22);controls=QVBoxLayout();controls.setSpacing(8)
        self.opacity_controls={}
        for key,title in [('tile_opacity','Icon backgrounds'),('group_opacity','Group strips')]:
            row=QHBoxLayout();row.addWidget(label(title));row.addStretch()
            value=QLabel();value.setFixedWidth(54);value.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
            value.setAccessibleName(title+' opacity');row.addWidget(value);controls.addLayout(row)
            slider=QSlider(Qt.Orientation.Horizontal);slider.setRange(0,100);slider.setPageStep(10)
            slider.setAccessibleName(title+' opacity');controls.addWidget(slider)
            slider.valueChanged.connect(lambda number,k=key:owner.set_surface(k,number))
            self.opacity_controls[key]=(slider,value)
        controls.addWidget(label('0% transparent · 100% opaque','muted'))
        row=QHBoxLayout();title=label('Group-strip background');title.setWordWrap(False);row.addWidget(title)
        self.group_source=label('','muted');self.group_source.setWordWrap(False);row.addWidget(self.group_source);row.addStretch();controls.addLayout(row)
        row=QHBoxLayout();row.addWidget(button('Choose image or GIF…',owner.choose_group_image))
        self.remove_group_image=button('Remove image',lambda:owner.set_surface('group_image',''))
        row.addWidget(self.remove_group_image);row.addStretch();controls.addLayout(row)
        surfaces.addLayout(controls,1);self.surface_preview=SurfacePreview();surfaces.addWidget(self.surface_preview,1)
        root.addLayout(surfaces)
        self.profile=ProfileCard();self.profile.setMinimumHeight(140);self.profile.setMaximumHeight(160);root.addWidget(self.profile)
        controls=QHBoxLayout();controls.addWidget(label('Your profile image','muted'));controls.addStretch()
        controls.addWidget(button('Choose image or GIF…',owner.choose_avatar))
        account=button('Use account picture',lambda:owner.set_avatar('auto'))
        account.setToolTip('Use your Linux account’s profile picture, or the bundled Xetal image if none is set. This changes the avatar shown here; it does not edit your account picture.')
        controls.addWidget(account)
        root.addLayout(controls);root.addStretch()
        self.refresh_background()
    def refresh_background(self):
        self.background_preview.refresh(self.owner.background,self.owner.backdrop)
        self.background_source.setText('Custom image' if self.owner.background else 'Desktop wallpaper')
        self.visibility.blockSignals(True);self.visibility.setValue(self.owner.visibility);self.visibility.blockSignals(False)
        self.visibility.setEnabled(self.owner.backdrop);self.visibility_value.setText(str(self.owner.visibility)+'%')
        self.refresh_surfaces()
    def refresh_surfaces(self):
        style=self.owner.menu_design();options=self.owner.surfaces[style]
        self.surface_style.setText(runtime.DESIGNS[style]+' settings')
        for key,(slider,value) in self.opacity_controls.items():
            slider.blockSignals(True);slider.setValue(options[key]);slider.blockSignals(False)
            value.setText(str(options[key])+'%')
        choice=options['group_image']
        self.group_source.setText('GIF background' if choice.lower().endswith('.gif') else 'Custom image' if choice else 'None')
        self.group_source.setToolTip(choice);self.remove_group_image.setEnabled(bool(choice))
        self.surface_preview.refresh(style,self.owner.mode.currentData(),options,self.owner.background,self.owner.backdrop,self.owner.labels,self.owner.visibility)
        for key,check in self.label_controls.items():
            check.blockSignals(True);check.setChecked(self.owner.labels[key]);check.blockSignals(False)
    def refresh(self):
        self.profile.refresh();self.profile.avatar.refresh(self.owner.avatar)
        self.refresh_background()


class ThemePage(QWidget):
    def __init__(self,async_run,filename=''):
        super().__init__(); self.async_run=async_run; self.applying=False; self.token=None
        self.avatar=runtime.state().get('avatar','assets/account.gif')
        self.backdrop=runtime.launcher_wallpaper()
        self.background=runtime.launcher_background()
        self.surfaces=runtime.launcher_surfaces()
        self.labels=runtime.launcher_labels();self.visibility=runtime.launcher_background_visibility()
        self.baseline=theme_draft.current()
        root=QVBoxLayout(self);root.setContentsMargins(18,16,18,16)
        heading=QHBoxLayout();brand=label('Theme & wallpaper','brand');brand.setWordWrap(False);heading.addWidget(brand);heading.addStretch()
        self.design=QComboBox();self.design.setAccessibleName('Desktop theme')
        for value,title in runtime.DESIGNS.items():self.design.addItem(title,value)
        self.design.setCurrentIndex(self.design.findData(self.baseline[0]));heading.addWidget(self.design)
        self.mode=QComboBox()
        for value,title in runtime.MODES.items():self.mode.addItem(title,value)
        self.mode.setCurrentIndex(self.mode.findData(self.baseline[1]));heading.addWidget(self.mode)
        self.apply=button('Apply theme',self.save_mode,True);heading.addWidget(self.apply);root.addLayout(heading)
        self.status=label('Choose your design and colors. Keep your apps, shortcuts and workspace just how you like them.','muted');root.addWidget(self.status)
        self.conflict_actions=QWidget();conflicts=QHBoxLayout(self.conflict_actions);conflicts.setContentsMargins(0,0,0,0)
        conflicts.addWidget(button('Keep my edits',lambda:self.resolve_conflicts('edited')))
        conflicts.addWidget(button('Use saved values',lambda:self.resolve_conflicts('saved')));conflicts.addStretch()
        self.conflict_actions.hide();root.addWidget(self.conflict_actions)
        self.tabs=QTabWidget();self.wallpapers=WallpapersPage(async_run,filename);self.appearance=WindowEffectsPage(async_run)
        self.file_transfer=FileTransferPage(async_run)
        self.design_page=DesignPage(self)
        self.start_menu_page=StartMenuPage(self)
        self.tabs.addTab(self.design_page,'Design');self.tabs.addTab(self.start_menu_page,'Start Menu')
        self.tabs.addTab(self.wallpapers,'Wallpapers');self.tabs.addTab(self.file_transfer,'File Transfer');self.tabs.addTab(self.appearance,'Window effects');root.addWidget(self.tabs,1)
        if filename:self.tabs.setCurrentWidget(self.wallpapers)
        self.design.currentIndexChanged.connect(self.changed);self.mode.currentIndexChanged.connect(self.changed)
        self.launcher_style.currentIndexChanged.connect(self.changed)
        self.tabs.currentChanged.connect(lambda _:self.tabs.currentWidget().refresh());self.changed()
    def choice(self):return self.design.currentData(),self.mode.currentData(),self.avatar,self.backdrop,self.background,copy.deepcopy(self.surfaces),dict(self.labels),self.visibility,self.launcher_style.currentData()
    def menu_design(self):
        style=self.launcher_style.currentData()
        return self.design.currentData() if style=='follow' else style
    @property
    def dirty(self):return self.wallpapers.dirty or self.appearance.dirty or self.file_transfer.dirty or self.choice()!=self.baseline
    @property
    def busy(self):return self.applying or self.wallpapers.busy or self.appearance.busy or self.file_transfer.busy
    def refresh(self):
        if not self.applying and self.choice()==self.baseline:
            self.baseline,self.token=self.read_saved();self.set_choice(self.baseline);self.changed()
        self.tabs.currentWidget().refresh()
    def read_saved(self):
        for _ in range(3):
            token=backend.theme_token();saved=theme_draft.current()
            if token==backend.theme_token():return saved,token
        raise ValueError('Theme settings are still changing. Apply again in a moment.')
    def set_choice(self,value):
        style,mode,self.avatar,self.backdrop,self.background,surfaces,labels,self.visibility,menu=value
        self.surfaces=copy.deepcopy(surfaces);self.labels=dict(labels)
        for control,option in ((self.design,style),(self.mode,mode),(self.launcher_style,menu)):
            control.blockSignals(True);control.setCurrentIndex(control.findData(option));control.blockSignals(False)
        self.start_menu_page.wallpaper.blockSignals(True);self.start_menu_page.wallpaper.setChecked(self.backdrop);self.start_menu_page.wallpaper.blockSignals(False)
        self.design_page.refresh();self.start_menu_page.refresh()
    def resolve_conflicts(self,prefer):
        try:
            saved,token=self.read_saved();merged,_=theme_draft.merge(self.baseline,self.choice(),saved,prefer)
            self.baseline=saved;self.token=token;self.set_choice(merged);self.conflict_actions.hide();self.changed()
            self.status.setText('Choices updated. Apply theme to save your changes.')
        except (OSError,ValueError) as exc:self.failed(str(exc))
    def changed(self,*_):
        self.apply.setEnabled(not self.applying and self.choice()!=self.baseline)
        if not self.applying and self.choice()!=self.baseline:
            self.status.setText('Previewing appearance changes. Apply theme to save them.')
        for control in (self.mode,self.design,self.design_page,self.start_menu_page):control.setEnabled(not self.applying)
        self.design_page.refresh();self.start_menu_page.refresh_surfaces()
    def set_surface(self,key,value):
        self.surfaces[self.menu_design()][key]=value
        self.changed()
    def set_label(self,key,value):
        self.labels[key]=value;self.changed()
    def set_visibility(self,value):
        self.visibility=value;self.start_menu_page.refresh_background();self.changed()
    def reset_surfaces(self):
        style=self.menu_design();self.surfaces[style]=dict(DEFAULTS[style]);self.changed()
    def choose_group_image(self):
        filename=ImagePicker.choose(self,'Choose group-strip image or GIF',str(Path.home()/'Pictures'),
            'Images (*.gif *.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff *.avif);;All files (*)',self.async_run)
        if filename:
            options=self.surfaces[self.menu_design()]
            options['group_image']=filename
            if options['group_opacity']==0:options['group_opacity']=100
            self.changed()
    def set_avatar(self,choice):
        self.avatar=choice;self.start_menu_page.refresh();self.changed()
    def set_backdrop(self,enabled):
        self.backdrop=enabled;self.start_menu_page.refresh_background();self.changed()
    def set_background(self,choice):
        self.background=choice;self.backdrop=True
        self.start_menu_page.wallpaper.setChecked(True);self.start_menu_page.refresh_background();self.changed()
    def choose_background(self):
        filename=ImagePicker.choose(self,'Choose Apps background',str(Path.home()/'Pictures'),
            'Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff *.avif);;All files (*)',self.async_run)
        if filename:self.set_background(filename)
    def choose_avatar(self):
        picker=ImagePicker(self,'Choose profile image or GIF',str(Path.home()/'Pictures'),'Images (*.gif *.png *.jpg *.jpeg *.webp)',self.async_run)
        if picker.exec() and picker.selectedFiles():self.set_avatar(picker.selectedFiles()[0])
    def save_mode(self):
        if self.applying:return
        try:
            saved,token=self.read_saved();choice,conflicts=theme_draft.merge(self.baseline,self.choice(),saved)
            if conflicts:
                self.status.setText('Also changed in another window: '+', '.join(conflicts)+'. Choose which values to keep.')
                self.conflict_actions.show();return
        except (OSError,ValueError) as exc:self.failed(str(exc));return
        self.set_choice(choice);self.conflict_actions.hide()
        style,value,avatar,backdrop,background,surfaces,labels,visibility,launcher_style=choice
        self.applying=True;self.changed();self.status.setText('Applying '+runtime.DESIGNS[style]+'…')
        self.async_run(lambda:backend.apply_mode(value,token,style,avatar,backdrop,background,surfaces,launcher_style,
            launcher_labels=labels,launcher_background_visibility=visibility),lambda token:self.saved(choice,token),self.failed)
    def saved(self,value,token):
        self.background=runtime.launcher_background()
        self.surfaces=runtime.launcher_surfaces()
        self.baseline=(*value[:4],self.background,copy.deepcopy(self.surfaces),dict(self.labels),self.visibility,value[-1]);self.token=token;self.applying=False;self.changed()
        self.design_page.refresh();self.start_menu_page.refresh()
        menu=value[0] if value[-1]=='follow' else value[-1]
        self.status.setText(runtime.DESIGNS[value[0]]+' desktop · '+runtime.DESIGNS[menu]+' Start menu applied. Older applications may need reopening.')
    def failed(self,message):self.applying=False;self.changed();self.status.setText(message)
