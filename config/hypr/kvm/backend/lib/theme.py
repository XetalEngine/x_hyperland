"""Theme engine, ported from the CachyOsTools (xetal) Qt app.

Same three-colour model as thememanager.h over there: accent, background and
text, where an empty background or text means "inherit whatever the system
theme gives us". Presets and the stylesheet are kept deliberately close to the
original so the two applications read as one product -- if the look changes in
one, the diff to make here is obvious.

The choice lives in theme.json next to the program rather than in QSettings.
vmstart_2 already keeps its state that way (last-session.json, presets/), and
the point of this program is that copying the directory copies everything.
"""

import os
import json

from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                             QComboBox, QPushButton, QDialog, QColorDialog,
                             QGridLayout, QDialogButtonBox)
from PyQt6.QtGui import QColor, QPalette

from portable import data_root
APP_DIR = str(data_root())
THEME_FILE = os.path.join(APP_DIR, "theme.json")

DEFAULT_ACCENT = "#27ae60"

# name, accent, background, text.  Empty background = keep the system palette,
# which is the look this program had before any of this existed.
THEME_PRESETS = [
    ("System Default (XETAL Green)", DEFAULT_ACCENT, "",        ""),
    ("XETAL Dark",                   DEFAULT_ACCENT, "#1d1f24", ""),
    ("XETAL Red",                    "#c0392b",      "#201a1a", ""),
    ("Midnight Blue",                "#3498db",      "#0f1626", ""),
    ("Matrix",                       "#00cc44",      "#0a0f0a", "#9dffb0"),
    ("Solar Light",                  "#e67e22",      "#f5f1e8", ""),
    ("Purple Haze",                  "#9b59b6",      "#191221", ""),
    ("Custom",                       "",             "",        ""),
]
CUSTOM_INDEX = len(THEME_PRESETS) - 1


# ----------------------------------------------------------------- state ---
def load(path=None):
    """Return (accent, background, text, preset_index), falling back to preset 0."""
    try:
        with open(path or THEME_FILE) as fh:
            d = json.load(fh)
        return (d.get("accent") or DEFAULT_ACCENT, d.get("background", ""),
                d.get("text", ""), int(d.get("preset", 0)))
    except Exception:
        # A missing or unreadable theme.json is not worth a dialog: the program
        # is perfectly usable with the default look.
        return DEFAULT_ACCENT, "", "", 0


def save(accent, background, text, preset, path=None):
    try:
        with open(path or THEME_FILE, "w") as fh:
            json.dump({"accent": accent, "background": background,
                       "text": text, "preset": preset}, fh, indent=2)
    except OSError:
        pass


# ------------------------------------------------------------ stylesheet ---
def _rgba(c, alpha):
    return "rgba(%d,%d,%d,%s)" % (c.red(), c.green(), c.blue(), alpha)


def _contrast(c):
    """Black or white, whichever stays readable on top of c."""
    return "#ffffff" if c.lightness() < 140 else "#101010"


