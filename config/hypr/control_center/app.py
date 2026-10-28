#!/usr/bin/env python3
"""A native, session-local Hyprland control panel. No KDE settings are written."""
from __future__ import annotations

import argparse
import copy
import html
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

from PyQt6.QtCore import Qt, QTimer, QRunnable, QThreadPool, QObject, pyqtSignal, QPropertyAnimation, QEasingCurve, QFileSystemWatcher, QStandardPaths, QSize
from PyQt6.QtGui import QFont, QKeySequence, QShortcut, QColor, QPalette, QTextCharFormat
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QCheckBox, QTabWidget, QTabBar,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QSplitter,
    QFormLayout, QGroupBox, QMessageBox, QTextEdit, QSlider, QCalendarWidget,
    QProgressBar, QListWidget, QFrame, QGraphicsOpacityEffect, QScrollArea, QFileDialog, QSizePolicy,
)
import keys
from key_capture import CaptureEdit
sys.path.insert(0, str(keys.ROOT / 'theme'))
import runtime as theme_runtime
from display_page import DisplaysPage
from preferences_page import PreferencesPage
from page import ThemePage
from audio_page import AudioPage, STYLE as AUDIO_STYLE
from context_menu_page import ContextMenuPage, STYLE as CONTEXT_STYLE
from window_chrome import close_button
from home_page import HomePage
from identity import Avatar
from icons import icon as navigation_icon

STYLE = '''
QWidget { background: #171b22; color: #d8e0ec; font-family: "DejaVu Sans"; font-size: 12px; }
QMainWindow { background: #14181e; }
QLabel#brand { color: #f0f5fa; font-size: 21px; font-weight: 700; letter-spacing: 1px; }
QLabel#eyebrow { color: #65d5cb; font-family: "DejaVu Sans Mono"; font-size: 10px; letter-spacing: 2px; }
QLabel#muted { color: #8d9bad; }
QLabel#status { color: #65d5cb; background: #1c252b; padding: 9px; border: 1px solid #2c3b44; }
QLabel#metric { font-size: 25px; color: #edf3fb; font-weight: 600; }
QTabWidget::pane { border: 1px solid #343c49; background: #171b22; }
QTabBar::tab { background: #202630; color: #94a3b7; padding: 10px 17px; border-right: 1px solid #14181e; }
QTabBar::tab:selected { background: #2b3742; color: #80e2d8; border-top: 2px solid #65d5cb; padding-top: 8px; }
QTabBar::tab:hover { background: #2a333f; color: #e9eff7; }
QPushButton { background: #293340; border: 1px solid #3a4859; border-radius: 2px; padding: 7px 13px; }
QPushButton:hover { background: #36475a; border-color: #70909d; }
QPushButton:pressed { background: #182e36; }
QPushButton:disabled { color: #617083; background: #202630; border-color: #2b3340; }
QPushButton#primary { background: #245e60; border-color: #4fa59d; color: #eafffa; font-weight: 600; }
QPushButton#primary:hover { background: #2f7977; }
QPushButton#primary:disabled { background: #253d43; border-color: #35545a; color: #718c91; }
QPushButton#danger { color: #edb0b0; border-color: #6a424b; }
QLineEdit, QComboBox, QTextEdit, QListWidget { background: #10151c; border: 1px solid #364251; padding: 7px; selection-background-color: #31586b; }
QLineEdit:focus, QComboBox:focus { border-color: #65d5cb; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: #202630; selection-background-color: #31586b; }
QTableWidget { background: #141920; alternate-background-color: #1b222c; border: 1px solid #303c49; gridline-color: #27303b; selection-background-color: #284855; selection-color: #ecfffb; }
QTableWidget::item { padding: 6px; border: none; }
QTableWidget::item:selected { background: #284855; }
QHeaderView::section { background: #242d38; color: #a5b4c7; border: none; border-right: 1px solid #354151; border-bottom: 1px solid #354151; padding: 8px; font-size: 11px; font-weight: 600; }
QTableCornerButton::section { background: #242d38; border: none; }
QGroupBox { border: 1px solid #354151; margin-top: 14px; padding: 13px 10px 10px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; color: #afc4d4; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 14px; height: 14px; background: #11171e; border: 1px solid #4c6072; }
QCheckBox::indicator:checked { background: #4b9c95; border: 2px solid #8ce4d7; }
QScrollBar:vertical { background: #141920; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #3c4c5d; min-height: 25px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QSplitter::handle { background: #2a333f; width: 5px; }
QSlider::groove:horizontal { height: 5px; background: #303d4b; }
QSlider::sub-page:horizontal { background: #58afa8; }
QSlider::handle:horizontal { background: #a8e8dd; width: 13px; margin: -5px 0; border-radius: 2px; }
QProgressBar { background: #11171e; border: 1px solid #364251; text-align: center; min-height: 20px; }
QProgressBar::chunk { background: #315f68; }
QToolTip { color: #e2edf5; background: #252f3c; border: 1px solid #4c6176; padding: 5px; }
QCalendarWidget QAbstractItemView { background: #141920; selection-background-color: #356a70; color: #d8e0ec; }
QCalendarWidget QWidget#qt_calendar_navigationbar { background: #202b38; }
QCalendarWidget QToolButton { color: #d8e0ec; background: #202b38; padding: 9px; border: none; }
QCalendarWidget QToolButton:hover { background: #30475b; }
QCalendarWidget QMenu { background: #202b38; color: #d8e0ec; }
QFrame#changes { background: #111a24; border: 1px solid #315765; border-radius: 8px; }
QFrame#changes QLabel, QFrame#changes QTextEdit { background: transparent; border: none; }
QFrame#changes QTextEdit { font-family: "DejaVu Sans Mono"; font-size: 11px; }
QPushButton#windowClose { font-size: 23px; color: #a9bacd; background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 0; }
QPushButton#windowClose:hover { color: #fff1f3; background: #663544; border-color: #b3687f; }
'''+AUDIO_STYLE+CONTEXT_STYLE


