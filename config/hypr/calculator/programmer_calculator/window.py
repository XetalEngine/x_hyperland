"""Native Qt interface and focus-scoped keyboard controls."""

from pathlib import Path

from PyQt6.QtCore import QEvent, QPoint, QPointF, QRectF, QSettings, QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QFontMetrics, QIcon, QPainter, QPen, QPixmap, QPolygonF
from PyQt6.QtWidgets import (
    QApplication, QButtonGroup, QComboBox, QDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QPushButton, QRadioButton, QScrollArea, QSizeGrip,
    QSizePolicy, QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from .engine import Calculator, CalculatorError, HistoryEntry, OPERATORS, format_number
from .theme import ACCENT, MUTED, TEXT

ASSET_DIR = Path(__file__).parent / "assets"
SETTINGS_PATH = Path(__file__).resolve().parents[1] / "state/preferences.ini"


def ui_font_family() -> str:
    families = set(QFontDatabase.families())
    return next((name for name in ("Inter", "Segoe UI", "Adwaita Sans", "Noto Sans")
                 if name in families), "Sans Serif")


def mono_font_family() -> str:
    families = set(QFontDatabase.families())
    return next((name for name in ("Cascadia Code", "JetBrains Mono", "FiraCode Nerd Font",
                                  "DejaVu Sans Mono") if name in families), "Monospace")


def refresh_style(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def icon(name: str, color: str = MUTED, size: int = 20) -> QIcon:
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(size / 20, size / 20)
    painter.setPen(QPen(QColor(color), 1.4, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    if name == "close":
        painter.drawLine(6, 6, 14, 14)
        painter.drawLine(14, 6, 6, 14)
    elif name == "minimize":
        painter.drawLine(5, 10, 15, 10)
    elif name == "maximize":
        painter.drawRoundedRect(QRectF(5, 5, 10, 10), 1, 1)
    elif name == "copy":
        painter.drawRoundedRect(QRectF(7, 7, 9, 10), 2, 2)
        painter.drawPolyline(QPolygonF([QPointF(12, 4), QPointF(4, 4), QPointF(4, 13)]))
    elif name == "history":
        painter.drawArc(QRectF(4, 4, 13, 13), 45 * 16, -295 * 16)
        painter.drawPolyline(QPolygonF([QPointF(3, 4), QPointF(3, 8), QPointF(7, 8)]))
        painter.drawPolyline(QPolygonF([QPointF(10, 7), QPointF(10, 11), QPointF(13, 12)]))
    elif name == "keyboard":
        painter.drawRoundedRect(QRectF(2, 5, 16, 11), 2, 2)
        for y in (8, 11):
            for x in (5, 8, 11, 14):
                painter.drawPoint(x, y)
        painter.drawLine(7, 14, 13, 14)
    elif name == "backspace":
        painter.drawPolygon(QPolygonF([QPointF(2, 10), QPointF(7, 5), QPointF(18, 5),
                                        QPointF(18, 15), QPointF(7, 15)]))
        painter.drawLine(10, 8, 14, 12)
        painter.drawLine(14, 8, 10, 12)
    elif name == "chip":
        painter.drawRoundedRect(QRectF(5, 5, 10, 10), 2, 2)
        painter.drawRoundedRect(QRectF(8, 8, 4, 4), 0.5, 0.5)
        for point in (7, 10, 13):
            painter.drawLine(point, 2, point, 4)
            painter.drawLine(point, 16, point, 18)
            painter.drawLine(2, point, 4, point)
            painter.drawLine(16, point, 18, point)
    elif name == "trash":
        painter.drawLine(4, 5, 16, 5)
        painter.drawLine(8, 3, 12, 3)
        painter.drawPolyline(QPolygonF([QPointF(6, 7), QPointF(7, 17), QPointF(13, 17), QPointF(14, 7)]))
        painter.drawLine(9, 8, 9, 14)
        painter.drawLine(11, 8, 11, 14)
    painter.end()
    return QIcon(pixmap)


def tool_button(name: str, tooltip: str, parent: QWidget | None = None) -> QToolButton:
    button = QToolButton(parent)
    button.setIcon(icon(name))
    button.setIconSize(QSize(19, 19))
    button.setFixedSize(32, 32)
    button.setToolTip(tooltip)
    button.setAccessibleName(tooltip)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


class ElidingLabel(QLabel):
    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.full_text = text
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)
        self.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def setText(self, text: str) -> None:
        self.full_text = text
        self.setToolTip(text)
        self.setAccessibleName(text)
        self._elide()

    def _elide(self) -> None:
        super().setText(self.fontMetrics().elidedText(self.full_text, Qt.TextElideMode.ElideLeft,
                                                   max(0, self.contentsRect().width())))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._elide()


class NumberDisplay(QWidget):
    def __init__(self):
        super().__init__()
        self._text = "0"
        self.error = False
        self.setMinimumHeight(57)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setAccessibleName("Result")

    def set_value(self, text: str, error: bool = False) -> None:
        self._text = text
        self.error = error
        self.setAccessibleDescription(text)
        self.setToolTip(text)
        self.update()

    def text(self) -> str:
        return self._text

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        font = QFont(ui_font_family() if self.error else mono_font_family())
        size = 22 if self.error else 47
        font.setPixelSize(size)
        while QFontMetrics(font).horizontalAdvance(self._text) > self.width() - 2 and size > 12:
            size -= 1
            font.setPixelSize(size)
        painter.setFont(font)
        painter.setPen(QColor("#f5b895" if self.error else TEXT))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self._text)


class TitleBar(QWidget):
    def __init__(self, window: "CalculatorWindow"):
        super().__init__()
        self.owner = window
        self.offset: QPoint | None = None
        self.setObjectName("titlebar")
        self.setFixedHeight(38)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 3, 7, 2)
        layout.setSpacing(3)
        logo = QLabel()
        logo.setPixmap(QIcon(str(ASSET_DIR / "calculator.svg")).pixmap(19, 19))
        layout.addWidget(logo)
        title = QLabel("  Xetallic Calculator")
        title.setObjectName("appTitle")
        layout.addWidget(title)
        layout.addStretch()
        for name, tip, callback in (("minimize", "Minimize", window.showMinimized),
                                    ("maximize", "Maximize / restore", self.toggle_maximized),
                                    ("close", "Close", window.close)):
            button = tool_button(name, tip)
            button.setFixedSize(34, 29)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            if name == "close":
                button.setObjectName("closeButton")
            button.clicked.connect(callback)
            layout.addWidget(button)

    def toggle_maximized(self) -> None:
        self.owner.showNormal() if self.owner.isMaximized() else self.owner.showMaximized()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if not self.owner.windowHandle().startSystemMove():
                self.offset = event.globalPosition().toPoint() - self.owner.pos()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self.offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.owner.move(event.globalPosition().toPoint() - self.offset)

    def mouseReleaseEvent(self, event) -> None:
        self.offset = None

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_maximized()


class BaseRow(QFrame):
    def __init__(self, base: int):
        super().__init__()
        self.setObjectName("modeRow")
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        self.radio = QRadioButton("DEC" if base == 10 else "HEX")
        self.radio.setAccessibleName("Decimal" if base == 10 else "Hexadecimal")
        self.radio.setToolTip("Decimal · Ctrl+D" if base == 10 else "Hexadecimal · Ctrl+H")
        self.radio.setCursor(Qt.CursorShape.PointingHandCursor)
        self.value = ElidingLabel()
        self.value.setObjectName("baseValue")
        self.value.setFont(QFont(mono_font_family()))
        layout.addWidget(self.radio)
        layout.addWidget(self.value, 1)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.radio.setChecked(True)
            self.radio.setFocus(Qt.FocusReason.MouseFocusReason)
        super().mousePressEvent(event)


class CalculatorWindow(QWidget):
    def __init__(self, *, settings: QSettings | None = None):
        super().__init__()
        self.settings = settings if settings is not None else QSettings(
            str(SETTINGS_PATH), QSettings.Format.IniFormat)
        self.engine = Calculator()
        self.error = ""
        self.buttons: dict[str, QPushButton] = {}
        self.setWindowTitle("Programmer Calculator")
        self.setWindowIcon(QIcon(str(ASSET_DIR / "calculator.svg")))
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(494, 786)
        self.setMinimumSize(420, 720)
        self.notice_timer = QTimer(self)
        self.notice_timer.setSingleShot(True)
        self.notice_timer.timeout.connect(self._reset_status)
        self._build()
        self._restore_preferences()
        self._refresh()
        QApplication.instance().installEventFilter(self)

    def _restore_preferences(self) -> None:
        base = str(self.settings.value("base", 10))
        self.engine.set_base(int(base) if base in ("10", "16") else 10)
        auto = str(self.settings.value("autoCalculate", False)).lower() in ("true", "1")
        self.auto_calculate.blockSignals(True)
        self.auto_calculate.setChecked(auto)
        self.auto_calculate.blockSignals(False)

    def _save_preference(self, key: str, value: int | bool) -> None:
        self.settings.setValue(key, value)
        # Flush each change so the last choice survives an unexpected exit, too.
        self.settings.sync()
        if self.settings.status() != QSettings.Status.NoError:
            self._notice("Could not save preferences", warning=True)

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame = QFrame()
        frame.setObjectName("window")
        outer.addWidget(frame)
        root = QVBoxLayout(frame)
        root.setContentsMargins(1, 1, 1, 1)
        root.setSpacing(0)
        root.addWidget(TitleBar(self))
        body = QVBoxLayout()
        body.setContentsMargins(19, 6, 19, 9)
        body.setSpacing(14)
        root.addLayout(body, 1)

        header = QHBoxLayout()
        header.setSpacing(12)
        chip = QLabel()
        chip.setPixmap(icon("chip", ACCENT, 28).pixmap(28, 28))
        chip.setFixedSize(34, 38)
        header.addWidget(chip)
        self.heading = QLabel("Programmer")
        self.heading.setObjectName("heading")
        header.addWidget(self.heading)
        header.addStretch()
        help_button = tool_button("keyboard", "Keyboard shortcuts · F1")
        help_button.clicked.connect(self.show_shortcuts)
        header.addWidget(help_button)
        self.history_button = tool_button("history", "Calculation history")
        self.history_button.setCheckable(True)
        self.history_button.toggled.connect(self._toggle_history)
        header.addWidget(self.history_button)
        body.addLayout(header)

        self.pages = QStackedWidget()
        body.addWidget(self.pages, 1)
        calculator_page = QWidget()
        self.pages.addWidget(calculator_page)
        layout = QVBoxLayout(calculator_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(9)

        self.display_frame = QFrame()
        self.display_frame.setObjectName("display")
        display = QVBoxLayout(self.display_frame)
        display.setContentsMargins(16, 10, 16, 10)
        display.setSpacing(0)
        caption = QHBoxLayout()
        self.base_caption = QLabel("DECIMAL")
        self.base_caption.setObjectName("eyebrow")
        caption.addWidget(self.base_caption)
        caption.addStretch()
        self.auto_calculate = QRadioButton("Auto calculate")
        self.auto_calculate.setObjectName("autoCalculate")
        self.auto_calculate.setAutoExclusive(False)
        self.auto_calculate.setCursor(Qt.CursorShape.PointingHandCursor)
        self.auto_calculate.setToolTip("Update the result as you type. Enter saves the calculation to history.")
        self.auto_calculate.toggled.connect(self._auto_calculate_toggled)
        caption.addWidget(self.auto_calculate)
        caption.addSpacing(8)
        self.copy_button = tool_button("copy", "Copy result · Ctrl+C")
        self.copy_button.setFixedSize(26, 26)
        self.copy_button.clicked.connect(self.copy_result)
        caption.addWidget(self.copy_button)
        display.addLayout(caption)
        self.expression = ElidingLabel()
        self.expression.setObjectName("expression")
        self.expression.setFixedHeight(21)
        display.addWidget(self.expression)
        self.number = NumberDisplay()
        display.addWidget(self.number)
        layout.addWidget(self.display_frame)

        modes = QVBoxLayout()
        modes.setSpacing(5)
        self.base_group = QButtonGroup(self)
        self.base_rows = {}
        for base in (10, 16):
            row = BaseRow(base)
            self.base_rows[base] = row
            self.base_group.addButton(row.radio, base)
            modes.addWidget(row)
        self.base_group.idToggled.connect(self._base_toggled)
        layout.addLayout(modes)

        options = QHBoxLayout()
        options.setSpacing(8)
        word_label = QLabel("WORD SIZE")
        word_label.setObjectName("muted")
        options.addWidget(word_label)
        self.word_size = QComboBox()
        self.word_size.setAccessibleName("Word size")
        arrow_path = (ASSET_DIR / "chevron-down.svg").as_posix()
        self.word_size.setStyleSheet(f'QComboBox::down-arrow {{ image: url("{arrow_path}"); width: 12px; height: 12px; }}')
        for bits, label in ((64, "QWORD · 64 bit"), (32, "DWORD · 32 bit"),
                            (16, "WORD · 16 bit"), (8, "BYTE · 8 bit")):
            self.word_size.addItem(label, bits)
        self.word_size.setToolTip("Signed two’s-complement word size")
        self.word_size.currentIndexChanged.connect(self._word_changed)
        options.addWidget(self.word_size)
        options.addStretch()
        self.bits_toggle = QToolButton()
        self.bits_toggle.setText("Bit view")
        self.bits_toggle.setCheckable(True)
        self.bits_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bits_toggle.setToolTip("Inspect and toggle individual bits")
        self.bits_toggle.toggled.connect(self._toggle_bits)
        options.addWidget(self.bits_toggle)
        layout.addLayout(options)

        self.bits_panel = QFrame()
        self.bits_panel.setObjectName("bits")
        bit_layout = QGridLayout(self.bits_panel)
        bit_layout.setContentsMargins(8, 6, 8, 6)
        bit_layout.setHorizontalSpacing(3)
        bit_layout.setVerticalSpacing(3)
        self.bit_buttons = {}
        for row in range(4):
            label = QLabel(str(63 - row * 16))
            label.setObjectName("muted")
            label.setFixedWidth(20)
            bit_layout.addWidget(label, row, 0)
            for column in range(16):
                bit = 63 - row * 16 - column
                button = QPushButton("0")
                button.setObjectName("bit")
                button.setFixedHeight(19)
                button.setMinimumWidth(0)
                button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.setAccessibleName(f"Bit {bit}")
                button.setToolTip(f"Toggle bit {bit} · 2^{bit}")
                button.clicked.connect(lambda checked=False, bit=bit: self._perform(f"bit:{bit}"))
                bit_layout.addWidget(button, row, column + 1 + column // 4)
                self.bit_buttons[bit] = button
            for spacer_column in (5, 10, 15):
                bit_layout.setColumnMinimumWidth(spacer_column, 5)
        self.bits_panel.hide()
        layout.addWidget(self.bits_panel)

        keypad = QGridLayout()
        keypad.setSpacing(6)
        keys = [
            [(digit, digit, "hex") for digit in "ABCDEF"],
            [("(", "(", "function"), (")", ")", "function"),
             ("CE", "ce", "function"), ("C", "clear", "clear"),
             ("", "backspace", "function"), ("÷", "/", "operator")],
            [("AND", "AND", "function"), ("OR", "OR", "function"),
             ("7", "7", "number"), ("8", "8", "number"), ("9", "9", "number"), ("×", "*", "operator")],
            [("XOR", "XOR", "function"), ("NOT", "NOT", "function"),
             ("4", "4", "number"), ("5", "5", "number"), ("6", "6", "number"), ("−", "-", "operator")],
            [("≪", "<<", "function"), ("≫", ">>", "function"),
             ("1", "1", "number"), ("2", "2", "number"), ("3", "3", "number"), ("+", "+", "operator")],
            [("MOD", "MOD", "function"), ("±", "negate", "function"),
             ("0", "0", "number"), None, ("=", "=", "equals"), None],
        ]
        tips = {"ce": "Clear entry · Delete", "clear": "Clear all · Esc", "backspace": "Backspace",
                "negate": "Change sign · F9", "=": "Equals · Enter", "MOD": "Remainder · %",
                "AND": "Bitwise AND · &", "OR": "Bitwise OR · |", "XOR": "Bitwise XOR · ^",
                "NOT": "Bitwise NOT · ~", "<<": "Left shift · <", ">>": "Arithmetic right shift · >"}
        for row, items in enumerate(keys):
            keypad.setRowStretch(row, 3 if row else 2)
            for column, item in enumerate(items):
                if item is None:
                    continue
                label, action, kind = item
                button = QPushButton(label)
                button.setProperty("kind", kind)
                button.setObjectName(f"key_{action}")
                button.setAccessibleName(tips.get(action, label))
                button.setToolTip(tips.get(action, f"Hexadecimal {label}" if kind == "hex" else label))
                button.setMinimumSize(36, 36 if row == 0 else 45)
                button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                if action == "backspace":
                    button.setIcon(icon("backspace", "#b6bec8"))
                button.clicked.connect(lambda checked=False, action=action: self._perform(action))
                self.buttons[action] = button
                keypad.addWidget(button, row, column, 1, 2 if row == 5 and column in (2, 4) else 1)
        for column in range(6):
            keypad.setColumnStretch(column, 1)
        layout.addLayout(keypad, 1)

        self.history_page = QWidget()
        history_layout = QVBoxLayout(self.history_page)
        history_layout.setContentsMargins(0, 4, 0, 0)
        history_layout.setSpacing(12)
        history_heading = QHBoxLayout()
        label = QLabel("RECENT CALCULATIONS")
        label.setObjectName("eyebrow")
        history_heading.addWidget(label)
        history_heading.addStretch()
        self.clear_history_button = tool_button("trash", "Clear history")
        self.clear_history_button.clicked.connect(self._clear_history)
        history_heading.addWidget(self.clear_history_button)
        history_layout.addLayout(history_heading)
        self.history_scroll = QScrollArea()
        self.history_scroll.setWidgetResizable(True)
        self.history_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        history_layout.addWidget(self.history_scroll, 1)
        self.pages.addWidget(self.history_page)

        footer = QHBoxLayout()
        footer.setSpacing(6)
        self.activity_dot = QLabel("●")
        self.activity_dot.setFixedWidth(10)
        self.activity_dot.setStyleSheet(f"color: {ACCENT}; font-size: 9px;")
        footer.addWidget(self.activity_dot)
        self.status = QLabel("Keyboard ready")
        self.status.setObjectName("status")
        footer.addWidget(self.status, 1)
        self.word_status = QLabel("SIGNED · 64 BIT")
        self.word_status.setObjectName("muted")
        self.word_status.setStyleSheet("font-size: 10px; letter-spacing: 0.5px;")
        footer.addWidget(self.word_status)
        grip = QSizeGrip(self)
        grip.setFixedSize(13, 13)
        grip.setToolTip("Resize")
        footer.addWidget(grip)
        body.addLayout(footer)

    def _refresh(self) -> None:
        auto = self.auto_calculate.isChecked()
        self.display_value = self.engine.value
        self.display_error = self.error
        if auto and not self.error:
            try:
                self.display_value = self.engine.preview()
            except CalculatorError as error:
                # A temporary live error must not reset the expression on the
                # next digit, e.g. while changing the divisor from 0 to 02.
                self.display_error = str(error)
        result = format_number(self.display_value, self.engine.base, self.engine.bits, grouped=True)
        self.number.set_value(self.display_error or result, bool(self.display_error))
        self.display_frame.setProperty("error", bool(self.display_error))
        refresh_style(self.display_frame)
        self.expression.setText(self.engine.live_expression_text if auto else self.engine.expression_text)
        self.base_caption.setText("HEXADECIMAL" if self.engine.base == 16 else "DECIMAL")
        self.copy_button.setEnabled(not self.display_error)
        self.word_status.setText(f"SIGNED · {self.engine.bits} BIT")
        self.base_group.blockSignals(True)
        for base, row in self.base_rows.items():
            selected = self.engine.base == base
            row.radio.blockSignals(True)
            row.radio.setChecked(selected)
            row.radio.blockSignals(False)
            row.setProperty("selected", selected)
            row.value.setText("—" if self.display_error else
                              format_number(self.display_value, base, self.engine.bits, grouped=True))
            refresh_style(row)
            refresh_style(row.value)
        self.base_group.blockSignals(False)
        self.word_size.blockSignals(True)
        self.word_size.setCurrentIndex(self.word_size.findData(self.engine.bits))
        self.word_size.blockSignals(False)
        for digit in "ABCDEF":
            self.buttons[digit].setEnabled(self.engine.base == 16)
        for bit, button in self.bit_buttons.items():
            on = bool((self.display_value & self.engine.mask) & (1 << bit))
            button.setText("1" if on and bit < self.engine.bits else "0")
            button.setEnabled(bit < self.engine.bits and not self.display_error)
            button.setProperty("on", on and bit < self.engine.bits)
            button.setAccessibleDescription("1" if on else "0")
            refresh_style(button)

    def _perform(self, action: str) -> None:
        self.history_button.setChecked(False)
        if self.error:
            if len(action) == 1 and action in "0123456789ABCDEF":
                self.engine.clear()
                self.error = ""
            elif action in ("clear", "ce", "backspace"):
                self.error = ""
            else:
                return
        try:
            if len(action) == 1 and action in "0123456789ABCDEF":
                self.engine.input_digit(action)
            elif action in OPERATORS:
                self.engine.operator(action)
            elif action == "(":
                self.engine.open_parenthesis()
            elif action == ")":
                self.engine.close_parenthesis()
            elif action == "=":
                self.engine.calculate(auto=self.auto_calculate.isChecked())
            elif action == "clear":
                self.engine.clear()
            elif action == "ce":
                self.engine.clear_entry()
            elif action == "backspace":
                self.engine.backspace()
            elif action == "negate":
                self.engine.negate()
            elif action == "NOT":
                self.engine.bitwise_not()
            elif action.startswith("bit:"):
                if self.auto_calculate.isChecked():
                    # Bit editing starts from the live result shown in the grid.
                    value = self.engine.preview()
                    self.engine.clear()
                    self.engine.paste(format_number(value, self.engine.base, self.engine.bits))
                self.engine.toggle_bit(int(action[4:]))
        except CalculatorError as error:
            if action == "=":
                self.error = str(error)
            self._notice(str(error), warning=True)
        self._refresh()

    def _base_toggled(self, base: int, checked: bool) -> None:
        if checked:
            self.engine.set_base(base)
            self._save_preference("base", base)
            self._refresh()

    def _auto_calculate_toggled(self, checked: bool) -> None:
        self._save_preference("autoCalculate", checked)
        self._refresh()

    def _word_changed(self, index: int) -> None:
        old_value = self.engine.value
        self.engine.set_bits(self.word_size.itemData(index))
        self.error = ""
        self._refresh()
        if old_value != self.engine.value:
            self._notice(f"Value wrapped to {self.engine.bits} bits")

    def _toggle_bits(self, checked: bool) -> None:
        self.bits_panel.setVisible(checked)
        self.bits_toggle.setText("Hide bits" if checked else "Bit view")
        if not self.isMaximized():
            self.resize(self.width(), self.height() + (105 if checked else -105))

    def _toggle_history(self, checked: bool) -> None:
        if checked:
            self._render_history()
        self.pages.setCurrentIndex(1 if checked else 0)
        self.heading.setText("History" if checked else "Programmer")

    def _render_history(self) -> None:
        contents = QWidget()
        contents.setObjectName("historyContents")
        layout = QVBoxLayout(contents)
        layout.setContentsMargins(0, 0, 6, 0)
        layout.setSpacing(9)
        self.clear_history_button.setEnabled(bool(self.engine.history))
        if not self.engine.history:
            empty = QLabel("Your calculations, at a glance.\n\nResults will appear here as you calculate.")
            empty.setObjectName("muted")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setWordWrap(True)
            layout.addStretch()
            layout.addWidget(empty)
        for item in self.engine.history:
            card = QFrame()
            card.setObjectName("historyCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 10, 14, 10)
            card_layout.setSpacing(4)
            caption = QLabel(f"{'HEX' if item.base == 16 else 'DEC'}  ·  {item.bits} BIT")
            caption.setObjectName("eyebrow")
            card_layout.addWidget(caption)
            expression = ElidingLabel()
            expression.setObjectName("muted")
            expression.setText(item.expression)
            card_layout.addWidget(expression)
            result = QPushButton(format_number(item.result, item.base, item.bits, grouped=True))
            result.setObjectName("historyResult")
            result.setCursor(Qt.CursorShape.PointingHandCursor)
            result.setToolTip("Use this result")
            result.clicked.connect(lambda checked=False, item=item: self._restore_history(item))
            card_layout.addWidget(result)
            layout.addWidget(card)
        layout.addStretch()
        self.history_scroll.setWidget(contents)

    def _restore_history(self, item: HistoryEntry) -> None:
        self.engine.restore(item)
        self._save_preference("base", self.engine.base)
        self.error = ""
        self.history_button.setChecked(False)
        self._refresh()
        self._notice("Result restored")

    def _clear_history(self) -> None:
        self.engine.history.clear()
        self._render_history()

    def copy_result(self) -> None:
        if not self.display_error:
            QApplication.clipboard().setText(format_number(self.display_value, self.engine.base, self.engine.bits))
            self._notice("Result copied")

    def paste_value(self) -> None:
        try:
            self.engine.paste(QApplication.clipboard().text())
        except CalculatorError as error:
            self._notice(str(error), warning=True)
        else:
            self.error = ""
            self.history_button.setChecked(False)
            self._refresh()
            self._notice("Value pasted")

    def _notice(self, text: str, warning: bool = False) -> None:
        self.status.setText(text)
        self.status.setProperty("notice", not warning)
        self.status.setProperty("warning", warning)
        refresh_style(self.status)
        self.notice_timer.start(3200)

    def _reset_status(self) -> None:
        active = self.isActiveWindow()
        self.status.setText("Keyboard ready" if active else "Focus to use keyboard")
        self.status.setProperty("notice", False)
        self.status.setProperty("warning", False)
        refresh_style(self.status)
        self.activity_dot.setStyleSheet(f"color: {ACCENT if active else '#626a75'}; font-size: 9px;")

    def _flash(self, action: str) -> None:
        button = self.buttons.get(action)
        if button and button.isEnabled():
            button.setProperty("pressed", True)
            refresh_style(button)
            if not hasattr(button, 'flash_timer'):
                button.flash_timer = QTimer(button)
                button.flash_timer.setSingleShot(True)
                button.flash_timer.timeout.connect(lambda: self._release_flash(button))
            button.flash_timer.start(110)

    @staticmethod
    def _release_flash(button: QPushButton) -> None:
        button.setProperty("pressed", False)
        refresh_style(button)

    def eventFilter(self, watched, event) -> bool:
        if event.type() != QEvent.Type.KeyPress or not self.isActiveWindow():
            return super().eventFilter(watched, event)
        if not isinstance(watched, QWidget) or watched.window() is not self:
            return super().eventFilter(watched, event)
        key = event.key()
        modifiers = event.modifiers()
        control = bool(modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier))
        if control:
            callbacks = {Qt.Key.Key_C: self.copy_result, Qt.Key.Key_V: self.paste_value,
                         Qt.Key.Key_D: lambda: self.base_rows[10].radio.setChecked(True),
                         Qt.Key.Key_H: lambda: self.base_rows[16].radio.setChecked(True)}
            if key in callbacks:
                callbacks[key]()
                return True
            return False
        if modifiers & Qt.KeyboardModifier.AltModifier:
            return False
        if key == Qt.Key.Key_F1:
            self.show_shortcuts()
            return True
        keypad = bool(modifiers & Qt.KeyboardModifier.KeypadModifier)
        if isinstance(watched, QComboBox) and not keypad and key in (
                Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Space,
                Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Home, Qt.Key.Key_End):
            return False
        action = None
        if keypad:
            action = {Qt.Key.Key_Insert: "0", Qt.Key.Key_End: "1", Qt.Key.Key_Down: "2",
                      Qt.Key.Key_PageDown: "3", Qt.Key.Key_Left: "4", Qt.Key.Key_Clear: "5",
                      Qt.Key.Key_Right: "6", Qt.Key.Key_Home: "7", Qt.Key.Key_Up: "8",
                      Qt.Key.Key_PageUp: "9"}.get(key)
            # The keypad decimal separator has no meaning for integer arithmetic.
            if key in (Qt.Key.Key_Delete, Qt.Key.Key_Period, Qt.Key.Key_Comma):
                return True
        if action is None:
            action = {Qt.Key.Key_Return: "=", Qt.Key.Key_Enter: "=", Qt.Key.Key_Equal: "=",
                      Qt.Key.Key_Backspace: "backspace", Qt.Key.Key_Escape: "clear",
                      Qt.Key.Key_Delete: "ce", Qt.Key.Key_F9: "negate"}.get(key)
        if action is None:
            text = event.text().upper()
            if len(text) == 1 and text in "0123456789ABCDEF":
                if text in "ABCDEF" and self.engine.base != 16:
                    return True
                action = text
            elif text in ("+", "-", "*", "/", "(", ")"):
                action = text
            else:
                action = {"%": "MOD", "&": "AND", "|": "OR", "^": "XOR",
                          "~": "NOT", "<": "<<", ">": ">>"}.get(text)
        if action is not None:
            self._perform(action)
            self._flash(action)
            return True
        return super().eventFilter(watched, event)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.ActivationChange and hasattr(self, "status"):
            self._reset_status()

    def closeEvent(self, event) -> None:
        QApplication.instance().removeEventFilter(self)
        super().closeEvent(event)

    def show_shortcuts(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Keyboard shortcuts")
        dialog.setMinimumWidth(370)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(16)
        title = QLabel("At your fingertips.")
        title.setObjectName("heading")
        layout.addWidget(title)
        intro = QLabel("Shortcuts work while the calculator is focused.")
        intro.setObjectName("muted")
        layout.addWidget(intro)
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(8)
        rows = [("0–9 / Numpad", "Enter digits"), ("A–F", "HEX digits"),
                ("+  −  *  /  %", "Arithmetic / remainder"), ("Enter / =", "Calculate"),
                ("Ctrl+D / Ctrl+H", "DEC / HEX"), ("Backspace", "Remove last digit"),
                ("Delete / Esc", "Clear entry / clear all"), ("F9", "Change sign"),
                ("&  |  ^  ~", "AND / OR / XOR / NOT"), ("<  >", "Left / arithmetic right shift"),
                ("(  )", "Group an expression"), ("Ctrl+C / Ctrl+V", "Copy / paste an integer")]
        for row, (keys, description) in enumerate(rows):
            keycap = QLabel(keys)
            keycap.setObjectName("keycap")
            grid.addWidget(keycap, row, 0)
            grid.addWidget(QLabel(description), row, 1)
        layout.addLayout(grid)
        close = QPushButton("Got it")
        close.setProperty("kind", "equals")
        close.setStyleSheet("font-size: 14px; padding: 9px;")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()
