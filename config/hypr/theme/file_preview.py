"""Right-hand previews for QWidget file dialogs, with bounded background reads."""
from datetime import datetime
import os
from pathlib import Path
import stat
from PyQt6 import sip
from PyQt6.QtCore import (QEvent, QFile, QFileDevice, QIODevice, QObject, QRunnable,
                         QThreadPool, QTimer, Qt, pyqtSignal)
from PyQt6.QtGui import QImageReader, QPixmap
from PyQt6.QtWidgets import (QApplication, QFileDialog, QFrame, QGridLayout, QLabel,
                            QLineEdit, QPlainTextEdit, QScrollArea, QVBoxLayout, QWidget)

MARKER = 'xetalFilePreview'
JOBS = set()


class Signals(QObject):
    done = pyqtSignal(object)


class InspectJob(QRunnable):
    def __init__(self, filename):
        super().__init__(); self.filename = filename; self.signals = Signals()

    def run(self):
        try: result = inspect_path(self.filename)
        except Exception: result = {'message': 'This file could not be read.'}
        self.signals.done.emit(result)


def readable_size(size):
    amount = float(size)
    for unit in ('B', 'KiB', 'MiB', 'GiB', 'TiB'):
        if amount < 1024 or unit == 'TiB':
            return f'{amount:,.0f} {unit}' if unit == 'B' else f'{amount:,.1f} {unit}'
        amount /= 1024


def date_text(value):
    return datetime.fromtimestamp(value).astimezone().strftime('%b %d, %Y · %H:%M') if value else 'Not recorded'