def run(argv, timeout=6, check=True):
    result = subprocess.run(argv, text=True, capture_output=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError((result.stderr or result.stdout or f'{argv[0]} failed').strip())
    return result.stdout.strip()


def launch(argv, isolated=False):
    env = theme_runtime.environment()
    if isolated:
        env['XDG_CONFIG_HOME'] = str(keys.ROOT / 'apps')
        env['GSETTINGS_BACKEND'] = 'keyfile'
    subprocess.Popen(argv, env=env, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class Signals(QObject):
    done = pyqtSignal(object)
    failed = pyqtSignal(str)


class Job(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.fn, self.signals = fn, Signals()

    def run(self):
        try:
            self.signals.done.emit(self.fn())
        except Exception as exc:
            self.signals.failed.emit(str(exc))


JOBS = set()


def async_run(fn, done, failed):
    job = Job(fn)
    JOBS.add(job)
    def success(value):
        JOBS.discard(job)
        done(value)
    def failure(message):
        JOBS.discard(job)
        failed(message)
    job.signals.done.connect(success)
    job.signals.failed.connect(failure)
    QThreadPool.globalInstance().start(job)


def button(text, callback, primary=False):
    result = QPushButton(text)
    if primary:
        result.setObjectName('primary')
    result.clicked.connect(callback)
    return result


def label(text, name=''):
    result = QLabel(text)
    if name:
        result.setObjectName(name)
    return result


def table(headers):
    result = QTableWidget(0, len(headers))
    result.setHorizontalHeaderLabels(headers)
    result.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    result.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    result.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    result.setAlternatingRowColors(True)
    result.setShowGrid(False)
    result.verticalHeader().hide()
    result.verticalHeader().setDefaultSectionSize(36)
    result.horizontalHeader().setStretchLastSection(True)
    return result


class Hotkeys(QWidget):
    def __init__(self):
        super().__init__()
        self.store = keys.Store()
        self.records, self.expected = [], ''
        self.baseline = []
        self.current_id = None
        self.dirty = self.loading = self.busy = False
        self.preset_directory = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
                                     or str(Path.home()))
        self.values = keys.variables(self.store.main.read_text())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        tools = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search shortcuts, actions, commands…')
        self.search.textChanged.connect(self.render)
        tools.addWidget(self.search, 1)
        tools.addWidget(button('+ New binding', self.add))
        tools.addWidget(button('Reload', self.reload))
        self.apply_button = button('Apply changes  ·  Ctrl+S', self.apply, True)
        tools.addWidget(self.apply_button)
        layout.addLayout(tools)
        self.categories = QTabBar()
        self.categories.setExpanding(False)
        self.categories.setUsesScrollButtons(True)
        self.categories.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.categories.setMinimumWidth(0)
        for name in ['All', *keys.CATEGORIES, 'Live', 'History']:
            self.categories.addTab(name)
        self.categories.currentChanged.connect(self.render)
        navigation = QHBoxLayout()
        navigation.addWidget(self.categories, 1)
        self.reset_defaults_button = button('Reset defaults', self.reset_defaults)
        self.reset_defaults_button.setToolTip('Load your saved default hotkeys as a draft, then review and Apply.')
        self.save_preset_button = button('Save current…', self.save_preset)
        self.save_preset_button.setToolTip('Export all hotkeys in the editor, including pending edits, to a preset file.')
        self.load_preset_button = button('Load preset…', self.load_preset)
        self.load_preset_button.setToolTip('Load hotkeys from a file as a draft. Changes take effect after Apply.')
        for action in (self.reset_defaults_button, self.save_preset_button, self.load_preset_button):
            navigation.addWidget(action)
        layout.addLayout(navigation)
        split = QSplitter()
        self.bindings_table = table(['On', 'Shortcut', 'Action', 'Type'])
        self.bindings_table.setColumnWidth(0, 42)
        self.bindings_table.setColumnWidth(1, 220)
        self.bindings_table.setColumnWidth(2, 265)
        self.bindings_table.itemSelectionChanged.connect(self.selection)
        self.bindings_table.itemChanged.connect(self.checked)
        split.addWidget(self.bindings_table)
        self.inspector = QGroupBox('BINDING INSPECTOR');self.inspector.setObjectName('bindingInspector')
        inspector_layout=QVBoxLayout(self.inspector)
        inspector_layout.setContentsMargins(10,16,10,10);inspector_layout.setSpacing(10)
        fields_widget=QWidget()
        form = QFormLayout(fields_widget)
        form.setContentsMargins(0,0,6,0)
        form.setVerticalSpacing(10)
        self.fields = {}
        for title, field in [('Name', 'label'), ('Category', 'category'), ('Modifiers', 'mods'),
                              ('Key', 'key'), ('Action', 'dispatcher'), ('Command / args', 'args'),
                              ('Flags', 'flags'), ('Submap', 'submap')]:
            if field == 'category':
                widget = QComboBox()
                widget.addItems(keys.CATEGORIES)
            elif field == 'dispatcher':
                widget = QComboBox()
                widget.setEditable(True)
                widget.addItems(['exec', 'killactive', 'togglefloating', 'fullscreen', 'movefocus', 'movewindow',
                                 'resizewindow', 'workspace', 'movetoworkspace', 'movetoworkspacesilent',
                                 'togglespecialworkspace', 'layoutmsg', 'pseudo', 'exit', 'submap'])
            elif field == 'key':
                widget = CaptureEdit()
                widget.captured.connect(self.captured)
                widget.cancelled.connect(self.stop_capture)
            else:
                widget = QLineEdit()
            if isinstance(widget, QComboBox):
                widget.currentTextChanged.connect(lambda _text: self.edit(refresh=False))
                if widget.isEditable():
                    widget.lineEdit().editingFinished.connect(self.edit)
            else:
                widget.textEdited.connect(lambda _text: self.edit(refresh=False))
                widget.editingFinished.connect(self.edit)
            self.fields[field] = widget
            form.addRow(title, widget)
        self.fields['mods'].setPlaceholderText('SUPER / SUPER SHIFT / SUPER CTRL')
        self.fields['args'].setPlaceholderText('Command to launch, or action arguments')
        self.fields['flags'].setPlaceholderText('e = repeat, l = locked, r = release, m = mouse')
        self.fields['submap'].setPlaceholderText('reset = normal shortcuts')
        self.record_button = button('Record shortcut…', self.begin_capture)
        form.addRow('', self.record_button)
        self.enabled = QCheckBox('Enabled')
        self.enabled.stateChanged.connect(self.edit)
        form.addRow('', self.enabled)
        self.hint = label('Edit a row, then Apply changes.\nGlobal shortcuts use Super to preserve typing.\nCommands run only when you use the shortcut.', 'muted')
        self.hint.setWordWrap(True)
        form.addRow(self.hint)
        self.inspector_scroll=QScrollArea()
        self.inspector_scroll.setWidgetResizable(True)
        self.inspector_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.inspector_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.inspector_scroll.setWidget(fields_widget)
        inspector_layout.addWidget(self.inspector_scroll,1)
        controls = QHBoxLayout()
        self.duplicate_button=button('Duplicate', self.duplicate)
        self.remove_button=button('Remove', self.remove)
        controls.addWidget(self.duplicate_button);controls.addWidget(self.remove_button)
        inspector_layout.addLayout(controls)
        self.restore_button = button('Load selected backup', self.restore)
        inspector_layout.addWidget(self.restore_button)
        self.restore_button.hide()
        for widget in self.fields.values():
            widget.setEnabled(True)
        split.addWidget(self.inspector)
        split.setSizes([770, 355])
        layout.addWidget(split, 1)
        self.change_panel = QFrame()
        self.change_panel.setObjectName('changes')
        change_layout = QVBoxLayout(self.change_panel)
        change_layout.setContentsMargins(14, 9, 14, 9)
        change_header = QHBoxLayout()
        self.change_title = label('PENDING CHANGES', 'eyebrow')
        change_header.addWidget(self.change_title)
        change_header.addStretch()
        self.discard_button = button('Discard changes', self.discard)
        change_header.addWidget(self.discard_button)
        change_layout.addLayout(change_header)
        self.change_log = QTextEdit()
        self.change_log.setReadOnly(True)
        self.change_log.setMinimumHeight(0)
        change_layout.addWidget(self.change_log, 1)
        self.change_panel.setMaximumHeight(0)
        self.change_panel.hide()
        self.change_animation = QPropertyAnimation(self.change_panel, b'maximumHeight', self)
        self.change_animation.setDuration(180)
        self.change_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.change_animation.finished.connect(self.finish_change_animation)
        layout.addWidget(self.change_panel)
        self.status = label('', 'status')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.capture_timer = QTimer(self)
        self.capture_timer.setSingleShot(True)
        self.capture_timer.timeout.connect(self.stop_capture)
        self.capture_poll = QTimer(self)
        self.capture_poll.setInterval(300)
        self.capture_poll.timeout.connect(self.poll_capture)
        QShortcut(QKeySequence('Ctrl+S'), self).activated.connect(self.apply)
        QShortcut(QKeySequence('Ctrl+F'), self).activated.connect(self.search.setFocus)
        self.reload(force=True)
        self.file_watcher=QFileSystemWatcher([str(self.store.root)],self)
        self.file_delay=QTimer(self);self.file_delay.setSingleShot(True);self.file_delay.setInterval(160)
        self.file_watcher.directoryChanged.connect(lambda _:self.file_delay.start())
        self.file_watcher.fileChanged.connect(lambda _:self.file_delay.start())
        self.file_delay.timeout.connect(self.external_change)
        self.watch_files()

    def watch_files(self):
        for path in (self.store.path,self.store.main):
            if path.exists() and str(path) not in self.file_watcher.files():self.file_watcher.addPath(str(path))

    def external_change(self):
        self.watch_files()
        if self.busy:
            self.file_delay.start(300)
            return
        try:
            _,expected=self.store.load()
            values=keys.variables(self.store.main.read_text())
            if expected==self.expected and values==self.values:return
            if self.dirty or self.fields['key'].recording:
                self.tell('Hotkeys changed in another window. Your draft is kept; use Reload to load the saved changes.',True)
                return
            self.reload(force=True)
        except Exception as exc:self.tell(str(exc),True)

    def selected(self):
        return next((b for b in self.records if b.id == self.current_id), None)

    def tell(self, text, error=False):
        self.status.setText(text)
        self.status.setStyleSheet('color: #f0aaaa;' if error else '')

    def reload(self, checked=False, force=False):
        if self.busy or (self.dirty and not force and not self.confirm_discard()):
            return
        try:
            self.records, self.expected = self.store.load()
            self.values = keys.variables(self.store.main.read_text())
            self.dirty = False
            self.baseline = copy.deepcopy(self.records)
            self.update_changes()
            self.render()
            self.tell(f'{len(self.records)} configured shortcuts  ·  Edits apply live after validation')
        except Exception as exc:
            self.tell(str(exc), True)

    def render(self, *_):
        if self.loading:
            return
        self.apply_button.setEnabled(self.dirty and not self.busy)
        view = self.categories.tabText(self.categories.currentIndex())
        if view == 'Live':
            self.inspector.setEnabled(False)
            self.render_live()
            return
        if view == 'History':
            self.render_history()
            return
        self.restore_button.hide()
        for widget in self.fields.values():
            widget.setEnabled(True)
        self.bindings_table.setHorizontalHeaderLabels(['On', 'Shortcut', 'Action', 'Type'])
        query = self.search.text().casefold()
        visible = [b for b in self.records if (view == 'All' or b.category == view
                   or (view == 'Window hover' and 'movetoworkspace' in b.dispatcher))
                   and query in ' '.join([b.label, b.shortcut(self.values), b.dispatcher, b.args, b.category]).casefold()]
        self.loading = True
        self.bindings_table.setRowCount(len(visible))
        chosen = 0
        for row, b in enumerate(visible):
            state = QTableWidgetItem('')
            state.setData(Qt.ItemDataRole.UserRole, b.id)
            state.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable |
                           (Qt.ItemFlag.ItemIsUserCheckable if not b.protected else Qt.ItemFlag.NoItemFlags))
            state.setCheckState(Qt.CheckState.Checked if b.enabled else Qt.CheckState.Unchecked)
            items = [state, QTableWidgetItem(b.shortcut(self.values)), QTableWidgetItem(b.label),
                     QTableWidgetItem(b.category + (' · recovery' if b.protected else ''))]
            for col, item in enumerate(items):
                item.setToolTip(b.line() + (f'\nSubmap: {b.submap}' if b.submap != 'reset' else ''))
                self.bindings_table.setItem(row, col, item)
            if b.id == self.current_id:
                chosen = row
        self.loading = False
        if visible:
            self.bindings_table.selectRow(chosen)
            self.selection()
        else:
            self.current_id = None
            self.inspector.setEnabled(False)
        self.apply_button.setEnabled(self.dirty and not self.busy)

    def selection(self):
        if self.loading:
            return
        row = self.bindings_table.currentRow()
        if row < 0:
            return
        item = self.bindings_table.item(row, 0)
        self.current_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        b = self.selected()
        if not b:
            return
        self.loading = True
        for name, widget in self.fields.items():
            if isinstance(widget, QComboBox):
                widget.setCurrentText(getattr(b, name))
            else:
                widget.setText(getattr(b, name))
        self.enabled.setChecked(b.enabled)
        self.inspector.setEnabled(not b.protected and not self.busy)
        self.loading = False

    def checked(self, item):
        if self.loading or item.column() != 0:
            return
        b = next((b for b in self.records if b.id == item.data(Qt.ItemDataRole.UserRole)), None)
        if b and not b.protected:
            b.enabled = item.checkState() == Qt.CheckState.Checked
            self.mark_dirty()
            self.selection()

    def edit(self, *_, refresh=True):
        b = self.selected()
        if self.loading or not b or b.protected or self.busy:
            return
        before = copy.deepcopy(b)
        for name, widget in self.fields.items():
            value = widget.currentText() if isinstance(widget, QComboBox) else widget.text()
            setattr(b, name, value.strip())
        b.submap = b.submap or 'reset'
        b.enabled = self.enabled.isChecked()
        if before != b:
            self.mark_dirty()
            if refresh:
                self.render()
            else:
                # Keep the caret and text selection intact while logging typing.
                row = self.bindings_table.currentRow()
                if row >= 0:
                    self.loading = True
                    for col, value in [(1, b.shortcut(self.values)), (2, b.label), (3, b.category)]:
                        item = self.bindings_table.item(row, col)
                        if item:
                            item.setText(value)
                    self.loading = False

    def mark_dirty(self):
        self.dirty = self.records != self.baseline
        self.update_changes()
        problems = keys.conflicts(self.records, self.values)
        message = ('Unapplied changes  ·  Ctrl+S validates, saves a backup and reloads Hyprland'
                   if self.dirty else 'No pending changes')
        self.tell('\n'.join(problems) if problems else message, bool(problems))
        self.apply_button.setEnabled(self.dirty and not self.busy)

    def update_changes(self):
        before = {b.id: b for b in self.baseline}
        after = {b.id: b for b in self.records}
        entries = []
        names = {'label': 'Name', 'category': 'Category', 'enabled': 'Enabled', 'mods': 'Modifiers',
                 'key': 'Key', 'dispatcher': 'Action', 'args': 'Command / args', 'flags': 'Flags', 'submap': 'Submap'}
        def safe(value):
            if isinstance(value, bool):
                return 'On' if value else 'Off'
            return html.escape(str(value)) or '∅'
        for ident in dict.fromkeys([*before, *after]):
            old, new = before.get(ident), after.get(ident)
            if old == new:
                continue
            if old is None:
                entries.append(f'<b style="color:#83dfc4">+ Added · {safe(new.label)}</b><br>'
                               f'&nbsp;&nbsp;{safe(new.shortcut(self.values))} → {safe(new.dispatcher)} {safe(new.args)}')
            elif new is None:
                entries.append(f'<b style="color:#ed9cae">− Removed · {safe(old.label)}</b><br>'
                               f'&nbsp;&nbsp;{safe(old.shortcut(self.values))}')
            else:
                fields = [f'&nbsp;&nbsp;<span style="color:#93a9be">{title}</span> · '
                          f'<span style="color:#d59caa">{safe(getattr(old, field))}</span> → '
                          f'<span style="color:#83dfc4">{safe(getattr(new, field))}</span>'
                          for field, title in names.items() if getattr(old, field) != getattr(new, field)]
                entries.append(f'<b style="color:#9ecce9">~ Edited · {safe(new.label)}</b><br>' + '<br>'.join(fields))
        self.change_title.setText(f'PENDING CHANGES  ·  {len(entries)} binding' + ('' if len(entries) == 1 else 's'))
        scroll = self.change_log.verticalScrollBar()
        position = scroll.value()
        self.change_log.setHtml('<div style="color:#d8e0ec">' + '<br><br>'.join(entries) + '</div>')
        scroll.setValue(position)
        opening = bool(entries)
        target = 178 if opening else 0
        if opening:
            self.change_panel.show()
        if self.change_animation.endValue() != target or self.change_animation.state() == QPropertyAnimation.State.Stopped:
            if self.change_panel.maximumHeight() != target:
                self.change_animation.stop()
                self.change_animation.setStartValue(self.change_panel.maximumHeight())
                self.change_animation.setEndValue(target)
                self.change_animation.start()
            elif not opening:
                self.change_panel.hide()

    def finish_change_animation(self):
        if self.change_panel.maximumHeight() == 0:
            self.change_panel.hide()

    def discard(self):
        if not self.busy:
            self.stop_capture(silent=True)
            self.reload(force=True)

    def stage_preset(self, records, description):
        self.records = records
        self.current_id = None
        self.loading = True
        self.search.clear()
        self.categories.setCurrentIndex(0)
        self.loading = False
        self.mark_dirty()
        self.render()
        problems = keys.conflicts(self.records, self.values)
        message = (description + '  ·  Review the draft, then Apply changes'
                   if self.dirty else description + '  ·  Already matches your saved hotkeys')
        self.tell(message + ('\n' + '\n'.join(problems) if problems else ''), bool(problems))

    def reset_defaults(self):
        if self.busy:
            return
        self.stop_capture(silent=True)
        try:
            records = self.store.read_preset(self.store.defaults, self.baseline)
        except Exception as exc:
            self.tell('Could not load defaults: ' + str(exc), True)
            return
        prompt = QMessageBox(self)
        prompt.setWindowTitle('Reset default hotkeys?')
        prompt.setText('Load your saved default hotkeys into the editor?')
        prompt.setInformativeText(('Your pending edits will be replaced.\n\n' if self.dirty else '') +
                                  'Review the changes below, then Apply changes to activate them.')
        reset = prompt.addButton('Load defaults', QMessageBox.ButtonRole.AcceptRole)
        cancel = prompt.addButton(QMessageBox.StandardButton.Cancel)
        prompt.setDefaultButton(cancel)
        prompt.setEscapeButton(cancel)
        prompt.exec()
        if prompt.clickedButton() == reset:
            self.stage_preset(records, 'Defaults loaded')

    def save_preset(self):
        if self.busy:
            return
        self.stop_capture(silent=True)
        self.edit(refresh=False)
        path, _ = QFileDialog.getSaveFileName(self, 'Save current hotkeys as a preset',
            str(self.preset_directory / 'Xetal-hotkeys.conf'),
            'Hotkey presets (*.conf);;All files (*)', options=QFileDialog.Option.DontUseNativeDialog)
        if not path:
            return
        try:
            self.store.save_preset(path, copy.deepcopy(self.records))
            self.preset_directory = Path(path).parent
            self.tell('Saved all hotkeys to ' + path + ('  ·  Pending edits are still unapplied' if self.dirty else ''))
        except Exception as exc:
            self.tell('Could not save preset: ' + str(exc), True)

    def load_preset(self):
        if self.busy:
            return
        self.stop_capture(silent=True)
        path, _ = QFileDialog.getOpenFileName(self, 'Load hotkey preset', str(self.preset_directory),
            'Hotkey presets (*.conf);;All files (*)', options=QFileDialog.Option.DontUseNativeDialog)
        if not path:
            return
        try:
            records = self.store.read_preset(path, self.baseline)
            if self.dirty and not self.confirm_discard():
                return
            self.preset_directory = Path(path).parent
            self.stage_preset(records, 'Loaded ' + Path(path).name)
        except Exception as exc:
            self.tell('Could not load preset: ' + str(exc), True)

    def add(self):
        b = keys.Binding(uuid.uuid4().hex, 'New binding', 'Applications', True, 'SUPER', '', 'exec')
        self.records.append(b)
        self.current_id = b.id
        self.categories.setCurrentIndex(0)
        self.search.clear()
        self.mark_dirty()
        self.render()
        self.fields['key'].setFocus()

    def duplicate(self):
        selected = self.selected()
        if not selected:
            return
        b = copy.deepcopy(selected)
        b.id, b.label, b.key, b.protected = uuid.uuid4().hex, selected.label + ' (copy)', '', False
        self.records.append(b)
        self.current_id = b.id
        self.mark_dirty()
        self.render()
        self.fields['key'].setFocus()

    def remove(self):
        b = self.selected()
        if b and not b.protected:
            prompt = QMessageBox(self)
            prompt.setWindowTitle('Remove shortcut?')
            prompt.setIcon(QMessageBox.Icon.Warning)
            prompt.setTextFormat(Qt.TextFormat.PlainText)
            prompt.setText(f'Remove “{b.label}”?')
            prompt.setInformativeText(f'{b.shortcut(self.values)}\n\nThe removal takes effect only after Apply changes. You can discard it before then.')
            remove_button = prompt.addButton('Remove shortcut', QMessageBox.ButtonRole.DestructiveRole)
            cancel_button = prompt.addButton(QMessageBox.StandardButton.Cancel)
            prompt.setDefaultButton(cancel_button)
            prompt.setEscapeButton(cancel_button)
            prompt.exec()
            if prompt.clickedButton() != remove_button:
                return
            self.records.remove(b)
            self.current_id = None
            self.mark_dirty()
            self.render()

    def apply(self):
        self.edit()
        if self.busy or not self.dirty:
            return
        self.stop_capture(silent=True)
        self.busy = True
        self.setEnabled(False)
        self.tell('Validating the complete configuration…')
        def done(result):
            self.busy = False
            self.setEnabled(True)
            self.expected, backup = result
            self.dirty = False
            self.baseline = copy.deepcopy(self.records)
            self.update_changes()
            self.render()
            self.tell('Applied live  ·  No config errors  ·  Previous bindings saved in History')
        def failed(message):
            self.busy = False
            self.setEnabled(True)
            self.render()
            self.tell(message, True)
            QMessageBox.warning(self, 'Changes not applied', message)
        async_run(lambda: self.store.apply(copy.deepcopy(self.records), self.expected), done, failed)

    def confirm_discard(self):
        return QMessageBox.question(self, 'Unapplied changes', 'Discard your unapplied shortcut changes?',
                                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                                    QMessageBox.StandardButton.Cancel) == QMessageBox.StandardButton.Discard

    def begin_capture(self):
        try:
            if run(['hyprctl','submap'],timeout=2).strip() not in ('','reset','default'):
                raise RuntimeError('Another shortcut mode is active. Finish or cancel it before recording here.')
            run(['hyprctl', 'dispatch', 'submap', keys.CAPTURE_MAP], timeout=2)
        except Exception as exc:
            self.tell(str(exc), True)
            return
        widget = self.fields['key']
        widget.recording = True
        widget.setFocus()
        self.capture_timer.start(10000)
        self.capture_poll.start()
        self.tell('Recording: press your shortcut. Escape cancels; normal shortcuts return after 10 seconds.')

    def poll_capture(self):
        try:
            if run(['hyprctl', 'submap'], timeout=1).strip() != keys.CAPTURE_MAP:
                self.stop_capture()
        except Exception:
            self.stop_capture()

    def captured(self, mods, key):
        self.stop_capture(silent=True)
        self.loading = True
        self.fields['mods'].setText(mods)
        self.fields['key'].setText(key)
        self.loading = False
        self.edit()

    def stop_capture(self, *_ , silent=False):
        widget = self.fields['key']
        if not widget.recording:
            return
        widget.recording = False
        self.capture_timer.stop()
        self.capture_poll.stop()
        try:
            if run(['hyprctl','submap'],timeout=2).strip()==keys.CAPTURE_MAP:
                run(['hyprctl', 'dispatch', 'submap', 'reset'], timeout=2)
        except Exception:
            pass
        if not silent:
            self.tell('Recording cancelled. Normal shortcuts restored.')

    def hideEvent(self,event):
        self.stop_capture(silent=True)
        super().hideEvent(event)

    def render_live(self):
        self.tell('Reading bindings currently loaded by Hyprland…')
        def done(data):
            if self.categories.tabText(self.categories.currentIndex()) != 'Live':
                return
            self.loading = True
            query = self.search.text().casefold()
            rows = [b for b in data if query in json.dumps(b).casefold()]
            self.bindings_table.setHorizontalHeaderLabels(['On', 'Shortcut', 'Action / command', 'Submap'])
            self.bindings_table.setRowCount(len(rows))
            for row, b in enumerate(rows):
                mods = [name for mask, name in ((64, 'SUPER'), (4, 'CTRL'), (8, 'ALT'), (1, 'SHIFT')) if b.get('modmask', 0) & mask]
                values = ['live', ' + '.join(mods + [b.get('key') or f'code:{b.get("keycode", "?")}']),
                          b.get('dispatcher', '') + ' ' + b.get('arg', ''), b.get('submap') or 'normal']
                for col, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setToolTip(value)
                    self.bindings_table.setItem(row, col, item)
            self.loading = False
            self.tell(f'{len(data)} live bindings  ·  This view includes bindings added outside the editor')
        async_run(lambda: json.loads(run(['hyprctl', '-j', 'binds'])), done, lambda error: self.tell(error, True))

    def render_history(self):
        self.loading = True
        self.history = sorted(self.store.state.glob('keybindings-*.conf'), reverse=True)
        self.bindings_table.setHorizontalHeaderLabels(['', 'Saved backup (UTC)', 'Version', ''])
        self.bindings_table.setRowCount(len(self.history))
        for row, path in enumerate(self.history):
            for col, value in enumerate(['', path.name.removeprefix('keybindings-').removesuffix('.conf'), 'Previous bindings', '']):
                self.bindings_table.setItem(row, col, QTableWidgetItem(value))
        self.loading = False
        self.inspector.setEnabled(True)
        for widget in self.fields.values():
            widget.setEnabled(False)
        self.restore_button.show()
        self.tell('Select a backup to load it as a draft, then Apply changes to restore it.')

    def restore(self):
        row = self.bindings_table.currentRow()
        if row < 0 or row >= len(self.history):
            return
        if self.dirty and not self.confirm_discard():
            return
        try:
            self.stop_capture(silent=True)
            records = self.store.read_preset(self.history[row], self.baseline)
            self.stage_preset(records, 'Loaded backup ' + self.history[row].name)
        except Exception as exc:
            self.tell(str(exc), True)


class ControlPage(QWidget):
    def __init__(self, title, description):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(22, 18, 22, 18)
        self.layout.addWidget(label(title, 'brand'))
        self.layout.addWidget(label(description, 'muted'))
        self.status = label('Ready', 'status')
        self.status.setWordWrap(True)

    def perform(self, fn, after=None):
        self.status.setText('Working…')
        async_run(fn, lambda result: (self.status.setText('Done'), after() if after else None),
                  lambda error: self.status.setText(error))


def nm_fields(line):
    fields, current, escaped = [], '', False
    for character in line:
        if escaped:
            current += character
            escaped = False
        elif character == '\\':
            escaped = True
        elif character == ':':
            fields.append(current)
            current = ''
        else:
            current += character
    return fields + [current]


class NetworkPage(ControlPage):
    def __init__(self):
        super().__init__('Network connections', 'Wired, Wi-Fi and VPN state. Connect to a network or manage saved connections.')
        actions = QHBoxLayout()
        self.wifi = QCheckBox('Wi-Fi enabled')
        self.wifi.clicked.connect(lambda enabled: self.perform(lambda: run(['nmcli', 'radio', 'wifi', 'on' if enabled else 'off']), self.refresh))
        actions.addWidget(self.wifi)
        actions.addStretch()
        actions.addWidget(button('Saved connections / VPN', lambda: launch(['nm-connection-editor'], isolated=True)))
        actions.addWidget(button('Refresh', self.refresh))
        self.layout.addLayout(actions)
        self.devices = table(['Device', 'Type', 'State', 'Connection'])
        self.layout.addWidget(self.devices)
        self.layout.addWidget(label('AVAILABLE WI-FI NETWORKS', 'eyebrow'))
        self.networks = table(['', 'Network', 'Signal', 'Security'])
        self.networks.setColumnWidth(0, 32)
        self.networks.setColumnWidth(1, 350)
        self.layout.addWidget(self.networks, 1)
        controls = QHBoxLayout()
        controls.addWidget(button('Scan networks', lambda: self.perform(lambda: run(['nmcli', 'device', 'wifi', 'rescan']), self.refresh)))
        controls.addWidget(button('Connect selected…', self.connect_network, True))
        controls.addStretch()
        self.layout.addLayout(controls)
        self.layout.addWidget(self.status)

    def refresh(self):
        def read():
            return (run(['nmcli', '-t', '-f', 'DEVICE,TYPE,STATE,CONNECTION', 'device', 'status']),
                    run(['nmcli', 'radio', 'wifi']), run(['nmcli', '-g', 'CONNECTIVITY', 'general']),
                    run(['nmcli', '-t', '-f', 'IN-USE,SSID,SIGNAL,SECURITY', 'device', 'wifi', 'list', '--rescan', 'no']))
        def done(data):
            devices, radio, connectivity, networks = data
            self.wifi.setChecked(radio == 'enabled')
            for widget, text in ((self.devices, devices), (self.networks, networks)):
                rows = [nm_fields(line) for line in text.splitlines() if line]
                widget.setRowCount(len(rows))
                for row, fields in enumerate(rows):
                    for column, value in enumerate(fields[:4]):
                        widget.setItem(row, column, QTableWidgetItem(value))
            self.status.setText(f'Internet: {connectivity}  ·  Passwords, when needed, are requested in a terminal.')
        async_run(read, done, self.status.setText)

    def connect_network(self):
        row = self.networks.currentRow()
        if row < 0:
            self.status.setText('Select a Wi-Fi network first.')
            return
        ssid = self.networks.item(row, 1).text()
        if not ssid:
            self.status.setText('Use Saved connections for a hidden network.')
            return
        launch(['kitty', '--config', str(keys.ROOT / 'kitty.conf'), '--title', 'Connect to Wi-Fi',
                '-e', 'nmcli', '--ask', 'device', 'wifi', 'connect', ssid])
        self.status.setText('Complete the connection in the terminal, then Refresh.')


class BluetoothPage(ControlPage):
    def __init__(self):
        super().__init__('Bluetooth devices', 'Controller state and pairing controls.')
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.layout.addWidget(self.details, 1)
        actions = QHBoxLayout()
        actions.addWidget(button('Refresh', self.refresh))
        self.start_button = button('Start Bluetooth', lambda: self.perform(lambda: run(['systemctl', 'start', 'bluetooth.service'], timeout=60), self.refresh))
        actions.addWidget(self.start_button)
        actions.addWidget(button('Open device manager', lambda: launch(['blueman-manager'], isolated=True), True))
        actions.addStretch()
        self.layout.addLayout(actions)
        self.layout.addWidget(self.status)

    def refresh(self):
        def read():
            state = run(['systemctl', 'is-active', 'bluetooth.service'], check=False)
            if state != 'active':
                return 'Bluetooth service is not running.', 'Start Bluetooth to detect controllers and pair devices.', False
            controller = run(['bluetoothctl', '--timeout', '3', 'show'], timeout=4, check=False)
            devices = run(['bluetoothctl', '--timeout', '3', 'devices', 'Connected'], timeout=4, check=False)
            return controller + '\n\nConnected devices\n' + (devices or 'None'), 'Use the device manager to pair, connect or disconnect devices.', True
        async_run(read, lambda result: (self.details.setPlainText(result[0]), self.status.setText(result[1]), self.start_button.setEnabled(not result[2])), self.status.setText)


class CalendarPage(ControlPage):
    def __init__(self):
        super().__init__('Clock & calendar', 'Local time and a browsable month calendar.')
        self.clock = label('', 'metric')
        self.layout.addWidget(self.clock)
        self.calendar = QCalendarWidget()
        palette = self.calendar.palette()
        for role, color in {
            QPalette.ColorRole.Window: '#202b38', QPalette.ColorRole.WindowText: '#c4d4e5',
            QPalette.ColorRole.Base: '#141920', QPalette.ColorRole.AlternateBase: '#1b2430',
            QPalette.ColorRole.Text: '#d8e0ec', QPalette.ColorRole.Button: '#202b38',
            QPalette.ColorRole.ButtonText: '#d8e0ec', QPalette.ColorRole.Highlight: '#356a70',
            QPalette.ColorRole.HighlightedText: '#ffffff', QPalette.ColorRole.Light: '#344658',
            QPalette.ColorRole.Midlight: '#2a3746', QPalette.ColorRole.Mid: '#263343',
            QPalette.ColorRole.Dark: '#0d1219', QPalette.ColorRole.Shadow: '#080d13',
        }.items():
            palette.setColor(role, QColor(color))
        self.calendar.setPalette(palette)
        header_format = QTextCharFormat()
        header_format.setBackground(QColor('#202b38'))
        header_format.setForeground(QColor('#9eb4cc'))
        self.calendar.setHeaderTextFormat(header_format)
        for day in Qt.DayOfWeek:
            fmt = QTextCharFormat()
            fmt.setForeground(QColor('#e5a3b4' if day in (Qt.DayOfWeek.Saturday, Qt.DayOfWeek.Sunday) else '#d8e0ec'))
            self.calendar.setWeekdayTextFormat(day, fmt)
        self.calendar.setGridVisible(False)
        theme_runtime.style_calendar(self.calendar)
        self.calendar.setMinimumHeight(380)
        self.layout.addWidget(self.calendar, 1)
        self.selected = label('', 'status')
        self.calendar.selectionChanged.connect(self.selection)
        self.layout.addWidget(self.selected)
        actions = QHBoxLayout()
        actions.addWidget(button('Today', self.today))
        actions.addStretch()
        self.layout.addLayout(actions)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)
        self.tick()
        self.selection()

    def tick(self):
        from datetime import datetime
        self.clock.setText(datetime.now().astimezone().strftime('%A, %d %B  ·  %H:%M:%S %Z'))

    def selection(self):
        self.selected.setText(self.calendar.selectedDate().toString('dddd, MMMM d, yyyy'))

    def today(self):
        from PyQt6.QtCore import QDate
        self.calendar.setSelectedDate(QDate.currentDate())
        self.calendar.showToday()


