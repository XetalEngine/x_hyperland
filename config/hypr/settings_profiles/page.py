"""Native Fusion Settings page; expensive reads and authentication stay off UI."""
from pathlib import Path
import json
import time

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTabWidget, QLabel,
    QPushButton, QCheckBox, QLineEdit, QTreeWidget, QTreeWidgetItem, QScrollArea, QFileDialog,
    QFrame, QProgressBar, QAbstractItemView)

from . import archive, backend, catalog


def caption(text, name=None):
    label = QLabel(text); label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.PlainText)
    if name: label.setObjectName(name)
    return label


class Selection(QWidget):
    def __init__(self, changed):
        super().__init__(); layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout(); all_button = QPushButton('Select All'); none = QPushButton('Clear selection')
        row.addWidget(all_button); row.addWidget(none); layout.addLayout(row)
        self.checks = {}
        scroller = QScrollArea(); scroller.setWidgetResizable(True); scroller.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget(); items = QVBoxLayout(content); items.setContentsMargins(0, 6, 8, 6); items.setSpacing(12)
        for group in catalog.CATEGORIES:
            check = QCheckBox(group.title.replace('&', '&&')); check.setChecked(True); check.setToolTip(group.description)
            check.setAccessibleDescription(group.description); check.toggled.connect(changed)
            self.checks[group.id] = check; items.addWidget(check)
            hint = caption(group.description + ('  ·  Administrator' if group.administrator else ''), 'muted')
            hint.setIndent(23); items.addWidget(hint)
        items.addStretch(); scroller.setWidget(content); layout.addWidget(scroller)
        all_button.clicked.connect(lambda: self.select(True)); none.clicked.connect(lambda: self.select(False))

    def select(self, enabled):
        for check in self.checks.values():
            if check.isEnabled(): check.setChecked(enabled)

    def groups(self): return [key for key, check in self.checks.items() if check.isChecked() and check.isEnabled()]

    def available(self, groups):
        for key, check in self.checks.items():
            check.setEnabled(key in groups); check.setChecked(key in groups)


class Inventory(QWidget):
    def __init__(self):
        super().__init__(); box = QVBoxLayout(self); box.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit(); self.search.setPlaceholderText('Find any saved file, setting or value…')
        self.search.setClearButtonEnabled(True); self.search.setAccessibleName('Search saved settings')
        box.addWidget(self.search)
        self.tree = QTreeWidget(); self.tree.setColumnCount(2); self.tree.setHeaderLabels(['Setting / file', 'Saved value'])
        self.tree.setAlternatingRowColors(True); self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.header().setStretchLastSection(True); self.tree.setColumnWidth(0, 370)
        box.addWidget(self.tree, 1); self.summary = caption('Choose Refresh inventory to list current values.', 'muted'); box.addWidget(self.summary)
        self.search.textChanged.connect(self.filter)
        self.groups = {}; self.data = None
        self.selected = set(catalog.BY_ID)

    def populate(self, document, blobs):
        self.data = (document, blobs); self.tree.clear(); self.groups = {}
        count = 0; files = 0
        for key, path, rows in archive.values(document, blobs):
            if key not in self.groups:
                self.groups[key] = QTreeWidgetItem(self.tree, [catalog.BY_ID[key].title, ''])
            node = QTreeWidgetItem(self.groups[key], [path, f'{len(rows):,} values'])
            node.setToolTip(0, path)
            # Lazy expansion keeps large inventories responsive; filtering still
            # searches every stored value, not merely visible tree items.
            node.setData(0, Qt.ItemDataRole.UserRole, rows)
            node.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
            count += len(rows); files += 1
        for key, value in (('packages', document.get('packages')), ('system', document.get('hardware'))):
            if value is None: continue
            if key not in self.groups: self.groups[key] = QTreeWidgetItem(self.tree, [catalog.BY_ID[key].title, ''])
            if key == 'packages':
                for package in value:
                    QTreeWidgetItem(self.groups[key], [package['name'], package['version'] + ' · ' + package['source'] + (' · explicit' if package['explicit'] else ' · dependency')])
                count += len(value)
            else:
                for name, saved in value.items(): QTreeWidgetItem(self.groups[key], [name, str(saved)])
                count += len(value)
        self.tree.itemExpanded.connect(self.expand, Qt.ConnectionType.UniqueConnection) if not getattr(self, '_connected', False) else None
        self._connected = True
        self.summary.setText(f'{files:,} files · {count:,} values. Private values are included and hidden in this list.')
        self.filter(self.search.text())

    def expand(self, node):
        rows = node.data(0, Qt.ItemDataRole.UserRole)
        if rows is not None and node.childCount() == 0:
            for key, value in rows:
                child = QTreeWidgetItem(node, [key, value]); child.setToolTip(1, value)

    def filter(self, query):
        query = query.casefold().strip()
        for key, group in self.groups.items():
            visible = False
            for index in range(group.childCount()):
                item = group.child(index); rows = item.data(0, Qt.ItemDataRole.UserRole) or []
                match = (not query or query in (group.text(0) + ' ' + item.text(0) + ' ' + item.text(1)).casefold()
                         or any(query in (str(k) + ' ' + str(v)).casefold() for k,v in rows))
                item.setHidden(not match); visible |= match
            group.setHidden(not visible or key not in self.selected)
            if query and visible: group.setExpanded(True)


