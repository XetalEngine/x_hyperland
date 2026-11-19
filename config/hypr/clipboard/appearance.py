"""Compact clipboard cards and the desktop's shared menu surface."""
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QStyle, QStyledItemDelegate

import runtime
from launcher_surfaces import paint_group

DETAIL = Qt.ItemDataRole.UserRole + 1
PINNED = Qt.ItemDataRole.UserRole + 2
IMAGE = Qt.ItemDataRole.UserRole + 3


def symbol(name, color, size=20):
    """Small palette-colored symbols, independent of the system icon theme."""
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 24, size / 24)
    p.setPen(QPen(QColor(color), 1.6, Qt.PenStyle.SolidLine,
                 Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)
    def line(x, y, a, b): p.drawLine(QPointF(x, y), QPointF(a, b))
    if name == 'clipboard':
        p.drawRoundedRect(QRectF(5, 5, 14, 16), 2, 2)
        p.drawRoundedRect(QRectF(9, 2, 6, 5), 1, 1)
        line(9, 11, 15, 11); line(9, 15, 15, 15)
    elif name == 'pin':
        path = QPainterPath(QPointF(8, 3))
        for x, y in ((16, 3), (15, 11), (19, 15), (5, 15), (9, 11), (8, 3)):
            path.lineTo(x, y)
        p.drawPath(path); line(12, 15, 12, 22)
    elif name == 'delete':
        line(4, 6, 20, 6); line(9, 3, 15, 3)
        path = QPainterPath(QPointF(6, 6))
        for x, y in ((7, 21), (17, 21), (18, 6)): path.lineTo(x, y)
        p.drawPath(path); line(10, 10, 10, 17); line(14, 10, 14, 17)
    elif name == 'copy':
        p.drawRoundedRect(QRectF(8, 8, 13, 13), 2, 2)
        path = QPainterPath(QPointF(16, 4))
        for x, y in ((16, 3), (3, 3), (3, 16), (4, 16)): path.lineTo(x, y)
        p.drawPath(path)
    elif name == 'close':
        line(6, 6, 18, 18); line(18, 6, 6, 18)
    p.end()
    return QIcon(pixmap)


def radius(style):
    return 2 if style in ('mystery98', 'platform95', 'shadowedge') else 5 if style in (
        'binaryknife', 'killerinstinct', 'kitemple', 'kiprimal', 'kifireice', 'starcraft', 'mortalkombat2', 'prisonbreak', 'infernalencore') else 14


def paint_panel(widget):
    p = QPainter(widget)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    box = QRectF(widget.rect()).adjusted(.5, .5, -.5, -.5)
    c, style = widget.colors, widget.design
    r = radius(style)
    clip = QPainterPath(); clip.addRoundedRect(box, r, r)
    p.setClipPath(clip)
    fill = QColor(c['Base']); fill.setAlpha(247)
    p.fillRect(box, fill)
    # The header uses the same materials/accents as the Apps menu. The list
    # stays quiet so copied text and thumbnail previews remain easy to read.
    paint_group(p, QRectF(0, 0, widget.width(), 66), c, style, 100)
    p.setPen(QPen(QColor(c['Mid']), 1)); p.drawLine(QPointF(14, 66), QPointF(widget.width()-14, 66))
    p.setClipping(False); p.setBrush(Qt.BrushStyle.NoBrush)
    border = QColor(c['Accent']); border.setAlpha(145)
    p.setPen(QPen(border, 1)); p.drawRoundedRect(box, r, r)
    p.end()


def refresh(widget):
    c = widget.colors = runtime.colors()
    widget.design = runtime.widget_design()
    r = max(3, radius(widget.design) - 5)
    check = runtime.ROOT/'assets'/('check-light.svg' if QColor(c['HighlightedText']).lightnessF() > .5 else 'check-dark.svg')
    widget.setStyleSheet(f'''
        QWidget {{background:transparent; color:{c['Text']}; font-family:"{runtime.ui_font()}"; font-size:12px;}}
        QLabel {{background:transparent; border:none;}}
        QLabel#clipboardTitle {{font-size:17px; font-weight:600;}}
        QLabel#muted {{color:{c['PlaceholderText']}; font-size:11px;}}
        QLabel#empty {{color:{c['PlaceholderText']}; padding:20px;}}
        QLineEdit {{background:{c['Window']}; border:1px solid {c['Mid']}; border-radius:{r}px; padding:8px 10px; min-height:16px;}}
        QLineEdit:focus {{border-color:{c['Accent']};}}
        QListWidget, QListWidget::item {{background:transparent; border:0; padding:0; outline:0;}}
        QPushButton {{background:transparent; border:1px solid transparent; border-radius:{r}px; padding:6px 8px; min-width:0; min-height:0;}}
        QPushButton:hover, QPushButton:focus {{background:{c['Button']}; border-color:{c['Accent']};}}
        QPushButton:disabled {{color:{c['Disabled']};}}
        QPushButton#copy {{background:{c['Highlight']}; color:{c['HighlightedText']}; border-color:{c['Accent']}; font-weight:600; padding:6px 14px;}}
        QPushButton#copy:disabled {{background:{c['Button']}; color:{c['Disabled']}; border-color:{c['Mid']};}}
        QPushButton#quiet {{color:{c['PlaceholderText']}; font-size:11px; padding:4px 6px;}}
        QCheckBox {{spacing:6px; color:{c['PlaceholderText']}; font-size:11px;}}
        QCheckBox::indicator {{width:14px; height:14px; border:1px solid {c['Midlight']}; border-radius:3px; background:{c['Window']};}}
        QCheckBox::indicator:checked {{image:url("{check}"); background:{c['Highlight']}; border-color:{c['Accent']};}}
        QScrollBar:vertical {{background:transparent; width:5px; margin:0;}}
        QScrollBar::handle:vertical {{background:{c['Mid']}; min-height:24px; border-radius:2px;}}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{height:0;}}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{background:transparent;}}
    ''')
    widget.mark.setPixmap(symbol('clipboard', c['Accent'], 26).pixmap(26, 26))
    widget.close_button.setIcon(symbol('close', c['Text'], 16))
    widget.copy.setIcon(symbol('copy', c['HighlightedText'], 16))
    widget.pin.setIcon(symbol('pin', c['Text'], 16))
    widget.delete.setIcon(symbol('delete', c['Text'], 16))
    widget.list.viewport().update(); widget.update()


class EntryDelegate(QStyledItemDelegate):
    def __init__(self, window):
        super().__init__(window.list)
        self.window = window

    def paint(self, p, option, index):
        c = self.window.colors
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        text = c['HighlightedText'] if selected else c['Text']
        muted = c['HighlightedText'] if selected else c['PlaceholderText']
        box = QRectF(option.rect).adjusted(1, 2, -1, -2)
        p.save(); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setClipRect(option.rect)
        p.setPen(QPen(QColor(c['Accent'] if selected or hovered else c['Mid']), 1))
        p.setBrush(QColor(c['Highlight'] if selected else c['Window']))
        r = max(3, radius(self.window.design) - 5)
        p.drawRoundedRect(box, r, r)
        left = box.left() + 12
        if index.data(IMAGE):
            icon = index.data(Qt.ItemDataRole.DecorationRole)
            if isinstance(icon, QIcon):
                icon.paint(p, int(left), int(box.top()+10), 72, int(box.height()-20), Qt.AlignmentFlag.AlignCenter)
            left += 84
        available = max(0, int(box.right() - left - 12))
        font = QFont(option.font); font.setPixelSize(12); p.setFont(font)
        label = p.fontMetrics().elidedText(index.data() or '', Qt.TextElideMode.ElideRight, available)
        p.setPen(QColor(text))
        p.drawText(QRectF(left, box.top()+11, available, 22), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)
        font.setPixelSize(10); p.setFont(font); p.setPen(QColor(muted))
        detail = index.data(DETAIL) or ''
        if index.data(PINNED):
            symbol('pin', muted, 12).paint(p, int(left), int(box.bottom()-23), 12, 12)
            left += 17; available -= 17
        detail = p.fontMetrics().elidedText(detail, Qt.TextElideMode.ElideRight, max(0, available))
        p.drawText(QRectF(left, box.bottom()-26, available, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, detail)
        p.restore()