class SystemPage(ControlPage):
    def __init__(self):
        super().__init__('System & session', 'Resource usage, screen capture, and session controls.')
        grid = QGridLayout()
        self.metrics = {}
        for row, name in enumerate(['CPU', 'Memory', 'Home disk']):
            grid.addWidget(label(name), row, 0)
            meter = QProgressBar()
            meter.setRange(0, 100)
            grid.addWidget(meter, row, 1)
            self.metrics[name] = meter
        self.temps = label('', 'muted')
        grid.addWidget(self.temps, 3, 0, 1, 2)
        self.layout.addLayout(grid)
        group = QGroupBox('QUICK ACTIONS')
        actions = QGridLayout(group)
        options = [('Task monitor', lambda: launch(['kitty', '--config', str(keys.ROOT / 'kitty.conf'), '-e', 'htop'])),
                   ('Capture selection', lambda: launch([str(keys.ROOT / 'scripts/screenshot.sh'), 'area'])),
                   ('Capture all displays', lambda: launch([str(keys.ROOT / 'scripts/screenshot.sh'), 'screen'])),
                   ('Notifications', lambda: launch(['swaync-client', '-t'])),
                   ('Lock screen', lambda: launch(['hyprlock', '--config', str(keys.ROOT / 'hyprlock.conf')]))]
        for index, (name, callback) in enumerate(options):
            actions.addWidget(button(name, callback), index // 3, index % 3)
        self.layout.addWidget(group)
        power = QGroupBox('POWER & SESSION')
        controls = QHBoxLayout(power)
        for text, argv in [('Suspend', ['systemctl', 'suspend']), ('Log out', ['hyprctl', 'dispatch', 'exit']),
                           ('Restart', ['systemctl', 'reboot']), ('Power off', ['systemctl', 'poweroff'])]:
            controls.addWidget(button(text, lambda _, t=text, a=argv: self.power(t, a)))
        self.layout.addWidget(power)
        self.layout.addStretch()
        self.layout.addWidget(self.status)
        self.timer = QTimer(self)
        self.timer.setInterval(2500)
        self.timer.timeout.connect(lambda: self.refresh() if self.isVisible() else None)
        self.timer.start()

    def refresh(self):
        import psutil
        self.metrics['CPU'].setValue(round(psutil.cpu_percent()))
        memory = psutil.virtual_memory()
        self.metrics['Memory'].setValue(round(memory.percent))
        self.metrics['Memory'].setFormat(f'{memory.used / 2**30:.1f} / {memory.total / 2**30:.1f} GiB  ·  %p%')
        disk = psutil.disk_usage(str(Path.home()))
        self.metrics['Home disk'].setValue(round(disk.percent))
        self.metrics['Home disk'].setFormat(f'{disk.free / 2**30:.0f} GiB free  ·  %p% used')
        temperatures = psutil.sensors_temperatures()
        self.temps.setText('   ·   '.join(f'{name}: {values[0].current:.0f}°C' for name, values in temperatures.items()
                                       if values and name in ('k10temp', 'coretemp', 'amdgpu', 'nvidia')))
        self.status.setText('Super + K opens Hotkeys  ·  Super + A opens Audio  ·  Super + N opens notifications')

    def power(self, title, argv):
        if QMessageBox.question(self, title, f'{title} this session now?', QMessageBox.StandardButton.Yes |
                                QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel) == QMessageBox.StandardButton.Yes:
            self.perform(lambda: run(argv))


class HintOverlay(QWidget):
    dismissed = pyqtSignal()

    def __init__(self, client, bindings):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle('Window shortcuts')
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.resize(650, 720)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        heading = QHBoxLayout()
        heading.addWidget(label('WINDOW UNDER POINTER', 'eyebrow'))
        heading.addStretch()
        heading.addWidget(button('×', self.close))
        layout.addLayout(heading)
        title = label(client.get('title', client.get('class', 'Window')) or 'Window', 'brand')
        title.setWordWrap(True)
        title.setMaximumHeight(60)
        title.setToolTip(client.get('title', ''))
        layout.addWidget(title)
        workspace = client.get('workspace', {}).get('name', '?')
        layout.addWidget(label(f'{client.get("class", "")}  ·  Workspace {workspace}  ·  ' +
                               ('Floating' if client.get('floating') else 'Tiled'), 'muted'))
        rows = table(['Action', 'Current shortcut'])
        self.rows = rows
        rows.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        rows.setColumnWidth(0, 330)
        values = keys.variables((keys.ROOT / 'hyprland.conf').read_text())
        relevant = [b for b in bindings if b.enabled and b.submap == 'reset' and
                    (b.category == 'Window hover' or 'movetoworkspace' in b.dispatcher)]
        data, grouped = [], {}
        for b in relevant:
            if b.dispatcher == 'exec':
                continue
            if 'movetoworkspace' in b.dispatcher and b.key in '1234567890' and len(b.key) == 1:
                signature = keys.expand(b.mods, values)
                grouped.setdefault(signature, []).append(b)
                continue
            data.append((b.label, b.shortcut(values)))
        for modifiers, matches in grouped.items():
            if {b.key for b in matches} == set('1234567890'):
                data.append(('Move to workspace 1–10', modifiers.replace(' ', ' + ') + ' + 1…0'))
            else:
                data += [(b.label, b.shortcut(values)) for b in matches]
        rows.setRowCount(len(data))
        rows.verticalHeader().setDefaultSectionSize(30)
        for row, (action, shortcut) in enumerate(data):
            rows.setItem(row, 0, QTableWidgetItem(action))
            rows.setItem(row, 1, QTableWidgetItem(shortcut))
        layout.addWidget(rows, 1)
        help_binding = next((b for b in bindings if b.enabled and '--window-hints' in b.args), None)
        help_key = help_binding.shortcut(values) if help_binding else 'Window help'
        footer = label('SUPER = Windows key  ·  Hold Super and drag with a mouse button\n' + help_key + ' toggles this overlay  ·  Super + K → Window hover edits these keys', 'status')
        footer.setWordWrap(True)
        layout.addWidget(footer)
        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)
        self.animation = QPropertyAnimation(self.effect, b'opacity', self)
        self.animation.setDuration(170)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.idle_timer = QTimer(self)
        self.idle_timer.setSingleShot(True)
        self.idle_timer.timeout.connect(self.close)
        QShortcut(QKeySequence('Escape'), self).activated.connect(self.close)
        self.show()
        self.animation.start()
        if not self.underMouse():
            self.idle_timer.start(18000)

    def enterEvent(self, event):
        self.idle_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.idle_timer.start(18000)
        super().leaveEvent(event)

    def closeEvent(self, event):
        self.idle_timer.stop()
        self.dismissed.emit()
        super().closeEvent(event)


