"""Recording preferences inside Fusion Settings."""
from pathlib import Path
import subprocess
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
    QFormLayout, QComboBox, QSpinBox, QLineEdit, QPushButton, QFileDialog, QScrollArea)
from . import backend, service


class CapturePage(QWidget):
    def __init__(self, async_run):
        super().__init__()
        self.async_run = async_run
        self.baseline, self.token = dict(backend.DEFAULTS), ''
        self.pending = self.loading = False
        self.state = {'phase': 'idle'}
        outer = QVBoxLayout(self)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); outer.addWidget(scroll)
        content = QWidget(); scroll.setWidget(content); body = QVBoxLayout(content)
        title = QLabel('Screen recording'); title.setObjectName('brand'); body.addWidget(title)
        description = QLabel('Alt + F9 starts and stops recording the display under your pointer.\n'
                             'Your recording stays on that display until you stop it.'); description.setWordWrap(True); body.addWidget(description)
        live = QGroupBox('Record your desktop'); live_layout = QVBoxLayout(live); body.addWidget(live)
        self.activity = QLabel('Ready to record'); self.activity.setWordWrap(True); live_layout.addWidget(self.activity)
        row = QHBoxLayout(); live_layout.addLayout(row)
        self.record = QPushButton('Start recording'); self.record.setObjectName('primary'); self.record.clicked.connect(self.toggle)
        open_folder = QPushButton('Open recordings'); open_folder.clicked.connect(self.browse)
        row.addWidget(self.record); row.addWidget(open_folder); row.addStretch()
        preferences = QGroupBox('Recording options'); form = QFormLayout(preferences); body.addWidget(preferences)
        self.fps = QSpinBox(); self.fps.setRange(1, 240); self.fps.setSuffix(' FPS'); form.addRow('Frame rate', self.fps)
        for name, label, choices in [
            ('audio', 'Audio', [('Desktop audio', 'desktop'), ('Microphone', 'microphone'), ('No audio', 'off')]),
            ('quality', 'Quality', [('High quality', 'high'), ('Balanced', 'balanced'), ('Smaller files', 'small')]),
            ('encoder', 'Encoding', [('Automatic · use the GPU when available', 'auto'), ('Software · use the CPU', 'software')])]:
            combo = QComboBox(); setattr(self, name, combo)
            for caption, value in choices: combo.addItem(caption, value)
            form.addRow(label, combo)
        form.addRow('Video format', QLabel('MP4'))
        folder = QWidget(); folder_row = QHBoxLayout(folder); folder_row.setContentsMargins(0, 0, 0, 0)
        self.directory = QLineEdit(); self.directory.setPlaceholderText(str(backend.videos_directory()))
        choose = QPushButton('Choose…'); choose.clicked.connect(self.choose_folder)
        default = QPushButton('Use Videos'); default.clicked.connect(self.directory.clear)
        folder_row.addWidget(self.directory, 1); folder_row.addWidget(choose); folder_row.addWidget(default); form.addRow('Save to', folder)
        note = QLabel('Desktop audio records the current output device; microphone records the current input.\n'
                      'Changes apply to your next recording. The REC timer in the bar also stops and saves.'); note.setWordWrap(True); body.addWidget(note)
        body.addStretch()
        self.status = QLabel(''); self.status.setWordWrap(True); outer.addWidget(self.status)
        footer = QHBoxLayout(); outer.addLayout(footer)
        defaults = QPushButton('Defaults'); defaults.clicked.connect(lambda: self.set_value(backend.DEFAULTS)); footer.addWidget(defaults)
        footer.addStretch()
        reload_button = QPushButton('Reload'); reload_button.clicked.connect(self.reload); footer.addWidget(reload_button)
        self.discard = QPushButton('Discard'); self.discard.clicked.connect(lambda: self.set_value(self.baseline)); footer.addWidget(self.discard)
        self.apply = QPushButton('Apply recording options'); self.apply.setObjectName('primary'); self.apply.clicked.connect(self.save); footer.addWidget(self.apply)
        self.fps.valueChanged.connect(self.changed)
        for combo in (self.audio, self.quality, self.encoder): combo.currentIndexChanged.connect(self.changed)
        self.directory.textChanged.connect(self.changed)
        self.reload()
        self.timer = QTimer(self); self.timer.setInterval(1000); self.timer.timeout.connect(self.poll); self.timer.start()

    def value(self):
        return dict(fps=self.fps.value(), audio=self.audio.currentData(), quality=self.quality.currentData(),
                    encoder=self.encoder.currentData(), directory=self.directory.text().strip())

    @property
    def dirty(self): return self.value() != self.baseline

    def set_value(self, value):
        self.loading = True
        self.fps.setValue(value['fps']); self.directory.setText(value['directory'])
        for name in ('audio', 'quality', 'encoder'):
            combo = getattr(self, name); combo.setCurrentIndex(combo.findData(value[name]))
        self.loading = False; self.changed()

    def changed(self, *_):
        if self.loading: return
        self.apply.setEnabled(self.dirty); self.discard.setEnabled(self.dirty)
        self.update_state(self.state)

    def refresh(self):
        if not self.dirty: self.reload()
        self.poll()

    def reload(self):
        try:
            self.baseline, self.token = backend.load(); self.set_value(self.baseline)
            self.status.setText('64 FPS · MP4 · Videos folder by default. Alt + F9 can be changed in Hotkeys.')
        except (OSError, ValueError) as error: self.status.setText(str(error))

    def save(self):
        try:
            self.baseline, self.token = backend.save(self.value(), self.token)
            self.changed(); self.status.setText('Saved for your next recording.')
        except (OSError, ValueError) as error: self.status.setText(str(error))

    def choose_folder(self):
        selected = QFileDialog.getExistingDirectory(self, 'Save recordings to', self.directory.text() or str(backend.videos_directory()))
        if selected: self.directory.setText(selected)

    def browse(self):
        try:
            directory = Path(self.baseline['directory']).expanduser() if self.baseline['directory'] else backend.videos_directory()
            directory.mkdir(parents=True, exist_ok=True)
            subprocess.Popen(['xdg-open', str(directory)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as error: self.status.setText(str(error))

    def toggle(self):
        if self.pending: return
        self.pending = True; self.record.setEnabled(False)
        self.async_run(lambda: service.request('toggle'), self.received, self.failed)

    def poll(self):
        if self.pending or not self.isVisible(): return
        self.pending = True
        self.async_run(lambda: service.request('status'), self.received, self.failed)

    def received(self, state):
        self.pending = False; self.update_state(state)

    def failed(self, message):
        self.pending = False; self.status.setText(message); self.update_state(self.state)

    def update_state(self, state):
        self.state = state; phase = state.get('phase', 'idle')
        capturing = phase in ('starting', 'recording')
        self.record.setText('Stop and save' if capturing else 'Saving…' if phase in ('stopping', 'saving') else 'Start recording')
        self.record.setEnabled(not self.pending and phase not in ('stopping', 'saving') and (capturing or not self.dirty))
        messages = {'starting': 'Starting on '+state.get('monitor', '')+'…',
                    'recording': f"Recording {state.get('monitor', '')} · {service.elapsed(state)} · {state.get('fps', 64)} FPS",
                    'stopping': 'Stopping capture…', 'saving': 'Saving your MP4…',
                    'saved': 'Saved: '+state.get('file', ''),
                    'error': state.get('error', '')+'\n'+state.get('recovery', '')}
        self.activity.setText(messages.get(phase, 'Apply your changes before recording.' if self.dirty else 'Ready to record · Alt + F9'))
