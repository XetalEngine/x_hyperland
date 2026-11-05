"""Visual dock selection shared by Minimize and Mix & match; never applies settings."""
import math
from pathlib import Path
import sys

from PyQt6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (QApplication, QBoxLayout, QDialog, QDialogButtonBox, QFrame,
    QGroupBox, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'theme'))
import runtime
from . import artwork, model


def resolved(value):
    return runtime.design() if value == 'follow' else value


def title(value):
    return 'Follow desktop theme' if value == 'follow' else model.DOCK_STYLES[value].split(' · ')[0]


def note(text):
    label = QLabel(text); label.setWordWrap(True); label.setObjectName('muted'); return label


class DesignCard(QPushButton):
    def __init__(self, design):
        super().__init__(); self.design = design; self.setCheckable(True)
        self.setFixedHeight(109); self.setMinimumWidth(172)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor); self.setAccessibleName(model.DOCK_STYLES[design])
        self.setToolTip(model.DOCK_STYLES[design]); self.refresh()

    def refresh(self):
        self.colors = runtime.colors(); self.sample_colors = runtime.colors(style=resolved(self.design)); self.update()

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled(): p.setOpacity(.5)
        accent = self.sample_colors['Accent']
        active = self.isChecked() or self.hasFocus()
        p.setPen(QPen(QColor(accent if active else self.colors['Midlight']), 2 if active else 1))
        p.setBrush(QColor(self.colors['AlternateBase'] if self.underMouse() or active else self.colors['Window']))
        p.drawRoundedRect(QRectF(1, 1, self.width()-2, self.height()-2), 12, 12)
        font = QFont(self.font()); font.setPointSize(10); font.setWeight(QFont.Weight.DemiBold); p.setFont(font)
        p.setPen(QColor(self.colors['Text']))
        caption = p.fontMetrics().elidedText(title(self.design), Qt.TextElideMode.ElideRight, self.width()-24)
        p.drawText(QRectF(12, 5, self.width()-24, 25), Qt.AlignmentFlag.AlignVCenter, caption)
        artwork.dock(p, QRectF(9, 32, self.width()-18, 54), resolved(self.design), self.sample_colors, phase=.8)
        font.setPointSize(8); font.setWeight(QFont.Weight.Normal); p.setFont(font); p.setPen(QColor(self.colors['PlaceholderText']))
        caption = title(resolved(self.design)) if self.design == 'follow' else model.DOCK_STYLES[self.design].split(' · ')[-1].capitalize()
        p.drawText(QRectF(9, 86, self.width()-18, 18), Qt.AlignmentFlag.AlignCenter, caption)


class DesignList(QScrollArea):
    valueChanged = pyqtSignal(str)

    def __init__(self):
        super().__init__(); self._value = 'follow'; self.cards = {}
        self.setWidgetResizable(True); self.setFrameShape(QFrame.Shape.NoFrame); self.setFixedWidth(212)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAccessibleName('Dock designs')
        content = QWidget(); layout = QVBoxLayout(content); layout.setContentsMargins(0, 2, 8, 2); layout.setSpacing(9)
        for design in model.DOCK_STYLES:
            card = DesignCard(design); card.clicked.connect(lambda _, value=design: self.setValue(value))
            layout.addWidget(card); self.cards[design] = card
        layout.addStretch(); self.setWidget(content); self.cards[self._value].setChecked(True)

    def value(self): return self._value

    def setValue(self, value):
        if value not in self.cards: raise ValueError('Unknown dock design: '+str(value))
        changed = self._value != value; self._value = value
        for key, card in self.cards.items(): card.setChecked(key == value)
        self.ensureWidgetVisible(self.cards[value], 0, 10)
        if changed: self.valueChanged.emit(value)

    def refresh(self):
        for card in self.cards.values(): card.refresh()

    def showEvent(self, event):
        super().showEvent(event); self.ensureWidgetVisible(self.cards[self._value], 0, 10)

    def resizeEvent(self, event):
        super().resizeEvent(event); self.ensureWidgetVisible(self.cards[self._value], 0, 10)


