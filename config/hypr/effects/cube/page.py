"""Desktop Cube and 3D Windows share one Control desk effect page."""
from copy import deepcopy
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor,QPixmap,QIcon
from PyQt6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QFormLayout,
    QGroupBox,QScrollArea,QLabel,QCheckBox,QSpinBox,QDoubleSpinBox,QComboBox,
    QPushButton,QColorDialog,QMessageBox)
from . import model,controller


class CubePage(QWidget):
    def __init__(self,async_run):
        super().__init__();self.async_run=async_run
        self.fields={};self.images={};self.colors={};self.busy=self.dirty=self.loading=False
        error=''
        try:self.baseline,self.token=model.load()
        except (OSError,ValueError) as exc:
            self.baseline,self.token=model.validate(model.DEFAULTS),None
            error=f'Cannot read Cube settings: {exc}. Repair effects/cube/settings.json, then Reload.'
        self.data=deepcopy(self.baseline)
        root=QVBoxLayout(self);root.setContentsMargins(16,12,16,12)
        row=QHBoxLayout();title=QLabel('Desktop Cube & 3D Windows');title.setObjectName('brand');row.addWidget(title);row.addStretch()
        self.enabled=QCheckBox('Enable Desktop Cube');self.fields['enabled']=self.enabled;row.addWidget(self.enabled);root.addLayout(row)
        hint=QLabel('Ctrl + Alt + hold left mouse to rotate the cube on that monitor. Release to select; Esc to cancel.')
        hint.setWordWrap(True);hint.setObjectName('muted');root.addWidget(hint)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.body=QWidget();grid=QGridLayout(self.body);grid.setContentsMargins(0,8,0,8);grid.setSpacing(14)
        cube=QGroupBox('Cube');cube_form=QFormLayout(cube)
        windows=QGroupBox('3D Windows');windows_form=QFormLayout(windows)
        caps=QGroupBox('Ceiling and floor');caps_form=QFormLayout(caps)
        sky=QGroupBox('Background and sky');sky_form=QFormLayout(sky)
        for form,key,label,suffix,scale,tip in [
            (cube_form,'wall_opacity','Wall opacity','%',100,'0% makes the desktop walls transparent; windows stay readable.'),
            (cube_form,'zoom','Cube size','%',100,'Zoom out for more space around the cube.'),
            (cube_form,'sensitivity','Mouse sensitivity','',1,'Degrees of rotation per mouse movement unit.'),
            (cube_form,'duration','Transition',' ms',1,'Duration of opening and returning to the selected workspace.'),
            (windows_form,'min_cube_size','Minimum cube size','%',1,'Compiz limits how much the cube shrinks to make room for raised windows.'),
            (windows_form,'window_space','Window separation','%',1,'Maximum space between successive window layers, as a percentage of cube size.'),
            (windows_form,'window_depth','Window thickness','',1,'Compiz depth value. Zero keeps raised windows flat.'),
            (sky_form,'sky_speed','Sky drift',' °/s',1,'Optional picture panning or panorama rotation, independent of the checkbox. Zero stops drift.'),
        ]:
            spin=QSpinBox() if type(model.DEFAULTS[key]) is int or scale==100 else QDoubleSpinBox()
            lo,hi=model.RANGES[key];spin.setRange(int(lo*scale) if isinstance(spin,QSpinBox) else lo,int(hi*scale) if isinstance(spin,QSpinBox) else hi)
            if isinstance(spin,QDoubleSpinBox):spin.setDecimals(2);spin.setSingleStep(.05 if key!='sky_speed' else .5)
            spin.setSuffix(suffix);spin.setKeyboardTracking(False);spin.setToolTip(tip);spin.setAccessibleName(label)
            spin.setProperty('cubeScale',scale);spin.valueChanged.connect(self.edited);self.fields[key]=spin;form.addRow(label,spin)
        raised=QCheckBox('Raise windows above the cube');self.fields['windows_3d']=raised;windows_form.insertRow(0,raised)
        mode=QComboBox();mode.addItem('Gradient','gradient');mode.addItem('Background picture','image');mode.addItem('Panoramic sky','sky')
        mode.currentIndexChanged.connect(self.edited);self.fields['sky_mode']=mode;sky_form.insertRow(0,'Background',mode)
        motion=QCheckBox('Move sky with cube rotation');self.fields['sky_motion']=motion;sky_form.insertRow(1,motion)
        motion.setToolTip('Pan a background picture or rotate a panoramic sky while you turn the cube. For a completely still background, also set Sky drift to zero.')
        for form,key,label in [(cube_form,'edge_color','Cube edge color'),(windows_form,'window_color','Window side color'),
                (caps_form,'cap_color','Ceiling / floor color'),(sky_form,'sky_top','Gradient top'),(sky_form,'sky_bottom','Gradient bottom')]:
            button=QPushButton();button.clicked.connect(lambda _,k=key:self.choose_color(k));button.setAccessibleName(label)
            self.colors[key]=button;form.addRow(label,button)
        for form,key,label in [(caps_form,'top_image','Ceiling picture'),(caps_form,'bottom_image','Floor picture'),(sky_form,'sky_image','Background / sky picture')]:
            row=QHBoxLayout();preview=QLabel();preview.setFixedSize(84,48);preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
            choose=QPushButton('Choose…');choose.clicked.connect(lambda _,k=key:self.choose_image(k));choose.setAccessibleName(label)
            clear=QPushButton('Clear');clear.clicked.connect(lambda _,k=key:self.clear_image(k));clear.setAccessibleName('Clear '+label.lower())
            row.addWidget(preview);row.addWidget(choose,1);row.addWidget(clear);self.images[key]=(preview,clear);form.addRow(label,row)
        grid.addWidget(cube,0,0);grid.addWidget(windows,0,1);grid.addWidget(caps,1,0);grid.addWidget(sky,1,1)
        grid.setColumnStretch(0,1);grid.setColumnStretch(1,1);grid.setRowStretch(2,1)
        scroll.setWidget(self.body);root.addWidget(scroll,1)
        self.status=QLabel('Each monitor keeps its own workspaces. Empty faces become new workspaces only when selected.')
        self.status.setWordWrap(True);self.status.setObjectName('muted');root.addWidget(self.status)
        row=QHBoxLayout()
        self.defaults=QPushButton('Defaults');self.defaults.clicked.connect(self.reset_defaults);row.addWidget(self.defaults)
        self.preview=QPushButton('Preview Cube');self.preview.clicked.connect(self.show_preview);row.addWidget(self.preview);row.addStretch()
        self.reload=QPushButton('Reload');self.reload.clicked.connect(lambda:self.refresh(True));row.addWidget(self.reload)
        self.discard=QPushButton('Discard');self.discard.clicked.connect(self.reset);row.addWidget(self.discard)
        self.apply=QPushButton('Apply Cube');self.apply.setObjectName('primary');self.apply.clicked.connect(self.save);row.addWidget(self.apply);root.addLayout(row)
        for field in (self.enabled,raised,motion):field.toggled.connect(self.edited)
        self.reset()
        if error:self.status.setText(error)

    def values(self):
        out=deepcopy(self.data)
        for key,field in self.fields.items():
            if isinstance(field,QCheckBox):out[key]=field.isChecked()
            elif isinstance(field,QComboBox):out[key]=field.currentData()
            else:
                value=field.value()/field.property('cubeScale')
                out[key]=int(value) if type(model.DEFAULTS[key]) is int else value
        return model.validate(out)

    def set_values(self,values):
        self.loading=True;self.data=deepcopy(values)
        for key,field in self.fields.items():
            if isinstance(field,QCheckBox):field.setChecked(values[key])
            elif isinstance(field,QComboBox):field.setCurrentIndex(field.findData(values[key]))
            else:
                value=values[key]*field.property('cubeScale');field.setValue(round(value) if isinstance(field,QSpinBox) else value)
        self.update_art();self.loading=False;self.edited()

    def update_art(self):
        for key,button in self.colors.items():
            c=QColor.fromRgbF(*self.data[key]);pix=QPixmap(20,20);pix.fill(c)
            button.setIcon(QIcon(pix));button.setText('Choose… '+c.name())
        for key,(preview,clear) in self.images.items():
            image=self.data[key];preview.clear();clear.setEnabled(bool(image))
            if image:
                pix=QPixmap(str(model.ROOT/image));preview.setPixmap(pix.scaled(preview.size(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
            else:preview.setText('No picture')

    def edited(self,*_):
        if self.loading:return
        self.dirty=self.values()!=self.baseline
        self.body.setEnabled(not self.busy);self.enabled.setEnabled(not self.busy)
        for key in ('sky_motion','sky_speed'):
            self.fields[key].setEnabled(self.fields['sky_mode'].currentData()!='gradient')
        self.apply.setEnabled(self.dirty and not self.busy and self.token is not None)
        self.discard.setEnabled(self.dirty and not self.busy)
        self.reload.setEnabled(not self.busy);self.defaults.setEnabled(not self.busy)
        self.preview.setEnabled(not self.busy and not self.dirty and self.baseline['enabled'] and self.token is not None)

    def choose_color(self,key):
        c=QColorDialog.getColor(QColor.fromRgbF(*self.data[key]),self,'Cube color',QColorDialog.ColorDialogOption.ShowAlphaChannel|QColorDialog.ColorDialogOption.DontUseNativeDialog)
        if c.isValid():self.data[key]=list(c.getRgbF());self.update_art();self.edited()

    def choose_image(self,key):
        from image_picker import ImagePicker
        name=ImagePicker.choose(self,'Choose cube picture',str(Path.home()/'Pictures'),'Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff);;All files (*)')
        if not name:return
        self.busy=True;self.edited();self.status.setText('Preparing picture…')
        def ready(relative):
            self.data[key]=relative;self.busy=False;self.update_art();self.edited();self.status.setText('Picture ready. Apply Cube to use it.')
        self.async_run(lambda:model.import_image(name),ready,self.failed)

    def clear_image(self,key):self.data[key]='';self.update_art();self.edited()
    def reset(self):self.set_values(self.baseline)
    def reset_defaults(self):
        values=model.validate(model.DEFAULTS);values['enabled']=self.enabled.isChecked();self.set_values(values)
    def refresh(self,force=False):
        if self.busy or (self.dirty and not force):return
        if self.dirty and QMessageBox.question(self,'Discard Cube edits?','Reload saved cube settings and discard these edits?',QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)!=QMessageBox.StandardButton.Discard:return
        try:self.baseline,self.token=model.load();self.reset()
        except (OSError,ValueError) as error:self.failed(str(error))
    def save(self):
        if self.busy or not self.dirty:return
        values=self.values();self.busy=True;self.edited();self.status.setText('Applying Cube… The first build may take a moment.')
        self.async_run(lambda:controller.save(values,self.token),self.saved,self.failed)
    def saved(self,result):
        self.baseline,self.token=result;self.busy=False;self.reset()
        self.status.setText('Desktop Cube is on and saved for future logins.' if self.baseline['enabled'] else 'Desktop Cube is off.')
    def failed(self,message):self.busy=False;self.edited();self.status.setText(str(message))
    def show_preview(self):
        if self.busy:return
        self.busy=True;self.edited()
        def preview():controller.activate(self.baseline);return controller.hypr('dispatch','xetalcube:preview')
        def ready(_):self.busy=False;self.edited();self.status.setText('Preview open. Press Esc or click to return.')
        self.async_run(preview,ready,self.failed)
