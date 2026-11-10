"""The attention queue inside a transfer card; file operations stay in the worker."""
from pathlib import Path

from PyQt6.QtCore import (QAbstractTableModel, QIODevice, QModelIndex, QProcess,
                         QSaveFile, QSortFilterProxyModel, Qt, pyqtSignal)
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QFileDialog, QGridLayout,
                            QHeaderView, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
                            QPushButton, QStyle, QTableView, QVBoxLayout, QWidget)


class QueueModel(QAbstractTableModel):
    def __init__(self, parent):
        super().__init__(parent)
        self.rows, self.positions = [], {}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 3

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid(): return None
        row = self.rows[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return row.get(('name', 'statusText', 'resultText')[index.column()], '')
        if role == Qt.ItemDataRole.ToolTipRole: return row.get('details', '')
        if role == Qt.ItemDataRole.UserRole: return row['id']
        if role == Qt.ItemDataRole.UserRole + 1:
            return '\n'.join(str(row.get(k, '')) for k in ('name', 'statusText', 'details', 'source', 'destination', 'resultText'))
        if row.get('status') == 'resolved' and index.column() == 1:
            if role == Qt.ItemDataRole.DecorationRole:
                return self.parent().style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton)
            if role == Qt.ItemDataRole.FontRole:
                font = QFont(); font.setBold(True); return font
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return ('Item', 'Status', 'Result / issue')[section]
        return None

    def update_rows(self, rows):
        for row in rows:
            index = self.positions.get(row['id'])
            if index is None:
                index = len(self.rows)
                self.beginInsertRows(QModelIndex(), index, index)
                self.positions[row['id']] = index; self.rows.append(row)
                self.endInsertRows()
            else:
                self.rows[index] = row
                self.dataChanged.emit(self.index(index, 0), self.index(index, 2))


