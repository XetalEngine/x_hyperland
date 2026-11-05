"""The wallpaper selector's entry point and presentation choice in Theme."""
import subprocess
import sys
from PyQt6.QtWidgets import QComboBox, QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout
from wallpaper import library


class SelectorSettings(QGroupBox):
    def __init__(self, async_run):
        super().__init__('Wallpaper Selector')
        self.async_run = async_run; self.busy = False; self.baseline = None
        body = QVBoxLayout(self)
        row = QHBoxLayout(); row.addWidget(QLabel('Style'))
        self.style = QComboBox(); self.style.setAccessibleName('Wallpaper Selector style')
        for key, title in library.STYLES.items(): self.style.addItem(title, key)
        row.addWidget(self.style); row.addStretch(); row.addWidget(QLabel('Super + W'))
        self.open = QPushButton('Open Wallpaper Selector'); self.open.setObjectName('primary')
        self.open.clicked.connect(self.launch); row.addWidget(self.open); body.addLayout(row)
        self.description = QLabel(); self.description.setWordWrap(True); body.addWidget(self.description)
        self.status = QLabel(); self.status.setObjectName('muted'); self.status.setWordWrap(True); body.addWidget(self.status)
        self.style.currentIndexChanged.connect(self.changed)
        self.refresh()

    def refresh(self):
        if self.busy: return
        try: self.loaded(library.read())
        except (OSError, ValueError) as error: self.failed(str(error)); self.style.setEnabled(False)

    def loaded(self, values):
        self.baseline = values; self.busy = False; self.style.setEnabled(True); self.open.setEnabled(True)
        self.style.blockSignals(True); self.style.setCurrentIndex(self.style.findData(values['style'])); self.style.blockSignals(False)
        self.description.setText(library.DESCRIPTIONS[values['style']])
        self.status.setText('Your style is saved automatically. All styles share your folders and wallpaper transitions.')

    def changed(self):
        if self.busy or self.baseline is None: return
        values = {**self.baseline, 'style': self.style.currentData()}; expected = dict(self.baseline)
        self.busy = True; self.style.setEnabled(False); self.open.setEnabled(False); self.status.setText('Saving selector style…')
        self.async_run(lambda: library.save(values, expected, fields=('style',)), self.loaded, self.failed)

    def failed(self, message):
        self.busy = False; self.open.setEnabled(True)
        if self.baseline is not None:
            self.style.blockSignals(True); self.style.setCurrentIndex(self.style.findData(self.baseline['style'])); self.style.blockSignals(False)
        self.style.setEnabled(self.baseline is not None); self.status.setText(str(message))

    def launch(self):
        try:
            subprocess.Popen([sys.executable, str(library.ROOT/'launch.py'), '--show'],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
        except OSError as error: self.failed(str(error))

    def showEvent(self, event):
        self.refresh(); super().showEvent(event)
