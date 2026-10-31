"""Dolphin Places sidebar for our Python Qt applications."""
import json
from pathlib import Path
from PyQt6.QtCore import QProcess, QTimer, Qt, QUrl
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QListView, QSplitter, QTreeWidget, QTreeWidgetItem, QStyle, QMessageBox

HELPER = Path(__file__).with_name('places.py')
ROLE = Qt.ItemDataRole.UserRole


class Sidebar(QTreeWidget):
    def __init__(self, dialog):
        super().__init__(dialog)
        self.dialog = dialog; self.previous = None
        self.setObjectName('xetalPlacesSidebar'); self.setHeaderHidden(True)
        self.setRootIsDecorated(False); self.setIndentation(0); self.setUniformRowHeights(True)
        from PyQt6.QtCore import QSize
        self.setIconSize(QSize(22, 22)); self.setMinimumWidth(200); self.setMaximumWidth(320)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setEditTriggers(self.EditTrigger.NoEditTriggers)
        self.setStyleSheet('QTreeWidget#xetalPlacesSidebar::item { min-height:28px; padding:3px 6px; }')
        self.itemClicked.connect(self.activate); self.itemActivated.connect(self.activate)
        self.listing = QProcess(self); self.listing.finished.connect(self.loaded)
        self.opening = QProcess(self); self.opening.finished.connect(self.opened)
        self.opening.errorOccurred.connect(self.failed)
        self.timer = QTimer(self); self.timer.setInterval(4000); self.timer.timeout.connect(self.load); self.timer.start()
        dialog.finished.connect(self.stop)
        QTimer.singleShot(0, self.load)

    def stop(self, *_):
        self.opening.kill(); self.listing.kill()

    def load(self):
        if self.dialog.isVisible() and self.listing.state() == QProcess.ProcessState.NotRunning:
            self.listing.start('python3', [str(HELPER)])

    def loaded(self, code, _status):
        raw = bytes(self.listing.readAllStandardOutput())
        try: entries = json.loads(raw)
        except (ValueError, UnicodeError): return
        if code or not isinstance(entries, list) or raw == self.previous: return
        self.previous = raw
        selected = self.currentItem().data(0, ROLE) if self.currentItem() else None
        scroll = self.verticalScrollBar().value(); self.clear()
        for group in dict.fromkeys(entry['group'] for entry in entries):
            heading = QTreeWidgetItem(self, [group]); heading.setFlags(Qt.ItemFlag.NoItemFlags)
            font = heading.font(0); font.setBold(True); heading.setFont(0, font)
            for entry in entries:
                if entry['group'] != group: continue
                item = QTreeWidgetItem(self, [entry['name']]); item.setData(0, ROLE, entry)
                item.setIcon(0, QIcon.fromTheme(entry['icon'], self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)))
                item.setToolTip(0, entry['url'] or 'Click to unlock or mount ' + entry.get('device', ''))
                if entry == selected: self.setCurrentItem(item)
        self.verticalScrollBar().setValue(scroll)

    def activate(self, item, _column=0):
        entry = item.data(0, ROLE)
        if not entry or self.opening.state() != QProcess.ProcessState.NotRunning: return
        url = QUrl(entry['url'])
        if url.isLocalFile(): self.dialog.setDirectoryUrl(url); return
        device = entry.get('device')
        self.setEnabled(False)
        self.opening.start('python3', [str(HELPER), '--device' if device else '--open', device or entry['url']])

    def opened(self, code, _status):
        self.setEnabled(True)
        raw = bytes(self.opening.readAllStandardOutput())
        if not self.dialog.isVisible(): return
        try: result = json.loads(raw)
        except (ValueError, UnicodeError): result = {}
        if code or not result or 'error' in result:
            QMessageBox.warning(self.dialog, 'Could not open location', result.get('error', 'The location helper could not complete. Try again.'))
        elif 'dolphin' in result:
            QProcess.startDetached(str(HELPER.parent.parent/'scripts/dolphin.sh'), [result['dolphin']])
        elif result.get('path'): self.dialog.setDirectory(result['path'])
        else: self.dialog.setDirectoryUrl(QUrl(result['url']))
        self.load()

    def failed(self, error):
        self.setEnabled(True)
        if error == QProcess.ProcessError.FailedToStart:
            QMessageBox.warning(self.dialog, 'Could not open location', self.opening.errorString())


def attach(dialog):
    if dialog.property('xetalFilePlaces'): return
    old = dialog.findChild(QListView, 'sidebar')
    splitter = old.parentWidget() if old else None
    if not isinstance(splitter, QSplitter): return
    dialog.setProperty('xetalFilePlaces', True)
    places = Sidebar(dialog); dialog.xetal_places = places
    splitter.insertWidget(0, places); old.hide()
    splitter.setCollapsible(0, False); splitter.setStretchFactor(0, 0)
    splitter.setSizes([230, 0, 600])