class QueuePanel(QWidget):
    collapse_requested = pyqtSignal()

    def __init__(self, job, parent=None):
        super().__init__(parent)
        self.job = job
        self.report_process = None
        self.setObjectName('transferQueue')
        self.setCursor(Qt.CursorShape.ArrowCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 10, 8, 8); layout.setSpacing(7)
        self.heading = QLabel('Items needing attention', self)
        self.heading.setObjectName('queueHeading'); layout.addWidget(self.heading)
        self.summary = self.label(layout)
        self.filter = QLineEdit(self); self.filter.setClearButtonEnabled(True)
        self.filter.setPlaceholderText('Filter items, paths or issues…')
        self.filter.setAccessibleName('Filter transfer queue'); layout.addWidget(self.filter)
        self.model = QueueModel(self)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterRole(Qt.ItemDataRole.UserRole + 1)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.table = QTableView(self); self.table.setObjectName('transferIssuesTable')
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True); self.table.setWordWrap(False)
        self.table.setSortingEnabled(True); self.table.sortByColumn(-1, Qt.SortOrder.AscendingOrder)
        self.table.verticalHeader().hide(); self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.horizontalHeader().setMinimumSectionSize(48)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setMinimumHeight(100)
        layout.addWidget(self.table, 1)
        self.detail = QPlainTextEdit(self); self.detail.setObjectName('transferIssueDetails')
        self.detail.setReadOnly(True); self.detail.setFixedHeight(90)
        self.detail.setPlaceholderText('Select an item for full details and paths.')
        layout.addWidget(self.detail)
        self.similar = QCheckBox('Apply to all items with the same issue', self)
        self.similar.setToolTip('Applies to matching unfinished items. Skip also applies to later matches in this transfer.')
        layout.addWidget(self.similar)
        self.hint = self.label(layout)
        self.access = self.label(layout)
        actions = QGridLayout(); actions.setSpacing(6); layout.addLayout(actions)
        self.buttons = {}
        for column, (choice, caption) in enumerate((('retry', 'Retry'), ('skip', 'Skip item'), ('replace', 'Replace…'))):
            button = self.button(caption, lambda _=False, c=choice: self.decide(c))
            button.setObjectName('transferIssue_' + choice)
            self.buttons[choice] = button; actions.addWidget(button, 0, column)
        self.buttons['authorize'] = self.button('Use administrator access…', lambda: self.decide('authorize'))
        self.buttons['authorize'].setObjectName('transferIssue_authorize')
        actions.addWidget(self.buttons['authorize'], 1, 0, 1, 3)
        self.save = self.button('Save report…', self.choose_report)
        self.save.setObjectName('saveTransferReport'); actions.addWidget(self.save, 2, 0)
        self.cancel = self.button('Cancel transfer', lambda: self.job.request('cancel'))
        actions.addWidget(self.cancel, 2, 1)
        self.hide_button = self.button('Collapse', self.collapse_requested.emit)
        actions.addWidget(self.hide_button, 2, 2)
        self.filter.textChanged.connect(self.proxy.setFilterFixedString)
        self.table.selectionModel().selectionChanged.connect(self.refresh)
        self.similar.toggled.connect(self.refresh)
        self.job.queue_changed.connect(self.update_queue)
        self.job.changed.connect(self.refresh)
        self.update_queue(list(job.queue_rows.values()))

    def label(self, layout):
        label = QLabel(self); label.setWordWrap(True); label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(label); return label

    def button(self, caption, callback):
        button = QPushButton(caption, self); button.setMinimumHeight(28)
        button.setCursor(Qt.CursorShape.PointingHandCursor); button.clicked.connect(callback)
        return button

    def selected(self):
        return [self.model.rows[self.proxy.mapToSource(i).row()]
                for i in self.table.selectionModel().selectedRows()]

    def update_queue(self, rows):
        first = not self.model.rows
        self.model.update_rows(rows)
        if first and self.proxy.rowCount(): self.table.selectRow(0)
        self.refresh()

    def refresh(self, *_):
        state = self.job.queue_state
        done = self.job.result is not None or state.get('done', False)
        self.heading.setText(state.get('heading', 'Items needing attention'))
        self.summary.setText(state.get('summary', 'Other files keep copying while you review these items.'))
        selected = self.selected()
        pending = [r for r in selected if r.get('status') == 'pending']
        enabled = bool(pending) and not done and self.job.pending != 'cancel'
        retryable = all(r.get('retry_allowed', True) for r in pending)
        self.buttons['retry'].setEnabled(enabled and retryable)
        self.buttons['skip'].setEnabled(enabled)
        self.buttons['skip'].setText('Skip similar' if pending and self.similar.isChecked() else
                                     'Skip selected' if len(pending) > 1 else 'Skip item')
        self.buttons['replace'].setEnabled(enabled and all(r.get('replace_allowed') is True for r in pending))
        self.buttons['authorize'].setEnabled(enabled and all(str(r.get('category', '')).endswith(':permission') for r in pending))
        self.buttons['authorize'].setText('Retry as administrator' if state.get('access') == 'authorized' else 'Use administrator access…')
        self.similar.setEnabled(not done)
        self.cancel.setEnabled(not done and bool(self.job.capabilities & 1) and self.job.pending != 'cancel')
        self.save.setEnabled(bool(state.get('journal') or state.get('reportFile')) and not self.report_process)
        self.access.setText(state.get('accessText', '') if not done else '')
        self.access.setVisible(bool(self.access.text()))
        self.hint.setText('Runtime endpoints cannot be copied. Skip keeps the originals.' if not retryable else
                          'Unfinished matching items only. Skip also applies to later matches.' if self.similar.isChecked() else
                          'Selected unfinished items only. Completed copies are kept.')
        self.hint.setVisible(enabled)
        if state.get('hintText'): self.hint.setText(state['hintText'])
        text = selected[0].get('details', '') if selected else ''
        if self.detail.toPlainText() != text: self.detail.setPlainText(text)

    def decide(self, choice):
        rows = [r for r in self.selected() if r.get('status') == 'pending']
        if not rows: return
        versions = {str(r['id']): r.get('version') for r in rows}
        if choice == 'replace':
            prompt = ('Replace the destination files for all currently queued conflicts of this type?' if self.similar.isChecked()
                      else 'Replace the destination files for the selected conflicts?')
            if QMessageBox.question(self, 'Replace destination files?', prompt,
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                    QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes: return
        self.job.decide_queue([r['id'] for r in rows], choice, self.similar.isChecked(), versions)

    def choose_report(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Save transfer report', 'transfer-report.txt', 'Text files (*.txt)')
        if path: self.save_report(path)

    def save_report(self, path):
        if self.report_process or not (self.job.queue_state.get('journal') or self.job.queue_state.get('reportFile')): return
        output = QSaveFile(path)
        if not output.open(QIODevice.OpenModeFlag.WriteOnly):
            QMessageBox.warning(self, 'Could not save report', output.errorString()); return
        process = QProcess(self); self.report_process = process
        self.save.setEnabled(False); self.save.setText('Saving…')
        failed, finished = [False], [False]

        def read():
            chunk = process.readAllStandardOutput()
            if output.write(chunk) != chunk.size(): failed[0] = True; process.kill()

        def complete(success):
            if finished[0]: return
            finished[0] = True; read()
            if not success or failed[0] or not output.commit():
                output.cancelWriting()
                message = output.errorString() if failed[0] else bytes(process.readAllStandardError()).decode('utf-8', 'replace')
                QMessageBox.warning(self, 'Could not save report', message or 'The report could not be saved.')
            self.report_process = None; process.deleteLater(); self.save.setText('Save report…'); self.refresh()

        process.readyReadStandardOutput.connect(read)
        process.finished.connect(lambda code, status: complete(code == 0 and status == QProcess.ExitStatus.NormalExit))
        process.errorOccurred.connect(lambda error: complete(False) if error == QProcess.ProcessError.FailedToStart else None)
        if self.job.queue_state.get('reportFile'):
            worker = Path(__file__).resolve().parents[1] / 'archive_manager' / 'report.py'
            process.start('/usr/bin/python3', ['-I', str(worker), self.job.queue_state['reportFile'], self.job.queue_state.get('journal','')])
        else:
            worker = Path(__file__).resolve().parents[1] / 'file_manager' / 'transfer_pending.py'
            process.start('/usr/bin/python3', ['-I', str(worker), '--report', self.job.queue_state['journal']])