def hovered_window():
    cursor = json.loads(run(['hyprctl', '-j', 'cursorpos']))
    monitors = json.loads(run(['hyprctl', '-j', 'monitors']))
    clients = json.loads(run(['hyprctl', '-j', 'clients']))
    x, y = cursor['x'], cursor['y']
    monitor = next((m for m in monitors if m['x'] <= x < m['x'] + m['width'] / m['scale']
                    and m['y'] <= y < m['y'] + m['height'] / m['scale']), None)
    if not monitor:
        raise RuntimeError('No monitor under the pointer.')
    special = monitor.get('specialWorkspace', {}).get('id', 0)
    workspaces = {monitor['activeWorkspace']['id']}
    if special:
        workspaces.add(special)
    candidates = []
    for client in clients:
        if not client.get('mapped') or client.get('hidden') or client.get('class') == 'hypr-control':
            continue
        if client.get('workspace', {}).get('id') not in workspaces:
            continue
        left, top = client.get('at', [0, 0])
        width, height = client.get('size', [0, 0])
        if left <= x < left + width and top <= y < top + height:
            candidates.append(client)
    if not candidates:
        raise RuntimeError('Place the pointer over a window and press Super + /.')
    return max(candidates, key=lambda c: (c.get('workspace', {}).get('id') == special,
               bool(c.get('floating')), bool(c.get('fullscreen')), -c.get('focusHistoryID', 999)))


