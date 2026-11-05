"""Minimize controls under Theme → Window effects."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon, QPixmap
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
                            QCheckBox, QSpinBox, QComboBox, QPushButton, QMessageBox, QDialog,
                            QColorDialog, QGroupBox, QTabWidget)
from . import model, controller
from .gallery import DesignList, PreviewDetails, PreviewPanel


class MinimizePage(QWidget):
    def __init__(self, async_run):
        super().__init__()
        self.async_run = async_run
        self.busy = self.dirty = self.loading = False
        self.previews = []
        error = ''
        try:
            self.baseline, self.token = model.load()
        except (OSError, ValueError) as exc:
            self.baseline, self.token = dict(model.DEFAULTS), None
            error = f'Cannot read Minimize settings: {exc}. Repair effects/minimize/settings.conf, then Reload.'
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        heading = QHBoxLayout()
        title = QLabel('Minimize'); title.setObjectName('brand'); heading.addWidget(title)
        heading.addStretch()
        self.enabled = QCheckBox('Enable minimizing'); heading.addWidget(self.enabled)
        root.addLayout(heading)
        description = QLabel('Super + Z sends a window into its Fireball slot. Click to restore it. '
                             'Choose an animated dock or keep the classic edge stack.')
        description.setWordWrap(True); description.setObjectName('muted'); root.addWidget(description)
        workspace = QHBoxLayout(); workspace.setSpacing(14)
        self.dock_style = DesignList(); workspace.addWidget(self.dock_style)
        self.dock_preview = PreviewPanel()
        controls = QTabWidget(); controls.setMinimumWidth(330)
        general = QGroupBox('Minimizer'); self.general_form = form = QFormLayout(general); form.setSpacing(12)
        self.presentation = QComboBox()
        for value,title in model.PRESENTATIONS.items():self.presentation.addItem(title,value)
        form.addRow('Presentation',self.presentation)
        self.effect = QComboBox()
        self.effect.addItem('Fireball', 'fireball')
        # self.effect.addItem('Splat', 'splat')  # Parked for a future revision.
        form.addRow('Minimize effect', self.effect)
        self.edge = QComboBox()
        for value, title in model.EDGES.items(): self.edge.addItem(title, value)
        form.addRow('Screen edge', self.edge)
        self.order = QComboBox()
        for value, title in model.ORDERS.items(): self.order.addItem(title, value)
        form.addRow('Stack direction', self.order)
        self.duration = QSpinBox(); self.duration.setRange(*model.RANGES['duration']); self.duration.setSuffix(' ms')
        self.duration.setKeyboardTracking(False); form.addRow('Travel time', self.duration)
        self.size = QSpinBox(); self.size.setRange(*model.RANGES['size']); self.size.setSuffix(' px')
        self.size.setKeyboardTracking(False); form.addRow('Effect size', self.size)
        self.speed = QSpinBox(); self.speed.setRange(*model.RANGES['speed']); self.speed.setSuffix('%')
        self.speed.setKeyboardTracking(False); form.addRow('Animation speed', self.speed)
        self.follow_theme = QCheckBox('Follow the active theme accent'); form.addRow(self.follow_theme)
        self.color = self.baseline['color']
        self.color_button = QPushButton(); self.color_button.clicked.connect(self.choose_color)
        form.addRow('Custom color', self.color_button)
        controls.addTab(general, 'Minimizer')
        self.dock_options = QGroupBox('Animated dock'); dock = QFormLayout(self.dock_options);dock.setSpacing(12)
        self.dock_edge = QComboBox()
        for value,title in model.DOCK_EDGES.items():self.dock_edge.addItem(title,value)
        dock.addRow('Position',self.dock_edge)
        self.auto_hide = QCheckBox('Automatically hide after use');dock.addRow(self.auto_hide)
        self.hide_animation=QComboBox()
        for value,title in model.HIDE_ANIMATIONS.items():self.hide_animation.addItem(title,value)
        dock.addRow('Hide animation',self.hide_animation)
        self.fire_indicator=QCheckBox('Fire indicator');dock.addRow(self.fire_indicator)
        self.fire_indicator.setToolTip('Keep a low flame along the dock edge while windows are minimized. It disappears when the dock is empty.')
        self.dock_form=dock
        for key,label,suffix in (('hide_delay','Hide after',' ms'),('dock_duration','Transition and resize time',' ms'),
                                 ('proximity','Edge proximity',' px'),('dock_zoom','Hover zoom','%')):
            field=QSpinBox();field.setRange(*model.RANGES[key]);field.setSuffix(suffix);field.setKeyboardTracking(False)
            setattr(self,key,field);dock.addRow(label,field)
        self.dock_note = QLabel('Each monitor has its own dock. It grows as windows arrive, then slides away or burns away to hide. '
                               'Move near that edge to reveal it; scroll over slots when it fills up. '
                               'Side proximity also works at shared monitor boundaries.')
        self.dock_note.setWordWrap(True);self.dock_note.setObjectName('muted');dock.addRow(self.dock_note)
        controls.addTab(self.dock_options, 'Dock behavior')
        controls.setCurrentWidget(self.dock_options if self.baseline['presentation'] == 'dock' else general)
        for layout in (form, dock):
            layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            layout.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        self.details = PreviewDetails(self.dock_preview, controls); workspace.addWidget(self.details, 1)
        root.addLayout(workspace, 1)
        note = QLabel('Your apps stay open. Turning this off restores all minimized windows to their workspaces.')
        note.setWordWrap(True); note.setObjectName('muted'); root.addWidget(note)
        self.status = QLabel(error or 'Choose a design to preview it. Apply Minimize updates your dock; Try minimizer opens a real test window.')
        self.status.setWordWrap(True); self.status.setObjectName('muted'); root.addWidget(self.status)
        row = QHBoxLayout()
        self.defaults = QPushButton('Defaults'); self.defaults.clicked.connect(self.use_defaults); row.addWidget(self.defaults)
        self.preview = QPushButton('Try minimizer'); self.preview.clicked.connect(self.show_preview); row.addWidget(self.preview)
        self.restore = QPushButton('Restore all windows'); self.restore.clicked.connect(self.restore_all); row.addWidget(self.restore)
        row.addStretch()
        self.reload = QPushButton('Reload'); self.reload.clicked.connect(lambda: self.refresh(True)); row.addWidget(self.reload)
        self.discard = QPushButton('Discard'); self.discard.clicked.connect(self.reset); row.addWidget(self.discard)
        self.apply = QPushButton('Apply Minimize'); self.apply.setObjectName('primary'); self.apply.clicked.connect(self.save); row.addWidget(self.apply)
        root.addLayout(row)
        self.enabled.toggled.connect(self.edited); self.effect.currentIndexChanged.connect(self.edited)
        for field in (self.edge,self.order,self.presentation,self.dock_edge,self.hide_animation):field.currentIndexChanged.connect(self.edited)
        self.dock_style.valueChanged.connect(self.edited)
        for field in (self.duration,self.size,self.speed,self.hide_delay,self.dock_duration,self.proximity,self.dock_zoom):field.valueChanged.connect(self.edited)
        self.follow_theme.toggled.connect(self.edited);self.auto_hide.toggled.connect(self.edited)
        self.fire_indicator.toggled.connect(self.edited)
        if hasattr(QApplication.instance(), 'hypr_theme'):
            QApplication.instance().hypr_theme.changed.connect(self.desktop_changed)
        self.reset()

    def values(self):
        return model.validate(dict(self.baseline,enabled=self.enabled.isChecked(), effect='fireball',
                                   edge=self.edge.currentData(), order=self.order.currentData(),
                                   presentation=self.presentation.currentData(),dock_edge=self.dock_edge.currentData(),dock_style=self.dock_style.value(),
                                   auto_hide=self.auto_hide.isChecked(),hide_delay=self.hide_delay.value(),dock_duration=self.dock_duration.value(),
                                   hide_animation=self.hide_animation.currentData(),fire_indicator=self.fire_indicator.isChecked(),
                                   proximity=self.proximity.value(),dock_zoom=self.dock_zoom.value(),
                                   duration=self.duration.value(), size=self.size.value(), follow_theme=self.follow_theme.isChecked(),
                                   color=self.color, speed=self.speed.value()))

    def reset(self):
        self.fill(self.baseline)

    def use_defaults(self):
        self.fill(model.DEFAULTS)

    def fill(self, values):
        self.loading = True
        self.enabled.setChecked(values['enabled'])
        self.effect.setCurrentIndex(self.effect.findData(values['effect']))
        self.edge.setCurrentIndex(self.edge.findData(values['edge'])); self.order.setCurrentIndex(self.order.findData(values['order']))
        self.duration.setValue(values['duration']); self.size.setValue(values['size'])
        self.follow_theme.setChecked(values['follow_theme']); self.color = values['color']
        self.speed.setValue(values['speed'])
        for key in ('presentation','dock_edge','hide_animation'):
            field=getattr(self,key);field.setCurrentIndex(field.findData(values[key]))
        self.dock_style.setValue(values['dock_style'])
        self.auto_hide.setChecked(values['auto_hide'])
        self.fire_indicator.setChecked(values['fire_indicator'])
        for key in ('hide_delay','dock_duration','proximity','dock_zoom'):getattr(self,key).setValue(values[key])
        self.loading = False; self.edited()

    def choose_color(self):
        color = QColorDialog.getColor(QColor(self.color), self, 'Minimize effect color')
        if color.isValid(): self.color = color.name(); self.edited()

    def edited(self, *_):
        if self.loading:
            return
        self.dirty = self.values() != self.baseline
        for field in (self.enabled, self.effect, self.edge, self.order, self.duration, self.size, self.speed, self.follow_theme,
                      self.presentation,self.defaults,self.reload,self.restore):
            field.setEnabled(not self.busy)
        dock=self.presentation.currentData()=='dock'
        self.dock_options.setEnabled(dock and not self.busy)
        self.dock_style.setEnabled(dock and not self.busy)
        self.general_form.setRowVisible(self.edge,not dock);self.general_form.setRowVisible(self.order,not dock)
        self.hide_delay.setEnabled(self.auto_hide.isChecked());self.proximity.setEnabled(self.auto_hide.isChecked())
        self.hide_animation.setEnabled(self.auto_hide.isChecked())
        self.dock_form.setRowVisible(self.fire_indicator,self.hide_animation.currentData()=='burn')
        self.fire_indicator.setEnabled(self.auto_hide.isChecked())
        self.color_button.setEnabled(not self.busy and not self.follow_theme.isChecked())
        self.color_button.setText('Choose… ' + self.color)
        swatch = QPixmap(18, 18); swatch.fill(QColor(self.color)); self.color_button.setIcon(QIcon(swatch))
        self.apply.setEnabled(self.dirty and not self.busy and self.token is not None)
        self.discard.setEnabled(self.dirty and not self.busy)
        self.preview.setEnabled(not self.busy and not self.dirty and self.baseline['enabled'] and self.token is not None)
        self.dock_preview.configure(self.values())

    def desktop_changed(self):
        self.dock_style.refresh(); self.dock_preview.configure(self.values()); self.details.arrange()

    def refresh(self, force=False):
        if self.busy or (self.dirty and not force):
            return
        if self.dirty and QMessageBox.question(self, 'Discard Minimize edits?', 'Reload saved settings and discard these edits?',
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Discard:
            return
        try:
            self.baseline, self.token = model.load(); self.reset()
        except (OSError, ValueError) as exc:
            self.failed(str(exc))

    def save(self):
        if self.busy or not self.dirty:
            return
        values = self.values(); self.busy = True; self.edited(); self.status.setText('Applying Minimize…')
        self.async_run(lambda: controller.save(values, self.token), self.saved, self.failed)

    def saved(self, result):
        self.baseline, self.token = result; self.busy = False; self.reset()
        self.status.setText('Minimize is on and saved for future logins.' if self.baseline['enabled'] else
                            'Minimize is off. Your windows have been restored.')

    def failed(self, message):
        self.busy = False; self.edited(); self.status.setText(str(message))

    def restore_all(self):
        if self.busy:
            return
        self.busy = True; self.edited()
        def done(_):
            self.busy = False; self.edited(); self.status.setText('All minimized windows returned to their workspaces.')
        self.async_run(lambda: controller.hypr('dispatch', 'xetalminimize:restoreall'), done, self.failed)

    def show_preview(self):
        if self.busy:
            return
        self.busy = True; self.edited()
        self.async_run(lambda: controller.activate(self.baseline), self.preview_ready, self.failed)

    def preview_ready(self, _):
        self.busy = False; self.edited()
        preview = QDialog(self.window()); preview.setWindowTitle('Minimize preview'); preview.setModal(False)
        preview.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose); preview.resize(520, 300)
        layout = QVBoxLayout(preview); layout.setContentsMargins(28, 24, 28, 24)
        text = QLabel('Minimize this window to try your dock or edge stack. Move near the dock’s edge to reveal it, then click its Fireball to restore.'); text.setWordWrap(True)
        layout.addWidget(text); layout.addStretch()
        minimize = QPushButton('Minimize this window'); minimize.setObjectName('primary'); minimize.clicked.connect(preview.showMinimized)
        layout.addWidget(minimize)
        close = QPushButton('Close preview'); close.clicked.connect(preview.close); layout.addWidget(close)
        self.previews.append(preview)
        preview.destroyed.connect(lambda: self.previews.remove(preview) if preview in self.previews else None)
        preview.show()
