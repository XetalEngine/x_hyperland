"""Compiz Wobbly Windows controls for Theme → Window effects."""
from PyQt6.QtCore import Qt, QTimer, QTime
from PyQt6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QFormLayout,QGroupBox,
    QScrollArea,QLabel,QCheckBox,QSpinBox,QDoubleSpinBox,QComboBox,QLineEdit,QPushButton,QMessageBox,QDialog,QTextBrowser)
from . import model,controller


class WobblyPage(QWidget):
    def __init__(self,async_run):
        super().__init__();self.async_run=async_run
        error=''
        try:self.baseline,self.token=model.load()
        except (OSError,ValueError) as exc:
            self.baseline,self.token=dict(model.DEFAULTS),None;error=f'Cannot read Wobbly settings: {exc}. Repair settings.json, then Reload.'
        self.fields={};self.dirty=self.busy=self.loading=False;self.previews=[]
        root=QVBoxLayout(self);root.setContentsMargins(16,12,16,12)
        row=QHBoxLayout();title=QLabel('Wobbly Windows');title.setObjectName('brand');row.addWidget(title);row.addStretch()
        self.enabled=QCheckBox('Enable Wobbly Windows');self.fields['enabled']=self.enabled;row.addWidget(self.enabled);root.addLayout(row)
        text=QLabel('The original Compiz springs, soft window edges and magnetic snapping. Drag a window to feel it.');text.setWordWrap(True);text.setObjectName('muted');root.addWidget(text)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.body=QWidget();grid=QGridLayout(self.body);grid.setContentsMargins(0,8,0,8);grid.setSpacing(14)
        motion=QGroupBox('Spring & mesh');m=QFormLayout(motion)
        snap=QGroupBox('Snapping & shiver');s=QFormLayout(snap)
        for key,label,tip in (
            ('friction','Friction','Spring damping. Lower values wobble for longer. Compiz default: 3.'),
            ('spring_k','Spring K','Spring stiffness. Compiz default: 8.'),
            ('grid_resolution','Grid resolution','Number of subdivisions along each window dimension. Higher values make smoother edges.'),
            ('min_grid_size','Minimum grid size','Smallest mesh cell in logical pixels. Compiz default: 8.')):
            field=QSpinBox() if type(model.DEFAULTS[key]) is int else QDoubleSpinBox()
            field.setRange(*model.RANGES[key]);field.setKeyboardTracking(False);field.setToolTip(tip);field.setAccessibleName(label)
            if isinstance(field,QDoubleSpinBox):field.setDecimals(1);field.setSingleStep(.1)
            field.valueChanged.connect(self.edited);self.fields[key]=field;m.addRow(label,field)
        key=QComboBox();key.setEditable(True)
        for text,value in [('Shift','<Shift>'),('Control','<Control>'),('Alt','<Alt>'),('Super','<Super>'),('Control + Alt','<Control><Alt>'),('Disabled','')]:key.addItem(text,value)
        key.setToolTip('Hold these modifiers while moving to magnetically resist screen and window edges. Custom example: <Control><Shift>.')
        key.currentIndexChanged.connect(self.edited);key.editTextChanged.connect(self.edited);self.fields['snap_key']=key;s.addRow('Snap windows',key)
        for form,name,label,tip in (
            (s,'snap_inverted','Invert snapping','Snap without the modifier; hold the modifier to release snapping.'),
            (s,'shiver','Shiver on application bell','Shiver when a Wayland or XWayland application rings its system bell.'),
            (m,'hotkey_drag','Wobble on '+model.drag_shortcut(),'Bend while moving or resizing through a configured mouse binding. Turning this off still lets you move windows.'),
            (m,'normal_drag','Wobble on normal drag','Bend when using an application title bar or the floating-window top grip. Text selection stays with the application.'),
            (m,'maximize_effect','Wobble when maximizing or restoring','Keep the corners anchored while the spring mesh catches up with the new size.')):
            field=QCheckBox(label);field.setToolTip(tip);field.toggled.connect(self.edited);self.fields[name]=field;form.addRow(field)
        for key,label,tip in (('map_effect','Map effect','Effect when a matching window opens.'),('focus_effect','Focus effect','Effect when a matching window gains focus.')):
            field=QComboBox();field.addItems(('None','Shiver'));field.setToolTip(tip);field.currentIndexChanged.connect(self.edited);self.fields[key]=field;s.addRow(label,field)
        grid.addWidget(motion,0,0);grid.addWidget(snap,0,1)
        matches=QGroupBox('Which windows?');f=QFormLayout(matches)
        help_row=QHBoxLayout();help_row.addStretch()
        self.help=QPushButton('Help');self.help.clicked.connect(self.show_help);help_row.addWidget(self.help);f.addRow(help_row)
        for key,label,tip in (
            ('move_window_match','Move windows','Windows that bend while moving or resizing.'),
            ('grab_window_match','Grab windows','Windows given an extra spring impulse when grabbed. Empty means no extra impulse.'),
            ('map_window_match','Map windows','Windows affected by Map effect.'),
            ('focus_window_match','Focus windows','Windows affected by Focus effect. Empty means none.')):
            field=QLineEdit();field.setMaxLength(1024);field.setToolTip(tip);field.setAccessibleName(label);field.textChanged.connect(self.edited)
            self.fields[key]=field;f.addRow(label,field)
        help=QLabel('Use Any, Normal or Dialog; combine with | (or), & (and), ! (not) and parentheses.\nExample: Normal & !class=kitty. App classes, titles and roles accept * and ? wildcards.\nWayland popups belong to their parent window; independent X11 menus can match their original Compiz types.')
        help.setObjectName('muted');help.setWordWrap(True);f.addRow(help);grid.addWidget(matches,1,0,1,2)
        grid.setColumnStretch(0,1);grid.setColumnStretch(1,1);grid.setRowStretch(2,1)
        scroll.setWidget(self.body);root.addWidget(scroll,1)
        self.status=QLabel('Apply, then move or resize a floating window.');self.status.setObjectName('muted');self.status.setWordWrap(True);root.addWidget(self.status)
        row=QHBoxLayout()
        self.system_defaults=QPushButton('System defaults');self.system_defaults.clicked.connect(lambda:self.set_values(model.DEFAULTS));row.addWidget(self.system_defaults)
        self.defaults=QPushButton('Compiz defaults');self.defaults.clicked.connect(self.reset_defaults);row.addWidget(self.defaults)
        self.preview=QPushButton('Try Wobbly');self.preview.clicked.connect(self.show_preview);row.addWidget(self.preview);row.addStretch()
        self.reload=QPushButton('Reload');self.reload.clicked.connect(lambda:self.refresh(True));row.addWidget(self.reload)
        self.discard=QPushButton('Discard');self.discard.clicked.connect(self.reset);row.addWidget(self.discard)
        self.apply=QPushButton('Apply Wobbly');self.apply.setObjectName('primary');self.apply.clicked.connect(self.save);row.addWidget(self.apply);root.addLayout(row)
        self.enabled.toggled.connect(self.edited);self.reset()
        if error:self.status.setText(error)

    def values(self):
        values={}
        for key,field in self.fields.items():
            if isinstance(field,QCheckBox):value=field.isChecked()
            elif isinstance(field,QLineEdit):value=field.text()
            elif isinstance(field,QComboBox):
                if key=='snap_key':
                    i=field.findText(field.currentText());value=field.itemData(i) if i>=0 else field.currentText()
                else:value=field.currentIndex()
            else:value=field.value()
            values[key]=value
        return model.validate(values)

    def set_values(self,values):
        self.loading=True
        for key,field in self.fields.items():
            value=values[key]
            if isinstance(field,QCheckBox):field.setChecked(value)
            elif isinstance(field,QLineEdit):field.setText(value)
            elif isinstance(field,QComboBox):
                if key=='snap_key':
                    i=field.findData(value)
                    if i>=0:field.setCurrentIndex(i)
                    else:field.setEditText(value)
                else:field.setCurrentIndex(value)
            else:field.setValue(value)
        self.loading=False;self.edited()

    def edited(self,*_):
        if self.loading:return
        valid=True
        try:self.dirty=self.values()!=self.baseline
        except ValueError as exc:self.dirty=True;valid=False;self.status.setText(str(exc))
        self.body.setEnabled(not self.busy);self.enabled.setEnabled(not self.busy)
        self.apply.setEnabled(valid and self.dirty and not self.busy);self.discard.setEnabled(self.dirty and not self.busy)
        for button in (self.reload,self.defaults,self.system_defaults):button.setEnabled(not self.busy)
        self.preview.setEnabled(not self.busy and not self.dirty and self.baseline['enabled'])
        self.preview.setToolTip('Enable and apply Wobbly, then open a sample window to drag, resize or shiver.')

    def reset(self):self.set_values(self.baseline)
    def reset_defaults(self):self.set_values(dict(model.COMPIZ_DEFAULTS,**model.DRAG_DEFAULTS,enabled=self.enabled.isChecked()))
    def refresh(self,force=False):
        self.fields['hotkey_drag'].setText('Wobble on '+model.drag_shortcut())
        if self.busy or self.dirty and not force:return
        if self.dirty and QMessageBox.question(self,'Discard Wobbly edits?','Reload saved settings and discard these edits?',QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)!=QMessageBox.StandardButton.Discard:return
        try:self.baseline,self.token=model.load();self.reset()
        except (OSError,ValueError) as exc:self.failed(str(exc))
    def save(self):
        if self.busy or not self.dirty:return
        try:values=self.values()
        except ValueError as exc:self.failed(str(exc));return
        self.busy=True;self.edited();self.status.setText('Applying Wobbly… The first enable may take a moment.')
        self.async_run(lambda:controller.save(values,self.token),self.saved,self.failed)
    def saved(self,result):
        self.baseline,self.token=result;self.busy=False;self.reset()
        self.status.setText('Wobbly Windows is on and saved for future logins.' if self.baseline['enabled'] else 'Wobbly is off. Normal window movement is restored.')
    def failed(self,message):self.busy=False;self.edited();self.status.setText(str(message))
    def show_help(self):
        from .help import window_help
        if getattr(self,'help_dialog',None) is not None:
            self.help_dialog.show();self.help_dialog.raise_();return self.help_dialog
        dialog=QDialog(self.window());dialog.setWindowTitle('Wobbly Windows — window matching');dialog.resize(740,650)
        self.help_dialog=dialog
        layout=QVBoxLayout(dialog);text=QTextBrowser();text.setHtml(window_help());layout.addWidget(text)
        close=QPushButton('Close');close.clicked.connect(dialog.close);layout.addWidget(close)
        dialog.show();return dialog
    def show_preview(self):
        self.busy=True;self.edited();self.async_run(lambda:controller.activate(self.baseline),self.preview_ready,self.failed)
    def preview_ready(self,_):
        self.busy=False;self.edited()
        dialog=QDialog(self.window());dialog.setWindowTitle('Wobbly Windows preview');dialog.setModal(False)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose);dialog.resize(560,350)
        root=QVBoxLayout(dialog);root.setContentsMargins(28,24,28,24)
        title=QLabel('Compiz Wobbly Windows');title.setObjectName('brand');root.addWidget(title)
        label=QLabel('Drag or resize this window. Hold your snapping modifier near another window or a screen edge.');label.setWordWrap(True);root.addWidget(label)
        field=QLineEdit('Live window content — edit me while it settles');root.addWidget(field)
        clock=QLabel();clock.setObjectName('brand');root.addWidget(clock);root.addStretch()
        tick=QTimer(dialog);tick.timeout.connect(lambda:clock.setText(QTime.currentTime().toString('hh:mm:ss.zzz')));tick.start(40)
        row=QHBoxLayout();shiver=QPushButton('Shiver');row.addWidget(shiver)
        shiver.clicked.connect(lambda:self.async_run(lambda:controller.hypr('dispatch','xetalwobbly:shiver'),lambda _:None,self.failed))
        close=QPushButton('Close');close.clicked.connect(dialog.close);row.addWidget(close);root.addLayout(row)
        self.previews.append(dialog);dialog.destroyed.connect(lambda:self.previews.remove(dialog) if dialog in self.previews else None)
        dialog.show()
