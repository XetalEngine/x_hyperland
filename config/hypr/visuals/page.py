"""Parked experimental editor; not exposed by Fusion Settings or its launcher.

Focus is now integrated into visuals.appearance. Keep the other editor code for
future material work; its settings are inactive while EXPERIMENTAL_VISUALS=False.
"""
from copy import deepcopy
import subprocess
import sys
from PyQt6.QtCore import Qt,QTimer
from PyQt6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QComboBox,
    QCheckBox,QSpinBox,QDoubleSpinBox,QPushButton,QTabWidget,QScrollArea,QPlainTextEdit)
from visuals import model,controller


def note(text):
    widget=QLabel(text);widget.setWordWrap(True);widget.setObjectName('muted');return widget


def combo(items):
    widget=QComboBox()
    for key,title in items.items():widget.addItem(title,key)
    return widget


def spin(low,high):
    widget=QSpinBox();widget.setRange(low,high);return widget


class VisualsPage(QWidget):
    def __init__(self,async_run):
        super().__init__();self.async_run=async_run;self.busy=False;self.dirty=False;self.loading=True;self.lease=''
        load_error=''
        try:self.baseline,self.token=model.load()
        except (OSError,ValueError) as error:
            self.baseline=deepcopy(model.DEFAULTS);self.token=None
            load_error='Visual preferences could not be read. Restore visuals/settings.json, then Reload. '+str(error)
        self.draft=deepcopy(self.baseline);self.theme=model.theme_name()
        root=QVBoxLayout(self)
        title=QLabel('Glass, focus & workspace visuals');title.setObjectName('brand');root.addWidget(title)
        root.addWidget(note('Materials and focus follow each theme. Quality limits are separate from your saved Compiz effects.'))
        self.tabs=QTabWidget();root.addWidget(self.tabs,1)
        glass,form=self.form('Glass & materials')
        self.material=QCheckBox('Customize glass for this theme');form.addRow(self.material)
        self.variant=combo(model.VARIANTS);form.addRow('Material',self.variant)
        suggest=QPushButton('Try this theme’s suggested material');suggest.clicked.connect(self.suggest);form.addRow(suggest)
        self.size=spin(1,15);form.addRow('Blur size',self.size)
        self.passes=spin(1,4);form.addRow('Blur passes',self.passes)
        self.proportional=QCheckBox('Proportional blur · experimental');form.addRow(self.proportional)
        form.addRow(note('Proportional blur needs shader blending. It is unavailable on rotated displays.'))
        self.parameters=QWidget();self.parameter_form=QFormLayout(self.parameters);form.addRow(self.parameters)
        form.addRow(note('Glass appears through transparent app backgrounds. Text stays opaque. Preview affects the desktop for 20 seconds; Apply keeps it.'))
        sample=QPushButton('Open a glass sample');sample.clicked.connect(lambda:self.launch('sample'));form.addRow(sample)
        focus,form=self.form('Focus')
        self.focus=QCheckBox('Coordinate borders, shadows, glow and Fusion headers');form.addRow(self.focus)
        form.addRow(note('Uses the current theme’s accent for the active window and a quieter border for inactive windows.'))
        self.border=spin(1,8);form.addRow('Border width',self.border)
        self.shadow=spin(0,40);form.addRow('Shadow size · 0 is off',self.shadow)
        self.glow=QCheckBox('Subtle glow on the active window');form.addRow(self.glow)
        self.glow_size=spin(1,30);form.addRow('Glow size',self.glow_size)
        self.exceptions=QPlainTextEdit();self.exceptions.setPlaceholderText('One app class per line, for example: mpv');self.exceptions.setMaximumHeight(125)
        form.addRow('Apps without glow or shadow',self.exceptions)
        quality,form=self.form('Quality & previews')
        self.quality=combo(model.QUALITY);form.addRow('Visual quality',self.quality)
        form.addRow(note('Lightweight disables blur and glow and limits live previews to 5 fps. Balanced limits blur to 4 / 2 passes and previews to 20 fps. Full effects allows up to 60 fps. Keep current tuning removes the quality limits.'))
        self.reduced=QCheckBox('Reduced motion');form.addRow(self.reduced)
        form.addRow(note('Uses static glass and immediate window transitions; pauses Compiz wobble and burn. Your original effect tuning is retained.'))
        self.hover=QCheckBox('Show large window previews on taskbar hover')
        # Paused by request: do not expose taskbar hover previews.
        # form.addRow(self.hover)
        self.preview_size=spin(240,520);self.preview_size.setSuffix(' px');form.addRow('Preview width',self.preview_size)
        self.preview_fps=spin(1,60);self.preview_fps.setSuffix(' fps');form.addRow('Overview / taskbar preview rate',self.preview_fps)
        workspace,form=self.form('Workspace tools')
        form.addRow(note('Overview shows live window cards across your workspaces. Search by title or app, click to switch, or drag a card to another workspace. Choose a display to see its cube faces.'))
        overview=QPushButton('Open Fusion Overview');overview.clicked.connect(lambda:self.launch('overview'));form.addRow(overview)
        picker=QPushButton('Preview the sharing picker');picker.clicked.connect(self.picker);form.addRow(picker)
        form.addRow(note('To share a workspace, start screen sharing in your app, then choose Workspaces in the Hyper Fusion picker. Switching to another workspace does not change the selected source.'))
        self.quiet=QCheckBox('Reduce distracting effects during screen or workspace capture');form.addRow(self.quiet)
        form.addRow(note('A desktop indicator appears during screen, region or workspace sharing and recording. End capture in the app. Effects return automatically after the final stream stops.'))
        buttons=QHBoxLayout();self.status=note('');root.addWidget(self.status)
        for caption,method in (('Reload',self.refresh),('Discard',self.discard),('Preview · 20 seconds',self.preview),('Apply visuals',self.save)):
            button=QPushButton(caption);button.clicked.connect(method);buttons.addWidget(button)
            if caption.startswith('Apply'):button.setObjectName('primary');self.apply_button=button
        root.addLayout(buttons)
        for control in (self.material,self.proportional,self.focus,self.glow,self.reduced,self.hover,self.quiet):control.toggled.connect(self.changed)
        for control in (self.size,self.passes,self.border,self.shadow,self.glow_size,self.preview_size,self.preview_fps):control.valueChanged.connect(self.changed)
        self.variant.currentIndexChanged.connect(self.variant_changed);self.quality.currentIndexChanged.connect(self.changed)
        self.exceptions.textChanged.connect(self.changed)
        self.clock=QTimer(self);self.clock.setSingleShot(True);self.clock.timeout.connect(self.expired)
        self.fill()
        if load_error:self.status.setText(load_error)

    def form(self,title):
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body=QWidget();form=QFormLayout(body);form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows);form.setContentsMargins(16,16,16,16);form.setSpacing(12)
        scroll.setWidget(body);self.tabs.addTab(scroll,title.replace('&','&&'));return body,form

    def fill(self):
        self.loading=True;theme=model.theme_settings(self.draft,self.theme);material=theme['material'];focus=theme['focus']
        for control,value in ((self.material,material['enabled']),(self.proportional,material['proportional']),
            (self.focus,focus['enabled']),(self.glow,focus['glow']),(self.reduced,self.draft['reduced_motion']),
            (self.hover,self.draft['hover_previews']),(self.quiet,self.draft['quiet_sharing'])):control.setChecked(value)
        for control,value in ((self.size,material['size']),(self.passes,material['passes']),(self.border,focus['border']),
            (self.shadow,focus['shadow']),(self.glow_size,focus['glow_size']),(self.preview_size,self.draft['preview_size']),
            (self.preview_fps,self.draft['preview_fps'])):control.setValue(value)
        self.variant.setCurrentIndex(self.variant.findData(material['variant']));self.quality.setCurrentIndex(self.quality.findData(self.draft['quality']))
        self.exceptions.setPlainText('\n'.join(focus['exceptions']));self.rebuild_parameters()
        self.loading=False;self.changed()

    def rebuild_parameters(self):
        while self.parameter_form.rowCount():self.parameter_form.removeRow(0)
        self.parameter_controls={};variant=self.variant.currentData();groups=[variant]
        if variant in ('aurora','drops','heat_shimmer','prism'):groups.append('glass')
        values=model.theme_settings(self.draft,self.theme)['material']['parameters']
        for group in groups:
            for name,(default,low,high) in model.PARAMETERS.get(group,{}).items():
                control=QDoubleSpinBox();control.setDecimals(3);control.setRange(low,high)
                control.setSingleStep(.05 if high<=10 else 1);control.setValue(values[group][name])
                control.valueChanged.connect(self.changed);self.parameter_controls[group,name]=control
                self.parameter_form.addRow(name.replace('_',' ').capitalize(),control)

    def variant_changed(self):
        if self.loading:return
        self.changed();self.rebuild_parameters()

    def changed(self,*_):
        if self.loading:return
        theme=model.theme_settings(self.draft,self.theme);material=theme['material'];focus=theme['focus']
        material.update(enabled=self.material.isChecked(),variant=self.variant.currentData(),size=self.size.value(),
                        passes=self.passes.value(),proportional=self.proportional.isChecked())
        for (group,name),control in self.parameter_controls.items():material['parameters'][group][name]=control.value()
        focus.update(enabled=self.focus.isChecked(),border=self.border.value(),shadow=self.shadow.value(),glow=self.glow.isChecked(),
                     glow_size=self.glow_size.value(),exceptions=list(dict.fromkeys(s.strip() for s in self.exceptions.toPlainText().splitlines() if s.strip())))
        if theme!=model.THEME or self.theme in self.draft['themes']:self.draft['themes'][self.theme]=theme
        self.draft.update(quality=self.quality.currentData(),reduced_motion=self.reduced.isChecked(),hover_previews=self.hover.isChecked(),
                          quiet_sharing=self.quiet.isChecked(),preview_size=self.preview_size.value(),preview_fps=self.preview_fps.value())
        self.dirty=self.draft!=self.baseline;self.apply_button.setEnabled(self.dirty and not self.busy)
        for control in (self.variant,self.size,self.passes,self.proportional,self.parameters):control.setEnabled(material['enabled'])
        for control in (self.border,self.shadow,self.glow,self.glow_size,self.exceptions):control.setEnabled(focus['enabled'])

    def suggest(self):
        self.material.setChecked(True);self.variant.setCurrentIndex(self.variant.findData(model.SUGGESTIONS.get(self.theme,'acrylic')))

    def refresh(self):
        if self.busy or self.dirty or self.lease:return
        try:self.baseline,self.token=model.load();self.draft=deepcopy(self.baseline);self.theme=model.theme_name();self.fill()
        except (OSError,ValueError) as error:self.status.setText(str(error))

    def job(self,fn,done):
        if self.busy:return
        self.busy=True;self.tabs.setEnabled(False);self.changed()
        def finished(result):self.busy=False;self.tabs.setEnabled(True);done(result);self.changed()
        def failed(message):self.busy=False;self.tabs.setEnabled(True);self.status.setText(message);self.changed()
        self.async_run(fn,finished,failed)

    def save(self):
        if self.busy:return
        if self.token is None:
            self.status.setText('Restore the unreadable visuals/settings.json file, then Reload before applying.');return
        values=deepcopy(self.draft);self.status.setText('Checking and applying visual settings…')
        def done(result):
            self.lease='';self.clock.stop();self.baseline,self.token=result;self.draft=deepcopy(self.baseline);self.fill()
            self.status.setText('Visual settings saved. Existing Compiz preferences are preserved.')
        self.job(lambda:controller.save(values,self.token),done)

    def preview(self):
        values=deepcopy(self.draft)
        def done(token):
            self.lease=token;self.clock.start(21000);self.status.setText('Live preview · automatically returns to saved settings in 20 seconds.')
            if not self.isVisible():self.job(lambda:controller.discard(token),lambda _:setattr(self,'lease',''))
        self.job(lambda:controller.preview(values),done)

    def expired(self):self.lease='';self.status.setText('Preview ended. Apply to keep your edits, or Discard to forget them.')

    def discard(self):
        def done(_):
            self.lease='';self.clock.stop();self.draft=deepcopy(self.baseline);self.fill();self.status.setText('Saved visuals restored.')
        self.job(lambda:controller.discard(self.lease),done)

    def hideEvent(self,event):
        # The guardian is independent of this widget and also covers forced exits.
        if self.lease and not self.busy:self.job(lambda:controller.discard(self.lease),lambda _:setattr(self,'lease',''))
        super().hideEvent(event)

    def launch(self,action):subprocess.Popen([sys.executable,str(model.ROOT/'visuals/app.py'),action])
    def picker(self):subprocess.Popen([sys.executable,str(model.ROOT/'share-picker/app.py'),'--preview'])