def inspect_path(filename):
    if not filename: return {'message': 'Select a file or folder'}
    path = Path(filename)
    data = {'name': path.name, 'image': None, 'text': '', 'message': '',
            'size': '—', 'dimensions': '—', 'format': 'File', 'modified': '—', 'created': '—'}
    try: info = path.stat()
    except FileNotFoundError: return {**data, 'message': 'New file · no preview yet'}
    data.update(modified=date_text(info.st_mtime), created=date_text(getattr(info, 'st_birthtime', None)))
    if stat.S_ISDIR(info.st_mode):
        entries = []
        with os.scandir(path) as items:
            for item in items:
                entries.append(item.name + ('/' if item.is_dir(follow_symlinks=False) else ''))
                if len(entries) == 41: break
        data.update(format='Folder', text='\n'.join(sorted(entries[:40], key=str.casefold)),
                    message='First 40 entries' if len(entries) > 40 else ('Folder contents' if entries else 'Empty folder'))
        return data
    if not stat.S_ISREG(info.st_mode): return {**data, 'message': 'No preview for this device or special file'}
    # Check the opened descriptor too: a selected path can change into a pipe
    # between stat and open. Never read devices, FIFOs or sockets.
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode): return {**data, 'message': 'Preview unavailable'}
        data['size'] = readable_size(info.st_size)
        head = os.read(fd, 65536); os.lseek(fd, 0, os.SEEK_SET)
        file = QFile()
        if not file.open(fd, QIODevice.OpenModeFlag.ReadOnly, QFileDevice.FileHandleFlag.DontCloseHandle):
            return {**data, 'message': 'This file could not be read.'}
        reader = QImageReader(file); reader.setAutoTransform(True)
        if reader.canRead():
            size = reader.size(); data['format'] = bytes(reader.format()).decode(errors='replace').upper()
            data['dimensions'] = f'{size.width():,} × {size.height():,} px'
            if not size.isValid() or size.width() * size.height() > 48_000_000 or info.st_size > 128*1024*1024:
                data['message'] = 'Image too large to preview'
            else:
                reader.setScaledSize(size.scaled(480, 340, Qt.AspectRatioMode.KeepAspectRatio))
                data['image'] = reader.read()
                if data['image'].isNull(): data['message'] = 'Image preview unavailable'
        else:
            data['format'] = path.suffix.lstrip('.').upper() or 'File'
            try:
                text = head.decode('utf-16' if head.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig')
                if any(ord(c) < 32 and c not in '\n\r\t' for c in text): raise ValueError('binary')
                data.update(text=text, message='First 64 KiB' if info.st_size > len(head) else ('Empty file' if not head else ''))
            except (ValueError, UnicodeError): data['message'] = 'No preview available for this file type'
        file.close()
    finally: os.close(fd)
    return data


class PreviewPane(QScrollArea):
    def __init__(self, dialog):
        super().__init__(dialog)
        self.setObjectName('xetalFilePreviewPane'); self.setWidgetResizable(True)
        self.setMinimumWidth(240); self.setMaximumWidth(300); self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget(); layout = QVBoxLayout(content); layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10); self.setWidget(content)
        title = QLabel('PREVIEW'); title.setObjectName('eyebrow'); layout.addWidget(title)
        self.preview = QLabel('Select a file or folder'); self.preview.setObjectName('xetalPreviewImage')
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter); self.preview.setWordWrap(True)
        self.preview.setMinimumHeight(160); self.preview.setMaximumHeight(210)
        self.preview.setStyleSheet('background:palette(base); border-radius:8px; padding:4px;')
        layout.addWidget(self.preview)
        self.name = QLabel(); self.name.setObjectName('xetalPreviewName'); self.name.setWordWrap(True)
        self.name.setTextFormat(Qt.TextFormat.PlainText); self.name.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.name)
        self.excerpt = QPlainTextEdit(); self.excerpt.setObjectName('xetalPreviewText'); self.excerpt.setReadOnly(True)
        self.excerpt.setMinimumHeight(160); self.excerpt.setMaximumHeight(220); self.excerpt.hide(); layout.addWidget(self.excerpt)
        self.values = {}
        for key, caption in [('format', 'Type'), ('dimensions', 'Dimensions'), ('size', 'Size'),
                             ('modified', 'Modified'), ('created', 'Created')]:
            label = QLabel(caption); label.setObjectName('muted'); layout.addWidget(label)
            field = QLabel('—'); field.setWordWrap(True); field.setTextFormat(Qt.TextFormat.PlainText)
            field.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(field); self.values[key] = field
        layout.addStretch()
        self.generation = 0; self.latest = ''; self.busy = False; self.image = None
        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.setInterval(100)
        self.timer.timeout.connect(self.inspect)
        dialog.currentChanged.connect(self.selected); dialog.directoryEntered.connect(self.selected)
        dialog.finished.connect(self.stop)
        edit = dialog.findChild(QLineEdit, 'fileNameEdit')
        if edit: edit.textEdited.connect(lambda _: self.selected(next(iter(dialog.selectedFiles()), '')))
        self.selected(next(iter(dialog.selectedFiles()), ''))

    def stop(self, *_):
        self.generation += 1; self.latest = ''; self.timer.stop()

    def selected(self, filename):
        self.generation += 1; self.latest = filename; self.image = None
        self.preview.clear(); self.preview.setText('Loading preview…' if filename else 'Select a file or folder')
        self.name.setText(Path(filename).name if filename else ''); self.excerpt.hide()
        for field in self.values.values(): field.setText('—')
        self.timer.start()

    def inspect(self):
        if self.busy: return
        self.busy = True; generation = self.generation
        job = InspectJob(self.latest); JOBS.add(job)
        def done(data):
            JOBS.discard(job)
            if sip.isdeleted(self): return
            self.busy = False
            if generation != self.generation:
                if self.latest: self.timer.start()
                return
            self.name.setText(data.get('name', '')); self.image = data.get('image')
            self.preview.setText(data.get('message', '')); self.update_image()
            self.excerpt.setPlainText(data.get('text', '')); self.excerpt.setVisible(bool(data.get('text')))
            for key, field in self.values.items(): field.setText(data.get(key, '—'))
        job.signals.done.connect(done); QThreadPool.globalInstance().start(job)

    def update_image(self):
        if self.image is not None and not self.image.isNull():
            self.preview.setPixmap(QPixmap.fromImage(self.image).scaled(max(1, self.viewport().width()-32), 200,
                Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'image'): self.update_image()


def attach(dialog):
    import file_places
    file_places.attach(dialog)
    if dialog.property(MARKER): return
    grid = dialog.layout()
    if not isinstance(grid, QGridLayout): return
    dialog.setProperty(MARKER, True)
    pane = PreviewPane(dialog); dialog.xetal_preview = pane
    grid.addWidget(pane, 0, grid.columnCount(), grid.rowCount(), 1)
    screen = dialog.screen()
    available = screen.availableGeometry().size() if screen else dialog.size()
    dialog.resize(min(max(900, dialog.width()+260), available.width()-32),
                  min(max(580, dialog.height()), available.height()-32))


class FileDialogs(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Show and isinstance(obj, QFileDialog): attach(obj)
        return False


def install(app):
    if hasattr(app, 'xetal_file_dialogs'): return
    app.xetal_file_dialogs = FileDialogs(app); app.installEventFilter(app.xetal_file_dialogs)
    for widget in QApplication.topLevelWidgets():
        if isinstance(widget, QFileDialog) and widget.isVisible(): attach(widget)
