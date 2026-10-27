"""Image chooser with a thumbnail and honest filesystem metadata."""
from datetime import datetime
from pathlib import Path
import os
from PyQt6 import sip
from PyQt6.QtCore import Qt,QSize,QTimer,QObject,pyqtSignal,QRunnable,QThreadPool
from PyQt6.QtGui import QImageReader,QPixmap
from PyQt6.QtWidgets import QFileDialog,QWidget,QVBoxLayout,QLabel,QFormLayout,QFrame,QTreeView

JOBS=set()
class Signals(QObject):
    done=pyqtSignal(object)
    failed=pyqtSignal(str)
class InspectJob(QRunnable):
    def __init__(self,fn):super().__init__();self.fn=fn;self.signals=Signals()
    def run(self):
        try:self.signals.done.emit(self.fn())
        except Exception as error:self.signals.failed.emit(str(error))
def background(fn,done,failed):
    job=InspectJob(fn);JOBS.add(job)
    def success(data):JOBS.discard(job);done(data)
    def failure(message):JOBS.discard(job);failed(message)
    job.signals.done.connect(success);job.signals.failed.connect(failure);QThreadPool.globalInstance().start(job)


def readable_size(size):
    amount=float(size)
    for unit in ['B','KiB','MiB','GiB','TiB']:
        if amount<1024 or unit=='TiB': return f'{amount:,.0f} {unit}' if unit=='B' else f'{amount:,.1f} {unit}'
        amount/=1024


def date_text(value):
    return datetime.fromtimestamp(value).astimezone().strftime('%b %d, %Y · %I:%M:%S %p %Z') if value else 'Not recorded by this filesystem'


def inspect_image(filename):
    path=Path(filename)
    if not path.is_file(): return None
    stat=path.stat(); created=getattr(stat,'st_birthtime',None)
    if created is None:
        try:
            from gi.repository import Gio
            info=Gio.File.new_for_path(str(path)).query_info('time::created',Gio.FileQueryInfoFlags.NONE,None)
            if info.has_attribute('time::created'): created=info.get_attribute_uint64('time::created') or None
        except Exception: pass
    reader=QImageReader(str(path));reader.setAutoTransform(True);size=reader.size()
    format=bytes(reader.format()).decode(errors='replace').upper()
    if size.width()>480 or size.height()>340: reader.setScaledSize(size.scaled(480,340,Qt.AspectRatioMode.KeepAspectRatio))
    image=reader.read() if reader.canRead() else None
    return {'name':path.name,'image':image,'size':readable_size(stat.st_size)+f' ({stat.st_size:,} bytes)',
            'dimensions':f'{size.width():,} × {size.height():,} px' if size.isValid() else 'Not available',
            'format':format or path.suffix.removeprefix('.').upper() or 'File',
            'created':date_text(created),'modified':date_text(stat.st_mtime),'folder':str(path.parent)}


class ImagePicker(QFileDialog):
    def __init__(self,parent,title,directory,filters,async_run=None):
        super().__init__(parent,title,directory,filters);self.async_run=async_run or background;self.generation=0;self.latest=''
        self.setOption(QFileDialog.Option.DontUseNativeDialog,True);self.setFileMode(QFileDialog.FileMode.ExistingFile)
        self.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen);self.resize(1100,680)
        panel=QFrame(self);panel.setObjectName('imageDetails');panel.setMinimumWidth(255);panel.setMaximumWidth(300)
        panel.setFrameShape(QFrame.Shape.StyledPanel);layout=QVBoxLayout(panel);layout.setContentsMargins(14,14,14,14);layout.setSpacing(14)
        title_widget=QLabel('IMAGE PREVIEW');title_widget.setObjectName('eyebrow');layout.addWidget(title_widget)
        self.preview=QLabel('Select an image');self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter);self.preview.setMinimumSize(225,180)
        self.preview.setMaximumHeight(225);self.preview.setStyleSheet('QLabel {background:palette(base); border:1px solid palette(mid); border-radius:8px;}');layout.addWidget(self.preview)
        self.name=QLabel('');self.name.setWordWrap(True);self.name.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);layout.addWidget(self.name)
        form=QFormLayout();form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows);form.setVerticalSpacing(10);self.values={}
        for key,title in [('dimensions','Dimensions'),('size','File size'),('format','Type'),('created','Created'),('modified','Modified')]:
            text=QLabel('—');text.setWordWrap(True);text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            caption=QLabel(title);caption.setObjectName('muted');form.addRow(caption,text);self.values[key]=text
        layout.addLayout(form);layout.addStretch()
        grid=self.layout();grid.addWidget(panel,0,grid.columnCount(),grid.rowCount(),1)
        tree=self.findChild(QTreeView,'treeView')
        if tree:
            tree.header().setStretchLastSection(True)
            for column,width in enumerate((290,95,125,190)):tree.setColumnWidth(column,width)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.inspect)
        self.currentChanged.connect(self.selected);self.finished.connect(lambda _:self.timer.stop())
        self.directoryEntered.connect(lambda _:self.selected(''))
    def selected(self,filename):
        self.latest=filename;self.generation+=1;self.preview.clear();self.preview.setText('Loading preview…' if filename else 'Select an image')
        self.name.setText(Path(filename).name if filename else '')
        for value in self.values.values():value.setText('—')
        self.timer.start(100)
    def inspect(self):
        generation=self.generation;filename=self.latest
        def done(data):
            if sip.isdeleted(self) or generation!=self.generation:return
            if not data:self.preview.setText('Select an image');return
            self.name.setText(data['name'])
            if data['image'] is not None and not data['image'].isNull():
                self.preview.setPixmap(QPixmap.fromImage(data['image']).scaled(self.preview.size()-QSize(16,16),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
            else:self.preview.setText('Preview unavailable')
            for key,value in self.values.items():value.setText(data[key])
        def failed(message):
            if not sip.isdeleted(self) and generation==self.generation:self.preview.setText('Preview unavailable');self.preview.setToolTip(message)
        if self.async_run:self.async_run(lambda:inspect_image(filename),done,failed)
        else:
            try:done(inspect_image(filename))
            except Exception as error:failed(str(error))
    @classmethod
    def choose(cls,parent,title,directory,filters,async_run=None):
        dialog=cls(parent,title,directory,filters,async_run)
        result=dialog.exec();files=dialog.selectedFiles() if result else [];dialog.deleteLater()
        return files[0] if files else ''
