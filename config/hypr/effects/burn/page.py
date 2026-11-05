"""Compiz Burn controls, integrated into Theme → Window effects."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QGroupBox, QScrollArea, QLabel, QCheckBox, QSpinBox, QDoubleSpinBox, QComboBox,
    QPushButton, QColorDialog, QMessageBox, QDialog, QTabWidget)
from . import model, controller


class BurnPage(QWidget):
    def __init__(self, async_run):
        super().__init__()
        self.async_run = async_run
        load_error = ''
        try:self.baseline, self.token = model.load()
        except (OSError,ValueError) as error:
            self.baseline, self.token = model.validate(model.DEFAULTS), None
            load_error = f'Cannot read Burn settings: {error}. Repair effects/burn/settings.conf, then Reload.'
        self.fields = {}; self.busy = self.dirty = self.loading = False
        self.previews = []
        root = QVBoxLayout(self);root.setContentsMargins(16,12,16,12)
        title = QHBoxLayout()
        heading = QLabel('Burn');heading.setObjectName('brand');title.addWidget(heading)
        title.addStretch();self.enabled = QCheckBox('Burn closing windows');title.addWidget(self.enabled)
        self.fields['enabled'] = self.enabled;root.addLayout(title)
        text = QLabel('The original Compiz flame, with its particle texture and controls.');text.setObjectName('muted');text.setWordWrap(True);root.addWidget(text)
        scroll = QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.body = QWidget();body = QGridLayout(self.body);body.setContentsMargins(0,8,0,8);body.setSpacing(14)
        flames = QGroupBox('Flames');f = QFormLayout(flames);f.setSpacing(10)
        motion = QGroupBox('Animation');m = QFormLayout(motion);m.setSpacing(10)
        for form, key, title, tooltip in [
            (f,'fire_particles','Number of particles','Maximum fire particles. Smoke uses one tenth of this number.'),
            (f,'fire_size','Fire size','Original Compiz particle size, before the window-size variation.'),
            (f,'fire_life','Fire life','Higher values let individual flames live longer.'),
            (f,'fire_slowdown','Fire slowdown','Higher values slow the particles down.'),
            (m,'duration','Duration','How long the window takes to burn. Remaining particles fade out afterwards.'),
            (m,'time_step_intense','Animation time step','Milliseconds between intense-effect steps. Higher values make movement jerkier.'),
        ]:
            spin = QSpinBox() if type(model.DEFAULTS[key]) is int else QDoubleSpinBox()
            spin.setRange(*model.RANGES[key]);spin.setKeyboardTracking(False)
            if isinstance(spin,QDoubleSpinBox):spin.setDecimals(1);spin.setSingleStep(.1)
            if key in ('duration','time_step_intense'):spin.setSuffix(' ms')
            spin.setToolTip(tooltip);spin.setAccessibleName(title);spin.setMinimumWidth(100)
            spin.valueChanged.connect(self.edited);form.addRow(title,spin);self.fields[key] = spin
        self.color = list(self.baseline['fire_color'])
        self.color_button = QPushButton();self.color_button.clicked.connect(self.choose_color)
        self.color_button.setAccessibleName('Fire color and opacity');f.addRow('Fire color',self.color_button)
        direction = QComboBox();direction.addItems(model.DIRECTIONS);direction.currentIndexChanged.connect(self.edited)
        direction.setToolTip('Automatic burns toward the pointer position when the window closes, as in Compiz.')
        self.fields['fire_direction'] = direction;m.insertRow(0,'Direction',direction)
        for form,key,title,tip in [
            (m,'fire_constant_speed','Constant speed','Keep the burn speed proportional to window height, as in Compiz.'),
            (m,'fire_smoke','Smoke','Add the original Compiz smoke particles.'),
            (m,'fire_mystical','Randomly colored fire','Mystical Fire: random particle colors, using the opacity from your chosen fire color.'),
        ]:
            field = QCheckBox(title);field.setToolTip(tip);field.toggled.connect(self.edited)
            self.fields[key] = field;form.addRow(field)
        body.addWidget(flames,0,0);body.addWidget(motion,0,1);body.setColumnStretch(0,1);body.setColumnStretch(1,1);body.setRowStretch(1,1)
        scroll.setWidget(self.body);root.addWidget(scroll,1)
        self.status = QLabel('Changes apply to the next window you close.');self.status.setWordWrap(True);self.status.setObjectName('muted');root.addWidget(self.status)
        row = QHBoxLayout()
        self.defaults = QPushButton('Compiz defaults');self.defaults.clicked.connect(self.reset_defaults);row.addWidget(self.defaults)
        self.preview = QPushButton('Preview Burn');self.preview.clicked.connect(self.show_preview);row.addWidget(self.preview)
        row.addStretch()
        self.reload = QPushButton('Reload');self.reload.clicked.connect(lambda:self.refresh(True));row.addWidget(self.reload)
        self.discard = QPushButton('Discard');self.discard.clicked.connect(self.reset);row.addWidget(self.discard)
        self.apply = QPushButton('Apply Burn');self.apply.setObjectName('primary');self.apply.clicked.connect(self.save);row.addWidget(self.apply)
        root.addLayout(row);self.enabled.toggled.connect(self.edited);self.reset()
        if load_error:self.status.setText(load_error)

    def values(self):
        values = {}
        for key,field in self.fields.items():
            values[key] = field.isChecked() if isinstance(field,QCheckBox) else field.currentIndex() if isinstance(field,QComboBox) else field.value()
        values['fire_color'] = list(self.color)
        return model.validate(values)

    def set_values(self,values):
        self.loading = True
        for key,field in self.fields.items():
            if isinstance(field,QCheckBox):field.setChecked(values[key])
            elif isinstance(field,QComboBox):field.setCurrentIndex(values[key])
            else:field.setValue(values[key])
        self.color = list(values['fire_color']);self.update_color();self.loading = False;self.edited()

    def update_color(self):
        c = QColor.fromRgba64(*self.color)
        self.color_button.setText(f'Choose…  #{c.red():02X}{c.green():02X}{c.blue():02X}{c.alpha():02X}')
        # A swatch in the button icon keeps the normal theme's button styling.
        from PyQt6.QtGui import QPixmap,QIcon
        image = QPixmap(22,22);image.fill(c);self.color_button.setIcon(QIcon(image))

    def choose_color(self):
        color = QColorDialog.getColor(QColor.fromRgba64(*self.color),self,'Fire color',
            QColorDialog.ColorDialogOption.ShowAlphaChannel|QColorDialog.ColorDialogOption.DontUseNativeDialog)
        if color.isValid():
            c = color.rgba64();self.color = [c.red(),c.green(),c.blue(),c.alpha()];self.update_color();self.edited()

    def edited(self,*_):
        if self.loading:return
        self.dirty = self.values() != self.baseline
        self.body.setEnabled(not self.busy);self.enabled.setEnabled(not self.busy)
        self.apply.setEnabled(self.dirty and not self.busy);self.discard.setEnabled(self.dirty and not self.busy)
        self.reload.setEnabled(not self.busy);self.defaults.setEnabled(not self.busy)
        self.preview.setEnabled(not self.busy and not self.dirty and self.baseline['enabled'])
        self.preview.setToolTip('Apply your Burn settings, then close a sample window to preview them.')

    def reset(self):self.set_values(self.baseline)

    def reset_defaults(self):
        values = model.validate(model.DEFAULTS);values['enabled'] = self.enabled.isChecked();self.set_values(values)

    def refresh(self,force=False):
        if self.busy or (self.dirty and not force):return
        if self.dirty and QMessageBox.question(self,'Discard Burn edits?','Reload saved Burn settings and discard these edits?',
            QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Discard:return
        try:self.baseline,self.token = model.load();self.reset()
        except (OSError,ValueError) as error:self.failed(str(error))

    def save(self):
        if self.busy or not self.dirty:return
        values = self.values();self.busy = True;self.edited();self.status.setText('Applying Burn… The first enable may take a moment.')
        self.async_run(lambda:controller.save(values,self.token),self.saved,self.failed)

    def saved(self,result):
        self.baseline,self.token = result;self.busy = False;self.reset()
        self.status.setText('Burn is on and saved for future logins.' if self.baseline['enabled'] else 'Burn is off. Normal closing animations are restored.')

    def failed(self,message):
        self.busy = False;self.edited();self.status.setText(str(message))

    def show_preview(self):
        if self.busy:return
        self.busy = True;self.edited();self.status.setText('Preparing the preview…')
        self.async_run(lambda:controller.activate(self.baseline),self.preview_ready,self.failed)

    def preview_ready(self,_):
        self.busy = False;self.edited();self.status.setText('Close the preview window to try Burn.')
        dialog = QDialog(self.window());dialog.setWindowTitle('Burn preview');dialog.setModal(False)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose);dialog.resize(540,320)
        layout = QVBoxLayout(dialog);layout.setContentsMargins(28,24,28,24)
        header = QHBoxLayout();title = QLabel('Compiz Burn');title.setObjectName('brand');header.addWidget(title);header.addStretch()
        from window_chrome import close_button
        header.addWidget(close_button(dialog));layout.addLayout(header)
        message = QLabel('Close this window to see your flame settings in action.');message.setWordWrap(True);layout.addWidget(message)
        layout.addStretch();close = QPushButton('Burn this window');close.setObjectName('primary');close.clicked.connect(dialog.close);layout.addWidget(close)
        self.previews.append(dialog)
        dialog.destroyed.connect(lambda:self.previews.remove(dialog) if dialog in self.previews else None)
        dialog.show()


class WindowEffectsPage(QWidget):
    def __init__(self,async_run):
        super().__init__()
        from preferences_page import PreferencesPage
        from effects.cube.page import CubePage
        from effects.minimize.page import MinimizePage
        from effects.wobbly.page import WobblyPage
        from cursors.mouse_page import MouseEffectsPage
        self.burn = BurnPage(async_run);self.cube = CubePage(async_run);self.appearance = PreferencesPage('appearance',async_run)
        self.minimize = MinimizePage(async_run);self.wobbly = WobblyPage(async_run)
        self.mouse = MouseEffectsPage(async_run)
        layout = QVBoxLayout(self);layout.setContentsMargins(0,8,0,0)
        self.tabs = QTabWidget();self.tabs.addTab(self.burn,'Burn');self.tabs.addTab(self.cube,'Desktop Cube + 3D');self.tabs.addTab(self.appearance,'Window appearance');layout.addWidget(self.tabs)
        self.tabs.insertTab(2,self.minimize,'Minimize')
        self.tabs.setTabToolTip(2, 'Animated dock and Fireball edge stack · Super + Z')
        self.tabs.insertTab(2,self.wobbly,'Wobbly Windows')
        self.tabs.insertTab(4,self.mouse,'Mouse effects')
        self.tabs.currentChanged.connect(lambda _:self.refresh())

    @property
    def dirty(self):return self.burn.dirty or self.cube.dirty or self.minimize.dirty or self.wobbly.dirty or self.mouse.dirty or self.appearance.dirty
    @property
    def busy(self):return self.burn.busy or self.cube.busy or self.minimize.busy or self.wobbly.busy or self.mouse.busy or self.appearance.busy
    def refresh(self):self.tabs.currentWidget().refresh()
