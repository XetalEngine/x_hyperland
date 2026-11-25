"""The integrated Kitty, Bash, history and welcome settings surface."""
import html
from pathlib import Path
import subprocess

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFontComboBox,
    QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QScrollArea, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from . import model, preferences
from .page import TerminalPage as WelcomePage, note


class TerminalPage(QWidget):
    def __init__(self, async_run):
        super().__init__()
        self.async_run = async_run
        self.loading = True; self.inputs = {}
        load_error = ''
        try: self.baseline = preferences.load()
        except (OSError, ValueError) as error:
            self.baseline = dict(preferences.DEFAULTS); load_error = str(error)
        layout = QVBoxLayout(self); layout.setContentsMargins(18, 16, 18, 16); layout.setSpacing(12)
        heading = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel('Kitty terminal'); title.setObjectName('brand'); titles.addWidget(title)
        titles.addWidget(note('A smarter prompt. Make typing, history and your terminal feel right for you.'))
        heading.addLayout(titles, 1)
        self.open_button = QPushButton('Open terminal'); self.open_button.clicked.connect(self.open_terminal)
        heading.addWidget(self.open_button); layout.addLayout(heading)
        self.tabs = QTabWidget(); layout.addWidget(self.tabs, 1)

        typing = self.new_tab('Typing && completion')
        self.command_preview = QLabel(); self.command_preview.setObjectName('terminalCommandPreview')
        self.command_preview.setWordWrap(True); self.command_preview.setMinimumHeight(84)
        self.command_preview.setTextFormat(Qt.TextFormat.RichText); typing.addWidget(self.command_preview)
        shell = self.group(typing, 'Your shell')
        self.combo(shell, 'shell', 'Open new terminals with',
                   [('Enhanced Bash', 'bash'), ('My login shell', 'login')])
        self.check(shell, 'enhanced', 'Enable enhanced Bash editing')
        shell.addRow(note('Bash keeps your aliases and prompt from .bashrc. The login-shell option uses your account’s shell. These typing and history controls apply to Bash.'))
        editing = self.group(typing, 'As you type')
        self.check(editing, 'syntax_highlighting', 'Color commands, options, strings, variables and errors')
        self.check(editing, 'autosuggestions', 'Suggest commands from history and completion')
        self.spin(editing, 'suggestion_delay', 'Suggestion delay', suffix=' ms')
        self.check(editing, 'completion_menu', 'Show a selectable completion menu')
        self.check(editing, 'completion_fuzzy', 'Offer fuzzy matches when an exact match is unavailable')
        self.check(editing, 'completion_ignore_case', 'Ignore letter case when completing')
        self.combo(editing, 'keymap', 'Editing keys', [('Standard (Emacs)', 'emacs'), ('Vim', 'vi')])
        editing.addRow(note('Tab: complete or browse choices · Right / End: accept a suggestion\nCtrl+R: search history · Up / Down: find earlier commands starting with what you typed\nCompletion definitions load on demand, including installed tools and commands after sudo.'))
        typing.addStretch()

        history = self.new_tab('History')
        commands = self.group(history, 'Command history')
        self.check(commands, 'history_enabled', 'Remember commands I run')
        self.spin(commands, 'history_size', 'Maximum saved history', suffix=' entries')
        self.check(commands, 'history_share', 'Share new commands between open Fusion terminals')
        self.check(commands, 'history_ignore_duplicates', 'Skip consecutive duplicate commands')
        self.check(commands, 'history_ignore_space', 'Skip commands that start with a space')
        commands.addRow(note('Fusion uses a private copy of your existing Bash history, created once. These controls leave the original .bash_history and other shells’ histories alone.'))
        self.history_status = note(); commands.addRow(self.history_status)
        self.clear_button = QPushButton('Clear Fusion command history…')
        self.clear_button.clicked.connect(self.clear_history); commands.addRow(self.clear_button)
        commands.addRow(note('Clearing removes the saved Fusion history. Open Bash terminals forget old entries at their next command or prompt.'))
        output = self.group(history, 'Terminal output · scrollback')
        self.spin(output, 'scrollback_lines', 'Lines available when scrolling', suffix=' lines')
        self.spin(output, 'pager_history_mb', 'Extra history for the pager', suffix=' MiB')
        output.addRow(note('Ctrl+Shift+H: browse terminal output · Ctrl+Shift+Delete: clear output and scrollback up to the prompt. This is separate from command history.'))
        history.addStretch()

        appearance = self.new_tab('Kitty appearance')
        text = self.group(appearance, 'Text & window')
        self.check(text, 'follow_theme_font', 'Use the desktop theme’s terminal font')
        font = QFontComboBox(); font.setFontFilters(QFontComboBox.FontFilter.MonospacedFonts)
        self.inputs['font_family'] = font; text.addRow('Font family', font)
        font.currentFontChanged.connect(self.changed)
        self.spin(text, 'font_size', 'Font size', suffix=' pt', decimal=True)
        self.spin(text, 'padding', 'Window padding', suffix=' pt')
        self.spin(text, 'opacity', 'Background opacity', suffix='%')
        self.check(text, 'remember_window_size', 'Remember the last terminal window size')
        text.addRow(note('Colors follow your desktop theme. New windows use these settings; Kitty can reload appearance with Ctrl+Shift+F5. History limits and scrollback size take full effect in new terminals.'))
        cursor = self.group(appearance, 'Cursor & tabs')
        self.combo(cursor, 'cursor_shape', 'Cursor shape', [('Block', 'block'), ('Beam', 'beam'), ('Underline', 'underline')])
        self.check(cursor, 'cursor_blink', 'Blink the cursor')
        self.check(cursor, 'cursor_trail', 'Animate the cursor trail')
        self.combo(cursor, 'scrollbar', 'Scrollbar', [('Always visible', 'always'), ('On hover', 'hovered'), ('Hidden', 'never')])
        self.combo(cursor, 'tab_style', 'Tab style', [(s.title(), s) for s in preferences.CHOICES['tab_style']])
        self.combo(cursor, 'tab_edge', 'Tabs position', [('Top', 'top'), ('Bottom', 'bottom')])
        behavior = self.group(appearance, 'Behavior')
        self.check(behavior, 'copy_on_select', 'Copy selected text to the clipboard automatically')
        self.check(behavior, 'audio_bell', 'Allow terminal alert sounds')
        self.check(behavior, 'confirm_close', 'Confirm closing windows with running commands')
        appearance.addStretch()

        self.welcome = WelcomePage(async_run); self.tabs.addTab(self.welcome, 'Welcome')
        self.status = note(); layout.addWidget(self.status)
        self.footer = QWidget(); buttons = QHBoxLayout(self.footer); buttons.setContentsMargins(0, 0, 0, 0)
        self.reset_button = QPushButton('Reset terminal preferences'); self.reset_button.clicked.connect(self.reset)
        buttons.addWidget(self.reset_button); buttons.addStretch()
        self.reload_button = QPushButton('Reload'); self.reload_button.clicked.connect(self.discard); buttons.addWidget(self.reload_button)
        self.discard_button = QPushButton('Discard'); self.discard_button.clicked.connect(self.discard); buttons.addWidget(self.discard_button)
        self.apply_button = QPushButton('Apply terminal'); self.apply_button.setObjectName('primary')
        self.apply_button.clicked.connect(self.save); buttons.addWidget(self.apply_button); layout.addWidget(self.footer)
        self.tabs.currentChanged.connect(lambda index: self.footer.setVisible(index != 3))
        self.set_value(self.baseline); self.refresh_history()
        if load_error: self.status.setText(load_error)
        from PyQt6.QtWidgets import QApplication
        if hasattr(QApplication.instance(), 'hypr_theme'):
            QApplication.instance().hypr_theme.changed.connect(self.preview)

    def new_tab(self, name):
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget(); layout = QVBoxLayout(body); layout.setContentsMargins(16, 16, 16, 16); layout.setSpacing(14)
        scroll.setWidget(body); self.tabs.addTab(scroll, name)
        return layout

    def group(self, layout, title):
        group = QGroupBox(title); form = QFormLayout(group)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setSpacing(12); layout.addWidget(group)
        return form

    def check(self, form, key, caption):
        widget = QCheckBox(caption); widget.toggled.connect(self.changed)
        self.inputs[key] = widget; form.addRow(widget)

    def combo(self, form, key, caption, choices):
        widget = QComboBox()
        for label, value in choices: widget.addItem(label, value)
        widget.currentIndexChanged.connect(self.changed)
        widget.setAccessibleName(caption); self.inputs[key] = widget; form.addRow(caption, widget)

    def spin(self, form, key, caption, suffix='', decimal=False):
        widget = QDoubleSpinBox() if decimal else QSpinBox()
        widget.setRange(*preferences.RANGES[key]); widget.setSuffix(suffix)
        if decimal: widget.setDecimals(1); widget.setSingleStep(0.5)
        elif key in ('history_size', 'scrollback_lines'): widget.setSingleStep(1000)
        widget.valueChanged.connect(self.changed); widget.setAccessibleName(caption)
        self.inputs[key] = widget; form.addRow(caption, widget)

    def value(self):
        value = dict(version=1)
        for key, widget in self.inputs.items():
            if isinstance(widget, QCheckBox): value[key] = widget.isChecked()
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)): value[key] = widget.value()
            elif isinstance(widget, QFontComboBox): value[key] = widget.currentFont().family()
            else: value[key] = widget.currentData()
        return value

    def set_value(self, value):
        self.loading = True
        for key, widget in self.inputs.items():
            if isinstance(widget, QCheckBox): widget.setChecked(value[key])
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)): widget.setValue(value[key])
            elif isinstance(widget, QFontComboBox): widget.setCurrentFont(QFont(value[key]))
            else: widget.setCurrentIndex(widget.findData(value[key]))
        self.loading = False; self.changed()

    @property
    def dirty(self):
        return self.value() != self.baseline or self.welcome.dirty

    def changed(self, *_):
        if self.loading: return
        changed = self.value() != self.baseline
        self.apply_button.setEnabled(changed); self.discard_button.setEnabled(changed)
        enhanced = self.inputs['enhanced'].isChecked()
        for key in ('syntax_highlighting', 'autosuggestions', 'suggestion_delay', 'completion_menu', 'completion_fuzzy'):
            self.inputs[key].setEnabled(enhanced)
        history = self.inputs['history_enabled'].isChecked()
        for key in ('history_size', 'history_share', 'history_ignore_duplicates', 'history_ignore_space'):
            self.inputs[key].setEnabled(history)
        self.inputs['font_family'].setEnabled(not self.inputs['follow_theme_font'].isChecked())
        self.preview()

    def preview(self, *_):
        colors = model.runtime.colors()
        enabled = self.inputs['enhanced'].isChecked() and self.inputs['syntax_highlighting'].isChecked()
        tokens = [('sudo ', '#78d7b6'), ('pacman ', '#78d7b6'), ('-S --needed ', '#73d4d1'),
                  ('"app name" ', '#d8ce99'), ('${HOME}', '#b7a2e4')]
        text = ''.join(f'<span style="color:{color if enabled else colors["Text"]}">{html.escape(word)}</span>' for word, color in tokens)
        self.command_preview.setText('<span style="font-family:monospace;font-size:15px">❯ ' + text + '</span><br><br><small>Commands · options · quoted text · variables</small>')
        self.command_preview.setStyleSheet(f'background:{colors["Base"]};color:{colors["Text"]};border:1px solid {colors["Mid"]};border-radius:8px;padding:16px;')

    def save(self):
        try:
            self.baseline = preferences.save(self.value(), expected=self.baseline)
            self.set_value(self.baseline)
            self.status.setText('Saved. Open a new terminal to use all changes. Existing Kitty windows can reload appearance with Ctrl+Shift+F5.')
        except (OSError, ValueError) as error: self.status.setText(str(error))

    def discard(self):
        try:
            self.baseline = preferences.load(); self.set_value(self.baseline)
            self.status.setText('Saved terminal preferences restored.')
        except (OSError, ValueError) as error: self.status.setText(str(error))

    def reset(self):
        self.set_value(preferences.DEFAULTS)
        self.status.setText('Default terminal preferences selected. Apply to save. Your command history is kept.')

    def refresh(self):
        if not self.dirty: self.discard()
        self.welcome.refresh(); self.refresh_history()

    def refresh_history(self):
        try: self.history_status.setText(preferences.history_status())
        except (OSError, ValueError) as error: self.history_status.setText(str(error))

    def clear_history(self):
        answer = QMessageBox.question(self, 'Clear Fusion command history?',
            'Permanently delete saved Fusion Bash commands? Open Fusion terminals will forget them at their next command or prompt. Other shells and the original Bash history are kept.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        if answer != QMessageBox.StandardButton.Yes: return
        try:
            preferences.clear_history(); self.refresh_history()
            self.status.setText('Fusion command history cleared. Open terminals will refresh at their next command or prompt.')
        except (OSError, ValueError) as error: self.status.setText(str(error))

    def open_terminal(self):
        try:
            subprocess.Popen(['kitty', '--config', str(preferences.ROOT.parent / 'kitty.conf')],
                             start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as error: self.status.setText(str(error))
