"""Theme page navigation that keeps every tab visible as the window resizes."""
from PyQt6.QtCore import QEvent, QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QButtonGroup, QPushButton, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget


class TabRows(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.buttons = []
        self.pending = False
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def addButton(self, button):
        button.setParent(self)
        self.buttons.append(button)
        button.installEventFilter(self)
        self.schedule()

    def minimumSizeHint(self):
        return QSize(max((button.sizeHint().width() for button in self.buttons), default=0), 0)

    def sizeHint(self):
        return QSize(sum(button.sizeHint().width() + 6 for button in self.buttons), self.height())

    def schedule(self):
        if not self.pending:
            self.pending = True
            QTimer.singleShot(0, self.reflow)

    def reflow(self):
        self.pending = False
        width = self.width()
        gap = 6
        x = y = row_height = 0
        for button in self.buttons:
            hint = button.sizeHint()
            w, h = min(width, hint.width()), hint.height()
            if x and x + w > width:
                x = 0
                y += row_height + gap
                row_height = 0
            rect = QRect(x, y, w, h)
            if self.layoutDirection() == Qt.LayoutDirection.RightToLeft:
                rect.moveLeft(width - x - w)
            button.setGeometry(rect)
            x += w + gap
            row_height = max(row_height, h)
        self.setFixedHeight(y + row_height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reflow()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange, QEvent.Type.LayoutDirectionChange):
            self.schedule()

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange, QEvent.Type.LayoutRequest):
            self.schedule()
        return super().eventFilter(obj, event)


class WrappingTabs(QWidget):
    currentChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.rows = TabRows(self)
        self.stack = QStackedWidget(self)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.group.idClicked.connect(self.setCurrentIndex)
        self.stack.currentChanged.connect(self.changed)
        layout.addWidget(self.rows)
        layout.addWidget(self.stack, 1)
        for key, direction in (('Ctrl+Tab', 1), ('Ctrl+Shift+Tab', -1)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(lambda step=direction: self.advance(step))

    def addTab(self, page, title):
        index = self.count()
        button = QPushButton(title)
        button.setCheckable(True)
        button.setAutoDefault(False)
        button.setAccessibleName(title.replace('&&', '&'))
        button.installEventFilter(self)
        self.group.addButton(button, index)
        self.rows.addButton(button)
        self.stack.addWidget(page)
        button.setChecked(index == self.currentIndex())
        return index

    def count(self): return self.stack.count()
    def widget(self, index): return self.stack.widget(index)
    def indexOf(self, page): return self.stack.indexOf(page)
    def currentIndex(self): return self.stack.currentIndex()
    def currentWidget(self): return self.stack.currentWidget()
    def setCurrentIndex(self, index): self.stack.setCurrentIndex(index)
    def setCurrentWidget(self, page): self.stack.setCurrentWidget(page)
    def tabText(self, index): return self.rows.buttons[index].text()

    def changed(self, index):
        for number, button in enumerate(self.rows.buttons):
            button.setChecked(number == index)
        self.rows.schedule()
        self.currentChanged.emit(index)

    def advance(self, direction):
        if self.count():
            self.setCurrentIndex((self.currentIndex() + direction) % self.count())
            self.rows.buttons[self.currentIndex()].setFocus()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress and obj in self.rows.buttons:
            key = event.key()
            if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
                step = 1 if key == Qt.Key.Key_Right else -1
                if self.layoutDirection() == Qt.LayoutDirection.RightToLeft: step = -step
                self.advance(step)
                return True
            if key in (Qt.Key.Key_Home, Qt.Key.Key_End):
                self.setCurrentIndex(0 if key == Qt.Key.Key_Home else self.count() - 1)
                self.rows.buttons[self.currentIndex()].setFocus()
                return True
        return super().eventFilter(obj, event)