class DefaultSettingsPage(QWidget):
    def __init__(self, async_run):
        super().__init__(); self.async_run = async_run; self.busy = False; self.dirty = False
        self.loaded = None; self.inventory_started = False
        layout = QVBoxLayout(self); layout.setContentsMargins(16, 12, 16, 12); layout.setSpacing(12)
        layout.addWidget(caption('Your setup. Saved, restored, or fresh again.', 'brand'))
        layout.addWidget(caption('Keep the details that make Hyper Fusion yours—from individual window controls to system-wide preferences.', 'muted'))
        self.tabs = QTabWidget(); layout.addWidget(self.tabs, 1)
        self.save_tab = QWidget(); self.load_tab = QWidget(); self.reset_tab = QWidget()
        self.tabs.addTab(self.save_tab, 'Save System Settings'); self.tabs.addTab(self.load_tab, 'Load'); self.tabs.addTab(self.reset_tab, 'Reset Defaults')
        self.save_selection, self.save_inventory, save_box = self.selection_tab(self.save_tab)
        save_buttons = QHBoxLayout(); self.refresh_button = QPushButton('Refresh inventory'); self.inspect_system = QPushButton('Inspect system values…')
        self.save_button = QPushButton('Save System Settings…'); self.save_button.setObjectName('primary')
        save_buttons.addWidget(self.refresh_button); save_buttons.addWidget(self.inspect_system); save_buttons.addStretch(); save_buttons.addWidget(self.save_button)
        save_box.addLayout(save_buttons)
        save_box.addWidget(caption('The archive includes selected credentials and private preferences. Save it somewhere private. Apps are recorded as a package list; personal documents and VM disks stay in place.', 'muted'))
        load_box = QVBoxLayout(self.load_tab)
        file_row = QHBoxLayout(); self.file_label = caption('Choose a Hyper Fusion settings archive (.hfsettings).', 'muted')
        self.open_button = QPushButton('Choose archive…'); file_row.addWidget(self.file_label, 1); file_row.addWidget(self.open_button); load_box.addLayout(file_row)
        self.load_selection, self.load_inventory, _ = self.selection_tab(self.load_tab, load_box)
        self.load_selection.available([])
        self.plan_label = caption('Select what to restore. Everything else keeps its current settings.', 'muted'); load_box.addWidget(self.plan_label)
        load_buttons = QHBoxLayout(); self.review_button = QPushButton('Review package changes'); load_buttons.addWidget(self.review_button)
        load_buttons.addStretch(); self.load_button = QPushButton('Load selected settings'); self.load_button.setObjectName('primary'); load_buttons.addWidget(self.load_button); load_box.addLayout(load_buttons)
        load_box.addWidget(caption('A recovery archive is saved first. Desktop settings apply at your next sign-in; system changes may require a restart. Missing apps use available Pacman/AUR versions. AUR review opens in a terminal.', 'muted'))
        reset_box = QVBoxLayout(self.reset_tab); reset_box.setContentsMargins(26, 24, 26, 24); reset_box.setSpacing(18)
        reset_box.addWidget(caption('Return to your fresh-install setup.', 'brand'))
        reset_box.addWidget(caption('Reset every category in one action: themes, sounds, hotkeys, window sizes and positions, individual title bars, workspaces, app preferences, CPU and power settings, GRUB, firewall, services and installed applications.'))
        self.factory_label = caption('', 'status'); reset_box.addWidget(self.factory_label)
        reset_box.addWidget(caption('Your user account, documents, disks and operating system remain. A complete recovery archive is saved before changes start. Desktop preferences apply at the next sign-in; restart afterward for system and boot changes.', 'muted'))
        reset_box.addStretch()
        self.reset_button = QPushButton('Reset to defaults'); self.reset_button.setObjectName('danger'); self.reset_button.setMinimumHeight(46)
        reset_box.addWidget(self.reset_button)
        self.progress = QProgressBar(); self.progress.setRange(0, 0); self.progress.setVisible(False); layout.addWidget(self.progress)
        self.status = caption('Select the categories you want to keep.', 'status'); layout.addWidget(self.status)
        recovery = QHBoxLayout(); self.open_recovery = QPushButton('Open recovery folder'); self.cancel_button = QPushButton('Cancel pending desktop load')
        recovery.addWidget(self.open_recovery); recovery.addWidget(self.cancel_button); recovery.addStretch(); layout.addLayout(recovery)
        self.refresh_button.clicked.connect(self.refresh_inventory)
        self.inspect_system.clicked.connect(self.system_inventory)
        self.save_button.clicked.connect(self.save)
        self.open_button.clicked.connect(self.choose)
        self.load_button.clicked.connect(self.load)
        self.review_button.clicked.connect(self.review)
        self.reset_button.clicked.connect(self.reset)
        self.open_recovery.clicked.connect(self.recovery)
        self.cancel_button.clicked.connect(lambda: self.work(backend.cancel_pending, lambda message:self.status.setText(message), 'Cancelling the pending desktop change…'))
        self.refresh()

    def selection_tab(self, parent, box=None):
        box = box or QVBoxLayout(parent)
        split = QSplitter(); selection = Selection(self.changed); selection.setMinimumWidth(280)
        inventory = Inventory(); split.addWidget(selection); split.addWidget(inventory)
        split.setStretchFactor(0, 0); split.setStretchFactor(1, 1); split.setSizes([330, 650]); box.addWidget(split, 1)
        return selection, inventory, box

    def changed(self, *_):
        if not hasattr(self, 'review_button'): return
        self.save_button.setEnabled(not self.busy and bool(self.save_selection.groups()))
        self.load_button.setEnabled(not self.busy and self.loaded is not None and bool(self.load_selection.groups()))
        self.review_button.setEnabled(not self.busy and self.loaded is not None and 'packages' in self.load_selection.groups())
        for selection, inventory in ((self.save_selection, self.save_inventory), (self.load_selection, self.load_inventory)):
            inventory.selected = set(selection.groups()); inventory.filter(inventory.search.text())

    def refresh(self):
        if self.busy: return
        state = backend.factory_status(); self.factory_label.setText(state['detail'])
        self.reset_button.setEnabled(state['desktop'] and state['system'])
        self.cancel_button.setEnabled((backend.STATE/'pending.json').exists())
        result = backend.STATE/'last-result.json'
        if result.exists():
            try:
                data = json.loads(result.read_text())
                self.status.setText(('Settings loaded. ' if data.get('status') == 'complete' else 'Load stopped: ' + data.get('error', '') + ' ') + 'Recovery: ' + data.get('recovery', ''))
            except (OSError, ValueError): pass
        self.changed()
        if not self.inventory_started and self.isVisible():
            self.inventory_started = True
            self.refresh_inventory()

    def work(self, action, success, text):
        if self.busy: return
        self.busy = True; self.status.setText(text); self.progress.show(); self.tabs.setEnabled(False)
        self.open_recovery.setEnabled(False); self.cancel_button.setEnabled(False)
        def finish():
            self.busy = False; self.progress.hide(); self.tabs.setEnabled(True); self.open_recovery.setEnabled(True); self.refresh()
        def done(value): finish(); success(value)
        def failed(error): finish(); self.status.setText(str(error))
        self.async_run(action, done, failed)

    def refresh_inventory(self):
        self.inventory_started = True
        groups = self.save_selection.groups()
        if not groups: return
        self.work(lambda: backend.preview(groups), lambda data:self.show_inventory(data), 'Reading selected desktop preferences…')

    def show_inventory(self, data):
        self.save_inventory.populate(*data)
        self.status.setText('Desktop values listed. Use Inspect system values for the administrator-protected inventory; Save always reads every selected category again.')

    def system_inventory(self):
        self.inventory_started = True
        groups = self.save_selection.groups()
        if not groups: return
        self.work(lambda: backend.snapshot(groups, live=False), lambda data:self.show_inventory(data), 'Reading the selected system and desktop settings…')

    def save(self):
        groups = self.save_selection.groups()
        path, _ = QFileDialog.getSaveFileName(self, 'Save System Settings', str(Path.home()/('HyperFusion-' + time.strftime('%Y-%m-%d') + '.hfsettings')),
                                             'Hyper Fusion settings (*.hfsettings)', options=QFileDialog.Option.DontUseNativeDialog)
        if not path: return
        if not path.endswith('.hfsettings'): path += '.hfsettings'
        def done(data):
            self.save_inventory.populate(*data); self.status.setText('Settings saved to ' + path)
        self.work(lambda: backend.save(Path(path), groups), done, 'Saving your selected settings and application inventory…')

    def choose(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Load System Settings', str(Path.home()), 'Hyper Fusion settings (*.hfsettings)', options=QFileDialog.Option.DontUseNativeDialog)
        if not path: return
        # A failed second choice must not leave the previous archive actionable.
        self.loaded = None; self.load_selection.available([]); self.changed()
        def done(data):
            self.loaded = data; self.file_label.setText(path); self.load_selection.available(data[0]['categories'])
            self.load_inventory.populate(*data); self.changed(); self.status.setText('Archive verified. Select the categories to load.')
        self.work(lambda: archive.read(path), done, 'Checking the archive and every file checksum…')

    def review(self):
        if not self.loaded: return
        document, blobs = self.loaded; groups = self.load_selection.groups()
        def done(plan):
            items = ['Install: ' + (', '.join(plan['pacman'] + plan['foreign']) or 'none'), 'Remove: ' + (', '.join(plan['remove']) or 'none')]
            if plan['different_versions']: items.append(f"{len(plan['different_versions'])} installed versions differ; existing packages are not silently downgraded.")
            self.plan_label.setText('\n'.join(items))
        self.work(lambda: backend.validate_load(document, blobs, groups), done, 'Comparing the saved and installed package sets…')

    def load(self):
        if not self.loaded: return
        document, blobs = self.loaded; groups = self.load_selection.groups()
        self.work(lambda: backend.load(document, blobs, groups), self.loaded_result, 'Creating a recovery archive, then restoring the selected settings…')

    def reset(self):
        # This is the requested single action, with an automatic recovery backup.
        def action():
            document, blobs = backend.factory_snapshot()
            return backend.load(document, blobs, list(catalog.BY_ID))
        self.work(action, self.loaded_result, 'Saving recovery settings, then resetting every category to installation defaults…')

    def loaded_result(self, result):
        message = 'Ready for your next sign-in. Restart afterward for system changes.' if result['status'] == 'pending-sign-in' else 'System settings restored. Restart to finish applying them.'
        self.status.setText(message + '\nRecovery archive: ' + result['recovery'])

    def recovery(self):
        import subprocess
        folder = backend.STATE/'recovery'; folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        subprocess.Popen([str(backend.ROOT/'scripts/files.sh'), str(folder)], start_new_session=True)