class DockPreview(QWidget):
    countChanged = pyqtSignal(int)

    def __init__(self):
        super().__init__(); self.setMinimumSize(240, 180); self.setMouseTracking(True)
        self.setAccessibleName('Animated dock preview'); self.setToolTip('Hover to zoom. Click a sample slot to restore it.')
        self.options = dict(model.DEFAULTS); self.count = 3; self.weights = [1., 1., 1.]; self.zooms = [1., 1., 1.]
        self.hover = -1; self.slots = []; self.phase = 0.
        self.clock = QElapsedTimer(); self.clock.start()
        self.animation = QTimer(self); self.animation.setInterval(33); self.animation.timeout.connect(self.tick)
        self.configure(self.options)

    def configure(self, options):
        self.options = dict(options); self.style = resolved(options['dock_style']); self.colors = dict(runtime.colors())
        if not options['follow_theme']: self.colors['Accent'] = options['color']
        self.update()

    def add_window(self):
        if self.count >= 5: return
        self.count += 1
        if len(self.weights) < self.count: self.weights.append(0.); self.zooms.append(1.)
        self.countChanged.emit(self.count); self.update()

    def restore_window(self):
        if self.count == 0: return
        self.count -= 1; self.hover = -1; self.countChanged.emit(self.count); self.update()

    def tick(self):
        dt = min(.06, self.clock.restart()/1000); self.phase += dt*self.options['speed']/100
        step = 1-math.exp(-dt*5000/self.options['dock_duration'])
        for index in range(len(self.weights)):
            target = 1. if index < self.count else 0.
            self.weights[index] += (target-self.weights[index])*step
            zoom = self.options['dock_zoom']/100 if index == self.hover else 1.
            self.zooms[index] += (zoom-self.zooms[index])*min(1., dt*14)
        while len(self.weights) > self.count and self.weights[-1] < .005:
            self.weights.pop(); self.zooms.pop()
        self.update()

    def showEvent(self, event):
        super().showEvent(event); self.clock.restart(); self.animation.start()

    def hideEvent(self, event):
        self.animation.stop(); self.hover = -1; super().hideEvent(event)

    def mouseMoveEvent(self, event):
        self.hover = next((i for i, rect in enumerate(self.slots[:self.count]) if rect.contains(event.position())), -1)
        self.setCursor(Qt.CursorShape.PointingHandCursor if self.hover >= 0 else Qt.CursorShape.ArrowCursor)

    def leaveEvent(self, event): self.hover = -1; super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and any(r.contains(event.position()) for r in self.slots[:self.count]):
            self.restore_window()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = QRectF(self.rect()).adjusted(4, 8, -4, -8)
        p.setPen(QPen(artwork.alpha(self.colors['Midlight'], .65), 1)); p.setBrush(QColor(self.colors['Base']))
        p.drawRoundedRect(area, 12, 12)
        p.setClipRect(area.adjusted(2, 2, -2, -2))
        p.setPen(QPen(artwork.alpha(self.colors['Accent'], .13), 1))
        for x in range(24, self.width(), 28): artwork.line(p, x, 12, x, self.height()-12)
        for y in range(24, self.height(), 28): artwork.line(p, 8, y, self.width()-8, y)
        stack = self.options['presentation'] == 'stack'
        edge = self.options['edge'] if stack else self.options['dock_edge']
        if edge == 'auto': edge = 'bottom'  # Representative output with its Waybar at the top.
        vertical = edge in ('left', 'right')
        length = 48+sum(self.weights)*74
        scale = min(self.options['size']/76., (area.height()-72)/(length if vertical else 96), (area.width()-48)/(96 if vertical else length))
        w, h = (96*scale, length*scale) if vertical else (length*scale, 96*scale)
        spot = QRectF(area.center().x()-w/2, area.center().y()-h/2, w, h)
        margin = 28
        if edge == 'bottom': spot.moveBottom(area.bottom()-margin)
        elif edge == 'top': spot.moveTop(area.top()+margin)
        elif edge == 'left': spot.moveLeft(area.left()+margin)
        else: spot.moveRight(area.right()-margin)
        self.slots = artwork.dock(p, spot, self.style, self.colors, phase=self.phase, weights=self.weights,
                                  zoom=self.zooms, vertical=vertical, stack=stack)
        if not self.weights:
            p.setPen(QColor(self.colors['PlaceholderText']))
            p.drawText(area, Qt.AlignmentFlag.AlignCenter, 'Dock empty\nAdd a sample window to preview it.')


class PreviewPanel(QGroupBox):
    def __init__(self):
        super().__init__('Live preview'); self.setMinimumWidth(280)
        layout = QVBoxLayout(self); layout.setContentsMargins(12, 16, 12, 12); layout.setSpacing(9)
        self.name = QLabel(); self.name.setWordWrap(True); layout.addWidget(self.name)
        self.description = note(''); layout.addWidget(self.description)
        self.scene = DockPreview(); layout.addWidget(self.scene, 1)
        self.summary = note(''); self.summary.setAlignment(Qt.AlignmentFlag.AlignCenter); layout.addWidget(self.summary)
        controls = QHBoxLayout(); self.add = QPushButton('Add window'); self.remove = QPushButton('Restore window')
        self.add.clicked.connect(self.scene.add_window); self.remove.clicked.connect(self.scene.restore_window)
        controls.addWidget(self.add); controls.addWidget(self.remove); layout.addLayout(controls)
        layout.addWidget(note('Hover to zoom; click a slot to restore the sample. Preview only · your windows stay as they are.'))
        self.scene.countChanged.connect(self.count_changed); self.configure(model.DEFAULTS)

    def configure(self, options):
        self.scene.configure(options)
        self.name.setText(model.DOCK_STYLES[self.scene.style] if options['presentation'] == 'dock' else 'Classic edge stack · Fireball')
        self.description.setText(('Follows '+title(self.scene.style)+'. ' if options['dock_style'] == 'follow' else '')+
                                 'Uses your desktop colors'+(' and custom accent.' if not options['follow_theme'] else '.'))
        self.count_changed(self.scene.count)

    def count_changed(self, count):
        self.add.setEnabled(count < 5); self.remove.setEnabled(count > 0)
        self.summary.setText(f'{count} sample window'+('s' if count != 1 else '')+
                             f" · {self.scene.options['size']} px · {self.scene.options['dock_zoom']}% hover zoom")