class Window(QMainWindow):
    def __init__(self, tab='hotkeys', visible=True):
        super().__init__()
        self.setWindowTitle('Xetal / Session tools')
        self.resize(1230, 790)
        self.setMinimumSize(1040, 650)
        root = QWidget();root.setObjectName('controlRoot')
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 16, 18, 14)
        header = QHBoxLayout()
        titles = QVBoxLayout()
        self.eyebrow=label('XETAL  /  SESSION TOOLS', 'eyebrow');titles.addWidget(self.eyebrow)
        self.brand=label('Control desk', 'brand');titles.addWidget(self.brand)
        header.addLayout(titles)
        header.addStretch()
        self.header_hint=label('LIVE CONFIGURATION\nSuper + K', 'muted');header.addWidget(self.header_hint)
        self.close_button=close_button(self,title='Close Control desk')
        header.addSpacing(12);header.addWidget(self.close_button)
        layout.addLayout(header)
        self.tabs = QTabWidget()
        self.pages = {'hotkeys': Hotkeys(), 'audio': AudioPage(async_run), 'network': NetworkPage(),
                      'bluetooth': BluetoothPage(), 'displays': DisplaysPage(async_run),
                      'input': PreferencesPage('input', async_run), 'theme': ThemePage(async_run),
                      'context-menu': ContextMenuPage(async_run),
                      'calendar': CalendarPage(), 'system': SystemPage()}
        for name, page in self.pages.items():
            self.tabs.addTab(page, name.replace('-', ' ').title())
        self.tabs.currentChanged.connect(self.changed)
        content=QHBoxLayout();content.setSpacing(16)
        self.modern_rail=QWidget();self.modern_rail.setObjectName('modernRail');self.modern_rail.setFixedWidth(66)
        rail=QVBoxLayout(self.modern_rail);rail.setContentsMargins(8,12,8,12);rail.setSpacing(4)
        self.rail_avatar=Avatar(46);self.rail_avatar.clicked.connect(lambda:self.switch('home'));rail.addWidget(self.rail_avatar)
        self.rail_buttons={}
        for name in ['home',*self.pages]:
            caption=name.replace('-',' ').title();control=QPushButton();control.setObjectName('railButton');control.setCheckable(True)
            control.setFixedSize(48,42);control.setIconSize(QSize(22,22));control.setToolTip(caption);control.setAccessibleName(caption)
            control.clicked.connect(lambda _,n=name:self.switch(n));rail.addWidget(control);self.rail_buttons[name]=control
        rail.addStretch();content.addWidget(self.modern_rail);content.addWidget(self.tabs,1);layout.addLayout(content,1)
        self.home=HomePage(self.switch,async_run,launch)
        self.home.setParent(self.tabs);self.home.hide()
        self.pages['home']=self.home
        self.setCentralWidget(root)
        self.hints = None
        self.fade = None
        self.changing_design=False
        self.apply_design()
        if hasattr(QApplication.instance(),'hypr_theme'):QApplication.instance().hypr_theme.changed.connect(self.apply_design)
        # Release pages, timers and signal callbacks while Qt is still alive.
        QApplication.instance().aboutToQuit.connect(self.deleteLater)
        if visible:
            self.switch(tab)

    def switch(self, name):
        if name == 'window-hints':
            self.toggle_hints()
            return
        if name in self.pages:
            self.tabs.setCurrentWidget(self.pages[name])
            self.changed()
        self.show()
        self.raise_()
        self.activateWindow()

    def changed(self, *_):
        if getattr(self,'changing_design',False):return
        page = self.tabs.currentWidget()
        if page is None:return
        self.update_navigation()
        if hasattr(page, 'refresh'):
            page.refresh()
        if self.fade:
            self.fade.stop()
        effect = QGraphicsOpacityEffect(page)
        page.setGraphicsEffect(effect)
        self.fade = QPropertyAnimation(effect, b'opacity', self)
        self.fade.setDuration(150)
        self.fade.setStartValue(0.5)
        self.fade.setEndValue(1.0)
        self.fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.fade.start()

    def update_navigation(self):
        modern=theme_runtime.design()=='modern';current=self.tabs.currentWidget()
        name=next((name for name,page in self.pages.items() if page is current),'hotkeys')
        if modern:self.brand.setText(name.replace('-',' ').title())
        for key,control in self.rail_buttons.items():
            selected=key==name;control.setChecked(selected)
            control.setIcon(navigation_icon(key,theme_runtime.colors()['HighlightedText' if selected else 'Accent']))

    def apply_design(self):
        self.changing_design=True
        modern=theme_runtime.design()=='modern';current=self.tabs.currentWidget()
        if modern and self.tabs.indexOf(self.home)<0:self.tabs.insertTab(0,self.home,'Home')
        elif not modern and self.tabs.indexOf(self.home)>=0:
            if current is self.home:current=self.pages['hotkeys']
            self.tabs.removeTab(self.tabs.indexOf(self.home));self.home.hide()
        if current:self.tabs.setCurrentWidget(current)
        self.modern_rail.setVisible(modern);self.tabs.tabBar().setVisible(not modern)
        self.eyebrow.setVisible(not modern);self.header_hint.setVisible(not modern)
        if not modern:self.brand.setText('Control desk')
        self.rail_avatar.refresh();self.home.update_design();self.update_navigation();self.changing_design=False

    def toggle_hints(self):
        if self.hints and self.hints.isVisible():
            self.hints.close()
            return
        def show(data):
            client, bindings = data
            self.hints = HintOverlay(client, bindings)
            self.hints.dismissed.connect(lambda: QApplication.instance().quit() if not self.isVisible() else None)
        def failed(message):
            launch(['notify-send', '-a', 'Xetal Control desk', 'Window shortcuts', message])
            if not self.isVisible():
                QApplication.instance().quit()
        async_run(lambda: (hovered_window(), keys.parse((keys.ROOT / 'keybindings.conf').read_text())), show, failed)

    def closeEvent(self, event):
        hotkeys = self.pages['hotkeys']
        if hotkeys.busy or (hotkeys.dirty and not hotkeys.confirm_discard()):
            event.ignore()
            return
        if not self.pages['displays'].can_close() or any(self.pages[name].busy for name in ('input','theme','context-menu')):
            event.ignore()
            return
        unsaved = [name.replace('-', ' ').title() for name in ('displays','input','theme','context-menu') if self.pages[name].dirty]
        if unsaved and QMessageBox.question(self, 'Discard unsaved changes?',
                'Discard the draft in '+', '.join(unsaved)+' and close?',
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Discard:
            event.ignore()
            return
        hotkeys.stop_capture(silent=True)
        super().closeEvent(event)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tab', choices=['home', 'hotkeys', 'audio', 'network', 'bluetooth', 'displays', 'input', 'theme', 'context-menu', 'calendar', 'system'], default='hotkeys')
    parser.add_argument('--preview', help='Render the initial window to a PNG and exit')
    parser.add_argument('--window-hints', action='store_true')
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName('hypr-control')
    app.setDesktopFileName('hypr-control')
    theme_runtime.install(app, STYLE)
    app.setQuitOnLastWindowClosed(True)
    address = None
    if not args.preview:
        instance = os.environ.get('HYPRLAND_INSTANCE_SIGNATURE')
        if not instance:
            print('Launch Hyprland Control from the Hyprland bar or Super+K.', file=sys.stderr)
            return 1
        address = str(Path(os.environ['XDG_RUNTIME_DIR']) / 'hypr' / instance / 'control-center.sock')
        connection = QLocalSocket()
        connection.connectToServer(address)
        if connection.waitForConnected(300):
            connection.write(('window-hints' if args.window_hints else args.tab).encode())
            connection.waitForBytesWritten(500)
            connection.disconnectFromServer()
            return 0
    window = Window(args.tab, visible=not args.window_hints)
    if args.window_hints:
        QTimer.singleShot(0, window.toggle_hints)
    server = QLocalServer()
    if address:
        QLocalServer.removeServer(address)
        if not server.listen(address):
            raise RuntimeError(server.errorString())
        def incoming():
            connection = server.nextPendingConnection()
            def receive():
                name = bytes(connection.readAll()).decode().strip()
                window.switch(name)
                # Wayland may deny a generic raise; ask this compositor to focus our app.
                if name != 'window-hints':
                    subprocess.Popen(['hyprctl', 'dispatch', 'focuswindow', 'class:^(hypr-control)$'],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                connection.disconnectFromServer()
            connection.readyRead.connect(receive)
            connection.disconnected.connect(connection.deleteLater)
            if connection.bytesAvailable():
                receive()
        server.newConnection.connect(incoming)
        lifetime = QLocalSocket(app)
        lifetime.connectToServer(str(Path(address).parent / '.socket2.sock'))
        lifetime.readyRead.connect(lambda: lifetime.readAll())
        lifetime.disconnected.connect(app.quit)
    if args.preview:
        def preview():
            window.grab().save(args.preview)
            app.quit()
        QTimer.singleShot(650, preview)
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
