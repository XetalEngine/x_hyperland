"""Terminal welcome choices and a compact preview of the actual greeting."""
import copy
import html
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QFontMetrics, QPixmap
from PyQt6.QtWidgets import (QApplication, QBoxLayout, QCheckBox, QComboBox,
    QFileDialog, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from . import artwork, model


LOGOS = [('Arch · Neon', 'arch'), ('Arch · Text', 'arch-ascii'),
         ('Hyper Fusion · Text', 'fusion'), ('Custom image', 'custom'), ('No logo', 'none')]
DESCRIPTIONS = {
    'arch': 'An illustrated Arch emblem that follows your desktop colors.',
    'arch-ascii': 'The classic Arch logo, drawn with terminal characters.',
    'fusion': 'The Fusion mark, drawn with terminal characters.',
    'custom': 'Use your own image. Its colors and proportions stay intact.',
    'none': 'A clean welcome with just your selected information.',
}


def note(text=''):
    label = QLabel(text); label.setWordWrap(True); label.setObjectName('muted')
    return label


class TerminalPage(QWidget):
    def __init__(self, async_run):
        super().__init__()
        self.async_run = async_run; self.data = {}; self.loading = False
        self.image_name = ''; self.image_valid = True
        root = QVBoxLayout(self); root.setContentsMargins(18, 16, 18, 16); root.setSpacing(12)
        title = QLabel('Terminal welcome'); title.setObjectName('brand'); root.addWidget(title)
        root.addWidget(note('Make each new terminal yours. Choose a logo and the information you want to see.'))
        self.enabled = QCheckBox('Show welcome when a Fusion terminal opens'); root.addWidget(self.enabled)

        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget(); content_layout = QVBoxLayout(content); content_layout.setContentsMargins(0, 0, 0, 0)
        self.columns = QBoxLayout(QBoxLayout.Direction.LeftToRight); self.columns.setSpacing(18)
        content_layout.addLayout(self.columns); content_layout.addStretch()
        self.controls = QWidget(); controls_layout = QVBoxLayout(self.controls)
        controls_layout.setContentsMargins(0, 0, 0, 0); controls_layout.setSpacing(12)
        self.controls.setFixedWidth(344)

        logo_group = QGroupBox('Logo'); logo_layout = QVBoxLayout(logo_group); logo_layout.setSpacing(10)
        self.logo = QComboBox(); self.logo.setAccessibleName('Terminal logo')
        for caption, value in LOGOS: self.logo.addItem(caption, value)
        logo_layout.addWidget(self.logo)
        self.logo_description = note(); logo_layout.addWidget(self.logo_description)
        self.choose = QPushButton('Choose image…'); self.choose.clicked.connect(self.choose_image)
        self.choose.setToolTip('Import a PNG, JPEG, WebP, SVG or BMP as your terminal logo.')
        logo_layout.addWidget(self.choose)
        self.image_status = note(); logo_layout.addWidget(self.image_status)
        controls_layout.addWidget(logo_group)

        information = QGroupBox('Information'); fields_layout = QVBoxLayout(information); fields_layout.setSpacing(12)
        self.user = QCheckBox('Username and hostname'); fields_layout.addWidget(self.user)
        self.palette = QCheckBox('Color palette'); fields_layout.addWidget(self.palette)
        line = QFrame(); line.setFrameShape(QFrame.Shape.HLine); fields_layout.addWidget(line)
        self.fields = {}; grid = QGridLayout(); grid.setVerticalSpacing(10); grid.setHorizontalSpacing(16)
        for i, (key, caption) in enumerate(model.FIELDS.items()):
            box = QCheckBox(caption); grid.addWidget(box, i // 2, i % 2); self.fields[key] = box
            box.toggled.connect(self.preview)
        fields_layout.addLayout(grid)
        controls_layout.addWidget(information); controls_layout.addStretch()
        self.columns.addWidget(self.controls, 0, Qt.AlignmentFlag.AlignTop)

        self.preview_group = QGroupBox('Live preview'); preview_layout = QVBoxLayout(self.preview_group)
        preview_layout.setSpacing(12)
        preview_header = QHBoxLayout(); self.preview_title = QLabel(''); preview_header.addWidget(self.preview_title)
        preview_header.addStretch(); self.refresh_button = QPushButton('Refresh information')
        self.refresh_button.clicked.connect(self.refresh_data); preview_header.addWidget(self.refresh_button)
        preview_layout.addLayout(preview_header)
        self.canvas = QFrame(); self.canvas.setObjectName('terminalCanvas')
        canvas_layout = QVBoxLayout(self.canvas); canvas_layout.setContentsMargins(16, 18, 16, 18)
        welcome = QHBoxLayout(); welcome.setSpacing(12)
        self.emblem = QLabel(); self.emblem.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome.addWidget(self.emblem, 0, Qt.AlignmentFlag.AlignVCenter)
        self.display = QLabel(); self.display.setTextFormat(Qt.TextFormat.RichText)
        self.display.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.display.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.display.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.display.setMinimumWidth(0)
        self.preview_font = QFont('monospace'); self.preview_font.setPixelSize(13)
        self.display.setFont(self.preview_font)
        self.display.setStyleSheet('font-family: monospace; font-size: 13px;')
        welcome.addWidget(self.display, 1)
        canvas_layout.addLayout(welcome)
        self.prompt = QLabel('  ~  ❯ _'); self.prompt.setFont(self.preview_font); canvas_layout.addWidget(self.prompt)
        preview_layout.addWidget(self.canvas)
        self.preview_note = note(); preview_layout.addWidget(self.preview_note)
        self.columns.addWidget(self.preview_group, 1, Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(content); root.addWidget(self.scroll, 1)

        self.status = note(); root.addWidget(self.status)
        buttons = QHBoxLayout(); reset = QPushButton('Reset choices'); reset.clicked.connect(lambda: self.set_value(model.DEFAULTS))
        buttons.addWidget(reset); buttons.addStretch()
        self.revert = QPushButton('Discard changes'); self.revert.clicked.connect(self.discard); buttons.addWidget(self.revert)
        self.apply = QPushButton('Save terminal'); self.apply.setObjectName('primary')
        self.apply.clicked.connect(self.save); buttons.addWidget(self.apply); root.addLayout(buttons)
        for box in (self.enabled, self.user, self.palette): box.toggled.connect(self.preview)
        self.logo.currentIndexChanged.connect(self.preview)
        self.refresh()
        if hasattr(QApplication.instance(), 'hypr_theme'):
            QApplication.instance().hypr_theme.changed.connect(self.preview)

    def value(self):
        return dict(version=1, enabled=self.enabled.isChecked(), logo=self.logo.currentData(),
            logo_image=self.image_name, show_user=self.user.isChecked(), show_palette=self.palette.isChecked(),
            fields=[key for key in model.FIELDS if self.fields[key].isChecked()])

    def set_value(self, value):
        self.loading = True
        self.enabled.setChecked(value['enabled']); self.user.setChecked(value['show_user'])
        self.palette.setChecked(value['show_palette']); self.image_name = value.get('logo_image', '')
        self.logo.setCurrentIndex(self.logo.findData(value['logo']))
        for key, box in self.fields.items(): box.setChecked(key in value['fields'])
        self.loading = False; self.preview()

    @property
    def dirty(self): return self.value() != self.baseline

    def refresh(self):
        if hasattr(self, 'baseline') and self.dirty: return
        try: self.baseline = model.load()
        except (OSError, ValueError) as error:
            self.status.setText(str(error)); self.baseline = copy.deepcopy(model.DEFAULTS)
        self.set_value(self.baseline)
        if not self.data: self.refresh_data()

    def discard(self):
        try:
            self.baseline = model.load(); self.set_value(self.baseline)
            self.status.setText('Saved choices restored.')
        except (OSError, ValueError) as error: self.status.setText(str(error))

    def refresh_data(self):
        self.refresh_button.setEnabled(False); self.status.setText('Reading system information…')
        self.async_run(model.system_data, self.loaded, self.refresh_failed)

    def refresh_failed(self, message):
        self.refresh_button.setEnabled(True); self.status.setText(message)

    def loaded(self, data):
        self.data = data; self.refresh_button.setEnabled(True); self.preview()
        self.status.setText('Save your choices to use them in new terminals.')

    def choose_image(self):
        filename, _ = QFileDialog.getOpenFileName(self, 'Choose a terminal logo', str(Path.home() / 'Pictures'),
            'Images (*.png *.jpg *.jpeg *.webp *.svg *.bmp)', options=QFileDialog.Option.DontUseNativeDialog)
        if filename: self.use_image(filename)

    def use_image(self, filename):
        try: path = artwork.import_logo(filename, model.ROOT / 'logos')
        except (OSError, ValueError) as error:
            self.status.setText(str(error)); return False
        self.image_name = path.name; self.logo.setCurrentIndex(self.logo.findData('custom')); self.preview()
        self.status.setText('Image ready. Save terminal to use it in new terminals.')
        return True

    def resizeEvent(self, event):
        stacked = self.width() < 900
        self.columns.setDirection(QBoxLayout.Direction.TopToBottom if stacked else QBoxLayout.Direction.LeftToRight)
        self.controls.setMinimumWidth(0 if stacked else 344)
        self.controls.setMaximumWidth(16777215 if stacked else 344)
        super().resizeEvent(event)
        QTimer.singleShot(0, self.preview)

    def preview(self, *_):
        if self.loading: return
        value = self.value(); colors = model.runtime.colors(); has_logo = False
        size = 216 if self.canvas.width() >= 650 else 176
        self.emblem.setFixedSize(size, size)
        self.logo_description.setText(DESCRIPTIONS[value['logo']]); self.image_valid = True
        self.choose.setText('Change image…' if value['logo'] == 'custom' and self.image_name else 'Choose image…')
        self.image_status.setVisible(value['logo'] == 'custom')
        self.image_status.setText('A copy is kept for your terminal, even if you move the original image.')
        if value['logo'] in ('arch', 'custom'):
            try:
                path = model.logo_path(value) if value['logo'] == 'custom' else artwork.png(colors)
                pixmap = QPixmap(str(path))
                if pixmap.isNull(): raise ValueError('The saved image is unavailable. Choose another image.')
                self.emblem.setPixmap(pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                                    Qt.TransformationMode.SmoothTransformation))
                has_logo = True
            except (ImportError, OSError, ValueError) as error:
                if value['logo'] == 'custom':
                    self.image_valid = False; self.image_status.setText(str(error))
        if not has_logo and value['logo'] in ('arch', 'arch-ascii', 'fusion'):
            lines = model.FUSION if value['logo'] == 'fusion' else model.ARCH
            text = '\n'.join(f'<span style="color:{model.blend(colors["Accent"], colors["Text"], .4 * (1 - i / len(lines)))}">'
                             f'{html.escape(line)}</span>' for i, line in enumerate(lines))
            self.emblem.setText(f'<pre style="font-family:monospace; font-size:{11 if size == 216 else 9}px">{text}</pre>')
            has_logo = True
        self.emblem.setVisible(has_logo and value['enabled'])
        self.display.setVisible(value['enabled'])
        width = max(28, (self.canvas.width() - 32 - (self.emblem.width() + 12 if has_logo else 0))
                    // max(1, QFontMetrics(self.preview_font).horizontalAdvance('M')))
        self.display.setText(model.render({**value, 'logo': 'none'},
                                         self.data, width=width, markup=True))
        self.canvas.setStyleSheet(f'QFrame#terminalCanvas {{ background: {colors["Base"]}; '
            f'border: 1px solid {colors["Mid"]}; border-radius: 8px; }} '
            'QFrame#terminalCanvas QLabel { background: transparent; border: none; padding: 0; }')
        self.prompt.setStyleSheet(f'color: {colors["Accent"]};')
        self.preview_title.setText(model.runtime.DESIGNS[model.runtime.design()] + ' · Kitty')
        self.preview_note.setText('Live system information from Fastfetch. Images appear in Fusion’s Kitty terminal; '
            'narrow terminals keep the text readable.' if value['enabled'] else
            'Welcome is off. New terminals will open directly at the prompt.')
        self.apply.setEnabled(self.dirty and self.image_valid)
        self.revert.setEnabled(self.dirty)

    def save(self):
        try:
            if self.value()['logo'] == 'custom' and not model.logo_path(self.value()).is_file():
                raise ValueError('Choose an image for your custom logo.')
            model.save(self.value(), expected=self.baseline)
            self.baseline = self.value(); self.preview()
            self.status.setText('Saved. Open a new terminal to see your welcome.')
        except (OSError, ValueError) as error: self.status.setText(str(error))
