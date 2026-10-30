"""Mac settings backed by a staged OpenCore configuration, never live XML edits."""

import copy
import uuid

from PyQt6.QtCore import Qt, QEventLoop, pyqtSignal
from PyQt6.QtWidgets import (QApplication, QCheckBox, QDialog, QDialogButtonBox,
                             QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                             QMessageBox, QPlainTextEdit, QProgressDialog, QPushButton,
                             QSpinBox, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
                             QStyledItemDelegate, QGridLayout, QComboBox)

import opencore
import nvidia_offline
from opencore_choices import SIP_CHOICES, SECURE_BOOT_CHOICES, sip_description, rom_address
from tabs_boot_arguments import BootArgumentsTab


class ValueDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        # Only the value column of a scalar can be edited; keys/types stay fixed.
        if index.column() != 1 or index.siblingAtColumn(0).data(Qt.ItemDataRole.UserRole) is None:
            return None
        return super().createEditor(parent, option, index)


class OpenCoreTab(QWidget):
    applied = pyqtSignal()
    edited = pyqtSignal()
    updated = pyqtSignal()

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.snapshot = None
        self.draft = None
        self._loading = False
        self.busy = False
        self._errors = {}
        self._input_pending = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        note = QLabel("Edit the Mac boot configuration. Apply creates a checked copy of the OpenCore disk "
                      "and private NVRAM; previous boot files remain available for rollback. "
                      "Validation protects file integrity, but a real boot is still needed to confirm compatibility.")
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout()
        self.load_button = QPushButton("Load OpenCore settings")
        self.load_button.clicked.connect(self.reload)
        self.apply_button = QPushButton("Review && apply…")
        self.apply_button.setObjectName("accent")
        self.apply_button.clicked.connect(self.apply)
        self.rollback_button = QPushButton("Restore previous setup…")
        self.rollback_button.clicked.connect(self.restore)
        for button in (self.load_button, self.apply_button, self.rollback_button):
            row.addWidget(button)
        row.addStretch()
        layout.addLayout(row)
        self.state = QLabel("Load the settings with the VM shut down.")
        self.state.setWordWrap(True)
        self.state.setTextFormat(Qt.TextFormat.PlainText)
        self.state.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.state)
        nvidia = QGroupBox("Offline NVIDIA driver")
        nvidia_layout = QVBoxLayout(nvidia)
        note = QLabel("Install the archived driver inside macOS without downloads. For supported Turing and newer NVIDIA GPUs "
                      "passed through in Single GPU or Dual GPU mode, on x86_64 macOS 15.5+ or 26.x. "
                      "Preparation copies OpenCore and NVRAM and attaches a read-only installer disc. "
                      "Inside macOS, run Install-NVIDIA.command; administrator authorization and restarts are required.")
        note.setWordWrap(True)
        nvidia_layout.addWidget(note)
        nvidia_row = QHBoxLayout()
        self.nvidia_button = QPushButton("Prepare offline NVIDIA installer…")
        self.nvidia_button.clicked.connect(self.prepare_nvidia)
        nvidia_row.addWidget(self.nvidia_button)
        self.nvidia_restore = QPushButton("Restore setup from before NVIDIA preparation…")
        self.nvidia_restore.clicked.connect(self.restore_nvidia)
        self.nvidia_restore.setEnabled(bool(cfg.data.get("_meta", {}).get("nvidia_offline")))
        nvidia_row.addWidget(self.nvidia_restore)
        nvidia_row.addStretch()
        nvidia_layout.addLayout(nvidia_row)
        self.nvidia_state = QLabel("Driver 2.5.3 • Local archive: macos/NVIDIA-Offline • Run Check-NVIDIA.command after restarting to verify Metal.")
        self.nvidia_state.setWordWrap(True)
        nvidia_layout.addWidget(self.nvidia_state)
        layout.addWidget(nvidia)
        self.editor = QWidget()
        body = QVBoxLayout(self.editor)
        body.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.editor)

        group = QGroupBox("OpenCore boot menu")
        form = QFormLayout(group)
        note = QLabel("NVIDIA startup options and macOS flags are on the Boot Arguments page below Mac & OpenCore.")
        note.setWordWrap(True)
        form.addRow(note)
        self.timeout = QSpinBox()
        self.timeout.setRange(0, 65535)
        self.timeout.setSuffix(" seconds")
        self.timeout.valueChanged.connect(lambda value: self._put(("Misc", "Boot", "Timeout"), value))
        form.addRow("OpenCore menu timeout", self.timeout)
        self.picker = QCheckBox("Show the OpenCore boot menu")
        self.picker.toggled.connect(lambda value: self._put(("Misc", "Boot", "ShowPicker"), value))
        form.addRow(self.picker)
        body.addWidget(group)

        details = QGridLayout()
        details.setColumnStretch(0, 1)
        details.setColumnStretch(1, 1)
        body.addLayout(details)
        group = QGroupBox("Mac identity")
        form = QFormLayout(group)
        self.identity = {}
        for key, label in [("SystemProductName", "Mac model"), ("SystemSerialNumber", "System serial"),
                           ("MLB", "Board serial (MLB)"), ("SystemUUID", "System UUID")]:
            field = QLineEdit()
            field.editingFinished.connect(lambda k=key, w=field: self._identity_changed(k, w.text()))
            form.addRow(label, field)
            self.identity[key] = field
        self.rom = QComboBox()
        self.rom.currentIndexChanged.connect(self._rom_changed)
        form.addRow("ROM identity source", self.rom)
        self.rom_value = QLineEdit()
        self.rom_value.setReadOnly(True)
        form.addRow("ROM address", self.rom_value)
        note = QLabel("ROM is a six-byte Mac identity, commonly the network adapter address. "
                      "Keep it stable for this Mac. Choosing a VM adapter copies its current address once; "
                      "it does not change the adapter or link future edits. This is not GPU firmware.")
        note.setWordWrap(True)
        form.addRow(note)
        details.addWidget(group, 0, 0, 2, 1)

        group = QGroupBox("macOS security")
        form = QFormLayout(group)
        self.sip = QComboBox()
        self.sip.currentIndexChanged.connect(self._sip_changed)
        form.addRow("System Integrity Protection", self.sip)
        self.sip_note = QLabel()
        self.sip_note.setWordWrap(True)
        form.addRow(self.sip_note)
        self.secure_boot = QComboBox()
        self.secure_boot.currentIndexChanged.connect(self._secure_boot_changed)
        form.addRow("Apple Secure Boot model", self.secure_boot)
        self.secure_boot_note = QLabel()
        self.secure_boot_note.setWordWrap(True)
        form.addRow(self.secure_boot_note)
        details.addWidget(group, 0, 1)

        group = QGroupBox("Memory description")
        form = QFormLayout(group)
        self.memory = QLabel()
        self.memory.setWordWrap(True)
        form.addRow(self.memory)
        sync = QPushButton("Sync OpenCore description to VM RAM")
        sync.clicked.connect(self._sync_memory)
        form.addRow(sync)
        details.addWidget(group, 1, 1)

        group = QGroupBox("Advanced OpenCore settings")
        form = QVBoxLayout(group)
        note = QLabel("Double-click a value to edit. Booleans use true/false; data uses hex. "
                      "Keys, value types and list structure are preserved. Enabled kexts, drivers and ACPI entries "
                      "must reference files already present in this boot image.")
        note.setWordWrap(True)
        form.addWidget(note)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Setting", "Value", "Type"])
        self.tree.setColumnWidth(0, 370)
        self.tree.setColumnWidth(1, 520)
        self.tree.setMinimumHeight(350)
        self.tree.setItemDelegate(ValueDelegate(self.tree))
        self.tree.itemChanged.connect(self._tree_changed)
        form.addWidget(self.tree)
        body.addWidget(group)
        for field in self.editor.findChildren(QLineEdit):
            field.textEdited.connect(self._pending)
        self.editor.setEnabled(False)
        self._refresh_apply_button()
        self.rollback_button.setEnabled(bool(cfg.data.get("_meta", {}).get("opencore_editor")))
        self.arguments_page = BootArgumentsTab(self)

    @property
    def dirty(self):
        return self.snapshot is not None and (self._input_pending or bool(self._errors)
                                             or self.draft != self.snapshot.config)

    def _refresh_apply_button(self):
        if self.busy:
            label, tip = "Applying…", "Wait for the current OpenCore operation to finish."
        elif self.draft is None:
            label, tip = "Review && apply…", "Load OpenCore settings with the VM shut down first."
        elif self._errors:
            label, tip = "Fix invalid values", "Fix before applying: " + "; ".join(self._errors.values())
        elif self.dirty:
            label, tip = "Review && apply…", "Review your changes before creating a verified boot-file copy."
        else:
            label, tip = "No changes to apply", "These settings already match the loaded OpenCore image. Edit a setting to enable Apply."
        self.apply_button.setText(label)
        self.apply_button.setToolTip(tip)
        self.apply_button.setEnabled(self.dirty and not self._errors and not self.busy)

    def _loaded_state(self):
        return "No changes to apply. These settings already match the loaded OpenCore image.\nLoaded: " + str(self.snapshot.image)

    def _pending(self, *_):
        self._input_pending = True
        self._refresh_apply_button()
        if not self._errors:
            self.state.setText("Unapplied OpenCore changes. Review & apply to update the boot files.")
        self.updated.emit()
        self.edited.emit()

    def flush(self):
        """Commit a focused text/tree editor before Save, switch or launch."""
        focus = QApplication.focusWidget()
        if focus and (self.editor.isAncestorOf(focus) or self.arguments_page.isAncestorOf(focus)):
            focus.clearFocus()

    def refresh_memory(self):
        if self.draft is not None:
            self.memory.setText(opencore.memory_note(self.draft, self.cfg))

    def _invalid(self, key, exc):
        self._errors[key] = str(exc)
        self._input_pending = False
        self.state.setText("Fix before applying: " + "; ".join(self._errors.values()))
        self._refresh_apply_button()
        self.updated.emit()
        self.edited.emit()

    def reload(self):
        self.flush()
        if self.dirty and QMessageBox.question(self, "Reload OpenCore", "Discard unapplied OpenCore edits?") != QMessageBox.StandardButton.Yes:
            return False
        if self.dirty:
            self._draft_path().unlink(missing_ok=True)
        try:
            self.snapshot = opencore.inspect(self.cfg)
            self.draft = copy.deepcopy(self.snapshot.config)
            self.arguments_page.model = None
            self._errors.clear()
            self._input_pending = False
            self.editor.setEnabled(True)
            self._fill()
            self.restore_draft()
            return True
        except Exception as exc:
            self.state.setText(str(exc))
            self.snapshot = self.draft = None
            self.editor.setEnabled(False)
            self._refresh_apply_button()
            self.updated.emit()
            return False

    def _draft_path(self):
        from pathlib import Path
        return Path(self.cfg.root)/'macos/opencore-draft.plist'

    def save_draft(self):
        import plistlib
        from settings_defaults import atomic_write
        if self.snapshot is None: return
        if not self.dirty:
            self._draft_path().unlink(missing_ok=True)
            return
        value = dict(image=str(self.snapshot.image), image_hash=self.snapshot.image_hash,
                     variables=str(self.snapshot.variables), vars_hash=self.snapshot.vars_hash,
                     draft=self.draft)
        self._draft_path().parent.mkdir(parents=True, exist_ok=True)
        atomic_write(self._draft_path(), plistlib.dumps(value, sort_keys=False))

    def restore_draft(self):
        import plistlib
        path = self._draft_path()
        if not path.is_file(): return
        try:
            saved = plistlib.loads(path.read_bytes())
            if (saved['image'], saved['image_hash'], saved['variables'], saved['vars_hash']) != (
                    str(self.snapshot.image), self.snapshot.image_hash,
                    str(self.snapshot.variables), self.snapshot.vars_hash):
                self.state.setText('A saved draft belongs to older boot files; it remains in '+str(path))
                return
            self.draft = saved['draft']
            self._fill()
            self.state.setText('Restored your unapplied OpenCore draft. Review & apply when ready.')
        except (ValueError, KeyError, OSError) as error:
            self.state.setText('Could not restore the OpenCore draft: '+str(error))

    def _fill(self, tree=True):
        if self.draft is None:
            return
        self._loading = True
        self.timeout.setValue(self.draft["Misc"]["Boot"]["Timeout"])
        self.picker.setChecked(self.draft["Misc"]["Boot"]["ShowPicker"])
        for key, field in self.identity.items():
            value = self.draft["PlatformInfo"]["Generic"].get(key, "")
            if key not in self._errors:
                field.setText(value.hex() if isinstance(value, bytes) else str(value))
        self._fill_choices()
        self.memory.setText(opencore.memory_note(self.draft, self.cfg))
        if tree:
            self.tree.clear()
            self._add_tree(self.tree.invisibleRootItem(), self.draft, ())
        self._loading = False
        self._refresh_apply_button()
        if self._errors:
            self.state.setText("Fix before applying: " + "; ".join(self._errors.values()))
        elif self.snapshot:
            self.state.setText("Unapplied OpenCore changes. Review & apply to update the boot files."
                               if self.dirty else self._loaded_state())
        self.updated.emit()

    @staticmethod
    def _choices(combo, choices, current):
        combo.clear()
        for label, value in choices:
            combo.addItem(label, value)
        index = next((i for i in range(combo.count()) if combo.itemData(i) == current), -1)
        if index < 0:
            combo.addItem("Custom value — preserved", current)
            index = combo.count() - 1
        combo.setCurrentIndex(index)

    def _fill_choices(self):
        current = self.draft["NVRAM"]["Add"].get(opencore.APPLE_GUID, {}).get("csr-active-config")
        saved = self.snapshot.config["NVRAM"]["Add"].get(opencore.APPLE_GUID, {}).get("csr-active-config")
        self._choices(self.sip, [("Keep loaded configuration", saved), *SIP_CHOICES], current)
        self.sip_note.setText(sip_description(current))
        current = self.draft["Misc"]["Security"]["SecureBootModel"]
        self._choices(self.secure_boot, [(label, value) for label, value, _ in SECURE_BOOT_CHOICES], current)
        self.secure_boot_note.setText(next((note for _, value, note in SECURE_BOOT_CHOICES if value == current),
                                          f"Existing model: {current}. This custom model is preserved. It defines which signed macOS versions may boot."))
        current = self.draft["PlatformInfo"]["Generic"].get("ROM", b"")
        saved = self.snapshot.config["PlatformInfo"]["Generic"].get("ROM", b"")
        choices = [("Keep loaded identity", saved)]
        for device in self.cfg.devices:
            if not device.get("netdev") or not device.get("mac"):
                continue
            try:
                address = bytes.fromhex(device["mac"].replace(":", ""))
            except (ValueError, TypeError):
                continue
            if len(address) == 6:
                choices.append((f"Use VM adapter {device.get('id', device['netdev'])} — {rom_address(address)}", address))
        self._choices(self.rom, choices, current)
        self.rom_value.setText(rom_address(current))

    def _add_tree(self, parent, value, path):
        items = value.items() if isinstance(value, dict) else enumerate(value)
        for key, child in items:
            if isinstance(key, str) and key.startswith("#"):
                continue  # OpenCore sample comments are preserved, not editable settings.
            location = (*path, key)
            container = isinstance(child, (dict, list))
            text = "" if container else self._display(child)
            item = QTreeWidgetItem(parent, [str(key), text, type(child).__name__])
            if container:
                self._add_tree(item, child, location)
            else:
                item.setData(0, Qt.ItemDataRole.UserRole, location)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)

    @staticmethod
    def _display(value):
        if isinstance(value, bytes):
            return value.hex()
        if isinstance(value, bool):
            return str(value).lower()
        return str(value)

    def _get(self, path):
        value = self.draft
        for part in path:
            value = value[part]
        return value

    def _put(self, path, value, rebuild=True):
        if self._loading or self.draft is None:
            return
        target = self.draft
        for part in path[:-1]:
            target = target[part]
        target[path[-1]] = value
        self._input_pending = False
        self._fill(tree=rebuild)
        self.edited.emit()

    def _tree_changed(self, item, column):
        if self._loading or column != 1:
            return
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path is None:
            return
        old, text = self._get(path), item.text(1)
        try:
            if isinstance(old, bool):
                if text.lower() not in ("true", "false"):
                    raise ValueError("Use true or false.")
                value = text.lower() == "true"
            elif isinstance(old, bytes):
                value = bytes.fromhex(text)
            elif isinstance(old, int):
                value = int(text, 16 if text.lower().startswith("0x") else 10)
            elif isinstance(old, str):
                value = text
            else:
                raise ValueError("This value type is read only.")
            if path == ("NVRAM", "Add", opencore.APPLE_GUID, "boot-args"):
                # An explicit Advanced edit replaces any unfinished row edits.
                self._errors = {k: v for k, v in self._errors.items() if not k.startswith("boot:")}
                self.arguments_page.model = None
            self._put(path, value, rebuild=False)
        except (ValueError, TypeError) as exc:
            self._loading = True
            item.setText(1, self._display(old))
            self._loading = False
            self.state.setText("Invalid value: " + str(exc))

    def _identity_changed(self, key, text):
        if self._loading or self.draft is None:
            return
        try:
            value = text.strip()
            if key == "SystemUUID" and value:
                uuid.UUID(value)
            self._errors.pop(key, None)
            self._put(("PlatformInfo", "Generic", key), value)
        except ValueError as exc:
            self._invalid(key, exc)

    def _sip_changed(self):
        if self._loading or self.draft is None or self.sip.currentIndex() < 0:
            return
        value = self.sip.currentData()
        target = self.draft["NVRAM"]["Add"].setdefault(opencore.APPLE_GUID, {})
        if value is None:
            target.pop("csr-active-config", None)
        else:
            target["csr-active-config"] = value
        self._fill()
        self.edited.emit()

    def _rom_changed(self):
        if not self._loading and self.rom.currentIndex() >= 0:
            self._put(("PlatformInfo", "Generic", "ROM"), self.rom.currentData())

    def _secure_boot_changed(self):
        if not self._loading and self.secure_boot.currentIndex() >= 0:
            self._put(("Misc", "Security", "SecureBootModel"), self.secure_boot.currentData())

    def _sync_memory(self):
        try:
            opencore.sync_memory(self.draft, self.cfg)
            self._fill()
            self.edited.emit()
        except (ValueError, KeyError) as exc:
            self.state.setText(str(exc))

    def apply(self):
        self.flush()
        if self.busy:
            return False
        if self._errors:
            self.state.setText("Fix before applying: " + "; ".join(self._errors.values()))
            self.updated.emit()
            return False
        if self.snapshot is None:
            self.state.setText("Load OpenCore settings with the VM shut down first.")
            self.updated.emit()
            return False
        if not self.dirty:
            self.state.setText(self._loaded_state())
            self._refresh_apply_button()
            self.updated.emit()
            return True
        self.draft = opencore.prepare_changes(self.snapshot.config, self.draft)
        dialog = QDialog(self)
        dialog.setWindowTitle("Review OpenCore changes")
        dialog.resize(850, 480)
        layout = QVBoxLayout(dialog)
        note = QLabel("A new boot image and private NVRAM will be created. The previous setup stays available. "
                      "Save current setup after applying to remember the new paths.")
        note.setWordWrap(True)
        layout.addWidget(note)
        review = QPlainTextEdit("\n".join(opencore.changes(self.snapshot.config, self.draft)))
        review.setReadOnly(True)
        layout.addWidget(review)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self.state.setText("Review canceled. Your edits are still unapplied.")
            self.updated.emit()
            return False
        self.busy = True
        self._refresh_apply_button()
        self.state.setText("Applying: validating OpenCore…")
        self.updated.emit()
        progress = QProgressDialog("Validating OpenCore", "", 0, 100, self)
        progress.setCancelButton(None)
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        def update(value, message):
            progress.setLabelText(message)
            progress.setValue(value)
            self.state.setText(f"Applying ({value}%): {message}")
            self.updated.emit()
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
        try:
            version = opencore.publish(self.cfg, self.snapshot, self.draft, update)
            self._draft_path().unlink(missing_ok=True)
            self.snapshot = None
            self.draft = None
            self.reload()
            self.state.setText(f"Applied and verified: {version.name}. Save current setup to remember this version.")
            self.rollback_button.setEnabled(True)
            self.applied.emit()
            return True
        except Exception as exc:
            self.state.setText("Not applied: " + str(exc))
            QMessageBox.warning(self, "OpenCore was not changed", str(exc))
            return False
        finally:
            progress.close()
            self.busy = False
            self._refresh_apply_button()
            self.updated.emit()

    def restore(self):
        if QMessageBox.question(self, "Restore previous setup", "Restore the preset from before the last OpenCore edit? "
                                "The installed macOS system disk is unaffected.") != QMessageBox.StandardButton.Yes:
            return
        try:
            opencore.rollback(self.cfg)
            self.snapshot = self.draft = None
            self.reload()
            self.rollback_button.setEnabled(bool(self.cfg.data.get("_meta", {}).get("opencore_editor")))
            self.applied.emit()
        except Exception as exc:
            QMessageBox.warning(self, "Restore failed", str(exc))

    def prepare_nvidia(self):
        self.flush()
        if self.busy:
            return False
        if self.dirty:
            self.nvidia_state.setText("Apply or discard your pending OpenCore edits before preparing the NVIDIA installer.")
            return False
        self.busy = True
        self._refresh_apply_button()
        self.updated.emit()
        self.nvidia_button.setEnabled(False)
        progress = QProgressDialog("Checking the local NVIDIA installer", "", 0, 100, self)
        progress.setCancelButton(None)
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        def update(value, message):
            progress.setValue(value)
            progress.setLabelText(message)
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
        try:
            directory = nvidia_offline.prepare(self.cfg, update)
            self.snapshot = self.draft = None
            self.reload()
            self.nvidia_restore.setEnabled(True)
            progress.close()
            QMessageBox.information(self, "Offline NVIDIA installer prepared",
                                    "Save current setup, then boot macOS with the NVIDIA GPU passed through.\n\n"
                                    "In Finder, open the VM2_NVIDIA disc and run Install-NVIDIA.command. "
                                    "Follow its restart instructions, then run Check-NVIDIA.command to verify acceleration.\n\n"
                                    "Original boot files and the previous preset are preserved. Setup copy:\n" + str(directory))
            self.applied.emit()
            return True
        except Exception as exc:
            self.nvidia_state.setText("Not prepared: " + str(exc))
            QMessageBox.warning(self, "NVIDIA installer was not prepared", str(exc))
            return False
        finally:
            progress.close()
            self.busy = False
            self._refresh_apply_button()
            self.nvidia_button.setEnabled(True)
            self.updated.emit()

    def restore_nvidia(self):
        self.flush()
        if self.busy or self.dirty:
            self.nvidia_state.setText("Apply or discard pending OpenCore edits before restoring a setup.")
            return False
        if QMessageBox.question(self, "Restore previous NVIDIA setup",
                                "Restore all VM settings and boot paths from before NVIDIA preparation? "
                                "Later preset changes will be discarded. Guest driver files and the macOS system disk "
                                "are unaffected; use the OpenCore recovery entry to remove a guest driver.") != QMessageBox.StandardButton.Yes:
            return False
        try:
            nvidia_offline.restore(self.cfg)
            self.snapshot = self.draft = None
            self.reload()
            self.applied.emit()
            return True
        except Exception as exc:
            QMessageBox.warning(self, "Restore failed", str(exc))
            return False
