#!/usr/bin/env python3
"""vmstart_2 - libvirt-free QEMU launcher / command line builder.

Standalone alternative to the win10 zsh function: it owns the whole sequence
itself, so ~/.zshrc stays as the known-good path.
"""

import os
import sys
import json
import shutil
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QPushButton, QTabWidget,
                             QPlainTextEdit, QLineEdit, QComboBox, QSpinBox,
                             QFormLayout, QGroupBox, QFileDialog, QMessageBox,
                             QTableWidget, QTableWidgetItem, QHeaderView,
                             QCheckBox, QScrollArea, QGridLayout, QMenu,
                             QSizePolicy, QButtonGroup)
from PyQt6.QtCore import Qt, QTimer, QSignalBlocker, QSize
from PyQt6.QtGui import QFont, QKeySequence, QPixmap, QIcon

import hostinfo
from model import (VMConfig, CPU_FEATURES, FEATURE_CHOICES, FEATURE_VENDOR,
                   LAST_STATE, PRESET_DIR, TEMPLATE)
from tabs import PinningTab, MemoryTab
from tabs_disks import DisksTab
from tabs_hw import PassthroughTab, MachineTab
from tabs_paths import PathsTab
from tabs_procedure import ProcedureTab
from tabs_tpm import TpmTab
from tabs_wizard import WizardTab
from tabs_virtual import VirtualGPUTab
from tabs_dual import DualGPUTab
from tabs_opencore import OpenCoreTab
import launcher
import virtual_gpu
import randomize
import theme
import settings_defaults
import profiles
from navigation import PageNavigation
from uiutil import guard_all, polish_page

MONO = "Monospace"


def _printable(text):
    """Show control bytes as \\xNN so a NUL in an SMBIOS string is visible."""
    return "".join(ch if ch.isprintable() else f"\\x{ord(ch):02x}" for ch in text)


def _unprintable(text):
    """Inverse of _printable, so what is typed round-trips to the real bytes."""
    import re as _re
    return _re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), text)


