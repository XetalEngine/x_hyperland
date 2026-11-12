"""Per-drag extraction leases using the archive handoff already supported by KIO."""
from pathlib import Path
import uuid

from PyQt6.QtCore import QObject, QMimeData, QTimer, QUrl, pyqtClassInfo, pyqtSignal, pyqtSlot
from PyQt6.QtDBus import QDBusConnection, QDBusMessage
from engine import ArchiveError, safe_member

SERVICE_MIME = 'application/x-kde-ark-dndextract-service'
PATH_MIME = 'application/x-kde-ark-dndextract-path'


def archive_identity(path):
    value=Path(path).stat()
    return [value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns]


def destination_path(value):
    if not isinstance(value,str) or not value or '\x00' in value:
        raise ArchiveError('Choose a local folder for the extracted files.')
    if not value.startswith('/'):
        url=QUrl(value)
        if not url.isLocalFile() or url.host() not in ('','localhost') or url.hasQuery() or url.hasFragment():
            raise ArchiveError('Extract to a local folder first, then copy the files to the remote location.')
        value=url.toLocalFile()
    target=Path(value)
    if not target.is_absolute() or not target.is_dir():
        raise ArchiveError('The extraction destination is no longer an available folder.')
    return str(target)


@pyqtClassInfo('D-Bus Interface','org.kde.ark.DndExtract')
class ArchiveDrag(QObject):
    launch=pyqtSignal(dict)
    failed=pyqtSignal(str)
    closed=pyqtSignal()

    def __init__(self, archive, members, password=None, parent=None, bus=None):
        super().__init__(parent)
        self.bus=bus if bus is not None else QDBusConnection.sessionBus()
        self.path='/org/xetal/Archives/drag/d'+uuid.uuid4().hex
        self.archive=str(Path(archive).absolute())
        self.members=tuple(safe_member(member) for member in members)
        if not self.members or '.' in self.members: raise ArchiveError('Select files or folders to drag out of the archive.')
        self.identity=archive_identity(self.archive)
        self.password=password; self.active=False; self.used=False; self.drag_finished=False
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.dispose)

    def mime_data(self):
        if not self.bus.isConnected() or not self.bus.registerObject(self.path,self,QDBusConnection.RegisterOption.ExportAllSlots):
            raise ArchiveError('The desktop file-drop connection is unavailable. Use Extract… to choose a folder.')
        self.active=True
        mime=QMimeData()
        mime.setData(SERVICE_MIME,self.bus.baseService().encode())
        mime.setData(PATH_MIME,self.path.encode())
        return mime

    def dropped(self, _accepted):
        self.drag_finished=True
        if self.active:
            # QDrag's Wayland result and KIO's D-Bus call arrive independently.
            # IgnoreAction can arrive before a valid destination request too.
            # Only that request starts extraction; an abandoned lease simply
            # expires. Do not revoke it based on the transport's return value.
            self.timer.start(60000)
        else:self.deleteLater()

    @pyqtSlot(str,QDBusMessage)
    def extractSelectedFilesTo(self, destination, message=None):
        try:
            if not self.active or self.used: raise ArchiveError('This archive drag has already finished. Drag the selection again.')
            target=destination_path(destination)
            if archive_identity(self.archive)!=self.identity:
                raise ArchiveError('The archive changed during this drag. Reload it and drag the selection again.')
            request=dict(operation='extract',sources=[self.archive],members=list(self.members),
                         destination=target,password=self.password,strip_common_parent=True,source_identity=self.identity)
            self.used=True;self.password=None
            # Queue the job after replying to the file manager; password prompts,
            # conflicts and long extraction work belong to the normal job UI.
            QTimer.singleShot(0,lambda:self.launch.emit(request))
        except (OSError,ArchiveError) as error:
            self.failed.emit(str(error))
            if message is not None:
                message.setDelayedReply(True)
                self.bus.send(message.createErrorReply('org.freedesktop.DBus.Error.Failed',str(error)))
        finally:
            QTimer.singleShot(0,self.dispose)

    def dispose(self):
        self.timer.stop();self.password=None
        if self.active:
            self.active=False;self.bus.unregisterObject(self.path);self.closed.emit()
        if self.drag_finished:self.deleteLater()

