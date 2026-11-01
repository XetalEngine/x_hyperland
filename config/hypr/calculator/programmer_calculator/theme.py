"""Shared colors and the application's dark widget theme."""

BACKGROUND = "#17191d"
SURFACE = "#202328"
TEXT = "#edf0f4"
MUTED = "#90969f"
ACCENT = "#8de4c5"

STYLESHEET = """
QWidget {
    color: #edf0f4;
    font-size: 13px;
    selection-background-color: #8de4c5;
    selection-color: #15251f;
}
QFrame#window {
    background: #17191d;
    border: 1px solid #373b42;
    border-radius: 14px;
}
QWidget#titlebar { background: transparent; }
QLabel { background: transparent; border: none; }
QLabel#appTitle { color: #a7adb6; font-size: 12px; }
QLabel#heading { font-size: 25px; font-weight: 600; letter-spacing: -0.6px; }
QLabel#eyebrow { color: #8de4c5; font-size: 10px; font-weight: 600; letter-spacing: 1.5px; }
QLabel#muted, QLabel#expression { color: #90969f; font-size: 12px; }
QLabel#expression { font-size: 13px; }
QLabel#status { color: #90969f; font-size: 11px; }
QLabel#status[notice="true"] { color: #8de4c5; }
QLabel#status[warning="true"] { color: #f5b895; }
QFrame#display {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 #20262a, stop:1 #1c2025);
    border: 1px solid #2b3338;
    border-radius: 12px;
}
QFrame#display[error="true"] { border-color: #916552; }
QFrame#modeRow { background: #1d2025; border: 1px solid #292d33; border-radius: 8px; }
QFrame#modeRow[selected="true"] { background: #22322e; border-color: #3c5b4f; }
QRadioButton { background: transparent; border: none; font-size: 11px; font-weight: 600; spacing: 9px; }
QRadioButton::indicator { width: 10px; height: 10px; border: 1px solid #65706e; border-radius: 6px; background: transparent; }
QRadioButton::indicator:checked { background: #8de4c5; border: 2px solid #355448; }
QRadioButton:checked { color: #a4edcf; }
QRadioButton:focus { color: #b4ffe0; }
QLabel#baseValue { font-size: 13px; color: #bec6cb; }
QFrame#modeRow[selected="true"] QLabel#baseValue { color: #b6ecd6; }
QPushButton {
    background: #30343b;
    border: 1px solid #3b4048;
    border-bottom: 2px solid #22252a;
    border-radius: 8px;
    padding: 2px;
    font-size: 21px;
    font-weight: 500;
}
QPushButton:hover { background: #3c414a; border-color: #4c535e; }
QPushButton:pressed, QPushButton[pressed="true"] {
    background: #464e55; border-bottom: 1px solid #4e625a; color: #baffdf;
}
QPushButton:focus { border: 1px solid #8de4c5; }
QPushButton[kind="function"] { background: #24282e; border-color: #2e333a; font-size: 12px; color: #afb7c3; }
QPushButton[kind="function"]:hover { background: #30363e; color: #e2ebe8; border-color: #454e55; }
QPushButton[kind="operator"] { background: #272e32; border-color: #354148; color: #b7d2ca; font-size: 22px; }
QPushButton[kind="operator"]:hover { background: #36433f; border-color: #56756a; }
QPushButton[kind="hex"] { background: #252e2d; border-color: #35443f; color: #a3d9c7; font-size: 14px; }
QPushButton[kind="hex"]:hover { background: #344b43; border-color: #668b7c; }
QPushButton[kind="hex"]:disabled { background: #1e2126; border-color: #262a30; color: #545b66; }
QPushButton[kind="clear"] { background: #2c2829; border-color: #3c3232; color: #efb5a4; font-size: 13px; }
QPushButton[kind="clear"]:hover { background: #443335; border-color: #6a4848; }
QPushButton[kind="equals"] { background: #8de4c5; border: 1px solid #a9f3d7; border-bottom: 2px solid #589d82; color: #163b2e; font-size: 25px; }
QPushButton[kind="equals"]:hover { background: #a4eed3; }
QPushButton[kind="equals"]:pressed, QPushButton[kind="equals"][pressed="true"] { background: #70c9a9; }
QPushButton[pressed="true"] { background: #414e49; border-color: #8de4c5; }
QToolButton { background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 5px; color: #909aa5; font-size: 11px; }
QToolButton:hover { background: #2d3239; color: #edf0f4; }
QToolButton:checked { background: #283e35; border-color: #3c5b4f; color: #a4edcf; }
QToolButton:focus { border-color: #8de4c5; }
QToolButton#closeButton:hover { background: #a63e48; }
QComboBox { background: #24292f; color: #b9c4cd; border: 1px solid #363d45; border-radius: 6px; padding: 5px 10px; font-size: 11px; }
QComboBox:hover { border-color: #5c756b; }
QComboBox:focus { border-color: #8de4c5; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: #252b31; color: #d9e1e8; selection-background-color: #345346; selection-color: #c2f3de; outline: none; padding: 5px; border: 1px solid #48534f; }
QFrame#bits { background: #1c2024; border: 1px solid #30383d; border-radius: 8px; }
QPushButton#bit { border: none; border-radius: 3px; background: transparent; color: #68737c; font-size: 11px; padding: 0; }
QPushButton#bit:hover { background: #32483f; color: #b9f6dc; }
QPushButton#bit[on="true"] { color: #a4edcf; background: #2b4439; }
QPushButton#bit:disabled { color: #32383f; background: transparent; }
QPushButton#bit:focus { border: 1px solid #8de4c5; }
QScrollArea { background: transparent; border: none; }
QWidget#historyContents { background: transparent; }
QFrame#historyCard { background: #22272d; border: 1px solid #343d44; border-radius: 10px; }
QPushButton#historyResult { text-align: right; background: transparent; border: none; font-size: 23px; padding: 6px 0; color: #a4edcf; }
QPushButton#historyResult:hover { color: #defff0; }
QScrollBar:vertical { border: none; background: transparent; width: 5px; margin: 0; }
QScrollBar::handle:vertical { background: #46514c; min-height: 24px; border-radius: 2px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QDialog { background: #1e2227; }
QLabel#keycap { border: 1px solid #444d55; background: #2a3138; border-radius: 5px; color: #b3e7d2; font-size: 12px; padding: 5px 9px; }
QToolTip { background: #29332f; color: #d8f7e9; border: 1px solid #4d675b; border-radius: 4px; padding: 6px; }
"""
