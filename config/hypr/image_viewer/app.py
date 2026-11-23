#!/usr/bin/env python3
"""Fusion Viewer: a read-only, themed viewer with folder navigation."""
import argparse
from pathlib import Path
import subprocess
import sys

from PyQt6 import sip
from PyQt6.QtCore import Qt, QStandardPaths, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QIcon, QKeySequence, QMovie, QPainter, QPixmap, QShortcut
from PyQt6.QtWidgets import (QApplication, QFrame, QGraphicsPixmapItem, QGraphicsScene, QGraphicsView,
    QGridLayout, QHBoxLayout, QLabel, QMenu, QPushButton, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget)
import images
import window_size

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'theme'))
import runtime as theme_runtime
from image_picker import ImagePicker, background, readable_size
from window_chrome import window_controls

STYLE = '''
QWidget {background:#171b22; color:#d8e0ec; font-family:"DejaVu Sans"; font-size:12px;}
QLabel {background:transparent;}
QLabel#brand {color:#80e2d8; font-size:15px; font-weight:700;}
QLabel#filename {font-size:14px; font-weight:600;}
QLabel#muted {color:#8d9bad;}
QLabel#empty {background:#10151c; color:#8d9bad; font-size:16px; padding:30px; border-radius:12px;}
QPushButton {background:#293340; border:1px solid #3a4859; border-radius:7px; padding:7px 11px;}
QPushButton:hover {background:#36475a; border-color:#70909d;}
QPushButton:pressed {background:#182e36;}
QPushButton:checked {color:#eafffa; background:#245e60; border-color:#4fa59d;}
QPushButton:disabled {color:#617083; background:#202630; border-color:#2b3340;}
QPushButton#arrow {font-size:23px; padding:0;}
QGraphicsView {background:#10151c; border:none;}
QScrollBar:vertical {background:#141920; width:9px;}
QScrollBar:horizontal {background:#141920; height:9px;}
QScrollBar::handle {background:#3c4c5d; min-height:24px; min-width:24px; border-radius:4px;}
QScrollBar::add-line, QScrollBar::sub-line {width:0; height:0;}
QToolTip {background:#252f3c; color:#e2edf5; border:1px solid #4c6176; padding:5px;}
'''


class Canvas(QGraphicsView):
    zoomChanged = pyqtSignal(float, bool)

    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.picture = QGraphicsPixmapItem()
        self.picture.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.scene().addItem(self.picture)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.fit_mode = True
        self.rotation = 0
        self.fit_timer = QTimer(self)
        self.fit_timer.setSingleShot(True)
        self.fit_timer.timeout.connect(self.fit_image)

    def set_image(self, image, reset=True):
        pixmap = image if isinstance(image, QPixmap) else QPixmap.fromImage(image)
        pixmap.setDevicePixelRatio(1)
        if reset:
            self.rotation = 0
        self.picture.setPixmap(pixmap)
        self.picture.setTransformOriginPoint(self.picture.boundingRect().center())
        self.picture.setRotation(self.rotation)
        self.setSceneRect(self.picture.sceneBoundingRect())
        if reset or self.fit_mode:
            self.fit_image()

    def fit_image(self):
        if self.picture.pixmap().isNull():
            return
        self.fit_mode = True
        size = self.picture.sceneBoundingRect()
        scale = min((self.viewport().width() - 4) / size.width(),
                    (self.viewport().height() - 4) / size.height(), 1.0)
        self.resetTransform()
        self.scale(max(.001, scale), max(.001, scale))
        self.centerOn(self.picture)
        self.zoomChanged.emit(self.transform().m11(), True)

    def set_zoom(self, scale, position=None):
        if self.picture.pixmap().isNull():
            return
        self.fit_mode = False
        position = position or self.viewport().rect().center()
        before = self.mapToScene(position)
        factor = max(.01, min(32.0, scale)) / self.transform().m11()
        self.scale(factor, factor)
        after = self.mapToScene(position)
        delta = after - before
        self.translate(delta.x(), delta.y())
        self.zoomChanged.emit(self.transform().m11(), False)

    def zoom(self, factor, position=None):
        self.set_zoom(self.transform().m11() * factor, position)

    def rotate_image(self, degrees):
        if self.picture.pixmap().isNull(): return
        self.rotation = (self.rotation + degrees) % 360
        self.picture.setRotation(self.rotation)
        self.setSceneRect(self.picture.sceneBoundingRect())
        if self.fit_mode: self.fit_image()
        else: self.centerOn(self.picture)

    def wheelEvent(self, event):
        amount = event.angleDelta().y() or event.pixelDelta().y()
        if amount:
            self.zoom(1.2 ** max(-4, min(4, amount / 120)), event.position().toPoint())
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.fit_mode:
                self.set_zoom(1.0, event.position().toPoint())
            else:
                self.fit_image()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.fit_mode:
            self.fit_timer.start(0)

    def drawBackground(self, painter, rect):
        palette = self.palette()
        painter.fillRect(rect, palette.base())
        if self.picture.pixmap().hasAlphaChannel():
            # The pattern is bounded to the image; transparent edges remain visible.
            tile = QPixmap(24, 24)
            a = palette.base().color()
            b = a.lighter(140) if a.lightness() < 128 else a.darker(110)
            tile.fill(a)
            brush = QPainter(tile)
            brush.fillRect(0, 0, 12, 12, b)
            brush.fillRect(12, 12, 12, 12, b)
            brush.end()
            painter.fillRect(rect.intersected(self.sceneRect()), QBrush(tile))


