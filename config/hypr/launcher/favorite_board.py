"""Fixed-column favorite tiles with native Qt drag/drop and keyboard navigation."""
import json
import uuid

from PyQt6.QtCore import Qt, QPoint, QRect, QRectF, QMimeData, QTimer, QPropertyAnimation, pyqtProperty, pyqtSignal
from PyQt6.QtGui import QColor, QDrag, QPainter, QPen, QFont, QCursor, QPalette
from PyQt6.QtWidgets import QApplication, QScrollArea, QWidget, QPushButton, QToolButton

import favorite_layout as layout

MIME = 'application/x-xetal-favorite-layout'
HEADER = 34
GROUP_GAP = 24
STRIDE = layout.COLUMN_WIDTH + layout.COLUMN_GAP


class Draggable(QPushButton):
    def __init__(self, board, kind, ident, parent):
        super().__init__(parent)
        self.board, self.kind, self.ident = board, kind, ident
        self.origin = None
        self.dragged = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.context)

    def context(self, point):
        signal = self.board.appMenuRequested if self.kind == 'tile' else self.board.groupMenuRequested
        signal.emit(self.ident, self.mapToGlobal(point if point.x() >= 0 else self.rect().center()))

    def mousePressEvent(self, event):
        self.origin = event.position().toPoint() if event.button() == Qt.MouseButton.LeftButton else None
        self.dragged = False
        if self.kind == 'group':
            self.board.selected_group = self.ident
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (self.origin is not None and event.buttons() & Qt.MouseButton.LeftButton
                and (event.position().toPoint() - self.origin).manhattanLength() >= QApplication.startDragDistance()):
            self.dragged = True
            self.setDown(False)
            drag = QDrag(self.board)
            drag.setMimeData(self.board.mime(self.kind, self.ident))
            drag.setPixmap(self.grab())
            drag.setHotSpot(self.origin)
            self.origin = None
            self.board.begin_drag()
            try:
                drag.exec(Qt.DropAction.MoveAction)
            finally:
                self.board.end_drag()
                drag.deleteLater()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.dragged:
            self.dragged = False
            self.origin = None
            self.setDown(False)
            event.accept()
            return
        self.origin = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self.kind == 'group' and event.button() == Qt.MouseButton.LeftButton:
            self.board.renameRequested.emit(self.ident)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class Tile(Draggable):
    def __init__(self, board, ident, size, parent):
        super().__init__(board, 'tile', ident, parent)
        self.size_name = size
        self.amount = 0.0
        self.animation = QPropertyAnimation(self, b'glow', self)
        self.animation.setDuration(160)
        self.clicked.connect(lambda: board.activated.emit(ident))
        self.setAccessibleName(board.items[ident]['name'])
        self.setToolTip(board.items[ident]['tooltip'])

    @pyqtProperty(float)
    def glow(self):
        return self.amount

    @glow.setter
    def glow(self, value):
        self.amount = value
        self.update()

    def enterEvent(self, event):
        self.animation.stop()
        self.animation.setStartValue(self.amount)
        self.animation.setEndValue(1.0)
        self.animation.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.animation.stop()
        self.animation.setStartValue(self.amount)
        self.animation.setEndValue(0.0)
        self.animation.start()
        super().leaveEvent(event)

    def focusInEvent(self, event):
        self.board.select(self.ident)
        super().focusInEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
            self.board.navigate(self.ident, event.key())
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.click()
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event):
        data = self.board.items.get(self.ident)
        if data is None:
            return
        painter = QPainter(self)
        self.board.draw_tile(painter, self.rect(), data['icon'], data['name'], data['hotkeys'],
                             self.board.selected == self.ident, self.amount, self.size_name == 'small')