def build_stylesheet(accent=DEFAULT_ACCENT, background="", text=""):
    a = QColor(accent if accent else DEFAULT_ACCENT)
    if not a.isValid():
        a = QColor(DEFAULT_ACCENT)
    hexa = a.name()

    style = f"""
/* --- cards ---------------------------------------------------------- */
QGroupBox {{
    background: rgba(127,127,127,0.04);
    border: 1px solid rgba(127,127,127,0.25);
    border-radius: 8px;
    margin-top: 16px;
    padding: 14px 10px 10px 10px;
    font-weight: bold;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; }}
/* Only the card title is bold; everything inside goes back to normal, or a
   dense tab like Disks turns into a wall of bold. */
QGroupBox QLabel, QGroupBox QPushButton, QGroupBox QCheckBox,
QGroupBox QRadioButton, QGroupBox QComboBox, QGroupBox QSpinBox,
QGroupBox QLineEdit, QGroupBox QPlainTextEdit, QGroupBox QTextEdit {{
    font-weight: normal;
}}

/* --- buttons --------------------------------------------------------- */
QPushButton {{
    border: 1px solid rgba(127,127,127,0.3);
    border-radius: 6px;
    padding: 6px 10px;
    background: rgba(127,127,127,0.08);
}}
QPushButton:hover  {{ background: {_rgba(a, 0.25)}; border-color: {hexa}; }}
QPushButton:pressed {{ background: {_rgba(a, 0.40)}; }}
QPushButton:focus {{ border-color: {hexa}; }}
QPushButton[profileSelector="true"] {{ padding: 6px 12px; min-height: 20px; }}
QPushButton[profileSelector="true"]:checked {{
    border-color: {hexa}; background: {_rgba(a, 0.22)}; font-weight: bold;
}}
QPushButton:disabled {{
    color: rgba(127,127,127,0.6);
    background: rgba(127,127,127,0.05);
}}

/* The handful of buttons that used to be hardcoded green. Setting an object
   name instead of an inline stylesheet is what lets them follow the accent. */
QPushButton#accent {{
    background: {hexa};
    color: {_contrast(a)};
    border: 1px solid {hexa};
    font-weight: bold;
}}
QPushButton#accent:enabled:hover   {{ background: {a.lighter(115).name()}; }}
QPushButton#accent:enabled:pressed {{ background: {a.darker(115).name()}; }}
QPushButton#accentBig {{
    background: {hexa};
    color: {_contrast(a)};
    border: 1px solid {hexa};
    font-weight: bold;
    font-size: 14px;
}}
QPushButton#accentBig:enabled:hover   {{ background: {a.lighter(115).name()}; }}
QPushButton#accentBig:enabled:pressed {{ background: {a.darker(115).name()}; }}
/* Object-name selectors override the generic disabled rule above. */
QPushButton#accent:disabled, QPushButton#accentBig:disabled {{
    color: rgba(127,127,127,0.6);
    background: rgba(127,127,127,0.05);
    border-color: rgba(127,127,127,0.3);
}}

/* --- main tab bar ----------------------------------------------------- */
QTabWidget::pane {{
    border: 1px solid rgba(127,127,127,0.25);
    border-radius: 6px;
    top: -1px;
}}
QTabBar::tab {{
    background: rgba(127,127,127,0.08);
    border: 1px solid rgba(127,127,127,0.2);
    padding: 6px 14px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background: {_rgba(a, 0.18)};
    border-top: 2px solid {hexa};
    font-weight: bold;
}}
QTabBar::tab:hover:!selected {{ background: rgba(127,127,127,0.18); }}
QTabWidget#editorPages::pane {{ border: none; }}

/* --- navigation and page hierarchy ----------------------------------- */
QWidget#navigationPanel {{
    background: rgba(127,127,127,0.05);
    border: 1px solid rgba(127,127,127,0.15);
    border-radius: 8px;
}}
QListWidget#pageNavigation {{ border: none; background: transparent; outline: none; }}
QListWidget#pageNavigation::item {{ border-radius: 6px; padding-left: 10px; }}
QListWidget#pageNavigation::item:selected {{
    background: {_rgba(a, 0.20)};
    color: palette(text);
    border-left: 3px solid {hexa};
    font-weight: bold;
}}
QListWidget#pageNavigation::item:hover:enabled {{ background: {_rgba(a, 0.12)}; }}
QListWidget#pageNavigation::item:disabled {{ color: #888888; background: transparent; }}
QLabel#appTitle {{ font-size: 20px; font-weight: bold; }}
QLabel#pageTitle {{ font-size: 24px; font-weight: bold; }}
QLabel#eyebrow {{ color: {hexa}; font-size: 10px; font-weight: bold; }}
QLabel#muted {{ color: palette(placeholder-text); }}
QLabel#wizardStepTitle {{ font-size: 20px; font-weight: bold; }}
QMenu {{ padding: 6px; }}
QMenu::item {{ padding: 8px 20px; border-radius: 4px; }}

/* --- tables, trees, lists --------------------------------------------- */
QTableWidget, QTreeWidget, QListWidget {{
    border: 1px solid rgba(127,127,127,0.25);
    border-radius: 8px;
    gridline-color: rgba(127,127,127,0.12);
    alternate-background-color: rgba(127,127,127,0.06);
    selection-background-color: {_rgba(a, 0.40)};
    selection-color: palette(text);
}}
QHeaderView::section {{
    background: rgba(127,127,127,0.12);
    border: none;
    border-bottom: 1px solid rgba(127,127,127,0.25);
    padding: 5px;
    font-weight: bold;
}}

/* --- inputs ------------------------------------------------------------ */
QLineEdit, QComboBox, QSpinBox, QTextEdit, QPlainTextEdit {{
    border: 1px solid rgba(127,127,127,0.3);
    border-radius: 6px;
    padding: 3px 6px;
    background: rgba(127,127,127,0.06);
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus,
QTextEdit:focus, QPlainTextEdit:focus {{
    border: 1px solid {hexa};
}}
/* ::drop-down and ::down-arrow are deliberately NOT styled. Touching either
   makes Qt stop drawing the native arrow and expect an image instead, and a
   combo box with no arrow is indistinguishable from a line edit -- on the
   Disks tab that is forty controls that stop looking clickable. */
QComboBox QAbstractItemView {{
    border: 1px solid {hexa};
    selection-background-color: {_rgba(a, 0.40)};
}}

/* --- checkboxes -------------------------------------------------------- */
QCheckBox::indicator, QRadioButton::indicator {{
    width: 14px; height: 14px;
    border: 1px solid rgba(127,127,127,0.5);
    border-radius: 3px;
    background: rgba(127,127,127,0.10);
}}
QRadioButton::indicator {{ border-radius: 7px; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {hexa};
    border: 1px solid {hexa};
}}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border: 1px solid {hexa};
}}

/* --- progress bars ----------------------------------------------------- */
QProgressBar {{
    border: 1px solid rgba(127,127,127,0.3);
    border-radius: 6px;
    text-align: center;
    background: rgba(127,127,127,0.08);
}}
QProgressBar::chunk {{ background: {hexa}; border-radius: 5px; }}

/* --- splitters and scrollbars ------------------------------------------ */
QSplitter::handle {{ background: rgba(127,127,127,0.2); }}
QSplitter::handle:hover {{ background: {hexa}; }}
QScrollBar:vertical, QScrollBar:horizontal {{
    background: transparent;
    width: 12px; height: 12px;
    margin: 0;
}}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: rgba(127,127,127,0.35);
    border-radius: 6px;
    min-height: 24px; min-width: 24px;
}}
QScrollBar::handle:hover {{ background: {_rgba(a, 0.65)}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

/* The scroll areas on CPU Features and Pinning are containers, not surfaces;
   giving them a frame draws a box around a box. */
QScrollArea {{ border: none; }}
QToolTip {{
    border: 1px solid {hexa};
    border-radius: 4px;
    padding: 4px;
}}
"""

    # Optional full background/text override, for the presets past the first.
    if background:
        bg = QColor(background)
        if bg.isValid():
            dark = bg.lightness() < 128
            base = bg.lighter(135) if dark else bg.darker(104)   # inputs/views
            fg = QColor(text) if text else QColor("#e6e6e6" if dark else "#1c1c1c")
            style += f"""
QMainWindow, QDialog {{ background: {bg.name()}; }}
QWidget {{ color: {fg.name()}; }}
QTabWidget::pane {{ background: {bg.name()}; }}
QMenuBar {{ background: {bg.name()}; color: {fg.name()}; }}
QMenuBar::item:selected {{ background: {_rgba(a, 0.35)}; }}
QMenu {{
    background: {base.name()};
    color: {fg.name()};
    border: 1px solid rgba(127,127,127,0.3);
}}
QMenu::item:selected {{ background: {_rgba(a, 0.35)}; }}
QTableWidget, QTreeWidget, QListWidget, QTextEdit, QPlainTextEdit,
QLineEdit, QComboBox, QSpinBox {{
    background: {base.name()};
    color: {fg.name()};
}}
QHeaderView::section {{ color: {fg.name()}; }}
QStatusBar {{ background: {bg.name()}; color: {fg.name()}; }}
QGroupBox {{ color: {fg.name()}; }}
"""
    return style