class Viewer(QWidget):
    def __init__(self, filename=None, async_run=background, remember=True):
        super().__init__()
        self.setWindowTitle('Fusion Viewer')
        self.setWindowIcon(QIcon.fromTheme('image-x-generic'))
        self.setMinimumSize(580, 400)
        self.setAcceptDrops(True)
        self.async_run, self.remember = async_run, remember
        self.current = None
        self.files = []
        self.generation = 0
        self.movie = None
        self.closed = False
        self.loading = False
        self.wallpaper_action = None
        self.shortcuts = []
        self.resize(window_size.DEFAULT)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 12)
        layout.setSpacing(12)
        header = QGridLayout()
        header.setSpacing(6)
        header.setColumnStretch(0, 1); header.setColumnStretch(2, 1)
        identity = QWidget(); identity.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        title = QHBoxLayout(identity); title.setContentsMargins(0, 0, 0, 0); title.setSpacing(6)
        self.brand = QLabel('Fusion Viewer'); self.brand.setObjectName('brand'); title.addWidget(self.brand)
        self.name = QLabel('Open a picture to begin'); self.name.setObjectName('filename')
        self.name.setTextFormat(Qt.TextFormat.PlainText)
        self.name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        title.addWidget(self.name, 1); header.addWidget(identity, 0, 0)

        self.toolbar = QWidget(); self.toolbar.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        controls = QHBoxLayout(self.toolbar); controls.setContentsMargins(0, 0, 0, 0); controls.setSpacing(6)
        self.canvas = Canvas()
        self.canvas.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.canvas.customContextMenuRequested.connect(self.show_context_menu)
        self.fit = self.button('Fit', 'Fit to window · F', self.canvas.fit_image)
        self.fit.setCheckable(True); self.fit.setChecked(True); controls.addWidget(self.fit)
        self.actual = self.button('100%', 'Actual size · 1', lambda: self.canvas.set_zoom(1))
        controls.addWidget(self.actual)
        self.minus = self.button('−', 'Zoom out · −', lambda: self.canvas.zoom(1 / 1.2)); controls.addWidget(self.minus)
        self.percent = QLabel('—'); self.percent.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.percent.setFixedWidth(58); controls.addWidget(self.percent)
        self.plus = self.button('+', 'Zoom in · +', lambda: self.canvas.zoom(1.2)); controls.addWidget(self.plus)
        controls.addSpacing(4)
        controls.addWidget(self.button('⛶', 'Full screen · F11', self.fullscreen))
        controls.addSpacing(8)
        controls.addWidget(self.button('Open…', 'Open image · Ctrl+O', self.choose))
        self.folder = self.button('↗', 'Show image in folder', self.show_folder)
        self.folder.setFixedWidth(36); self.folder.setEnabled(False); controls.addWidget(self.folder)
        header.addWidget(self.toolbar, 0, 1, Qt.AlignmentFlag.AlignCenter)
        header.addWidget(window_controls(self,focus_indicator=False), 0, 2, Qt.AlignmentFlag.AlignRight)
        layout.addLayout(header)

        self.pages = QStackedWidget()
        self.pages.addWidget(self.canvas)
        self.message = QLabel('Drop an image here\nor choose Open…')
        self.message.setObjectName('empty'); self.message.setWordWrap(True)
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pages.addWidget(self.message); self.pages.setCurrentWidget(self.message)
        layout.addWidget(self.pages, 1)
        self.notice = QLabel(''); self.notice.setObjectName('muted'); self.notice.setWordWrap(True)
        self.notice.setTextFormat(Qt.TextFormat.PlainText); self.notice.hide(); layout.addWidget(self.notice)
        self.notice_timer = QTimer(self); self.notice_timer.setSingleShot(True)
        self.notice_timer.timeout.connect(self.notice.hide)
        footer = QGridLayout()
        footer.setColumnStretch(0, 1); footer.setColumnStretch(2, 1)
        self.details = QLabel(''); self.details.setObjectName('muted')
        self.details.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        footer.addWidget(self.details, 0, 0)
        navigation = QHBoxLayout(); navigation.setSpacing(6)
        self.previous = self.button('‹', 'Previous image · Left arrow', lambda: self.navigate(-1))
        self.next = self.button('›', 'Next image · Right arrow', lambda: self.navigate(1))
        for arrow in (self.previous, self.next):
            arrow.setObjectName('arrow'); arrow.setFixedSize(36, 32); navigation.addWidget(arrow)
        self.count = QLabel(''); self.count.setObjectName('muted'); navigation.addWidget(self.count)
        self.pause = self.button('Pause', 'Play / pause animation · Space', self.pause_movie)
        navigation.addWidget(self.pause); self.pause.hide()
        footer.addLayout(navigation, 0, 1)
        self.folder_name = QLabel(''); self.folder_name.setObjectName('muted')
        self.folder_name.setTextFormat(Qt.TextFormat.PlainText)
        self.folder_name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        footer.addWidget(self.folder_name, 0, 2, Qt.AlignmentFlag.AlignRight); layout.addLayout(footer)
        self.canvas.zoomChanged.connect(self.zoom_changed)
        for key, action in [('Left', lambda: self.navigate(-1)), ('Right', lambda: self.navigate(1)),
            ('Ctrl+O', self.choose), ('Escape', self.escape), ('F11', self.fullscreen), ('F', self.canvas.fit_image),
            ('1', lambda: self.canvas.set_zoom(1)), ('+', lambda: self.canvas.zoom(1.2)),
            ('=', lambda: self.canvas.zoom(1.2)), ('-', lambda: self.canvas.zoom(1 / 1.2)), ('Space', self.pause_movie)]:
            shortcut = QShortcut(QKeySequence(key), self); shortcut.activated.connect(action); self.shortcuts.append(shortcut)
        self.navigation()
        self.image_controls(False)
        self.size_memory = window_size.Memory(self) if remember else None
        if filename:
            self.open_path(filename)

    def button(self, text, tip, action):
        button = QPushButton(text)
        button.setToolTip(tip); button.setAccessibleName(tip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(action)
        return button

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Keep the actions on one readable row in small windows. The filename
        # remains in the window title when there is no room for its header.
        compact = event.size().width() < 820
        self.brand.setVisible(not compact)
        self.name.setVisible(not compact)

    def navigation(self):
        index = self.files.index(self.current) if self.current in self.files else -1
        self.previous.setEnabled(index > 0)
        self.next.setEnabled(0 <= index < len(self.files) - 1)
        self.count.setText(f'{index + 1} / {len(self.files)}' if index >= 0 else '')

    def image_controls(self, enabled):
        for button in (self.fit, self.actual, self.minus, self.plus): button.setEnabled(enabled)

    def context_menu(self):
        menu = QMenu(self)
        ready = not self.loading and self.pages.currentWidget() is self.canvas and not self.canvas.picture.pixmap().isNull()
        for text, degrees in (('Rotate left', -90), ('Rotate right', 90)):
            action = menu.addAction(text)
            action.setEnabled(ready)
            action.triggered.connect(lambda checked=False, angle=degrees: self.canvas.rotate_image(angle))
        menu.addSeparator()
        wallpaper = menu.addAction('Set as wallpaper')
        wallpaper.setEnabled(ready and not (self.wallpaper_action and self.wallpaper_action.busy))
        wallpaper.triggered.connect(self.set_wallpaper)
        return menu

    def show_context_menu(self, position):
        menu = self.context_menu()
        menu.aboutToHide.connect(menu.deleteLater)
        menu.popup(self.canvas.viewport().mapToGlobal(position))

    def set_wallpaper(self):
        if self.loading or self.pages.currentWidget() is not self.canvas or not self.current: return
        if self.wallpaper_action is None:
            from wallpaper_action import WallpaperAction
            self.wallpaper_action = WallpaperAction(self)
            self.wallpaper_action.message.connect(self.wallpaper_message)
        self.wallpaper_action.start(self.current, self.canvas.picture.pixmap().toImage(), self.canvas.rotation)

    def wallpaper_message(self, text):
        self.notice_timer.stop(); self.notice.setText(text); self.notice.setVisible(bool(text))
        if text.startswith('Wallpaper applied to '): self.notice_timer.start(4000)

    def open_path(self, filename):
        try:
            path = images.local_path(filename)
        except ValueError as error:
            self.show_error(str(error)); return
        self.generation += 1
        generation = self.generation
        self.stop_movie()
        if not self.current or self.current.parent != path.parent:
            self.files = []
        self.current = path
        self.loading = True
        self.name.setText(path.name); self.name.setToolTip(str(path))
        self.setWindowTitle(path.name + ' — Fusion Viewer')
        self.folder_name.setText(path.parent.name); self.folder_name.setToolTip(str(path.parent))
        self.details.clear(); self.percent.setText('—')
        self.folder.setEnabled(path.is_file())
        self.image_controls(False); self.navigation()
        self.message.setText('Loading image…'); self.pages.setCurrentWidget(self.message)
        def done(data):
            if not sip.isdeleted(self) and not self.closed and generation == self.generation:
                self.loaded(path, data)
        def failed(message):
            if not sip.isdeleted(self) and not self.closed and generation == self.generation:
                self.files = images.folder_images(path); self.navigation(); self.show_error(message)
        self.async_run(lambda: images.load(path), done, failed)

    def loaded(self, path, data):
        self.loading = False
        self.files = data['files']; self.navigation()
        self.pages.setCurrentWidget(self.canvas)
        self.canvas.set_image(data['image'])
        self.image_controls(True)
        self.details.setText(f"{data['format']}  ·  {data['image'].width():,} × {data['image'].height():,}  ·  {readable_size(data['bytes'])}")
        if data['animated']:
            movie = QMovie(str(path), parent=self)
            if movie.isValid():
                self.movie = movie
                movie.frameChanged.connect(self.movie_frame)
                movie.start(); self.pause.setText('Pause'); self.pause.show()
            else:
                movie.deleteLater()

    def show_error(self, message):
        self.loading = False
        self.message.setText('Could not open this image\n\n' + message)
        self.pages.setCurrentWidget(self.message); self.image_controls(False)

    def navigate(self, direction):
        if self.current not in self.files: return
        index = self.files.index(self.current) + direction
        if 0 <= index < len(self.files): self.open_path(self.files[index])

    def zoom_changed(self, scale, fit):
        self.percent.setText(f'{scale * 100:.0f}%' if scale >= .1 else f'{scale * 100:.1f}%')
        self.fit.setChecked(fit)

    def movie_frame(self):
        if self.movie: self.canvas.set_image(self.movie.currentPixmap(), reset=False)

    def stop_movie(self):
        if self.movie:
            self.movie.stop(); self.movie.deleteLater(); self.movie = None
        self.pause.hide()

    def pause_movie(self):
        if self.movie:
            paused = self.movie.state() == QMovie.MovieState.Paused
            self.movie.setPaused(not paused); self.pause.setText('Pause' if paused else 'Play')

    def choose(self):
        folder = str(self.current.parent) if self.current else QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)
        patterns = ' '.join('*.' + extension for extension in sorted(images.extensions()))
        filename = ImagePicker.choose(self, 'Open image', folder, f'Images ({patterns});;All files (*)')
        if filename: self.open_path(filename)

    def show_folder(self):
        if self.current and self.current.is_file():
            subprocess.Popen([str(ROOT/'scripts/dolphin.sh'), '--select', str(self.current)],
                             env=theme_runtime.environment(), start_new_session=True)

    def fullscreen(self):
        if self.isFullScreen(): self.showNormal()
        else: self.showFullScreen()

    def escape(self):
        if self.isFullScreen(): self.showNormal()
        else: self.close()

    def dragEnterEvent(self, event):
        if any(url.isLocalFile() for url in event.mimeData().urls()): event.acceptProposedAction()

    def dropEvent(self, event):
        files = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if files: self.open_path(files[0]); event.acceptProposedAction()

    def closeEvent(self, event):
        if self.wallpaper_action: self.wallpaper_action.shutdown()
        self.closed = True; self.generation += 1; self.stop_movie()
        super().closeEvent(event)


def main():
    parser = argparse.ArgumentParser(description='Open an image in Fusion Viewer')
    parser.add_argument('files', nargs='*')
    args = parser.parse_args()
    app = QApplication([sys.argv[0]])
    app.setApplicationName('Fusion Viewer'); app.setDesktopFileName('xetal-image-viewer')
    theme_runtime.install(app, STYLE)
    window = Viewer(args.files[0] if args.files else None)
    window.show()
    return app.exec()


if __name__ == '__main__': raise SystemExit(main())
