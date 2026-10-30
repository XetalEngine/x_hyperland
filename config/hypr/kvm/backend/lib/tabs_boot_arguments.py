"""Checkbox / value / description view of the shared OpenCore draft."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QCheckBox, QGridLayout, QGroupBox, QHBoxLayout,
                             QLabel, QLineEdit, QPlainTextEdit, QPushButton,
                             QVBoxLayout, QWidget)

import opencore
from boot_arguments import ArgumentsDraft


class ArgumentRow:
    def __init__(self, page, entry, index, grid):
        self.entry = entry
        self.error_key = f"boot:{index}"
        self.check = QCheckBox(entry.key)
        self.check.setChecked(entry.enabled)
        self.value = QLineEdit(entry.value or "")
        self.value.setAccessibleName(f"{entry.key} value")
        self.value.setEnabled(entry.enabled and entry.value is not None)
        self.value.setPlaceholderText("No value — switch only" if entry.value is None else "Argument value")
        spec = entry.spec
        self.description = QLabel(spec.description if spec else
                                  "Custom argument from this boot image. Its effect is not in the built-in descriptions; "
                                  "the current spelling and value are preserved. Check its driver's documentation before editing.")
        self.description.setWordWrap(True)
        self.description.setTextFormat(Qt.TextFormat.PlainText)
        self.value.setToolTip(self.description.text())
        for column, widget in enumerate((self.check, self.value, self.description)):
            grid.addWidget(widget, index + 1, column)
        self.check.toggled.connect(lambda *_: page.change(self))
        self.value.textEdited.connect(page.owner._pending)
        self.value.editingFinished.connect(lambda: page.change(self))


class BootArgumentsTab(QWidget):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.model = None
        self.rows = []
        self._building = False
        layout = QVBoxLayout(self)
        note = QLabel("Choose which arguments macOS receives at startup. The checkbox includes the argument; "
                      "the value box holds only the part after =. Switches such as -v have no value. "
                      "These edits share the Mac & OpenCore draft and take effect after Review & apply and a VM restart.")
        note.setWordWrap(True)
        layout.addWidget(note)
        actions = QHBoxLayout()
        self.load_button = QPushButton("Load OpenCore settings")
        self.load_button.clicked.connect(owner.reload)
        self.apply_button = QPushButton("Review && apply…")
        self.apply_button.setObjectName("accent")
        self.apply_button.clicked.connect(owner.apply)
        actions.addWidget(self.load_button)
        actions.addWidget(self.apply_button)
        actions.addStretch()
        layout.addLayout(actions)
        self.state = QLabel()
        self.state.setWordWrap(True)
        self.state.setTextFormat(Qt.TextFormat.PlainText)
        self.state.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.state)
        self.group = QGroupBox("macOS boot arguments")
        self.group_layout = QVBoxLayout(self.group)
        self.table = None
        layout.addWidget(self.group)
        group = QGroupBox("Arguments for the next boot")
        box = QVBoxLayout(group)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMaximumHeight(100)
        self.preview.setAccessibleName("Complete boot arguments")
        box.addWidget(self.preview)
        layout.addWidget(group)
        layout.addStretch()
        owner.updated.connect(self.refresh)
        self.refresh()

    def refresh(self):
        owner = self.owner
        self.state.setText(owner.state.text())
        self.apply_button.setText(owner.apply_button.text())
        self.apply_button.setToolTip(owner.apply_button.toolTip())
        self.apply_button.setEnabled(owner.apply_button.isEnabled() and not owner.busy)
        self.load_button.setEnabled(not owner.busy)
        self.group.setEnabled(owner.draft is not None and not owner.busy)
        if owner.draft is None:
            self.preview.clear()
            self.model = None
            return
        text = opencore.arguments(owner.draft)
        if self.model is None or self.model.render() != text.strip():
            self._build(text)
        self.preview.setPlainText(text)

    def _build(self, text):
        self._building = True
        if self.table:
            self.group_layout.removeWidget(self.table)
            self.table.hide()
            self.table.deleteLater()
        self.table = QWidget()
        grid = QGridLayout(self.table)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(14)
        grid.setColumnMinimumWidth(0, 235)
        grid.setColumnMinimumWidth(1, 180)
        grid.setColumnStretch(2, 1)
        for index, title in enumerate(("Argument", "Value", "What it does")):
            label = QLabel(title)
            font = label.font()
            font.setBold(True)
            label.setFont(font)
            grid.addWidget(label, 0, index)
        self.model = ArgumentsDraft(text)
        self.rows = [ArgumentRow(self, e, i, grid) for i, e in enumerate(self.model.entries) if e.key]
        self.group_layout.addWidget(self.table)
        self._building = False

    def change(self, row):
        if self._building or self.owner.draft is None:
            return
        entry = row.entry
        enabled = row.check.isChecked()
        row.value.setEnabled(enabled and entry.value is not None)
        value = row.value.text() if entry.value is not None else None
        old = (entry.enabled, entry.raw, entry.value)
        try:
            # Merely checking/unchecking preserves an original custom value.
            if enabled != entry.enabled or (enabled and value != entry.value):
                raw = self.model.edited_token(entry, value) if enabled and value != entry.value else entry.raw
                entry.enabled, entry.raw = enabled, raw
                if enabled:
                    entry.value = value
                text = self.model.render()
                if text != opencore.arguments(self.owner.draft):
                    opencore.set_arguments(self.owner.draft, text)
        except ValueError as exc:
            entry.enabled, entry.raw, entry.value = old
            row.value.setToolTip(str(exc))
            self.owner._invalid(row.error_key, exc)
            return
        self.owner._errors.pop(row.error_key, None)
        self.owner._input_pending = False
        self.owner._fill()
        self.owner.edited.emit()