def apply_to(app, accent=DEFAULT_ACCENT, background="", text=""):
    """Paint the whole application. Safe to call again at any time."""
    # Scroll viewports use the palette even when the enclosing window has a
    # stylesheet. Set both so dark presets never leave white page surfaces.
    if not hasattr(app, "_vmstart2_system_palette"):
        app._vmstart2_system_palette = QPalette(app.palette())
    palette = QPalette(app._vmstart2_system_palette)
    if background and QColor(background).isValid():
        bg = QColor(background)
        dark = bg.lightness() < 128
        fg = QColor(text or ("#e6e6e6" if dark else "#1c1c1c"))
        base = bg.lighter(135) if dark else bg.darker(104)
        for role, color in (
                (QPalette.ColorRole.Window, bg),
                (QPalette.ColorRole.Base, base),
                (QPalette.ColorRole.AlternateBase, bg),
                (QPalette.ColorRole.Button, base),
                (QPalette.ColorRole.WindowText, fg),
                (QPalette.ColorRole.Text, fg),
                (QPalette.ColorRole.ButtonText, fg),
                (QPalette.ColorRole.ToolTipBase, base),
                (QPalette.ColorRole.ToolTipText, fg),
                (QPalette.ColorRole.PlaceholderText, QColor("#a4a8b2" if dark else "#60646c"))):
            palette.setColor(role, color)
        for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text,
                     QPalette.ColorRole.ButtonText):
            palette.setColor(QPalette.ColorGroup.Disabled, role,
                             QColor("#777b84" if dark else "#858585"))
    a = QColor(accent or DEFAULT_ACCENT)
    if not a.isValid():
        a = QColor(DEFAULT_ACCENT)
    palette.setColor(QPalette.ColorRole.Highlight, a)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(_contrast(a)))
    app.setPalette(palette)
    app.setStyleSheet(build_stylesheet(accent, background, text))