class PreviewDetails(QScrollArea):
    """Two columns when space permits; one scroll surface on narrow windows."""
    def __init__(self, preview, controls):
        super().__init__(); self.preview = preview; self.controls = controls; self.stacked = None
        self.setWidgetResizable(True); self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget(); self.columns = QBoxLayout(QBoxLayout.Direction.LeftToRight, content)
        self.columns.setContentsMargins(0, 0, 0, 0); self.columns.setSpacing(14)
        self.columns.addWidget(preview, 1); self.columns.addWidget(controls, 1); self.setWidget(content)

    def arrange(self):
        stacked = self.viewport().width() < max(730, self.preview.minimumSizeHint().width()+self.controls.minimumSizeHint().width()+24)
        if stacked != self.stacked:
            self.stacked = stacked
            self.columns.setDirection(QBoxLayout.Direction.TopToBottom if stacked else QBoxLayout.Direction.LeftToRight)
        height = max(420, self.preview.minimumSizeHint().height())
        self.preview.setMinimumHeight(height if stacked else 330); self.preview.setMaximumHeight(height if stacked else 16777215)

    def resizeEvent(self, event): super().resizeEvent(event); self.arrange()
    def showEvent(self, event): super().showEvent(event); self.arrange()


class DesignDialog(QDialog):
    def __init__(self, value, parent=None):
        super().__init__(parent); self.setWindowTitle('Choose a dock design'); self.resize(820, 610)
        layout = QVBoxLayout(self); layout.addWidget(note('Mix any dock design with your desktop theme. Preview it here, then choose Use design.'))
        workspace = QHBoxLayout(); self.designs = DesignList(); self.preview = PreviewPanel()
        workspace.addWidget(self.designs); workspace.addWidget(self.preview, 1); layout.addLayout(workspace, 1)
        try: self.options = model.load()[0]
        except (OSError, ValueError): self.options = dict(model.DEFAULTS)
        self.options = dict(self.options, presentation='dock', dock_style=value)
        self.designs.valueChanged.connect(self.select); self.designs.setValue(value); self.select(value)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Use design')
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
        app = QApplication.instance()
        if hasattr(app, 'hypr_theme'): app.hypr_theme.changed.connect(self.desktop_changed)

    def select(self, value):
        self.options['dock_style'] = value; self.preview.configure(self.options)

    def desktop_changed(self):
        self.designs.refresh(); self.preview.configure(self.options)


class DesignButton(QPushButton):
    """Compact visual entry point for the quick Mix & match form."""
    valueChanged = pyqtSignal(str)

    def __init__(self):
        super().__init__(); self._value = 'follow'; self.setMinimumHeight(76); self.setMinimumWidth(200)
        self.setCursor(Qt.CursorShape.PointingHandCursor); self.clicked.connect(self.choose); self.refresh()
        app = QApplication.instance()
        if hasattr(app, 'hypr_theme'): app.hypr_theme.changed.connect(self.refresh)

    def value(self): return self._value

    def setValue(self, value):
        if value not in model.DOCK_STYLES: raise ValueError('Unknown dock design')
        changed = value != self._value; self._value = value; self.refresh()
        if changed: self.valueChanged.emit(value)

    def refresh(self):
        self.colors = runtime.colors(); self.setToolTip(model.DOCK_STYLES[self._value]+' · Browse designs'); self.update()

    def choose(self):
        dialog = DesignDialog(self._value, self)
        if dialog.exec() == QDialog.DialogCode.Accepted: self.setValue(dialog.designs.value())
        dialog.deleteLater()

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(self.colors['Accent'] if self.hasFocus() or self.underMouse() else self.colors['Midlight']), 1))
        p.setBrush(QColor(self.colors['Base'])); p.drawRoundedRect(QRectF(1, 1, self.width()-2, self.height()-2), 9, 9)
        artwork.dock(p, QRectF(8, 5, 96, self.height()-10), resolved(self._value), self.colors, phase=.8)
        p.setPen(QColor(self.colors['Text'])); font = QFont(self.font()); p.setFont(font)
        caption = p.fontMetrics().elidedText(title(self._value), Qt.TextElideMode.ElideRight, max(10, self.width()-124))
        p.drawText(QRectF(112, 8, self.width()-124, 28), Qt.AlignmentFlag.AlignVCenter, caption)
        p.setPen(QColor(self.colors['PlaceholderText']))
        p.drawText(QRectF(112, 35, self.width()-124, 28), Qt.AlignmentFlag.AlignVCenter, 'Browse designs…')
