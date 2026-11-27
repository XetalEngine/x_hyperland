"""Archive member tree with local file drops and explicit destination feedback."""
from PyQt6.QtCore import QModelIndex, QPersistentModelIndex, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPalette, QPen
from PyQt6.QtWidgets import QAbstractItemView, QTreeView


class ArchiveTree(QTreeView):
    dragRequested = pyqtSignal()
    filesDropped = pyqtSignal(list, str)
    dropHint = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.drop_folder = None
        self.drop_index = QPersistentModelIndex()
        self.drag_position = None
        self.expand_timer = QTimer(self); self.expand_timer.setSingleShot(True)
        self.expand_timer.setInterval(650); self.expand_timer.timeout.connect(self.expand_destination)
        self.scroll_timer = QTimer(self); self.scroll_timer.setInterval(60)
        self.scroll_timer.timeout.connect(self.scroll_destination)
        self.setDragEnabled(True); self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)
        self.setDropIndicatorShown(False)

    def setModel(self, model):
        if self.model(): self.model().modelAboutToBeReset.disconnect(self.clear_drop)
        super().setModel(model)
        if model: model.modelAboutToBeReset.connect(self.clear_drop)

    def startDrag(self, _actions):
        self.dragRequested.emit()

    def local_files(self, event):
        if event.source() is self or not event.possibleActions() & Qt.DropAction.CopyAction:
            return []
        mime = event.mimeData()
        if not mime.hasUrls(): return []
        paths = []
        for url in mime.urls():
            if (not url.isLocalFile() or url.host().lower() not in ('', 'localhost') or
                    url.hasQuery() or url.hasFragment()): return []
            path = url.toLocalFile()
            if not path.startswith('/') or '\0' in path: return []
            if path not in paths: paths.append(path)
        return paths

    def update_destination(self, position):
        self.drag_position = position
        index = self.indexAt(position)
        folder = ''
        if index.isValid():
            item = self.model().node(index.internalId())
            folder = item['path'] if item and item['directory'] else None
        selected = QPersistentModelIndex(index.siblingAtColumn(0)) if folder else QPersistentModelIndex()
        if selected != self.drop_index or folder != self.drop_folder:
            self.expand_timer.stop()
            self.drop_folder = folder; self.drop_index = selected
            if selected.isValid() and not self.isExpanded(QModelIndex(selected)): self.expand_timer.start()
            self.viewport().update()
        self.dropHint.emit('Drop to add inside '+folder if folder else
                           'Drop to add at the archive root' if folder == '' else
                           'Drop on a folder or empty space to add files')
        return folder is not None

    def dragEnterEvent(self, event):
        if self.model().db is None or not self.local_files(event):
            event.ignore(); return
        self.update_destination(event.position().toPoint())
        self.scroll_timer.start()
        event.setDropAction(Qt.DropAction.CopyAction); event.accept()

    def dragMoveEvent(self, event):
        if self.model().db is not None and self.local_files(event):
            if self.update_destination(event.position().toPoint()):
                event.setDropAction(Qt.DropAction.CopyAction); event.accept(); return
        event.ignore()

    def dropEvent(self, event):
        paths = self.local_files(event)
        folder = None
        if self.model().db is not None and paths and self.update_destination(event.position().toPoint()):
            folder = self.drop_folder
        self.clear_drop()
        if folder is None: event.ignore(); return
        event.setDropAction(Qt.DropAction.CopyAction); event.accept()
        self.filesDropped.emit(paths, folder)

    def dragLeaveEvent(self, event):
        self.clear_drop(); event.accept()

    def clear_drop(self):
        self.expand_timer.stop(); self.scroll_timer.stop()
        self.drag_position = None; self.drop_folder = None; self.drop_index = QPersistentModelIndex()
        self.dropHint.emit(''); self.viewport().update()

    def expand_destination(self):
        if self.drop_index.isValid(): self.expand(QModelIndex(self.drop_index))
        if self.drag_position is not None: self.update_destination(self.drag_position)

    def scroll_destination(self):
        if self.drag_position is None: return
        y = self.drag_position.y(); height = self.viewport().height()
        direction = -1 if y < 28 else 1 if y > height-28 else 0
        bar = self.verticalScrollBar()
        if direction:
            bar.setValue(bar.value()+direction*max(1, bar.singleStep()))
            self.update_destination(self.drag_position)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.drop_folder is None: return
        rectangle = self.viewport().rect().adjusted(1, 1, -2, -2)
        if self.drop_index.isValid():
            rectangle = self.visualRect(QModelIndex(self.drop_index))
            rectangle.setLeft(1); rectangle.setRight(self.viewport().width()-2)
            rectangle.adjust(0, 0, 0, -1)
        painter = QPainter(self.viewport())
        accent = self.palette().color(QPalette.ColorRole.Highlight)
        if self.drop_folder:
            fill = QColor(accent); fill.setAlpha(65); painter.fillRect(rectangle, fill)
        painter.setPen(QPen(accent, 2)); painter.drawRect(rectangle)
