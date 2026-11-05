"""Frame Lab and Orbit Atlas layouts using the shared wallpaper controller."""
from collections import Counter
from pathlib import Path

from PyQt6.QtCore import Qt, QRectF, QSize
from PyQt6.QtGui import QImageReader, QPainter
from PyQt6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QScrollArea, QSlider, QVBoxLayout, QWidget)

from wallpaper import library
from wallpaper.skins import (PALETTES, Brand, CollectionDelegate, Filmstrip,
    GalleryStage, background)


def text(value='', name=''):
    widget = QLabel(value); widget.setObjectName(name); widget.setWordWrap(True)
    return widget


def control(caption, callback, name='', tip=''):
    widget = QPushButton(caption); widget.clicked.connect(callback); widget.setObjectName(name)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    if tip: widget.setToolTip(tip); widget.setAccessibleName(tip)
    return widget


class DetailsScroll(QScrollArea):
    """Let metadata scroll on short displays while keeping Apply reachable."""
    def sizeHint(self):
        return QSize(220, self.widget().sizeHint().height() + 4 if self.widget() else 200)


class Presentation:
    def __init__(self, window):
        self.window = w = window; self.style = w.style; self.palette = p = PALETTES[self.style]
        self.film = self.style == 'frame-lab'; self.metadata = {}; self.metadata_pending = set()
        self.collection_signature = None; self.extra_controls = []
        w.setStyleSheet(self.stylesheet())
        layout = QVBoxLayout(w); layout.setContentsMargins(24, 16, 24, 16); layout.setSpacing(14)
        header = QHBoxLayout(); header.setSpacing(12)
        self.brand = Brand(self.style); header.addWidget(self.brand)
        w.collection = QComboBox(); w.collection.setAccessibleName('Wallpaper collection')
        w.collection.addItem('All collections', ''); w.collection.setMinimumWidth(140); w.collection.setMaximumWidth(200)
        w.collection.currentIndexChanged.connect(w.filter)
        w.search = QLineEdit(); w.search.setPlaceholderText('Search wallpapers…'); w.search.setClearButtonEnabled(True)
        w.search.setAccessibleName('Search wallpapers'); w.search.setMinimumWidth(130); w.search.textChanged.connect(w.filter)
        w.folder_button = control('＋  Add / remove folders', w.folders, tip='Add or remove wallpaper folders')
        if self.film:
            header.addWidget(w.collection); header.addWidget(w.search, 1); header.addWidget(w.folder_button)
        else: header.addStretch()
        for caption, action, title in (('−', w.showMinimized, 'Minimize'),
                ('□', self.maximize, 'Maximize or restore'), ('×', w.close, 'Close · Esc / Super+W')):
            button = control(caption, action, 'windowButton', title); button.setFixedSize(32, 32); header.addWidget(button)
        layout.addLayout(header)

        self.body = QHBoxLayout(); self.body.setSpacing(18)
        self.sidebar = QFrame(); self.sidebar.setObjectName('collectionsPane'); self.sidebar.setFixedWidth(208)
        side = QVBoxLayout(self.sidebar); side.setContentsMargins(9, 12, 9, 12); side.setSpacing(14)
        if not self.film:
            side.addWidget(w.search); side.addWidget(w.collection)
        side.addWidget(text('C O L L E C T I O N S', 'studioEyebrow'))
        self.collections = QListWidget(); self.collections.setAccessibleName('Wallpaper collections')
        self.collections.setObjectName('collections'); self.collections.setMouseTracking(True)
        self.collections.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.collections.setItemDelegate(CollectionDelegate(self.style, self.collections))
        self.collections.currentItemChanged.connect(self.select_collection)
        side.addWidget(self.collections, 1)
        w.count = text('Opening your collection…', 'studioMuted'); side.addWidget(w.count)
        if not self.film: side.addWidget(w.folder_button)
        self.body.addWidget(self.sidebar)

        w.carousel = GalleryStage(w.thumbnails, self.style)
        w.carousel.activated.connect(w.choose); w.carousel.selected.connect(w.selected); w.carousel.interacted.connect(w.pause)
        w.search.returnPressed.connect(w.carousel.activate)
        self.body.addWidget(w.carousel, 1)

        self.details = QFrame(); self.details.setObjectName('detailsPane'); self.details.setFixedWidth(268)
        details = QVBoxLayout(self.details); details.setContentsMargins(20, 22, 20, 22); details.setSpacing(16)
        facts = QWidget(); facts_layout = QVBoxLayout(facts); facts_layout.setContentsMargins(0, 0, 0, 0); facts_layout.setSpacing(16)
        facts_layout.addWidget(text('W A L L P A P E R', 'studioEyebrow'))
        w.title = text('Your next view', 'studioTitle'); w.title.setMaximumHeight(112); facts_layout.addWidget(w.title)
        w.meta = text('Choose an image to preview', 'studioMuted'); facts_layout.addWidget(w.meta)
        line = QFrame(); line.setFrameShape(QFrame.Shape.HLine); facts_layout.addWidget(line)
        self.resolution = text('—'); self.format = text('—'); self.position = text('—')
        for caption, value in (('Resolution', self.resolution), ('Format', self.format), ('In this collection', self.position)):
            row = QHBoxLayout(); row.addWidget(text(caption, 'studioMuted')); row.addStretch(); row.addWidget(value); facts_layout.addLayout(row)
        self.facts_scroll = DetailsScroll(); self.facts_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.facts_scroll.setWidgetResizable(True); self.facts_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.facts_scroll.setMinimumHeight(90); self.facts_scroll.setWidget(facts)
        details.addWidget(self.facts_scroll, 1)
        details.addSpacing(4); details.addWidget(text('TRANSITION', 'studioEyebrow'))
        w.transition = QComboBox(); w.transition.setAccessibleName('Wallpaper transition')
        for key, title in library.TRANSITIONS.items(): w.transition.addItem(title, key)
        details.addWidget(w.transition); details.addSpacing(6)
        w.apply = control('Use wallpaper  ↗', lambda: w.choose(w.carousel.current()), 'studioApply', 'Apply wallpaper · Enter')
        w.apply.setMinimumHeight(46); details.addWidget(w.apply)
        details.addStretch()
        self.details_note = text('Choose a frame below to preview.' if self.film else 'Explore the orbit. Choose a view.', 'studioMuted')
        details.addWidget(self.details_note)
        self.body.addWidget(self.details, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(self.body, 1)
        self.strip = Filmstrip(w.carousel) if self.film else None
        if self.strip: layout.addWidget(self.strip); self.extra_controls.append(self.strip)

        self.transport = QFrame(); self.transport.setObjectName('transport')
        transport = QHBoxLayout(self.transport); transport.setContentsMargins(20, 9, 20, 9); transport.setSpacing(12)
        self.counter = text('00 / 00', 'frameCounter'); self.counter.setMinimumWidth(80); transport.addWidget(self.counter)
        w.previous = control('◀', lambda: w.carousel.step(-1), 'transportButton', 'Previous wallpaper · Left')
        w.next = control('▶', lambda: w.carousel.step(1), 'transportButton', 'Next wallpaper · Right')
        w.play = control('▶', w.toggle_play, 'playButton', 'Preview slideshow · Space')
        w.play.setCheckable(True); w.play.setFixedSize(46, 46)
        for button in (w.previous, w.play, w.next): transport.addWidget(button)
        self.slideshow_label = text('Slideshow', 'studioMuted'); transport.addWidget(self.slideshow_label)
        self.seek = QSlider(Qt.Orientation.Horizontal); self.seek.setAccessibleName('Browse wallpaper collection')
        self.seek.setRange(0, 0); self.seek.valueChanged.connect(lambda value: w.carousel.go(value))
        if self.film: transport.addWidget(self.seek, 1)
        else: self.seek.hide(); transport.addStretch()
        w.hint = text('← →  Browse    Space  Slideshow    Enter  Use    Esc  Close', 'studioMuted')
        w.hint.setWordWrap(False); transport.addWidget(w.hint)
        self.extra_controls.extend((self.collections, self.seek))
        layout.addWidget(self.transport)
        w.status = text('Choose a thumbnail to preview · Use wallpaper to choose its display', 'studioMuted')
        layout.addWidget(w.status)

    def stylesheet(self):
        p = self.palette; radius = 10 if self.film else 18
        start, end = ('#ffd27a', '#ed940e') if self.film else ('#c4ffed', '#78dbc8')
        return f'''
        QWidget {{color:{p['text']}; font:13px "Noto Sans"; background:transparent;}}
        QWidget#wallpaperBrowser {{background:transparent;}}
        QLabel {{border:none; padding:0;}}
        QLabel#studioMuted {{color:{p['muted']}; font-size:11px;}}
        QLabel#studioEyebrow {{color:{p['bright']}; font-size:10px;}}
        QLabel#studioTitle {{font:24px "Noto Serif"; color:{p['text']};}}
        QLabel#frameCounter {{font:20px "Noto Serif"; color:{p['text']};}}
        QDialog {{background:{p['base']};}}
        QFrame#collectionsPane {{border:1px solid {p['edge'] if self.film else 'transparent'}; border-radius:{radius}px;
            background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {p['panel']},stop:1 {p['base']});}}
        QFrame#detailsPane {{border:1px solid {p['edge']}; border-radius:{radius}px;
            background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {p['panel']},stop:1 {p['base']});}}
        QFrame#transport {{border:1px solid {p['edge']}; border-radius:{12 if self.film else 32}px;
            background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {p['panel']},stop:1 {p['base']});}}
        QListWidget#collections {{background:transparent; border:none; outline:none; padding:0;}}
        QListWidget#collections::item {{padding:0; border:none; background:transparent;}}
        QPushButton,QComboBox,QLineEdit {{background:{p['panel']}; border:1px solid {p['edge']};
            border-radius:{7 if self.film else 12}px; padding:9px 10px; min-height:18px; color:{p['text']};}}
        QPushButton:hover,QComboBox:hover {{border-color:{p['accent']}; background:{p['base']};}}
        QPushButton:focus,QComboBox:focus,QLineEdit:focus {{border-color:{p['bright']};}}
        QPushButton:disabled,QComboBox:disabled {{color:{p['muted']}; border-color:{p['panel']};}}
        QLineEdit {{background:{p['base']}; selection-background-color:{p['accent']}; selection-color:{p['base']};}}
        QComboBox::drop-down {{border:none; width:20px;}}
        QComboBox QAbstractItemView {{background:{p['panel']}; color:{p['text']}; border:1px solid {p['edge']};
            selection-background-color:{p['accent']}; selection-color:{p['base']};}}
        QPushButton#studioApply {{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {start},stop:1 {end});
            border:1px solid {p['bright']}; border-radius:{10 if self.film else 25}px; color:{p['base']}; font:18px "Noto Serif";
            min-height:32px; max-height:32px;}}
        QPushButton#studioApply:hover {{background:{p['bright']};}}
        QPushButton#studioApply:disabled {{background:{p['panel']}; color:{p['muted']}; border-color:{p['edge']};}}
        QPushButton#windowButton {{border:none; background:transparent; padding:0; min-height:0; font-size:20px;}}
        QPushButton#windowButton:hover {{background:{p['panel']}; color:{p['accent']};}}
        QPushButton#playButton {{border:1px solid {p['accent']}; border-radius:23px;
            background:qradialgradient(cx:0.5,cy:0.5,radius:0.7,fx:0.4,fy:0.4,stop:0 {p['edge']},stop:1 {p['base']});
            color:{p['bright']}; font-size:23px; padding:0; min-height:44px; max-height:44px;}}
        QPushButton#playButton:checked {{background:{p['accent']}; color:{p['base']};}}
        QPushButton#transportButton {{border:none; background:transparent; font-size:15px; padding:8px;}}
        QSlider::groove:horizontal {{height:4px; background:{p['edge']}; border-radius:2px;}}
        QSlider::sub-page:horizontal {{background:{p['accent']}; border-radius:2px;}}
        QSlider::handle:horizontal {{width:10px; margin:-6px 0; background:{p['accent']}; border:1px solid {p['bright']}; border-radius:4px;}}
        QScrollBar:vertical {{background:transparent; width:5px;}}
        QScrollBar::handle:vertical {{background:{p['edge']}; min-height:26px; border-radius:2px;}}
        QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {{height:0;}}
        QToolTip {{background:{p['panel']}; color:{p['text']}; border:1px solid {p['edge']}; padding:6px;}}
        '''

    def maximize(self):
        if self.window.isMaximized(): self.window.showNormal()
        else: self.window.showMaximized()

    def paint(self):
        w = self.window; painter = QPainter(w)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        background(painter, QRectF(w.rect()), self.palette, w.thumbnails, w.carousel.current())

    def fit(self, width, height):
        w = self.window; narrow = width < 1120; compact = height < 740
        w.narrow = narrow
        w.layout().setContentsMargins(16 if narrow else 24, 12, 16 if narrow else 24, 12)
        w.layout().setSpacing(8 if compact else 14)
        self.sidebar.setVisible(not narrow); self.sidebar.setFixedWidth(180 if width < 1400 else 208)
        self.details.setFixedWidth(232 if width < 1400 else 268)
        self.details_note.setVisible(not compact); self.details.layout().setSpacing(10 if compact else 16)
        self.details.layout().setContentsMargins(16, 14 if compact else 22, 16, 14 if compact else 22)
        w.folder_button.setText('Folders…' if width < 1400 else '＋  Add / remove folders')
        w.hint.setVisible(width >= 1340); self.slideshow_label.setVisible(width >= 960)
        self.brand.setFixedWidth(254 if width < 1200 else 294)
        if self.strip: self.strip.setFixedHeight(132 if compact else 174)
        # The orbit sidebar owns these controls on a wide window. A compact
        # header keeps search, folders and collection filtering reachable.
        if not self.film:
            header = w.layout().itemAt(0).layout(); sidebar = self.sidebar.layout()
            if narrow and w.search.parentWidget() is self.sidebar:
                for widget in (w.search, w.collection, w.folder_button):
                    sidebar.removeWidget(widget); header.insertWidget(header.count() - 3, widget, 1 if widget is w.search else 0)
            elif not narrow and w.search.parentWidget() is w:
                for widget in (w.search, w.collection, w.folder_button): header.removeWidget(widget)
                sidebar.insertWidget(0, w.search); sidebar.insertWidget(1, w.collection); sidebar.addWidget(w.folder_button)
        self.playing(w.slideshow.isActive())
        w.layout().activate()

    def select_collection(self, item, _previous):
        if item is not None:
            key = item.data(Qt.ItemDataRole.UserRole)
            self.window.collection.setCurrentIndex(self.window.collection.findData(key))

    def filtered(self, pictures):
        w = self.window; counts = Counter(p.collection for p in w.pictures)
        signature = [(key, count) for key, count in counts.items()]
        if signature != self.collection_signature:
            self.collection_signature = signature; self.collections.blockSignals(True); self.collections.clear()
            for caption, key, count in [('All wallpapers', '', len(w.pictures)), *[(key, key, count) for key, count in signature]]:
                item = QListWidgetItem(caption); item.setData(Qt.ItemDataRole.UserRole, key)
                item.setData(Qt.ItemDataRole.UserRole + 1, count); item.setToolTip(f'{caption} · {count} wallpapers')
                self.collections.addItem(item)
            self.collections.blockSignals(False)
        self.collections.blockSignals(True)
        for row in range(self.collections.count()):
            if self.collections.item(row).data(Qt.ItemDataRole.UserRole) == w.collection.currentData(): self.collections.setCurrentRow(row); break
        self.collections.blockSignals(False)
        self.seek.blockSignals(True); self.seek.setRange(0, max(0, len(pictures) - 1)); self.seek.blockSignals(False)
        self.seek.setEnabled(len(pictures) > 1)
        if not pictures:
            self.counter.setText('00 / 00'); self.position.setText('—'); self.resolution.setText('—'); self.format.setText('—')
        if self.strip: self.strip.update()

    def selected(self, picture):
        w = self.window; count = len(w.carousel.pictures); index = w.carousel.index % count
        self.counter.setText(f'{index + 1:02d} / {count:02d}'); self.position.setText(f'{index + 1} / {count}')
        self.seek.blockSignals(True); self.seek.setRange(0, count - 1); self.seek.setValue(index); self.seek.blockSignals(False)
        w.meta.setText(picture.collection)
        if picture.path in self.metadata: self.show_metadata(picture.path, self.metadata[picture.path])
        elif picture.path not in self.metadata_pending:
            self.resolution.setText('…'); self.format.setText(Path(picture.path).suffix.lstrip('.').upper() or 'Image')
            self.metadata_pending.add(picture.path)
            def inspect():
                reader = QImageReader(picture.path); size = reader.size()
                return size.width(), size.height(), bytes(reader.format()).decode('ascii', errors='replace').upper()
            w.jobs.run(inspect, lambda result: self.show_metadata(picture.path, result),
                       lambda _: self.show_metadata(picture.path, (-1, -1, 'Image')))
        if self.strip: self.strip.update()

    def show_metadata(self, path, result):
        self.metadata_pending.discard(path); self.metadata[path] = result
        current = self.window.carousel.current()
        if current is None or current.path != path: return
        width, height, kind = result
        self.resolution.setText(f'{width} × {height}' if width > 0 and height > 0 else 'Unavailable')
        self.format.setText(kind or 'Image')

    def playing(self, playing):
        self.window.play.setChecked(playing); self.window.play.setText('Ⅱ' if playing else '▶')
        self.slideshow_label.setText('Playing slideshow' if playing else 'Slideshow')

    def set_busy(self, busy):
        for widget in self.extra_controls: widget.setEnabled(not busy)
        if not busy: self.seek.setEnabled(len(self.window.carousel.pictures) > 1)