# --------------------------------------------------------------- picker ---
def _swatch(button, color, empty_label):
    if not color:
        button.setText(empty_label)
        button.setStyleSheet("")
        return
    c = QColor(color)
    button.setText(color)
    button.setStyleSheet(
        "background: %s; color: %s; border: 1px solid rgba(127,127,127,0.5);"
        "border-radius: 6px; padding: 5px 10px; font-weight: bold;"
        % (color, "white" if c.lightness() < 128 else "black"))


class ThemeDialog(QDialog):
    """Accent / background / text pickers, applied live as they are chosen.

    Live preview matters here: a theme is judged by looking at it, and an OK
    button that only applies on close means picking a colour is guesswork.
    Cancel puts back whatever was in force on the way in.
    """

    def __init__(self, parent, accent, background, text, on_change):
        super().__init__(parent)
        self.setWindowTitle("Appearance")
        self.accent, self.background, self.text = accent, background, text
        self._on_change = on_change
        self._original = (accent, background, text)

        lay = QVBoxLayout(self)
        grid = QGridLayout()
        rows = (("Accent", "accent", DEFAULT_ACCENT, "Pick..."),
                ("Background", "background", "#1d1f24", "System (default)"),
                ("Text", "text", "#e6e6e6", "Auto"))
        self._buttons = {}
        for r, (label, attr, fallback, empty) in enumerate(rows):
            grid.addWidget(QLabel(label + ":"), r, 0)
            b = QPushButton()
            b.clicked.connect(lambda _, a=attr, f=fallback, t=label: self._pick(a, f, t))
            grid.addWidget(b, r, 1)
            self._buttons[attr] = (b, empty)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)

        note = QLabel("Leaving Background on “System (default)” keeps the "
                      "desktop’s own palette and only recolours the accents.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #888;")
        lay.addWidget(note)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel
                              | QDialogButtonBox.StandardButton.Reset)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self._cancel)
        bb.button(QDialogButtonBox.StandardButton.Reset).clicked.connect(self._reset)
        lay.addWidget(bb)
        self._refresh()

    def _refresh(self):
        for attr, (button, empty) in self._buttons.items():
            _swatch(button, getattr(self, attr), empty)

    def _pick(self, attr, fallback, title):
        current = getattr(self, attr)
        picked = QColorDialog.getColor(QColor(current or fallback), self,
                                       "Pick %s Colour" % title)
        if not picked.isValid():
            return
        setattr(self, attr, picked.name())
        self._refresh()
        self._on_change(self.accent, self.background, self.text)

    def _reset(self):
        self.accent, self.background, self.text = DEFAULT_ACCENT, "", ""
        self._refresh()
        self._on_change(self.accent, self.background, self.text)

    def _cancel(self):
        self.accent, self.background, self.text = self._original
        self._on_change(*self._original)
        self.reject()