class VMStart2(QMainWindow):
    def __init__(self):
        super().__init__()
        self.profile_id = profiles.selected(Path(LAST_STATE).parent)
        self._windows_runtime = {name: getattr(launcher, name) for name in
                                 ("RUN_DIR", *profiles.RUNTIME_FILES)}
        self._set_runtime()
        self.cfg = self._load_initial()
        self.host = {}
        self._set_profile_title()
        self._build()
        self._detect_host()
        self._refresh_all()
        self._size_and_centre()

    # ------------------------------------------------------------- state ---
    def _paths(self, key=None):
        paths = profiles.paths(Path(LAST_STATE).parent, key or self.profile_id)
        if paths.key == "windows":
            paths = replace(paths, session=Path(LAST_STATE), presets=Path(PRESET_DIR),
                            template=Path(TEMPLATE), defaults=Path(settings_defaults.DEFAULT_STATE),
                            default_theme=Path(settings_defaults.DEFAULT_THEME), theme=Path(theme.THEME_FILE))
        return paths

    def _set_runtime(self):
        if self.profile_id == "windows":
            for name, value in self._windows_runtime.items():
                setattr(launcher, name, value)
        else:
            profiles.configure_runtime(launcher, self._paths().run)

    def _set_profile_title(self):
        self.setWindowTitle(f"Xetal - vmstart_2 · {profiles.NAMES[self.profile_id]} "
                            "(libvirt-free QEMU builder)")

    def _read_profile(self, key):
        paths = self._paths(key)
        path = paths.session if paths.session.is_file() else paths.template
        cfg = VMConfig.load(path, root=paths.root)
        profiles.check(cfg.data, key)
        return cfg

    def _load_initial(self):
        """Resume this OS profile, never another OS's session or template."""
        paths = self._paths()
        if paths.session.is_file():
            try:
                cfg = self._read_profile(self.profile_id)
                self._baseline = json.dumps(cfg.data, sort_keys=True)
                return cfg
            except Exception:
                pass
        cfg = VMConfig.load(paths.template, root=paths.root)
        profiles.check(cfg.data, self.profile_id)
        self._baseline = json.dumps(cfg.data, sort_keys=True)
        return cfg

    def switch_profile(self, key):
        if key == self.profile_id:
            return
        if (virtual_gpu.service_active()
                or any(getattr(tab, "_submitting", False) for tab in (self.tab_virtual, self.tab_dual))
                or (not virtual_gpu.status(self.tab_dual.run)
                    and time.monotonic() < self.tab_dual._submission_deadline)):
            self.profile_buttons[self.profile_id].setChecked(True)
            self.status.setText("Shut down the running VM before switching Windows / Mac.")
            return
        previous, old_cfg, old_baseline = self.profile_id, self.cfg, self._baseline
        try:
            incoming = self._read_profile(key)
            # Hook editors contain independent, unsaved text outside cfg.data.
            for editor in (self.tab_proc.start, self.tab_proc.revert):
                if editor.edit.document().isModified():
                    editor.save()
            if not self.save_session(quiet=True):
                self.profile_buttons[previous].setChecked(True)
                return
            old_baseline = self._baseline
            self.profile_id, self.cfg = key, incoming
            self._set_runtime()
            self._rebuild_tabs()
            profiles.remember(self._paths().root, key)
        except Exception as error:
            self.profile_id, self.cfg, self._baseline = previous, old_cfg, old_baseline
            self._set_runtime()
            self._rebuild_tabs()
            self.profile_buttons[previous].setChecked(True)
            QMessageBox.critical(self, "Could not switch profile", str(error))
            return
        self._baseline = json.dumps(self.cfg.data, sort_keys=True)
        self.theme_bar.use_file(self._paths().theme)
        self._set_profile_title()
        self.profile_buttons[key].setChecked(True)
        self.launch_log.clear()
        self._hist_len = -1
        self._refresh_history()
        self._update_modified()
        self.status.setText(f"{profiles.NAMES[key]} profile · {profiles.NAMES[previous]} setup saved")

    def is_modified(self):
        editor = getattr(self, "tab_opencore", None)
        return bool(editor and editor.dirty) or json.dumps(self.cfg.data, sort_keys=True) != self._baseline

    def _resolve_opencore(self):
        editor = getattr(self, "tab_opencore", None)
        if editor:
            editor.flush()
        if editor and editor.busy:
            return False
        if editor and editor.dirty:
            return editor.apply()
        return True

    def _before_mac_launch(self):
        editor = getattr(self, "tab_opencore", None)
        if editor:
            editor.flush()
        if editor and (editor.dirty or editor.busy):
            if not editor.busy:
                if editor.apply():
                    self.status.setText("OpenCore applied; review the updated setup, then click Launch VM again")
            return False
        return True

    def save_session(self, quiet=False):
        """Write last-session.json, keeping the previous one as .prev.

        The previous copy exists because a config can be damaged by a single
        mis-click and the damage is not always obvious until launch time.
        """
        if not self._resolve_opencore():
            return False
        try:
            paths = self._paths()
            profiles.check(self.cfg.data, self.profile_id)
            # Normalise first. sync() mutates the config, and if it runs after
            # the baseline is taken the app claims unsaved changes the instant
            # you save.
            self.cfg.sync()
            # Then drop the tombstones. Removal only marks entries, so without
            # this a session accumulates every disk and device it ever had:
            # names stay reserved, duplicate node-names become possible, and a
            # lookup that matches by name can find a dead entry instead of the
            # live one. compact() renumbers data['order'] as it goes, so the
            # emitted command line is unchanged and live dicts keep their
            # identity for the widgets already holding them.
            dropped = self.cfg.compact()
            if paths.session.is_file():
                shutil.copyfile(paths.session, str(paths.session) + ".prev")
            self.cfg.save(paths.session)
            self._baseline = json.dumps(self.cfg.data, sort_keys=True)
            if not quiet:
                self.status.setText(f"current setup saved ({dropped} removed entries "
                                    f"purged)" if dropped else "current setup saved")
            self._update_modified()
            return True
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))
            return False

    def revert_session(self):
        """Throw away edits and reload the last saved session."""
        paths = self._paths()
        if not paths.session.is_file():
            self.reset_template()
            return
        if QMessageBox.question(
                self, "Revert",
                "Discard every change made since the last save and reload "
                f"{profiles.NAMES[self.profile_id]}'s saved setup?") != QMessageBox.StandardButton.Yes:
            return
        self.cfg = self._read_profile(self.profile_id)
        self._baseline = json.dumps(self.cfg.data, sort_keys=True)
        self._rebuild_tabs()
        self.status.setText("reverted to last saved setup")

    def _apply_theme(self, accent, background, text):
        """Repaint everything. Goes on the QApplication, not this window, so
        the wizard, the colour dialogs and every message box match too."""
        app = QApplication.instance()
        if app is not None:
            theme.apply_to(app, accent, background, text)
        # The modified indicator picks its own colour and has to be redone
        # after a repaint, or it keeps the shade from the previous theme.
        self._update_modified()

    def _update_modified(self):
        mod = self.is_modified()
        self.lbl_modified.setText("Unsaved changes" if mod else "Setup saved")
        self.lbl_modified.setStyleSheet("color: #e5c07b; font-weight: bold;" if mod
                                        else "color: #888;")

    def closeEvent(self, e):
        if self.is_modified():
            r = QMessageBox.question(
                self, "Unsaved changes",
                "The config has changed since the last save.\n\n"
                "Save the current setup before closing?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel)
            if r == QMessageBox.StandardButton.Cancel:
                e.ignore()
                return
            if r == QMessageBox.StandardButton.Save and not self.save_session(quiet=True):
                e.ignore()
                return
        super().closeEvent(e)

    # ---------------------------------------------------------------- ui ---
    def _build(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 12, 16, 8)
        root.setSpacing(12)

        bar = QHBoxLayout()
        brand = QLabel()
        brand.setObjectName("appLogo")
        brand.setAccessibleName("Xetal Engine — QEMU launcher")
        brand.setToolTip("Xetal Engine · vmstart_2 QEMU launcher")
        brand.setFixedSize(216, 40)
        brand.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        logo = QPixmap(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "assets", "XetalEngine.png"))
        if not logo.isNull():
            ratio = self.devicePixelRatioF()
            logo = logo.scaled(round(216 * ratio), round(40 * ratio),
                               Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
            logo.setDevicePixelRatio(ratio)
            brand.setPixmap(logo)
        else:
            brand.setText("Xetal Engine")
        bar.addWidget(brand)
        bar.addSpacing(16)
        self.btn_wizard = QPushButton("Wizard")
        self.btn_wizard.setToolTip("Start guided setup. Choose whether to keep "
                                   "your configuration or reset to the captured template.")
        self.btn_wizard.setObjectName("accent")
        self.btn_wizard.clicked.connect(self._open_wizard)
        bar.addWidget(self.btn_wizard)
        self.btn_reset_defaults = QPushButton("RESET DEFAULTS")
        self.btn_reset_defaults.setToolTip(
            "Restore your saved master VM settings and appearance, after confirmation")
        self.btn_reset_defaults.clicked.connect(self.reset_defaults)
        bar.addWidget(self.btn_reset_defaults)
        bar.addSpacing(10)
        self.profile_group = QButtonGroup(self)
        self.profile_buttons = {}
        for key, label in profiles.NAMES.items():
            button = QPushButton(label)
            button.setProperty("profileSelector", True)
            button.setCheckable(True)
            button.setChecked(key == self.profile_id)
            button.setIcon(QIcon(str(Path(__file__).parent / "assets" / f"{key}.svg")))
            button.setIconSize(QSize(22, 22))
            button.setAccessibleName(f"{label} VM profile")
            button.setToolTip(f"Switch to {label}'s settings, firmware and presets. "
                              "Your current profile is saved automatically.")
            button.clicked.connect(lambda _checked, profile=key: self.switch_profile(profile))
            self.profile_group.addButton(button)
            self.profile_buttons[key] = button
            bar.addWidget(button)
        bar.addStretch()

        self.btn_save = QPushButton("Save current setup")
        self.btn_save.setToolTip("Remember this setup for the next time you open the app (Ctrl+S)")
        self.btn_save.setShortcut(QKeySequence.StandardKey.Save)
        self.btn_save.clicked.connect(self.save_session)
        bar.addWidget(self.btn_save)
        self.btn_save_preset = QPushButton("Save preset…")
        self.btn_save_preset.setToolTip("Save a named configuration you can load again later")
        self.btn_save_preset.clicked.connect(self.save_preset)
        bar.addWidget(self.btn_save_preset)
        for title, actions in (
                ("Presets", (
                    ("Load preset…", self.load_preset, "Load a named preset file"),)),
                ("Setup", (
                    ("Revert to saved setup…", self.revert_session, "Discard changes since the last save"),
                    ("Reset to captured template…", self.reset_template, "Restore the captured command line"),
                    ("Re-detect host", self.redetect, "Refresh detected host hardware")))):
            button = QPushButton(title)
            menu = QMenu(button)
            menu.setToolTipsVisible(True)
            for label, slot, tip in actions:
                action = menu.addAction(label)
                action.setToolTip(tip)
                action.triggered.connect(slot)
            button.setMenu(menu)
            bar.addWidget(button)
        root.addLayout(bar)

        content = QHBoxLayout()
        content.setSpacing(16)
        self.navigation = PageNavigation()
        self.navigation.activated.connect(self._navigate)
        content.addWidget(self.navigation)
        page = QVBoxLayout()
        self.section_jump = QComboBox()
        self.section_jump.setAccessibleName("Jump to a section on this page")
        self.section_jump.setToolTip("Jump to a section without changing any settings")
        self.section_jump.setMinimumContentsLength(14)
        self.section_jump.setMaximumWidth(200)
        self.section_jump.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.section_jump.activated.connect(self._jump_to_section)
        self.navigation.layout().addWidget(self.section_jump)

        self.tabs = QTabWidget()
        self.issue_banner = QLabel()
        self.issue_banner.setWordWrap(True)
        self.issue_banner.setStyleSheet('color:#ef5350; padding:6px;')
        self.issue_banner.hide()
        page.addWidget(self.issue_banner)
        self.tabs.setObjectName("editorPages")
        self.tabs.tabBar().hide()
        page.addWidget(self.tabs, 1)
        content.addLayout(page, 1)
        root.addLayout(content, 1)

        footer = QHBoxLayout()
        self.lbl_modified = QLabel()
        footer.addWidget(self.lbl_modified)
        self.status = QLabel()
        self.status.setObjectName("muted")
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.status.setWordWrap(True)
        footer.addWidget(self.status, 1)
        self.theme_bar = theme.ThemeBar(self._apply_theme, path=self._paths().theme)
        footer.addWidget(self.theme_bar)
        root.addLayout(footer)

        self.tab_overview = self._tab_overview()
        self.tab_cpu = self._tab_cpu()
        self.tab_pin = PinningTab(self.cfg)
        self.tab_mem = MemoryTab(self.cfg)
        self.tab_disks = DisksTab(self.cfg)
        self.tab_hw = PassthroughTab(self.cfg)
        self.tab_machine = MachineTab(self.cfg)
        self.tab_paths = PathsTab(self.cfg)
        self.tab_tpm = TpmTab(self.cfg)
        self.tab_proc = ProcedureTab(self.cfg, self._pinning,
                                     lambda: self.chk_reboot.isChecked())
        self.tab_smbios = self._tab_smbios()
        self.tab_preview = self._tab_preview()
        self.tab_wizard = WizardTab(self.cfg)
        self.tab_virtual = VirtualGPUTab(self.cfg)
        self.tab_virtual.changed.connect(self._refresh_all)
        self.tab_dual = DualGPUTab(self.cfg)
        self.tab_dual.changed.connect(self._refresh_all)
        self.tab_wizard.changed.connect(self._refresh_all)
        self.tab_wizard.goto_tab.connect(self._select_tab_by_name)
        self.tab_wizard.config_reloaded.connect(self._rebuild_tabs)

        self.tabs.addTab(self.tab_overview, "Single GPU")
        self.tabs.addTab(self.tab_cpu, "CPU Features")
        self.tabs.addTab(self.tab_pin, "CPU Pinning")
        self.tabs.addTab(self.tab_mem, "Memory")
        self.tabs.addTab(self.tab_disks, "Disks")
        self.tabs.addTab(self.tab_hw, "PCI / USB")
        self.tabs.addTab(self.tab_machine, "Machine")
        self.tabs.addTab(self.tab_smbios, "SMBIOS")
        self.tabs.addTab(self.tab_tpm, "TPM")
        # Doubled ampersand: a single & is a mnemonic and Qt eats it, which
        # rendered this tab as "Paths_Tools" with the T underlined.
        self.tabs.addTab(self.tab_paths, "Paths && Tools")
        self.tabs.addTab(self.tab_proc, "Launch Procedure")
        self.tabs.addTab(self.tab_preview, "Command Preview")
        # Keep page indices stable for launch and existing wizard links.
        self.tabs.addTab(self.tab_wizard, "Wizard")
        self.tabs.addTab(self.tab_virtual, "Virtual GPU")
        self.tabs.addTab(self.tab_dual, "Dual GPU")
        self.tab_boot_arguments = self._tab_boot_arguments()
        self.tabs.addTab(self.tab_boot_arguments, "Boot Arguments")
        self.tabs.currentChanged.connect(lambda *_: self._refresh_all())
        self.tabs.currentChanged.connect(self._page_changed)

        self.tab_pin.changed.connect(self._pinning_changed)
        self.tab_mem.changed.connect(self._refresh_all)
        self.tab_disks.changed.connect(self._refresh_all)
        self.tab_hw.changed.connect(self._refresh_all)
        self.tab_machine.changed.connect(self._refresh_all)
        self.tab_paths.changed.connect(self._refresh_all)
        self.tab_tpm.changed.connect(self._refresh_all)
        self.tabs.currentChanged.connect(self._maybe_refresh_proc)
        self._polish_pages()
        self._page_changed(self.tabs.currentIndex())

        # The dirty indicator polls rather than relying on every mutation
        # path remembering to announce itself. A stale 'unsaved' is worse
        # than useless: it trains you to ignore it.
        self._dirty_timer = QTimer(self)
        self._dirty_timer.setInterval(400)
        self._dirty_timer.timeout.connect(self._update_modified)
        self._dirty_timer.start()

    def _polish_pages(self):
        self.navigation.set_profile(self.cfg.profile)
        self.tabs.setTabVisible(self.tabs.indexOf(self.tab_tpm), self.cfg.profile != "macos")
        self.tabs.setTabVisible(self.tabs.indexOf(self.tab_boot_arguments), self.cfg.profile == "macos")
        self.tab_virtual.before_launch = self._before_mac_launch
        self.tab_dual.before_launch = self._before_mac_launch
        for i in range(self.tabs.count()):
            polish_page(self.tabs.widget(i))
        guard_all(self)

    def _navigate(self, name):
        if name == "Wizard":
            self._open_wizard()
        else:
            self._select_tab_by_name(name)

    def _page_changed(self, index):
        key = self.tabs.tabText(index)
        self.navigation.select(key)
        self._refresh_sections()
        editor = getattr(self, "tab_opencore", None)
        if key in ("SMBIOS", "Boot Arguments") and editor and not editor.snapshot:
            editor.reload()
        elif key in ("SMBIOS", "Boot Arguments") and editor:
            editor.refresh_memory()

    def _tab_boot_arguments(self):
        return self._scroll(self.tab_opencore.arguments_page) if self.tab_opencore else QWidget()

    def _refresh_sections(self):
        if not hasattr(self, "tab_wizard"):
            return
        page = self.tabs.currentWidget()
        sections = page.findChildren(QGroupBox) if isinstance(page, QScrollArea) else []
        # Match the visual order, including cards arranged in columns.
        sections.sort(key=lambda w: (w.mapTo(page.widget(), w.rect().topLeft()).y(),
                                     w.mapTo(page.widget(), w.rect().topLeft()).x()))
        entries = [(box, box.title()) for box in sections]
        if entries != getattr(self, "_section_entries", None):
            self._section_entries = entries
            self.section_jump.clear()
            self.section_jump.addItem("Jump to section…")
            for box, title in entries:
                self.section_jump.addItem(title)
        self.section_jump.setVisible(bool(entries))

    def _jump_to_section(self, index):
        section = (self._section_entries[index - 1][0]
                   if 0 < index <= len(self._section_entries) else None)
        page = self.tabs.currentWidget()
        if section is not None and isinstance(page, QScrollArea):
            parent = section.parentWidget()
            while parent is not None and parent is not page:
                if isinstance(parent, QScrollArea):
                    page = parent
                    break
                parent = parent.parentWidget()
            # Align the title, not the middle of a potentially very tall card.
            y = section.mapTo(page.widget(), section.rect().topLeft()).y()
            page.verticalScrollBar().setValue(max(0, y - 12))
            page.horizontalScrollBar().setValue(0)
        self.section_jump.setCurrentIndex(0)

    def _scroll(self, inner):
        s = QScrollArea()
        s.setWidgetResizable(True)
        s.setWidget(inner)
        return s

    # -- overview -----------------------------------------------------------
    def _tab_overview(self):
        w = QWidget()
        lay = QVBoxLayout(w)

        self.host_box = QGroupBox("Detected host")
        hb = QGridLayout(self.host_box)
        hb.setContentsMargins(8, 4, 8, 6)
        hb.setVerticalSpacing(3)
        self.lbl_cpu = QLabel("...")
        self.lbl_topo = QLabel("...")
        self.lbl_ccd = QLabel("...")
        self.lbl_gpu = QLabel("...")
        self.lbl_disks = QLabel("...")
        self.lbl_misc = QLabel("...")
        for label in (self.lbl_cpu, self.lbl_ccd, self.lbl_gpu, self.lbl_misc):
            label.setWordWrap(True)
        # Two columns: the labels are short and the values are one line each, so
        # a single column wasted half the width and pushed everything down.
        left = (("CPU", self.lbl_cpu), ("Cores / threads", self.lbl_topo),
                ("L3 groups (CCDs)", self.lbl_ccd))
        right = (("GPUs", self.lbl_gpu), ("Disks", self.lbl_disks),
                 ("Bridges", self.lbl_misc))
        for r, (k, v) in enumerate(left):
            key = QLabel(k + ":")
            key.setStyleSheet("color: #888;")
            hb.addWidget(key, r, 0)
            hb.addWidget(v, r, 1)
        for r, (k, v) in enumerate(right):
            key = QLabel(k + ":")
            key.setStyleSheet("color: #888;")
            hb.addWidget(key, r, 2)
            hb.addWidget(v, r, 3)
        hb.setColumnStretch(1, 1)
        hb.setColumnStretch(3, 1)

        # --- launch ---------------------------------------------------------
        lb = QGroupBox("Launch")
        ll = QVBoxLayout(lb)
        note = QLabel(
            "Launching stops the display manager and rebinds the GPU, so this "
            "window disappears. QEMU is handed to systemd as the transient unit "
            "<b>vmstart2-vm</b> so it outlives the desktop. Preflight runs first "
            "and refuses to tear anything down if the config cannot start.")
        note.setWordWrap(True)
        ll.addWidget(note)

        opts = QHBoxLayout()
        self.chk_reboot = QCheckBox("Reboot the host when the guest shuts down")
        self.chk_reboot.setChecked(self.cfg.data.get("single_gpu", {}).get("reboot_after", True))
        self.chk_reboot.toggled.connect(lambda value: self.cfg.data.setdefault("single_gpu", {}).__setitem__("reboot_after", value))
        self.chk_reboot.setToolTip(
            "Restoring the host display after a single-GPU passthrough is "
            "unreliable. Rebooting is what actually works.")
        opts.addWidget(self.chk_reboot)
        opts.addStretch()
        ll.addLayout(opts)

        row = QHBoxLayout()
        b = QPushButton("Preflight check")
        b.setToolTip("Run every check without changing anything")
        b.clicked.connect(lambda: self._launch(dry=True))
        row.addWidget(b)

        b = QPushButton("Test QEMU (no GPU)")
        b.setToolTip("Start the real command line paused, minus the GPU and USB "
                     "passthrough, then quit. Proves every backend that can fail "
                     "while the desktop is still up.")
        b.clicked.connect(self._test_run)
        row.addWidget(b)

        b = QPushButton("Write launch script only")
        b.setToolTip(f"Generate {os.path.join('run', 'launch.sh')} without running it")
        b.clicked.connect(self._write_launch_script)
        row.addWidget(b)

        self.btn_launch = QPushButton("Launch VM")
        self.btn_launch.setMinimumHeight(38)
        self.btn_launch.setMinimumWidth(160)
        self.btn_launch.setObjectName("accentBig")
        self.btn_launch.clicked.connect(lambda: self._launch(dry=False))
        row.insertWidget(0, self.btn_launch)
        row.addStretch()
        ll.addLayout(row)

        self.launch_log = QPlainTextEdit()
        self.launch_log.setReadOnly(True)
        self.launch_log.setFont(QFont(MONO, 10))
        self.launch_log.setMinimumHeight(130)
        self.launch_log.setMaximumHeight(180)
        self.launch_log.setPlaceholderText("Preflight checks, QEMU tests, and launch output appear here.")
        ll.addWidget(self.launch_log)
        lay.addWidget(lb)
        lay.addWidget(self.host_box)

        # --- history -----------------------------------------------------------
        hb = QGroupBox("VM history and output")
        hl = QVBoxLayout(hb)
        hnote = QLabel("Launch and QEMU output, grouped by run. No sudo is needed to read this log.")
        hnote.setWordWrap(True)
        hl.addWidget(hnote)

        hrow = QHBoxLayout()
        self.chk_follow = QCheckBox("Follow (refresh every 2s)")
        self.chk_follow.setChecked(True)
        hrow.addWidget(self.chk_follow)
        b = QPushButton("Refresh now")
        b.clicked.connect(self._refresh_history)
        hrow.addWidget(b)
        b = QPushButton("Jump to last run")
        b.setToolTip("Scroll to the most recent VM STARTED banner")
        b.clicked.connect(self._jump_last_run)
        hrow.addWidget(b)
        b = QPushButton("Clear history")
        b.setToolTip(f"Empty {launcher.LOG}")
        b.clicked.connect(self._clear_history)
        hrow.addWidget(b)
        hrow.addStretch()
        self.lbl_runs = QLabel("")
        hrow.addWidget(self.lbl_runs)
        hl.addLayout(hrow)

        self.history = QPlainTextEdit()
        self.history.setReadOnly(True)
        self.history.setFont(QFont(MONO, 9))
        self.history.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.history.setMinimumHeight(260)
        hl.addWidget(self.history, 1)
        lay.addWidget(hb, 2)

        self._hist_timer = QTimer(self)
        self._hist_timer.setInterval(2000)
        self._hist_timer.timeout.connect(self._tick_history)
        self._hist_timer.start()
        self._hist_len = -1
        self._refresh_history()
        return self._scroll(w)

    def _maybe_refresh_proc(self, idx):
        if self.tabs.widget(idx) is getattr(self, "tab_proc", None):
            self.tab_proc.refresh()

    # -- history --------------------------------------------------------------
    def _tick_history(self):
        # Only touch the widget when the file actually grew, so following does
        # not fight the scrollbar while you are reading.
        if not self.chk_follow.isChecked():
            return
        try:
            size = os.path.getsize(launcher.LOG) if os.path.isfile(launcher.LOG) else 0
        except OSError:
            return
        if size != self._hist_len:
            self._refresh_history()

    def _refresh_history(self):
        text = launcher.read_log()
        self._hist_len = len(text.encode(errors="replace")) if text else 0
        try:
            self._hist_len = os.path.getsize(launcher.LOG)
        except OSError:
            pass
        at_bottom = (self.history.verticalScrollBar().value()
                     >= self.history.verticalScrollBar().maximum() - 4)
        self.history.setPlainText(text or "(no runs recorded yet)")
        runs = text.count("=============== VM STARTED")
        self.lbl_runs.setText(f"{runs} run{'s' if runs != 1 else ''}   "
                              f"{os.path.basename(launcher.LOG)}")
        if at_bottom:
            sb = self.history.verticalScrollBar()
            sb.setValue(sb.maximum())

    def _jump_last_run(self):
        text = self.history.toPlainText()
        i = text.rfind("=============== VM STARTED")
        if i < 0:
            return
        c = self.history.textCursor()
        c.setPosition(i)
        self.history.setTextCursor(c)
        self.history.centerCursor()

    def _clear_history(self):
        if QMessageBox.question(
                self, "Clear history",
                f"Empty {launcher.LOG}?\n\nEvery recorded run is discarded."
                ) != QMessageBox.StandardButton.Yes:
            return
        launcher.clear_log()
        self._refresh_history()
        self.status.setText("history cleared")

    # -- launch ---------------------------------------------------------------
    def _pinning(self):
        return self.cfg.data.get("pinning") or {}

    def _open_wizard(self):
        self.navigation.select("Wizard")
        self._select_tab_by_name("Wizard")
        self.tab_wizard._start_over()
        self.tab_wizard.btn_next.setFocus(Qt.FocusReason.OtherFocusReason)

    def _select_tab_by_name(self, name):
        if ((self.cfg.profile == "macos" and name == "TPM") or
                (self.cfg.profile != "macos" and name == "Boot Arguments")):
            return
        # Ampersands are stripped on both sides so a caller can ask for
        # "Paths & Tools" without knowing the label carries a doubled & to
        # stop Qt reading it as a mnemonic.
        want = ("Single GPU" if name == "Overview" else name).replace("&", "")
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i).replace("&", "") == want:
                self.tabs.setCurrentIndex(i)
                return

    def _write_launch_script(self):
        try:
            path, text = launcher.write_script(
                self.cfg, self._pinning(),
                standalone=self.chk_standalone.isChecked(),
                reboot_after=self.chk_reboot.isChecked())
        except Exception as e:
            self.launch_log.setPlainText(f"could not build script: {e}")
            return
        self.launch_log.setPlainText(f"wrote {path}\n\n{text}")
        self.status.setText("launch script written")

    def _test_run(self):
        """Prove the command line without tearing anything down."""
        self.tabs.setCurrentIndex(0)
        if virtual_gpu.service_active():
            self.launch_log.setPlainText("A VM is already running or stopping. Shut it down before testing "
                                         "the same disks and firmware state.")
            return
        self.launch_log.setPlainText("running test (this takes a few seconds)...")
        self.status.setText("testing")
        QApplication.processEvents()
        try:
            ok, out = launcher.test_run(
                self.cfg, standalone=self.chk_standalone.isChecked())
        except Exception as e:
            self.launch_log.setPlainText(f"test could not run: {e}")
            return
        head = ("TEST PASSED - QEMU initialised every backend and exited cleanly.\n"
                "Only the GPU and USB passthrough are untested; they need the "
                "display torn down.\n\n"
                if ok else
                "TEST FAILED - this is what the real launch would hit, with your "
                "desktop still up.\n\n")
        self.launch_log.setPlainText(head + out)
        self.status.setText("test passed" if ok else "test FAILED")

    def _launch(self, dry):
        if not dry and not self._before_mac_launch():
            return
        self.tabs.setCurrentIndex(0)
        checks = launcher.preflight(self.cfg, self._pinning())
        if virtual_gpu.service_active():
            checks.insert(0, ("error", "A VM is already running or stopping. Shut it down before launching again."))
        errors = [m for s, m in checks if s == "error"]
        warns = [m for s, m in checks if s == "warn"]

        lines = []
        for sev, msg in checks:
            lines.append(f"[{sev.upper():5}] {msg}")
        if not checks:
            lines.append("nothing to report")
        self.launch_log.setPlainText("\n".join(lines))

        if dry:
            self.status.setText(
                f"preflight: {len(errors)} errors, {len(warns)} warnings")
            return

        if errors:
            QMessageBox.critical(
                self, "Cannot launch",
                "Preflight found problems that would stop the VM from starting:\n\n"
                + "\n".join(f"• {e}" for e in errors[:8])
                + "\n\nNothing has been changed.")
            return

        body = ("This will:\n"
                "  • allocate hugepages\n"
                "  • stop the display manager and kill the desktop\n"
                "  • unbind the GPU from nvidia and bind it to vfio-pci\n"
                "  • start QEMU under systemd\n\n")
        if self.chk_reboot.isChecked():
            body += "The host will REBOOT when the guest shuts down.\n\n"
        if warns:
            body += "Warnings:\n" + "\n".join(f"  • {x}" for x in warns[:6]) + "\n\n"
        body += "This screen will go black. Continue?"

        if QMessageBox.warning(
                self, "Launch VM", body,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Yes:
            self.status.setText("launch cancelled")
            return

        # Save before anything is torn down: the desktop is about to die, and an
        # unsaved config would go with it.
        if not self.save_session(quiet=True):
            return
        try:
            self.cfg.save(self._paths().presets / "last-launched.json")
        except Exception:
            pass

        ok, out, path = launcher.launch(
            self.cfg, self._pinning(),
            standalone=self.chk_standalone.isChecked(),
            reboot_after=self.chk_reboot.isChecked())
        self.launch_log.appendPlainText(
            f"\n--- systemd-run ---\n{out}\n\nscript: {path}\nlog: {launcher.LOG}")
        if not ok:
            QMessageBox.critical(self, "Launch failed",
                                 f"systemd-run refused to start the unit:\n\n{out}")
        else:
            self.status.setText("launched as vmstart2-vm")

    # -- cpu features -------------------------------------------------------
    def _make_feature_table(self):
        t = QTableWidget(0, 3)
        t.setObjectName('cpuFeatureTable')
        t.setStyleSheet('QTableWidget#cpuFeatureTable::item { padding: 0 8px; }')
        t.setHorizontalHeaderLabels(["Feature", "State", "What it does"])
        t.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        t.setColumnWidth(0, 130)
        t.setColumnWidth(1, 150)
        t.verticalHeader().setVisible(False)
        t.verticalHeader().setMinimumSectionSize(34)
        t.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        return t

    def _tab_cpu(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        model_box = QGroupBox("Guest CPU")
        model_form = QFormLayout(model_box)
        self.cpu_model = QLineEdit()
        self.cpu_model.setPlaceholderText("host, Penryn, …")
        self.cpu_model.textEdited.connect(self._set_cpu_model)
        model_form.addRow("CPU model:", self.cpu_model)
        self.cpu_vendor = QLineEdit()
        self.cpu_vendor.setPlaceholderText("Model default")
        self.cpu_vendor.textEdited.connect(self._set_cpu_vendor)
        model_form.addRow("Vendor ID:", self.cpu_vendor)
        lay.addWidget(model_box)
        lay.addWidget(QLabel(
            "CPU settings belong to the selected OS profile. Changing the model "
            "keeps the feature overrides below. AMD and Intel extensions must "
            "match the guest CPU configuration."))

        # Full-width tables leave room to read what each feature does.
        top = QVBoxLayout()
        self.feat_amd = self._make_feature_table()
        self.feat_intel = self._make_feature_table()
        for title, table in (("AMD", self.feat_amd), ("Intel", self.feat_intel)):
            box = QGroupBox(title)
            bl = QVBoxLayout(box)
            bl.setContentsMargins(4, 4, 4, 4)
            bl.addWidget(table)
            top.addWidget(box)
        lay.addLayout(top)

        uni_box = QGroupBox("Universal (both vendors)")
        ul = QVBoxLayout(uni_box)
        ul.setContentsMargins(4, 4, 4, 4)
        self.feat_uni = self._make_feature_table()
        ul.addWidget(self.feat_uni)
        lay.addWidget(uni_box, 1)
        return self._scroll(w)

    def _set_cpu_model(self, value):
        self.cfg.data["cpu"]["model"] = value.strip()
        self._refresh_all()

    def _set_cpu_vendor(self, value):
        if value.strip():
            self.cfg.cpu_features["vendor"] = value.strip()
        else:
            self.cfg.cpu_features.pop("vendor", None)
        self._refresh_all()

    # -- pinning ------------------------------------------------------------
    # -- smbios -------------------------------------------------------------
    def _tab_smbios(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        actions = QHBoxLayout()
        self.smbios_blob_actions = []
        self.btn_apply_smbios = QPushButton("Apply SMBIOS Identity")
        self.btn_apply_smbios.setObjectName("accent")
        self.btn_apply_smbios.setToolTip(
            "Build the output blob from these values for the next VM launch.")
        self.btn_apply_smbios.clicked.connect(lambda: self._smbios_run(False))
        actions.addWidget(self.btn_apply_smbios)
        self.smbios_blob_actions.append(self.btn_apply_smbios)
        for text, slot, tip in (
                ("Dry run", lambda: self._smbios_run(True),
                 "Show what would be patched without writing the blob"),
                ("Regenerate all fields", self._smbios_regen_all,
                 "Give every enabled field a new random value of the same length and shape"),
                ("New System UUID", self._smbios_new_uuid,
                 "Generate a fresh SMBIOS System UUID"),
                ("Reload defaults", self._smbios_reload_defaults,
                 "Re-read presets/smbios-default.json, discarding edits")):
            button = QPushButton(text)
            button.setToolTip(tip)
            button.clicked.connect(slot)
            actions.addWidget(button)
            self.smbios_blob_actions.append(button)
        actions.addStretch()
        lay.addLayout(actions)
        self.smbios_help = QLabel(
            "Apply SMBIOS Identity builds the file for the next VM launch. "
            "Save current setup remembers your edits. The template stays unchanged.")
        self.smbios_help.setWordWrap(True)
        self.smbios_help.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.smbios_blob_help = self.smbios_help.text()
        lay.addWidget(self.smbios_help)

        identity_box = QGroupBox("Template and system identity")
        f = QFormLayout(identity_box)
        self.ed_tpl = QLineEdit()
        self.ed_out = QLineEdit()
        self.ed_uuid = QLineEdit()
        self.ed_tpl.setToolTip("The pristine dump. Never written to.")
        self.ed_out.setToolTip("Where the patched blob goes. Should match the "
                               "-smbios file= path on the Paths & Tools tab.")
        self.ed_uuid.setToolTip("Type 1 System UUID. This is what the guest reports "
                                "from 'wmic csproduct get uuid', and it overrides "
                                "-uuid.")
        for widget, key in ((self.ed_tpl, "template_blob"),
                            (self.ed_out, "output_blob"),
                            (self.ed_uuid, "system_uuid")):
            widget.textEdited.connect(
                lambda v, k=key: (self._smbios_cfg().__setitem__(k, v.strip()),
                                  self._update_modified()))
        f.addRow("Template blob (read only):", self.ed_tpl)
        f.addRow("Output blob:", self.ed_out)

        urow = QHBoxLayout()
        urow.addWidget(self.ed_uuid, 1)
        ub = QPushButton("Generate")
        ub.setFixedWidth(90)
        ub.setToolTip("Random UUID v4")
        ub.clicked.connect(self._smbios_new_uuid)
        urow.addWidget(ub)
        uholder = QWidget()
        uholder.setLayout(urow)
        f.addRow("System UUID:", uholder)
        lay.addWidget(identity_box)

        model_box = QGroupBox("Manufacturer and model")
        model_form = QFormLayout(model_box)
        self.chk_manufacturer_model = QCheckBox("Use these manufacturer and model values")
        self.chk_manufacturer_model.toggled.connect(self._toggle_manufacturer_model)
        model_form.addRow(self.chk_manufacturer_model)
        self.ed_manufacturer = QLineEdit()
        self.ed_manufacturer.setAccessibleName("SMBIOS manufacturer")
        self.ed_product_model = QLineEdit()
        self.ed_product_model.setAccessibleName("SMBIOS model or product")
        for editor in (self.ed_manufacturer, self.ed_product_model):
            editor.textEdited.connect(lambda _text: self._edit_manufacturer_model(finished=False))
            editor.editingFinished.connect(self._edit_manufacturer_model)
        model_form.addRow("Manufacturer:", self.ed_manufacturer)
        model_form.addRow("Model / product:", self.ed_product_model)
        self.manufacturer_model_note = QLabel()
        self.manufacturer_model_note.setWordWrap(True)
        model_form.addRow(self.manufacturer_model_note)
        lay.addWidget(model_box)

        # ---- Type 0, edited as fields rather than as byte patches -------------
        # A byte patch cannot change a string's length; Type 0 is rewritten
        # structurally instead, so "3.06" can become "F.42a" without corrupting
        # every structure behind it.
        t0box = QGroupBox("BIOS Information (SMBIOS Type 0)")
        t0g = QGridLayout(t0box)
        t0g.setContentsMargins(8, 4, 8, 6)
        t0g.setHorizontalSpacing(6)
        t0g.setVerticalSpacing(3)
        note = QLabel("What the guest reports as its BIOS. Blank means leave the "
                      "template's value alone.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #888;")
        t0g.addWidget(note, 0, 0, 1, 4)

        self.ed_bios_vendor = QLineEdit()
        self.ed_bios_vendor.setToolTip(
            "Type 0 Vendor. Win32_BIOS.Manufacturer. Should match the board "
            "vendor claimed in Type 2.")
        self.ed_bios_version = QLineEdit()
        self.ed_bios_version.setToolTip(
            "Type 0 BIOS Version. Win32_BIOS.SMBIOSBIOSVersion. Keep it in step "
            "with PcdFirmwareVersionString in the OVMF build, which is measured "
            "into PCR 0 as EV_S_CRTM_VERSION.")
        self.ed_bios_date = QLineEdit()
        self.ed_bios_date.setToolTip(
            "Type 0 BIOS Release Date, MM/DD/YYYY. Win32_BIOS.ReleaseDate.")
        t0g.addWidget(QLabel("Vendor:"), 1, 0)
        t0g.addWidget(self.ed_bios_vendor, 1, 1, 1, 3)
        t0g.addWidget(QLabel("BIOS version:"), 2, 0)
        t0g.addWidget(self.ed_bios_version, 2, 1)
        t0g.addWidget(QLabel("Release date:"), 2, 2)
        t0g.addWidget(self.ed_bios_date, 2, 3)

        self.sp_bios_major = QSpinBox()
        self.sp_bios_major.setRange(0, 255)
        self.sp_bios_minor = QSpinBox()
        self.sp_bios_minor.setRange(0, 255)
        for s in (self.sp_bios_major, self.sp_bios_minor):
            s.setFixedWidth(70)
            s.setToolTip("System BIOS Release, reported separately from the "
                         "version string. Shown by dmidecode as 'BIOS Revision'.")
        rrow = QHBoxLayout()
        rrow.setContentsMargins(0, 0, 0, 0)
        rrow.addWidget(self.sp_bios_major)
        rrow.addWidget(QLabel("."))
        rrow.addWidget(self.sp_bios_minor)
        rrow.addStretch()
        rh = QWidget()
        rh.setLayout(rrow)
        t0g.addWidget(QLabel("BIOS revision:"), 3, 0)
        t0g.addWidget(rh, 3, 1)

        rb = QPushButton("Read from template")
        rb.setToolTip("Load the pristine dump's own Type 0 values into these "
                      "fields, so you can edit from what the real board reports.")
        rb.clicked.connect(self._smbios_read_type0)
        t0g.addWidget(rb, 3, 3)

        for wdg in (self.ed_bios_vendor, self.ed_bios_version, self.ed_bios_date):
            wdg.textEdited.connect(self._push_type0)
        for s in (self.sp_bios_major, self.sp_bios_minor):
            s.valueChanged.connect(self._push_type0)
        t0g.setColumnStretch(1, 1)
        t0g.setColumnStretch(3, 1)
        lay.addWidget(t0box)

        self.smbios_table = QTableWidget(0, 5)
        self.smbios_table.setHorizontalHeaderLabels(
            ["On", "Field", "Original", "Guest value (double-click to edit)", ""])
        hh = self.smbios_table.horizontalHeader()
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.smbios_table.setColumnWidth(0, 40)
        self.smbios_table.setColumnWidth(1, 170)
        self.smbios_table.setColumnWidth(2, 220)
        # Ask the button how wide it needs to be rather than guessing: 90 px
        # clipped "Regenerate" to "Regenerat", and any font or theme change
        # moves the number again.
        self.smbios_table.setColumnWidth(
            4, QPushButton("Regenerate").sizeHint().width() + 16)
        self.smbios_table.itemChanged.connect(self._smbios_item_changed)
        patches_box = QGroupBox("Identity fields and byte patches")
        patches_layout = QVBoxLayout(patches_box)
        patch_help = QLabel(
            "Edit the manufacturer and model in the fields above. Double-click a guest "
            "value below to edit serial numbers or other identity fields. Save current "
            "setup remembers your edits; Apply SMBIOS Identity at the top builds the file "
            "for the next VM launch.")
        patch_help.setWordWrap(True)
        patches_layout.addWidget(patch_help)
        self.smbios_table.setMinimumHeight(240)
        patches_layout.addWidget(self.smbios_table, 1)
        lay.addWidget(patches_box, 1)

        self.smbios_log = QPlainTextEdit()
        self.smbios_log.setReadOnly(True)
        self.smbios_log.setFont(QFont(MONO, 10))
        self.smbios_log.setMinimumHeight(150)
        lay.addWidget(self.smbios_log)
        self.smbios_blob_editors = [identity_box, model_box, t0box, patches_box, self.smbios_log]
        self.tab_opencore = OpenCoreTab(self.cfg) if self.cfg.profile == "macos" else None
        if self.tab_opencore:
            lay.addWidget(self.tab_opencore)
            self.tab_opencore.edited.connect(self._update_modified)
            self.tab_opencore.applied.connect(self._opencore_applied)
        return self._scroll(w)

    def _opencore_applied(self):
        # Keep the result visible after rebuilding the editors for the new paths.
        self.status.setText("OpenCore setup updated. Save current setup to remember the boot files.")
        QTimer.singleShot(0, self._rebuild_tabs)

    # -- preview ------------------------------------------------------------
    def _tab_preview(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        row = QHBoxLayout()
        self.chk_standalone = QCheckBox("Standalone launch")
        self.chk_standalone.setToolTip("Drop libvirt's -S, secret object, and inherited monitor file descriptor.")
        self.chk_standalone.setChecked(self.cfg.data.get("single_gpu", {}).get("standalone", True))
        self.chk_standalone.toggled.connect(self._standalone_changed)
        row.addWidget(self.chk_standalone)
        row.addStretch()
        b = QPushButton("Export launch script")
        b.clicked.connect(self.export_script)
        row.addWidget(b)
        lay.addLayout(row)

        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setFont(QFont(MONO, 10))
        self.preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        lay.addWidget(self.preview, 1)
        return w

    def _standalone_changed(self, value):
        self.cfg.data.setdefault("single_gpu", {})["standalone"] = value
        self._refresh_all()

    # ------------------------------------------------------------- detect ---
    def _detect_host(self):
        try:
            self.host = {
                "topo": hostinfo.cpu_topology(),
                "gpus": hostinfo.gpus(),
                "disks": hostinfo.block_devices(),
                "bridges": hostinfo.net_bridges(),
                "tpm": hostinfo.tpm_devices(),
            }
        except Exception as e:
            self.host = {}
            self.status.setText(f"host detection failed: {e}")
            return

        t = self.host["topo"]
        self.lbl_cpu.setText(t["model"])
        self.lbl_topo.setText(f"{t['cores']} cores / {t['threads']} threads, SMT {'on' if t['smt'] else 'off'}")
        self.lbl_ccd.setText("   ".join(f"[{k}] cores {v}" for k, v in t["l3_to_cores"].items()) or "none detected")
        self.lbl_gpu.setText("\n".join(f"{g['slot']}  {g['device']}  (driver {g['driver'] or 'none'}, "
                                       f"iommu group {g['iommu_group'] or '?'})" for g in self.host["gpus"]) or "none")
        self.lbl_disks.setText(f"{len(self.host['disks'])} block devices")
        self.lbl_misc.setText(f"bridges: {', '.join(self.host['bridges']) or 'none'}" +
                             ("" if self.cfg.profile == "macos" else f"    tpm: {', '.join(self.host['tpm']) or 'none'}"))


    def redetect(self):
        self._detect_host()
        self.tab_dual.refresh_gpus()
        self._refresh_all()
        self.status.setText("host re-detected")

    # ------------------------------------------------------------ refresh ---
    def _refresh_all(self):
        # sync() stays for its side effect: it normalises the config. Only the
        # panel that displayed its findings is gone; validate() still runs at
        # launch, where preflight surfaces the same problems and can stop.
        self.cfg.sync()
        if getattr(self, "host", None):
            self.lbl_misc.setText(f"bridges: {', '.join(self.host['bridges']) or 'none'}" +
                                 ("" if self.cfg.profile == "macos" else f"    tpm: {', '.join(self.host['tpm']) or 'none'}"))

        self._fill_features()
        self._fill_smbios()
        self._update_modified()
        self.preview.setPlainText(self.cfg.to_script(self.chk_standalone.isChecked()))
        self._refresh_sections()

    def _fill_features(self):
        feats = self.cfg.cpu_features
        self.cpu_model.setText(self.cfg.data.get("cpu", {}).get("model", "host"))
        self.cpu_vendor.setText(str(feats.get("vendor", "")))
        names = list(feats.keys()) + [f for f in CPU_FEATURES if f not in feats]
        if self.cfg.profile == "macos":
            names = [name for name in names if not name.startswith("hv-")]
        groups = {"amd": [], "intel": [], "": []}
        for name in names:
            if name == "vendor":
                continue
            groups[FEATURE_VENDOR.get(name, "")].append(name)
        self._fill_feature_table(self.feat_amd, groups["amd"])
        self._fill_feature_table(self.feat_intel, groups["intel"])
        self._fill_feature_table(self.feat_uni, groups[""])
        for table in (self.feat_amd, self.feat_intel, self.feat_uni):
            table.setFixedHeight(self._feature_table_height(table))

    def _fill_feature_table(self, table, names):
        table.blockSignals(True)
        table.setRowCount(len(names))
        for r, name in enumerate(names):
            table.setItem(r, 0, QTableWidgetItem(name))
            combo = QComboBox()
            combo.addItems(FEATURE_CHOICES + ["(not set)"])
            cur = self.cfg.cpu_features.get(name)
            combo.setCurrentText(cur if cur in FEATURE_CHOICES else "(not set)")
            combo.currentTextChanged.connect(
                lambda val, n=name: self._set_feature(n, val))
            table.setCellWidget(r, 1, combo)
            combo.ensurePolished()
            table.setColumnWidth(1, max(table.columnWidth(1), combo.sizeHint().width() + 20))
            table.verticalHeader().setMinimumSectionSize(max(34, combo.sizeHint().height() + 8))
            text = CPU_FEATURES.get(name, "")
            if self.cfg.profile == "macos":
                text = {"svm": "Host AMD virtualization extension; keep the tested Mac guest CPU overrides.",
                        "vmx": "Intel nested virtualization extension; not needed to run macOS under KVM.",
                        "topoext": "AMD topology reporting; the Mac preset uses its selected Intel-compatible CPU model.",
                        "pmu": "Virtual CPU performance counters.",
                        "virt-ssbd": "Virtualized speculative-store-bypass control.",
                        "aes": "AES-NI instructions exposed to the guest."}.get(name, text)
            if self.cfg.profile == "macos" and name in ("kvm", "hypervisor", "kvmclock"):
                text = {"kvm": "KVM CPUID interface; enabled by the Mac masters.",
                        "hypervisor": "Reports that this guest is running in a virtual machine.",
                        "kvmclock": "KVM paravirtual clocksource."}[name]
            description = QTableWidgetItem(text)
            description.setToolTip(description.text())
            table.setItem(r, 2, description)
        table.blockSignals(False)
        guard_all(table)

    def _feature_table_height(self, table):
        h = table.horizontalHeader().height() + 2 * table.frameWidth()
        for r in range(table.rowCount()):
            h += table.rowHeight(r)
        return h

    def _set_feature(self, name, val):
        if val == "(not set)":
            self.cfg.cpu_features.pop(name, None)
        else:
            self.cfg.cpu_features[name] = val
        self.preview.setPlainText(self.cfg.to_script(self.chk_standalone.isChecked()))

    def _fill_smbios(self):
        cfg = self._smbios_cfg()
        opencore = self._smbios_uses_opencore()
        self.smbios_help.setText(
            "OpenCore supplies this Mac preset's model, serial number and BIOS identity. "
            "The editor below validates EFI/OC/config.plist and creates a recoverable boot-image version."
            if opencore else self.smbios_blob_help)
        for widget in self.smbios_blob_actions + self.smbios_blob_editors:
            widget.setVisible(not opencore)
            widget.setEnabled(not opencore)
        for widget, key in ((self.ed_tpl, "template_blob"),
                            (self.ed_out, "output_blob"),
                            (self.ed_uuid, "system_uuid")):
            v = cfg.get(key, "")
            if widget.text() != v:
                widget.blockSignals(True)
                widget.setText(v)
                widget.blockSignals(False)

        # Saved Type 0 edits win; anything the session never set is shown from
        # the template so the fields are populated rather than blank on a first
        # visit.
        saved = cfg.get("type0") or {}
        if saved:
            self._set_type0_widgets(saved)
        elif not self.ed_bios_vendor.text().strip():
            import smbios as sm
            tpl = cfg.get("template_blob", "")
            if os.path.isfile(tpl):
                try:
                    data = bytearray(open(tpl, "rb").read())
                    ep = sm.entry_point_len(data)
                    self._set_type0_widgets(sm.read_type0(data[ep:] if ep else data))
                except Exception:
                    pass

        pats = cfg.get("patches", [])
        self.smbios_table.blockSignals(True)
        self.smbios_table.setRowCount(len(pats))
        widest = 0
        for r, p in enumerate(pats):
            c = QCheckBox()
            c.setChecked(bool(p.get("enabled", True)))
            c.stateChanged.connect(
                lambda st, i=r: self._smbios_set(i, "enabled", bool(st)))
            self.smbios_table.setCellWidget(r, 0, c)

            for col, key in ((1, "label"), (2, "find_ascii"), (3, "replace_ascii")):
                # Show NUL and friends readably; the stored value keeps the
                # real bytes.
                text = _printable(p.get(key, ""))
                item = QTableWidgetItem(text)
                if col == 2:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    item.setToolTip("The bytes in the pristine dump. Read only: "
                                    "the pattern has to match what is actually there.")
                elif col == 3:
                    item.setToolTip(f"Must be exactly {len(p.get('find_ascii',''))} "
                                    f"characters. SMBIOS strings are fixed width.")
                self.smbios_table.setItem(r, col, item)

            b = QPushButton("Regenerate")
            b.setToolTip("New random value, same length and shape")
            b.clicked.connect(lambda _, i=r: self._smbios_regen(i))
            self.smbios_table.setCellWidget(r, 4, b)
            widest = max(widest, b.sizeHint().width())
        # Width the column from the text itself. A button's sizeHint is not
        # trustworthy here -- it still reports the old metrics until Qt polishes
        # the freshly created widget, so a larger theme font clipped the label
        # anyway. fontMetrics is correct immediately, and the sizeHint is used
        # only as a floor for styles whose padding exceeds the allowance.
        label = self.smbios_table.fontMetrics().horizontalAdvance("Regenerate")
        self.smbios_table.setColumnWidth(4, max(label + 44, widest + 16))
        self.smbios_table.blockSignals(False)
        self._fill_manufacturer_model()

    # -- smbios editing -------------------------------------------------------
    def _manufacturer_model_patch(self):
        for index, patch in enumerate(self._smbios_cfg().get("patches", [])):
            if patch.get("label", "").strip().casefold() != "manufacturer/model":
                continue
            original = patch.get("find_ascii", "").split("\0")
            current = patch.get("replace_ascii", "").split("\0")
            if len(original) == len(current) == 2:
                return index, patch, original, current
        return None

    def _fill_manufacturer_model(self):
        entry = self._manufacturer_model_patch()
        enabled = bool(entry and entry[1].get("enabled", True))
        blocker = QSignalBlocker(self.chk_manufacturer_model)
        self.chk_manufacturer_model.setEnabled(entry is not None)
        self.chk_manufacturer_model.setChecked(enabled)
        del blocker
        values = entry[3] if entry else ("", "")
        for editor, value in zip((self.ed_manufacturer, self.ed_product_model), values):
            blocker = QSignalBlocker(editor)
            editor.setEnabled(enabled)
            if editor.text() != value:
                editor.setText(value)
            del blocker
        if entry:
            lengths = [len(part) for part in entry[2]]
            self.manufacturer_model_note.setText(
                f"This template requires {lengths[0]} characters for the manufacturer "
                f"and {lengths[1]} for the model. Press Enter or leave a field to finish editing.")
        else:
            self.manufacturer_model_note.setText(
                "This preset has no separate Manufacturer/Model entry. "
                "Its identity fields are listed below.")

    def _toggle_manufacturer_model(self, enabled):
        entry = self._manufacturer_model_patch()
        if entry:
            self._smbios_set(entry[0], "enabled", enabled)
            self._fill_smbios()

    def _edit_manufacturer_model(self, finished=True):
        entry = self._manufacturer_model_patch()
        if not entry:
            return
        _index, patch, original, current = entry
        values = [self.ed_manufacturer.text(), self.ed_product_model.text()]
        if values == current:
            return
        for label, value, source in zip(("Manufacturer", "Model / product"), values, original):
            if (len(value) != len(source) or not value.isprintable()
                    or any(ord(char) > 255 for char in value)):
                if not finished:
                    return
                # Restore the saved values before opening a dialog, so a focus
                # change cannot submit the invalid edit a second time.
                self._fill_manufacturer_model()
                QMessageBox.warning(
                    self, "Invalid identity value",
                    f"{label} must contain exactly {len(source)} printable Latin-1 "
                    "characters to fit this template. The previous value was kept.")
                return
        patch["replace_ascii"] = "\0".join(values)
        patch["replace_hex"] = randomize.hex_of(patch["replace_ascii"])
        self._fill_smbios()
        self._update_modified()

    def _smbios_set(self, index, key, value):
        pats = self._smbios_cfg().get("patches", [])
        if 0 <= index < len(pats):
            pats[index][key] = value
            self._fill_manufacturer_model()
            self._update_modified()

    def _smbios_item_changed(self, item):
        """Only the spoofed value is editable, and only at the right length."""
        if item.column() not in (1, 3):
            return
        pats = self._smbios_cfg().get("patches", [])
        r = item.row()
        if not (0 <= r < len(pats)):
            return
        p = pats[r]
        if item.column() == 1:
            p["label"] = item.text()
            self._fill_manufacturer_model()
            self._update_modified()
            return

        want = len(p.get("find_ascii", ""))
        new = _unprintable(item.text())
        if len(new) != want:
            QMessageBox.warning(
                self, "Wrong length",
                f"'{p.get('label','patch')}' must be exactly {want} characters; "
                f"you gave {len(new)}.\n\nSMBIOS strings are fixed width - a "
                f"different length would shift every byte after it.")
            self._fill_smbios()
            return
        p["replace_ascii"] = new
        p["replace_hex"] = randomize.hex_of(new)
        self._fill_manufacturer_model()
        self._update_modified()

    def _smbios_regen(self, index):
        pats = self._smbios_cfg().get("patches", [])
        if not (0 <= index < len(pats)):
            return
        p = pats[index]
        new = randomize.like(p.get("find_ascii", ""))
        p["replace_ascii"] = new
        p["replace_hex"] = randomize.hex_of(new)
        self._fill_smbios()
        self.status.setText(f"regenerated {p.get('label','field')}")

    def _smbios_regen_all(self):
        pats = self._smbios_cfg().get("patches", [])
        n = 0
        for i, p in enumerate(pats):
            if p.get("enabled", True):
                self._smbios_regen_quiet(i)
                n += 1
        self._fill_smbios()
        self.status.setText(f"regenerated {n} SMBIOS fields")

    def _smbios_regen_quiet(self, index):
        p = self._smbios_cfg()["patches"][index]
        new = randomize.like(p.get("find_ascii", ""))
        p["replace_ascii"] = new
        p["replace_hex"] = randomize.hex_of(new)

    def _smbios_new_uuid(self):
        u = randomize.uuid4()
        self._smbios_cfg()["system_uuid"] = u
        self.ed_uuid.setText(u)
        self.status.setText(f"new System UUID {u}")

    def _smbios_reload_defaults(self):
        if QMessageBox.question(
                self, "Reload defaults",
                "Re-read presets/smbios-default.json?\n\nEdits to the patch "
                "list are discarded.") != QMessageBox.StandardButton.Yes:
            return
        self.cfg.data.pop("smbios", None)
        self._fill_smbios()
        self.status.setText("SMBIOS defaults reloaded")

    def _smbios_cfg(self):
        return self.cfg.smbios

    def _smbios_uses_opencore(self):
        import smbios as sm
        cfg = self._smbios_cfg()
        return (self.cfg.profile == "macos" and not cfg.get("template_blob")
                and not cfg.get("output_blob")
                and sm.blob_path(self.cfg.simple.get("smbios", "")) is None)

    def _type0_widgets(self):
        return (("vendor", self.ed_bios_vendor), ("version", self.ed_bios_version),
                ("date", self.ed_bios_date), ("release_major", self.sp_bios_major),
                ("release_minor", self.sp_bios_minor))

    def _push_type0(self, *_):
        """Store only what the user actually filled in.

        A blank field means 'keep the template's value', which is not the same
        as 'set it to empty', so blanks are dropped rather than written.
        """
        t0 = self._smbios_cfg().setdefault("type0", {})
        for key, wdg in self._type0_widgets():
            if isinstance(wdg, QSpinBox):
                t0[key] = wdg.value()
            else:
                v = wdg.text().strip()
                if v:
                    t0[key] = v
                else:
                    t0.pop(key, None)
        self._update_modified()

    def _smbios_read_type0(self):
        """Fill the Type 0 fields from the pristine template."""
        import smbios as sm
        tpl = self.ed_tpl.text().strip()
        if not os.path.isfile(tpl):
            self.smbios_log.setPlainText(f"template blob missing: {tpl}")
            return
        data = bytearray(open(tpl, "rb").read())
        ep = sm.entry_point_len(data)
        vals = sm.read_type0(data[ep:] if ep else data)
        if not vals:
            self.smbios_log.setPlainText(
                "the template has no Type 0 (BIOS Information) structure")
            return
        self._set_type0_widgets(vals)
        self._push_type0()
        self.smbios_log.setPlainText(
            "read Type 0 from the template:\n" +
            "\n".join(f"  {k:14} {v}" for k, v in vals.items()))

    def _set_type0_widgets(self, vals):
        for key, wdg in self._type0_widgets():
            if key not in vals:
                continue
            wdg.blockSignals(True)
            if isinstance(wdg, QSpinBox):
                wdg.setValue(int(vals[key] or 0))
            else:
                wdg.setText(str(vals[key]))
            wdg.blockSignals(False)

    def _smbios_run(self, dry):
        import smbios as sm
        if self._smbios_uses_opencore():
            self.smbios_log.setPlainText(self.smbios_help.text())
            return
        cfg = dict(self._smbios_cfg())
        cfg["template_blob"] = self.ed_tpl.text().strip()
        cfg["output_blob"] = self.ed_out.text().strip()
        cfg["system_uuid"] = self.ed_uuid.text().strip()
        cfg["type0"] = dict(self._smbios_cfg().get("type0") or {})
        for r in range(self.smbios_table.rowCount()):
            wdg = self.smbios_table.cellWidget(r, 0)
            cfg["patches"][r]["enabled"] = bool(wdg and wdg.isChecked())
        try:
            log = sm.apply(cfg, dry_run=dry)
            self.smbios_log.setPlainText("\n".join(log))
        except Exception as e:
            self.smbios_log.setPlainText(f"FAILED: {e}")

    # ------------------------------------------------------------ pinning ---
    def _pinning_changed(self):
        """Keep -smp in step with whatever the pinning tab just generated.

        The guest topology has to describe the cores it actually got. Claiming
        more cores than are pinned makes the Windows scheduler place threads on
        vCPUs that share a host thread, which costs more than it saves.
        """
        plan = self.cfg.data.get("pinning") or {}
        n = plan.get("vcpus", 0)
        if not n:
            return
        threads = 2 if plan.get("smt") else 1
        # One die per CCD the pinned cores touch, when the CPU Pinning tab asked
        # for it. Default is 1, which is the topology this VM has always run.
        dies = max(1, int(plan.get("cache_dies", 1) or 1))
        self.cfg.smp["vcpus"] = str(n)
        self.cfg.smp.setdefault("topology", {}).update(
            {"sockets": "1", "dies": str(dies), "clusters": "1",
             "cores": str(max(1, n // threads // dies)), "threads": str(threads)})

        # -smp alone only splits the guest into dies; it does not say the L3
        # follows them. smp-cache is what carries that, and without it the guest
        # still sees one cache domain spanning both.
        opts = self.cfg.data.setdefault("machine", {}).setdefault("opts", {})
        if dies > 1:
            opts["smp-cache.0.cache"] = "l3"
            opts["smp-cache.0.topology"] = "die"
        else:
            opts.pop("smp-cache.0.cache", None)
            opts.pop("smp-cache.0.topology", None)
        self._refresh_all()

    # ------------------------------------------------------------ presets ---
    def _rebuild_tabs(self):
        """Rebuild the stateful tabs after self.cfg has been replaced.

        Each of these holds direct references into the config dicts it edits,
        so swapping the config without rebuilding leaves them writing to the
        object that was just discarded.
        """
        current = self.tabs.currentIndex()
        blocker = QSignalBlocker(self.tabs)
        for widget, key in ((self.chk_reboot, "reboot_after"), (self.chk_standalone, "standalone")):
            with QSignalBlocker(widget):
                widget.setChecked(self.cfg.data.get("single_gpu", {}).get(key, True))
        for attr, cls, title in (("tab_pin", PinningTab, "CPU Pinning"),
                                 ("tab_mem", MemoryTab, "Memory"),
                                 ("tab_disks", DisksTab, "Disks"),
                                 ("tab_hw", PassthroughTab, "PCI / USB"),
                                 ("tab_machine", MachineTab, "Machine"),
                                 ("tab_smbios", lambda cfg: self._tab_smbios(), "SMBIOS"),
                                 ("tab_boot_arguments", lambda cfg: self._tab_boot_arguments(), "Boot Arguments"),
                                 ("tab_paths", PathsTab, "Paths && Tools"),
                                 ("tab_tpm", TpmTab, "TPM"),
                                 ("tab_virtual", VirtualGPUTab, "Virtual GPU"),
                                 ("tab_dual", DualGPUTab, "Dual GPU")):
            old = getattr(self, attr)
            idx = self.tabs.indexOf(old)
            new = cls(self.cfg)
            setattr(self, attr, new)
            self.tabs.removeTab(idx)
            self.tabs.insertTab(idx, new, title)
            old.deleteLater()

        self.tab_pin.changed.connect(self._pinning_changed)
        self.tab_mem.changed.connect(self._refresh_all)
        self.tab_disks.changed.connect(self._refresh_all)
        self.tab_hw.changed.connect(self._refresh_all)
        self.tab_machine.changed.connect(self._refresh_all)
        self.tab_paths.changed.connect(self._refresh_all)
        self.tab_tpm.changed.connect(self._refresh_all)
        self.tab_virtual.changed.connect(self._refresh_all)
        self.tab_dual.changed.connect(self._refresh_all)
        self.tab_proc.cfg = self.cfg
        self.tab_proc.refresh()
        # The wizard is not rebuilt (it has no per-config child widgets to leak),
        # but it caches the config reference and must be repointed, then re-drawn
        # so its current step reflects the swapped-in config.
        if getattr(self, "tab_wizard", None) is not None:
            self.tab_wizard.cfg = self.cfg
            self.tab_wizard.go(self.tab_wizard._state().get("step", 0), remember=False)
        self.tabs.setCurrentIndex(current)
        del blocker
        self._polish_pages()
        self._page_changed(self.tabs.currentIndex())
        self._refresh_all()

    def load_preset(self):
        editor = getattr(self, "tab_opencore", None)
        if editor and editor.busy:
            return
        if editor:
            editor.flush()
        paths = self._paths()
        p, _ = QFileDialog.getOpenFileName(self, f"Load {profiles.NAMES[self.profile_id]} preset", str(paths.presets), "JSON (*.json)")
        if not p:
            return
        try:
            incoming = VMConfig.load(p, root=paths.root)
            profiles.check(incoming.data, self.profile_id)
            if editor and editor.dirty and QMessageBox.question(
                    self, "Load preset", "Discard unapplied OpenCore edits and load this preset?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
                    ) != QMessageBox.StandardButton.Yes:
                return
            self.cfg = incoming
            self._rebuild_tabs()
            self.status.setText(f"loaded {os.path.basename(p)}")
        except Exception as e:
            QMessageBox.critical(self, "Load failed", str(e))

    def save_preset(self):
        if not self._resolve_opencore():
            return
        paths = self._paths()
        paths.presets.mkdir(parents=True, exist_ok=True)
        p, _ = QFileDialog.getSaveFileName(self, f"Save {profiles.NAMES[self.profile_id]} preset", str(paths.presets), "JSON (*.json)")
        if not p:
            return
        if not p.endswith(".json"):
            p += ".json"
        try:
            other = self._paths("macos" if self.profile_id == "windows" else "windows")
            if Path(p).resolve().is_relative_to(other.presets.resolve()):
                raise ValueError("Save this preset in the current OS profile's preset folder.")
            profiles.check(self.cfg.data, self.profile_id)
            self.cfg.save(p)
            self.status.setText(f"saved {os.path.basename(p)}")
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))

    def reset_template(self):
        if self.is_modified() and QMessageBox.question(
                self, "Reset",
                "Discard the current config and go back to the captured template?"
                ) != QMessageBox.StandardButton.Yes:
            return
        self.cfg = VMConfig.load(self._paths().template, root=self._paths().root)
        self._rebuild_tabs()
        self.status.setText("reset to captured template")

    def reset_defaults(self):
        if QMessageBox.question(
                self, "Reset defaults?",
                f"Restore {profiles.NAMES[self.profile_id]} VM settings and theme from its saved master defaults?\n\n"
                "This replaces the current setup, including unsaved changes, and saves "
                "the restored setup. A dated recovery copy of the current setup will "
                "be kept in settings_backups.\n\n"
                "Restore the master defaults now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Yes:
            return
        old_cfg, old_baseline = self.cfg, self._baseline
        current_theme = dict(accent=self.theme_bar.accent,
                             background=self.theme_bar.background,
                             text=self.theme_bar.text,
                             preset=self.theme_bar.combo.currentIndex())
        try:
            state, appearance, state_bytes, theme_bytes = settings_defaults.read_defaults(
                self._paths().defaults, self._paths().default_theme)
            profiles.check(state, self.profile_id)
            self.cfg = VMConfig(state, root=self._paths().root)
            # Build the editors before committing the files. Invalid settings
            # must not replace a working saved session.
            self._rebuild_tabs()
            backup = settings_defaults.restore_files(
                [(self._paths().session, state_bytes), (self._paths().theme, theme_bytes)],
                old_cfg.data, current_theme)
        except Exception as error:
            if self.cfg is not old_cfg:
                self.cfg = old_cfg
                self._rebuild_tabs()
            self._baseline = old_baseline
            self._update_modified()
            QMessageBox.critical(self, "Reset failed", str(error))
            return
        self.theme_bar.accent = appearance["accent"]
        self.theme_bar.background = appearance["background"]
        self.theme_bar.text = appearance["text"]
        self.theme_bar.combo.setCurrentIndex(appearance["preset"])
        self._baseline = json.dumps(self.cfg.data, sort_keys=True)
        self.theme_bar.apply_current()
        self.status.setText(f"master defaults restored and saved; recovery copy: {backup}")

    def export_script(self):
        p, _ = QFileDialog.getSaveFileName(self, "Export launch script",
                                           os.path.expanduser("~/vmstart2-launch.sh"),
                                           "Shell (*.sh)")
        if not p:
            return
        with open(p, "w") as f:
            f.write("#!/usr/bin/env bash\nset -euo pipefail\n\n")
            f.write(self.cfg.to_script(self.chk_standalone.isChecked()) + "\n")
        os.chmod(p, 0o755)
        self.status.setText(f"exported {os.path.basename(p)}")

    # --------------------------------------------------------------- misc ---
    def _size_and_centre(self):
        scr = QApplication.primaryScreen().availableGeometry()
        # Start wide enough for two disk columns when the display allows it.
        self.resize(min(1750, scr.width() - 60), min(1000, scr.height() - 60))
        g = self.frameGeometry()
        self.move(scr.center().x() - g.width() // 2, scr.center().y() - g.height() // 2)


def main():
    app = QApplication(sys.argv)
    # Paint before the window is built so nothing flashes unstyled, then let
    # the window's own bar re-apply whatever it loaded from theme.json.
    theme.apply_to(app, *theme.load()[:3])
    w = VMStart2()
    w.theme_bar.apply_current()
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
