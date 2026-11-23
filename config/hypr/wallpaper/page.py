"""The wallpaper selector's entry point and presentation choice in Theme."""
import subprocess
import sys
from pathlib import Path
from PyQt6.QtWidgets import QComboBox, QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QFileDialog, QCheckBox, QDialog
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
        folders=QHBoxLayout()
        for caption,kind in [('Add picture folder…','folders'),('Add video folder…','video_folders')]:
            control=QPushButton(caption);control.clicked.connect(lambda _,k=kind:self.add_folder(k));folders.addWidget(control)
        manage=QPushButton('Manage folders…');manage.clicked.connect(self.manage_folders);folders.addWidget(manage);folders.addStretch();body.addLayout(folders)
        self.pause_battery=QCheckBox('Pause video wallpapers while on battery');self.pause_battery.toggled.connect(self.battery_changed);body.addWidget(self.pause_battery)
        self.build_video=QPushButton('Set up video wallpaper playback');self.build_video.clicked.connect(self.setup_video);body.addWidget(self.build_video)
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
        self.pause_battery.blockSignals(True);self.pause_battery.setChecked(values.get('pause_on_battery',True));self.pause_battery.blockSignals(False)
        from wallpaper import video
        self.build_video.setVisible(not video.binary())
        self.status.setText(f"{len(values['folders'])} picture folders · {len(values.get('video_folders',[]))} video folders. The selector remembers Pictures or Videos automatically.")

    def add_folder(self,kind):
        path=QFileDialog.getExistingDirectory(self,'Add video folder' if kind=='video_folders' else 'Add picture folder',str(Path.home()/('Videos' if kind=='video_folders' else 'Pictures')))
        if not path:return
        try:
            current=library.read();value={**current,kind:list(dict.fromkeys([*current.get(kind,[]),path]))}
            self.loaded(library.save(value,current,fields=(kind,)))
        except (OSError,ValueError) as error:self.failed(str(error))

    def manage_folders(self):
        from wallpaper.browser import Folders
        try:
            dialog=Folders(library.read(),self)
            if dialog.exec()==QDialog.DialogCode.Accepted:self.loaded(dialog.options)
        except (OSError,ValueError) as error:self.failed(str(error))

    def battery_changed(self,value):
        if self.baseline is None:return
        try:self.loaded(library.save({**self.baseline,'pause_on_battery':value},self.baseline,fields=('pause_on_battery',)))
        except (OSError,ValueError) as error:self.failed(str(error))

    def setup_video(self):
        from desktop_services.build import build
        self.build_video.setEnabled(False);self.status.setText('Building video wallpaper playback…')
        self.async_run(lambda:build('mpvpaper'),lambda _:self.refresh(),lambda error:(self.build_video.setEnabled(True),self.failed(error)))

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