class ThemeBar(QWidget):
    """Preset dropdown and custom colour pickers, kept visible in the footer."""

    def __init__(self, apply_cb, parent=None, path=None):
        super().__init__(parent)
        self._apply = apply_cb
        self.path = path
        self.accent, self.background, self.text, preset = load(path)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(QLabel("Theme:"))

        self.combo = QComboBox()
        self.combo.addItems([p[0] for p in THEME_PRESETS])
        self.combo.setCurrentIndex(preset if 0 <= preset < len(THEME_PRESETS) else 0)
        self.combo.setToolTip("Application colour scheme. Matches the presets "
                              "in the CachyOsTools app.")
        # activated, not currentIndexChanged: this sits in a toolbar and the
        # wheel-over-a-combo problem is the same one the Disks tab had.
        self.combo.activated.connect(self._preset_chosen)
        self.combo.wheelEvent = lambda e: e.ignore()
        lay.addWidget(self.combo)

        b = QPushButton("Colours…")
        b.setToolTip("Pick the accent, background and text colours by hand")
        b.clicked.connect(self._open_dialog)
        lay.addWidget(b)

    # -- called by the owner once the QApplication exists -------------------
    def apply_current(self):
        self._apply(self.accent, self.background, self.text)

    def _persist(self):
        save(self.accent, self.background, self.text, self.combo.currentIndex(), self.path)

    def use_file(self, path):
        self.path = path
        self.accent, self.background, self.text, preset = load(path)
        self.combo.setCurrentIndex(preset if 0 <= preset < len(THEME_PRESETS) else 0)
        self.apply_current()

    def _preset_chosen(self, index):
        if not (0 <= index < len(THEME_PRESETS)):
            return
        name, accent, background, text = THEME_PRESETS[index]
        if name != "Custom":
            self.accent, self.background, self.text = accent, background, text
        self._persist()
        self.apply_current()

    def _live(self, accent, background, text):
        self.accent, self.background, self.text = accent, background, text
        self.apply_current()

    def _open_dialog(self):
        dlg = ThemeDialog(self, self.accent, self.background, self.text, self._live)
        if dlg.exec():
            self.accent, self.background, self.text = dlg.accent, dlg.background, dlg.text
            # Any hand-picked colour is by definition no longer a preset.
            self.combo.setCurrentIndex(CUSTOM_INDEX)
        self._persist()
        self.apply_current()