class Canvas(QWidget):
    def __init__(self, board):
        super().__init__()
        self.board = board
        self.setAcceptDrops(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(lambda point: board.backgroundMenuRequested.emit(
            max(0, point.x() // STRIDE), self.mapToGlobal(point)))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(QFont('Noto Sans', 10))
        palette = self.palette()
        outline = palette.color(QPalette.ColorRole.Mid)
        text = palette.color(QPalette.ColorRole.PlaceholderText)
        accent = palette.color(QPalette.ColorRole.Link)
        for column, rect in self.board.empty_columns.items():
            painter.setPen(QPen(outline, 1, Qt.PenStyle.DashLine))
            painter.drawRoundedRect(QRectF(rect).adjusted(5, 4, -5, -4), 10, 10)
            painter.setPen(text)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, '+  Add a group\nDrop a tile or group here')
        for group in self.board.regions:
            if group['empty'] and group['column'] < self.board.visible_columns:
                painter.setPen(QPen(outline, 1, Qt.PenStyle.DashLine))
                painter.drawRoundedRect(QRectF(group['body']).adjusted(5, 4, -5, -4), 10, 10)
                painter.setPen(text)
                painter.drawText(group['body'], Qt.AlignmentFlag.AlignCenter, 'Drag favorites here')
        if self.board.drop_hint:
            painter.setPen(QPen(accent, 2))
            tint = QColor(accent)
            tint.setAlpha(24)
            painter.setBrush(tint)
            painter.drawRoundedRect(QRectF(self.board.drop_hint).adjusted(2, 2, -2, -2), 7, 7)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            for column, rect in self.board.empty_columns.items():
                if rect.contains(event.position().toPoint()):
                    self.board.newGroupRequested.emit(column)
                    return
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event):
        if self.board.payload(event.mimeData()):
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        payload = self.board.payload(event.mimeData())
        if payload:
            self.board.hover_drop(payload, event.position().toPoint())
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.board.clear_drop()
        event.accept()

    def dropEvent(self, event):
        payload = self.board.payload(event.mimeData())
        target = self.board.drop_target(payload, event.position().toPoint()) if payload else None
        self.board.clear_drop()
        if target:
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
            self.board.pending_drop = (payload, target)
            if not self.board.dragging:
                self.board.flush_drop()
        else:
            event.ignore()


class Board(QScrollArea):
    activated = pyqtSignal(str)
    selectedChanged = pyqtSignal(str)
    appMenuRequested = pyqtSignal(str, QPoint)
    groupMenuRequested = pyqtSignal(str, QPoint)
    backgroundMenuRequested = pyqtSignal(int, QPoint)
    newGroupRequested = pyqtSignal(int)
    renameRequested = pyqtSignal(str)
    dropped = pyqtSignal(object, object)
    dragStateChanged = pyqtSignal(bool)

    def __init__(self, draw_tile, parent=None):
        super().__init__(parent)
        self.draw_tile = draw_tile
        self.token = uuid.uuid4().hex
        self.data = {'version': 1, 'groups': []}
        self.items, self.tiles, self.headers, self.menus = {}, {}, {}, {}
        self.regions, self.empty_columns = [], {}
        self.selected = self.selected_group = None
        self.dragging = False
        self.pending_drop = self.drop_hint = self.drag_payload = None
        self.visible_columns = 1
        self.canvas = Canvas(self)
        self.setWidget(self.canvas)
        self.setWidgetResizable(False)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setStyleSheet('QScrollArea {background:transparent; border:0;}')
        self.horizontalScrollBar().valueChanged.connect(lambda value: self.horizontalScrollBar().setValue(0) if value else None)
        self.scroll_timer = QTimer(self)
        self.scroll_timer.setInterval(40)
        self.scroll_timer.timeout.connect(self.auto_scroll)

    def set_layout(self, data, items, selected=None):
        self.data, self.items = data, items
        for widget in [*self.tiles.values(), *self.headers.values(), *self.menus.values()]:
            widget.hide()
            widget.deleteLater()
        self.tiles, self.headers, self.menus = {}, {}, {}
        for group in data['groups']:
            ident = group['id']
            header = Draggable(self, 'group', ident, self.canvas)
            header.setText('⠿  ' + group['title'].replace('&', '&&'))
            header.setAccessibleName(group['title'] + ' group; drag to move')
            header.setToolTip('Drag this title to move the group · Double-click to rename')
            header.setStyleSheet('QPushButton {padding:4px 6px; font-size:13px; font-weight:600; color:palette(window-text);}')
            self.headers[ident] = header
            menu = QToolButton(self.canvas)
            menu.setText('⋯')
            menu.setAccessibleName('Options for ' + group['title'])
            menu.setToolTip('Rename, move or remove group')
            menu.setStyleSheet('QToolButton {border:0; border-radius:5px; color:palette(placeholder-text); font-size:20px;} QToolButton:hover {background:palette(highlight); color:palette(highlighted-text);}')
            menu.clicked.connect(lambda checked=False, ident=ident, menu=menu: self.groupMenuRequested.emit(ident, menu.mapToGlobal(menu.rect().bottomLeft())))
            self.menus[ident] = menu
            for tile in group['tiles']:
                if tile['app'] in items:
                    self.tiles[tile['app']] = Tile(self, tile['app'], tile['size'], self.canvas)
        self.selected = selected if selected in self.tiles else next(iter(self.tiles), None)
        self.relayout()

    def update_items(self, items):
        self.items = items
        for ident, tile in self.tiles.items():
            if ident in items:
                tile.setToolTip(items[ident]['tooltip'])
                tile.update()
            else:
                tile.hide()

    def select(self, ident):
        old = self.selected
        self.selected = ident
        if old in self.tiles:
            self.tiles[old].update()
        if ident in self.tiles:
            self.tiles[ident].update()
            self.selected_group = layout.find_tile(self.data, ident)[0]['id']
            self.selectedChanged.emit(ident)

    def focus_selected(self):
        choices = [tile for tile in self.tiles.values() if not tile.isHidden()]
        target = self.tiles.get(self.selected)
        if target is None or target.isHidden():
            target = choices[0] if choices else None
        if target:
            target.setFocus()
            self.ensureWidgetVisible(target, 0, 12)

    def navigate(self, ident, key):
        origin = self.tiles[ident].geometry().center()
        horizontal = key in (Qt.Key.Key_Left, Qt.Key.Key_Right)
        direction = -1 if key in (Qt.Key.Key_Left, Qt.Key.Key_Up) else 1
        choices = []
        for app, tile in self.tiles.items():
            if app == ident or tile.isHidden():
                continue
            delta = tile.geometry().center() - origin
            forward, cross = (delta.x(), delta.y()) if horizontal else (delta.y(), delta.x())
            if forward * direction > 0:
                choices.append((abs(cross) * 3 + abs(forward), app))
        if choices:
            self.select(min(choices)[1])
            self.focus_selected()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'canvas'):
            self.relayout()

    def relayout(self):
        self.visible_columns = max(1, (self.viewport().width() + layout.COLUMN_GAP) // STRIDE)
        columns = max(self.visible_columns, max((g['column'] + 1 for g in self.data['groups']), default=1))
        y_positions = [0] * columns
        self.regions, self.empty_columns = [], {}
        for group in self.data['groups']:
            ident, column = group['id'], group['column']
            x, y = column * STRIDE, y_positions[column]
            placed = layout.packed([tile for tile in group['tiles'] if tile['app'] in self.items])
            height = max((top + height for _, _, top, _, height in placed), default=layout.MEDIUM_HEIGHT)
            header = QRect(x, y, layout.COLUMN_WIDTH, HEADER)
            body = QRect(x, y + HEADER, layout.COLUMN_WIDTH, height)
            self.regions.append({'id': ident, 'column': column, 'header': header, 'body': body, 'empty': not placed})
            self.headers[ident].setGeometry(x, y, layout.COLUMN_WIDTH - 32, HEADER)
            self.menus[ident].setGeometry(x + layout.COLUMN_WIDTH - 30, y + 2, 28, HEADER - 4)
            visible = column < self.visible_columns
            self.headers[ident].setVisible(visible)
            self.menus[ident].setVisible(visible)
            for app, left, top, width, tile_height in placed:
                self.tiles[app].setGeometry(x + left, y + HEADER + top, width, tile_height)
                self.tiles[app].setVisible(visible)
            y_positions[column] = body.bottom() + 1 + GROUP_GAP
        for column in range(self.visible_columns):
            if y_positions[column] == 0:
                self.empty_columns[column] = QRect(column * STRIDE, 4, layout.COLUMN_WIDTH, HEADER + layout.MEDIUM_HEIGHT)
        height = max(self.viewport().height(), max(y_positions, default=0), HEADER + layout.MEDIUM_HEIGHT)
        self.canvas.resize(max(self.viewport().width(), columns * STRIDE - layout.COLUMN_GAP), height)
        self.canvas.update()

    def mime(self, kind, ident):
        mime = QMimeData()
        mime.setData(MIME, json.dumps({'token': self.token, 'kind': kind, 'id': ident}).encode())
        return mime

    def payload(self, mime):
        try:
            data = json.loads(bytes(mime.data(MIME)))
            if data.get('token') != self.token:
                return None
            valid = self.tiles if data.get('kind') == 'tile' else self.headers if data.get('kind') == 'group' else {}
            return data if data.get('id') in valid else None
        except (ValueError, TypeError, AttributeError):
            return None

    def drop_target(self, payload, point):
        column = point.x() // STRIDE
        if column < 0 or column >= self.visible_columns or point.y() < 0:
            return None
        groups = [g for g in self.regions if g['column'] == column]
        if payload['kind'] == 'group':
            before = next((g['id'] for g in groups if point.y() < g['body'].center().y()), None)
            return {'column': column, 'before': before}
        if not groups:
            return {'column': column, 'group': None, 'before': None}
        group = next((g for g in groups if point.y() <= g['body'].bottom() + GROUP_GAP // 2), groups[-1])
        before = None
        entries = layout.find_group(self.data, group['id'])['tiles']
        for index, tile in enumerate(entries):
            button = self.tiles.get(tile['app'])
            if button and button.geometry().contains(point):
                if point.x() <= button.geometry().center().x():
                    before = tile['app']
                else:
                    before = next((t['app'] for t in entries[index + 1:] if t['app'] != payload['id']), None)
                break
        return {'column': column, 'group': group['id'], 'before': before}

    def hover_drop(self, payload, point):
        self.drag_payload = payload
        target = self.drop_target(payload, point)
        self.drop_hint = None
        if target:
            if payload['kind'] == 'tile' and target.get('before') in self.tiles:
                self.drop_hint = self.tiles[target['before']].geometry()
            else:
                ident = target.get('group') or target.get('before')
                region = next((g for g in self.regions if g['id'] == ident), None)
                self.drop_hint = region['header'] if region else QRect(target['column'] * STRIDE, point.y(), layout.COLUMN_WIDTH, HEADER)
        self.canvas.update()

    def clear_drop(self):
        self.drop_hint = self.drag_payload = None
        self.canvas.update()

    def begin_drag(self):
        self.dragging = True
        self.pending_drop = None
        self.dragStateChanged.emit(True)
        self.scroll_timer.start()

    def end_drag(self):
        self.scroll_timer.stop()
        self.dragging = False
        self.clear_drop()
        self.flush_drop()
        self.dragStateChanged.emit(False)

    def flush_drop(self):
        if self.pending_drop:
            payload, target = self.pending_drop
            self.pending_drop = None
            self.dropped.emit(payload, target)

    def auto_scroll(self):
        point = self.viewport().mapFromGlobal(QCursor.pos())
        if not 0 <= point.x() < self.viewport().width():
            return
        delta = -18 if point.y() < 30 else 18 if point.y() > self.viewport().height() - 30 else 0
        if delta:
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() + delta)
            if self.drag_payload:
                self.hover_drop(self.drag_payload, self.canvas.mapFromGlobal(QCursor.pos()))
