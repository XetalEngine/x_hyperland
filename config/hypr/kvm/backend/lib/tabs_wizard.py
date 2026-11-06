#!/usr/bin/env python3
"""The setup wizard for vmstart_2.

One green button walks a fresh machine from "nothing configured" to "ready to
launch", filling in exactly the fields the other tabs expose but choosing sane
values from what the host actually is. It is deliberately vendor-aware: the same
wizard produces an intel_iommu / no-svm config on an Intel box and an
amd_iommu / svm config on a Ryzen, because the only thing that should differ
between two passthrough hosts is what the hardware forces.

Everything it writes goes through the shared VMConfig, so every choice is
visible and further editable on the normal tabs afterwards. Progress is stored
in cfg.data['wizard'], which rides along in last-session.json, so the IOMMU step
(which needs a reboot) can be resumed exactly where it was left.
"""

import os
import subprocess

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
                             QCheckBox, QComboBox, QSpinBox, QPushButton, QLineEdit,
                             QScrollArea, QGridLayout, QRadioButton, QButtonGroup,
                             QPlainTextEdit, QFileDialog, QMessageBox, QFrame,
                             QProgressBar)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QFont

import hostinfo
import wizard_support as ws
import randomize
import model
from uiutil import guard_all, sudo_command, polish_page

MONO = "Monospace"

# The CPU model the guest is given for each host vendor. 'host' passes the real
# features through; the explicit list is what hides the hypervisor and SWAPS the
# vendor-specific flags rather than merely dropping them: AMD gets svm/topoext,
# Intel gets vmx in its place. QEMU refuses to start if it is asked to enable a
# flag the physical CPU does not have, so the two sets are mutually exclusive on
# exactly svm/topoext/amd-ssbd/virt-ssbd (AMD) vs vmx (Intel). The shared,
# vendor-neutral flags below are identical in both.
_COMMON_FEATURES = [
    ("migratable", "off"), ("invtsc", "on"), ("rdtscp", "on"),
    ("hypervisor", "off"), ("rdpid", "off"), ("kvmclock", "off"),
    ("kvm", "off"), ("pmu", "off"), ("host-cache-info", "on"), ("l3-cache", "off"),
]
VENDOR_FEATURES = {
    # svm + topoext are the AMD virtualisation and topology flags; amd-ssbd /
    # virt-ssbd are the AMD spelling of the speculation-store-bypass control.
    "amd": [("svm", "on"), ("topoext", "on"), ("amd-ssbd", "on"),
            ("virt-ssbd", "off")] + _COMMON_FEATURES,
    # vmx is the Intel counterpart of svm; ssbd is the Intel spelling. None of
    # the AMD-only names appear, so the guest CPU matches an Intel host exactly.
    "intel": [("vmx", "on"), ("ssbd", "on")] + _COMMON_FEATURES,
}


def _hline():
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet("color:#444;")
    return f


class WizardTab(QScrollArea):
    """A single-page-at-a-time guided setup that writes into the shared config."""

    changed = pyqtSignal()
    goto_tab = pyqtSignal(str)        # ask the main window to switch tabs
    config_reloaded = pyqtSignal()    # wizard rewrote enough that tabs must rebuild
    finished = pyqtSignal()
    component_page = pyqtSignal(object)
    create_bridge = pyqtSignal(str)

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self._gpu_rom_choices = {}
        self._gpu_rom_config = cfg
        self._gpu_dump_token = None
        self.setWidgetResizable(True)
        # Ordered list of (key, title). The body for each is built on entry so
        # it always reflects current host state (disks appear, IOMMU flips).
        self.steps = [
            ("components", "Downloads"),
            ("vendor",  "CPU vendor"),
            ("iommu",   "IOMMU"),
            ("memory",  "Guest RAM"),
            ("cores",   "CPU cores"),
            ("gpu",     "GPU passthrough"),
            ("usb",     "USB devices"),
            ("drives",  "Drives"),
            ("tune",    "Vendor tuning"),
            ("done",    "Finish"),
        ]
        state = self._state()
        if state.get('layout', 1) < 2:
            state['step'] = state.get('step', 0) + 1 if state else 0
            state['layout'] = 2
        self.component_host = None
        self.components_ready = lambda: False
        self._build_frame()
        self.go(self._state().get("step", 0), remember=False)
        guard_all(self)

    # -------------------------------------------------------------- state ---
    def _state(self):
        return self.cfg.data.setdefault("wizard", {})

    def _ram_obj(self):
        for o in self.cfg.objects:
            if o.get("id") == "pc.ram":
                return o
        return None

    # -------------------------------------------------------------- frame ---
    def _build_frame(self):
        outer = QWidget()
        self.setWidget(outer)
        root = QVBoxLayout(outer)

        head = QHBoxLayout()
        self.lbl_title = QLabel("")
        self.lbl_title.setObjectName("wizardStepTitle")
        head.addWidget(self.lbl_title)
        head.addStretch()
        self.lbl_progress = QLabel("")
        self.lbl_progress.setObjectName("muted")
        head.addWidget(self.lbl_progress)
        self.btn_startover = QPushButton("Start over…")
        self.btn_startover.setToolTip("Restart setup, with a choice to keep your "
                                      "config or reset it to the captured template.")
        self.btn_startover.clicked.connect(self._start_over)
        head.addWidget(self.btn_startover)
        root.addLayout(head)

        self.dots = QLabel("")
        self.dots.setObjectName("muted")
        self.dots.setWordWrap(True)
        root.addWidget(self.dots)
        self.progress = QProgressBar()
        self.progress.setRange(0, len(self.steps))
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        root.addWidget(self.progress)

        # Only the step body scrolls: Back and Next stay in the same place even
        # on steps with long disk or USB lists.
        self.body_host = QWidget()
        self.body = QVBoxLayout(self.body_host)
        self.body.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.step_scroll = QScrollArea()
        self.step_scroll.setWidgetResizable(True)
        self.step_scroll.setWidget(self.body_host)
        root.addWidget(self.step_scroll, 1)

        root.addWidget(_hline())
        nav = QHBoxLayout()
        self.btn_back = QPushButton("Back")
        self.btn_back.clicked.connect(self._back)
        nav.addWidget(self.btn_back)
        nav.addStretch()
        self.btn_next = QPushButton("Next")
        self.btn_next.setMinimumWidth(140)
        # Named rather than styled inline so it follows the theme accent; an
        # inline sheet wins over the application one and would stay green.
        self.btn_next.setObjectName("accent")
        self.btn_next.clicked.connect(self._next)
        nav.addWidget(self.btn_next)
        root.addLayout(nav)

    def _clear_body(self):
        self._gpu_dump_token = None
        self.btn_startover.setEnabled(True)
        self.component_page.emit(None)
        self.component_host = None
        while self.body.count():
            it = self.body.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

    def _step_components(self):
        self._note('Your saved baseline is already loaded. Install the missing components first, '
                   'then review this computer’s CPU, memory and devices.')
        self.component_host = QWidget()
        QVBoxLayout(self.component_host).setContentsMargins(0, 0, 0, 0)
        self._add(self.component_host)
        self.component_page.emit(self.component_host)
        self.next_action = lambda: self.components_ready()

    # --------------------------------------------------------- navigation ---
    def go(self, index, remember=True):
        if self._gpu_rom_config is not self.cfg:
            self._gpu_rom_choices.clear()
            self._gpu_rom_config = self.cfg
        index = max(0, min(index, len(self.steps) - 1))
        self.step = index
        if remember:
            self._state()["step"] = index
        key, title = self.steps[index]
        self.lbl_title.setText(f"{title}")
        self.lbl_progress.setText(f"Step {index + 1} of {len(self.steps)}")
        self.progress.setValue(index + 1)
        self.dots.setText("   ".join(
            (f"● {t}" if i == index else f"○ {t}")
            for i, (k, t) in enumerate(self.steps)))

        self._clear_body()
        # next_action is run before advancing; returning False cancels the move.
        self.next_action = None
        self.btn_next.setText("Next")
        self.btn_next.setEnabled(True)
        self.btn_back.setEnabled(index > 0)

        builder = getattr(self, f"_step_{key}")
        builder()
        polish_page(self.step_scroll)
        guard_all(self.body_host)
        self.step_scroll.verticalScrollBar().setValue(0)
        self.changed.emit()

    def _back(self):
        self.go(self.step - 1)

    def _next(self):
        if self.next_action is not None:
            try:
                if self.next_action() is False:
                    return
            except Exception as e:
                QMessageBox.critical(self, "Wizard step failed", str(e))
                return
        if self.step >= len(self.steps) - 1:
            return
        self.go(self.step + 1)

    def _start_over(self):
        r = QMessageBox.question(
            self, "Start over",
            "Restart the wizard from step one.\n\n"
            "Also reset the whole VM config back to the captured template?\n\n"
            "Yes  - wipe the config and start clean (recommended on a new machine)\n"
            "No   - keep the config, just jump back to step one\n"
            "Cancel - continue at the current wizard step",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel)
        if r == QMessageBox.StandardButton.Cancel:
            return False
        if r == QMessageBox.StandardButton.Yes:
            from model import VMConfig
            try:
                fresh = (VMConfig.load_template(self.cfg.profile, self.cfg.root)
                         if self.cfg.profile != "windows" else VMConfig.load_template())
            except Exception as e:
                QMessageBox.critical(self, "Could not reset the configuration", str(e))
                return False
            self.cfg.data.clear()
            self.cfg.data.update(fresh)
        self._state().clear()
        self._gpu_rom_choices.clear()
        self._state()["step"] = 0
        self._state()['layout'] = 2
        self.go(0)
        if r == QMessageBox.StandardButton.Yes:
            self.config_reloaded.emit()
        return True

    # ---------------------------------------------------------- utilities ---
    def _add(self, w):
        self.body.addWidget(w)
        return w

    def _note(self, text, color=None):
        l = QLabel(text)
        l.setWordWrap(True)
        if color and color != "#ccc":
            l.setStyleSheet(f"color:{color};")
        elif color is None:
            l.setObjectName("muted")
        return self._add(l)

    def _next_dev_id(self, prefix):
        used = {d.get("id") for d in self.cfg.devices}
        n = 0
        while f"{prefix}{n}" in used:
            n += 1
        return f"{prefix}{n}"

    def _free_root_port(self):
        ports = [d["id"] for d in self.cfg.devices
                 if d.get("driver") == "pcie-root-port" and not d.get("_disabled")]
        taken = {d.get("bus") for d in self.cfg.devices if not d.get("_disabled")}
        for p in ports:
            if p not in taken:
                return p
        return ""

    def _ensure_root_port(self):
        """A free guest pcie-root-port to attach one device to — creating a new
        one if every existing port is taken. This is what makes the wizard work
        'from zero': a card with four functions needs four free ports, and a lean
        config may not ship enough."""
        p = self._free_root_port()
        if p:
            return p
        # The new id must collide neither with an existing device id nor with a
        # bus another device still points at, or the port would silently stack on
        # top of an unrelated device.
        ids = {d.get("id") for d in self.cfg.devices}
        buses = {d.get("bus") for d in self.cfg.devices}
        n = 1
        while f"pci.{n}" in ids or f"pci.{n}" in buses:
            n += 1
        rps = [d for d in self.cfg.devices if d.get("driver") == "pcie-root-port"]
        chassis = max([int(d.get("chassis", 0) or 0) for d in rps] + [0]) + 1
        port = max([int(d.get("port", 0) or 0) for d in rps] + [0]) + 1
        # A free top-level slot on the root complex (pcie.0), function 0.
        used = set()
        for d in self.cfg.devices:
            if d.get("bus") == "pcie.0":
                try:
                    used.add(int(str(d.get("addr", "0")).split(".")[0], 16))
                except ValueError:
                    pass
        slot = 1
        while slot in used and slot < 0x1f:
            slot += 1
        rp = {"driver": "pcie-root-port", "port": port, "chassis": chassis,
              "id": f"pci.{n}", "bus": "pcie.0", "addr": hex(slot)}
        self.cfg.devices.append(rp)
        return rp["id"]

    def _ensure_usb_controller(self):
        """The guest USB bus name to hang usb-host devices on, adding an xHCI
        controller (and its root port) if the config has none."""
        for d in self.cfg.devices:
            if d.get("driver") in ("qemu-xhci", "nec-usb-xhci", "usb-ehci", "ich9-usb-ehci1") and not d.get("_disabled"):
                return f"{d.get('id')}.0"
        bus = self._ensure_root_port()
        controller = {"driver": "qemu-xhci", "id": "usb", "bus": bus, "addr": "0x0"}
        if self.cfg.profile == "macos":
            controller.update(driver="nec-usb-xhci", p2=8)
        self.cfg.devices.append(controller)
        return "usb.0"

    # =====================================================================
    # Step 0: CPU vendor
    # =====================================================================
    def _step_vendor(self):
        detected = hostinfo.cpu_vendor()
        model = hostinfo._cpu_model()
        vflag = hostinfo.virt_flag()
        self._note(
            "This wizard fills in everything needed for a single-GPU passthrough "
            "VM and hands you a config ready to launch. It reads this machine "
            "directly, so the same steps work on any Intel or AMD box.", "#ccc")
        self._add(_hline())

        box = QGroupBox("Detected processor")
        gl = QGridLayout(box)
        gl.addWidget(QLabel("Model:"), 0, 0)
        gl.addWidget(QLabel(f"<b>{model}</b>"), 0, 1)
        gl.addWidget(QLabel("Vendor:"), 1, 0)
        gl.addWidget(QLabel(f"<b>{detected.upper() if detected!='unknown' else 'could not detect'}</b>"), 1, 1)
        gl.addWidget(QLabel("Virt flag:"), 2, 0)
        vtext = ({"vmx": "vmx (Intel VT-x) present",
                  "svm": "svm (AMD-V) present"}.get(vflag)
                 or "NONE — enable VT-x/AMD-V (SVM) in your BIOS/UEFI")
        vlbl = QLabel(vtext)
        if not vflag:
            vlbl.setStyleSheet("color:#e5c07b;")
        gl.addWidget(vlbl, 2, 1)
        self._add(box)

        sel = QGroupBox("Set the vendor for this build")
        sl = QVBoxLayout(sel)
        self.vendor_group = QButtonGroup(self)
        self.rb_intel = QRadioButton("Intel  (intel_iommu, no svm)")
        self.rb_amd = QRadioButton("AMD  (amd_iommu, svm + topoext)")
        if self.cfg.profile == "macos":
            sel.setTitle("Linux host processor — for IOMMU setup")
            self.rb_intel.setText("Intel host (intel_iommu)")
            self.rb_amd.setText("AMD host (amd_iommu)")
        self.vendor_group.addButton(self.rb_intel)
        self.vendor_group.addButton(self.rb_amd)
        sl.addWidget(self.rb_intel)
        sl.addWidget(self.rb_amd)
        chosen = self._state().get("vendor") or detected
        (self.rb_intel if chosen == "intel" else self.rb_amd).setChecked(
            chosen in ("intel", "amd"))
        if chosen not in ("intel", "amd"):
            self.rb_intel.setChecked(True)
        self._add(sel)

        if not vflag:
            self._note(
                "⚠ Hardware virtualisation is off. KVM will not start until you "
                "enable it in firmware: look for 'Intel VT-x' / 'SVM Mode' / "
                "'AMD-V'. You can keep going and fix this on the next reboot.",
                "#e5c07b")

        def commit():
            self._state()["vendor"] = "intel" if self.rb_intel.isChecked() else "amd"
            return True
        self.next_action = commit

    # =====================================================================
    # Step 1: IOMMU
    # =====================================================================
    def _step_iommu(self):
        vendor = self._state().get("vendor", hostinfo.cpu_vendor())
        info = hostinfo.iommu_active()
        boot = ws.detect_bootloader()
        current = ws.read_cmdline(boot)
        new_line, changes = ws.plan_iommu_cmdline(vendor, current)

        status = QGroupBox("IOMMU status right now")
        sl = QVBoxLayout(status)
        if info["active"]:
            l = QLabel(f"✓ IOMMU is ACTIVE — {info['groups']} groups present. "
                       "Nothing to do here.")
            l.setStyleSheet("color:#98c379; font-weight:bold;")
            sl.addWidget(l)
        else:
            l = QLabel("✗ IOMMU is NOT active — no groups under "
                       "/sys/kernel/iommu_groups. vfio cannot bind the GPU until "
                       "this is fixed.")
            l.setStyleSheet("color:#e06c75; font-weight:bold;")
            sl.addWidget(l)
        fw = {"intel-vt-d": "firmware exposes Intel VT-d (DMAR table present)",
              "amd-vi": "firmware exposes AMD-Vi (IVRS table present)",
              "none": "no VT-d/AMD-Vi ACPI table — you may need to enable it in BIOS"}
        sl.addWidget(QLabel(fw[info["firmware_table"]]))
        self._add(status)

        self._add(_hline())
        self._note(f"Bootloader: <b>{boot['kind']}</b>", "#ccc")
        cmd = QGroupBox("Kernel command line")
        cl = QVBoxLayout(cmd)
        cur = QPlainTextEdit(current)
        cur.setReadOnly(True)
        cur.setFont(QFont(MONO, 9))
        cur.setMaximumHeight(70)
        cl.addWidget(QLabel("current (next boot):"))
        cl.addWidget(cur)
        self._add(cmd)

        if info["active"]:
            self.next_action = lambda: True
            return

        if not changes:
            self._note(
                "The command line already asks for IOMMU, but it is not active. "
                "That means VT-d / AMD-Vi is switched off in your BIOS/UEFI. "
                "Enable it there, reboot, and come back to this step.", "#e5c07b")
            self.next_action = lambda: True
            return

        plan = QGroupBox("Proposed change")
        pl = QVBoxLayout(plan)
        pl.addWidget(QLabel("changes:  " + "; ".join(changes)))
        newp = QPlainTextEdit(new_line)
        newp.setReadOnly(True)
        newp.setFont(QFont(MONO, 9))
        newp.setMaximumHeight(70)
        pl.addWidget(QLabel("new (next boot):"))
        pl.addWidget(newp)
        self._add(plan)

        self.iommu_log = QPlainTextEdit()
        self.iommu_log.setReadOnly(True)
        self.iommu_log.setFont(QFont(MONO, 9))
        self.iommu_log.setMaximumHeight(120)

        row = QHBoxLayout()
        if boot["kind"] == "grub":
            btn = QPushButton("Apply to GRUB and regenerate (sudo)")
            btn.setObjectName("accent")
            btn.setToolTip("Backs up /etc/default/grub, rewrites the command line, "
                           "and runs grub-mkconfig. You then reboot.")
            btn.clicked.connect(lambda: self._apply_iommu(boot, new_line))
            row.addWidget(btn)
        else:
            self._note(ws.manual_iommu_steps(boot, vendor, new_line), "#e5c07b")
        holder = QWidget()
        holder.setLayout(row)
        pl.insertWidget(0, holder)
        self._add(self.iommu_log)

        self._note(
            "After applying: REBOOT, make sure VT-d / AMD-Vi is enabled in BIOS, "
            "then start the wizard again — it resumes right here and will show "
            "IOMMU as active.", "#ccc")

        # Do not let the user skip past a dead IOMMU by accident.
        def gate():
            if hostinfo.iommu_active()["active"]:
                return True
            r = QMessageBox.question(
                self, "IOMMU still inactive",
                "IOMMU is not active yet. It usually takes a reboot (and the BIOS "
                "setting) before it comes up.\n\nContinue anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            return r == QMessageBox.StandardButton.Yes
        self.next_action = gate

    def _apply_iommu(self, boot, new_line):
        if QMessageBox.question(
                self, "Edit the bootloader",
                "This will back up /etc/default/grub, change the kernel command "
                "line, and run grub-mkconfig with sudo.\n\nProceed?"
                ) != QMessageBox.StandardButton.Yes:
            return
        script = ws.build_iommu_script(boot, new_line)
        if not script:
            self.iommu_log.setPlainText(ws.manual_iommu_steps(
                boot, self._state().get("vendor", ""), new_line))
            return
        argv, env, can = sudo_command(["bash", "-c", script],
                                     prompt="vmstart_2: update the kernel command line (root)")
        if not can:
            self.iommu_log.setPlainText(
                "editing GRUB needs root and no password prompt is available. Run "
                "manually:\n" + ws.manual_iommu_steps(boot, self._state().get("vendor", ""),
                                                      new_line))
            return
        self.iommu_log.setPlainText("running (a password prompt may appear)...")
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        try:
            r = subprocess.run(argv, capture_output=True, text=True, timeout=180, env=env)
            ok, out = r.returncode == 0, (r.stdout + r.stderr).strip()
        except Exception as e:
            ok, out = False, f"failed to run the edit: {e}"
        self.iommu_log.setPlainText(out or ("done" if ok else "failed"))
        if ok:
            QMessageBox.information(
                self, "Applied",
                "Command line updated and GRUB regenerated.\n\n"
                "Reboot now, enable VT-d/AMD-Vi in BIOS if needed, then reopen the "
                "wizard — it will resume at this step with IOMMU active.")

    # =====================================================================
    # Step 2: Guest RAM
    # =====================================================================
    def _step_memory(self):
        host_gib = hostinfo.total_ram_gib()
        pools = hostinfo.hugepage_pools()
        self._note(
            f"This host has <b>{host_gib} GiB</b> of RAM. Leave enough for the "
            "host itself — 8–16 GiB is typical. The guest RAM is backed by "
            "hugepages, which avoids a page-fault storm at boot and cuts TLB "
            "misses.", "#ccc")

        box = QGroupBox("Allocation")
        gl = QGridLayout(box)
        gl.addWidget(QLabel("Guest RAM:"), 0, 0)
        self.mem_gib = QSpinBox()
        self.mem_gib.setRange(1, max(1, host_gib))
        self.mem_gib.setSuffix(" GiB")
        # Sensible default: leave 16 GiB for the host, or half on small machines.
        default = self._current_gib() or (max(1, host_gib - 16) if host_gib > 24
                                          else max(1, host_gib // 2))
        self.mem_gib.setValue(min(default, max(1, host_gib)))
        gl.addWidget(self.mem_gib, 0, 1)

        gl.addWidget(QLabel("Hugepages:"), 1, 0)
        self.mem_hp = QCheckBox("Back guest RAM with hugepages")
        self.mem_hp.setChecked(self.cfg.data.get('memory', {}).get('hugepages', True))
        gl.addWidget(self.mem_hp, 1, 1)

        gl.addWidget(QLabel("Page size:"), 2, 0)
        self.mem_ps = QComboBox()
        for size in sorted(pools):
            self.mem_ps.addItem(_size_name(size), size)
        if not pools:
            self.mem_ps.addItem("2 MiB (no pool yet)", 2 * 1024 * 1024)
        selected = self.mem_ps.findData(self.cfg.data.get('memory', {}).get('pagesize'))
        if selected >= 0: self.mem_ps.setCurrentIndex(selected)
        gl.addWidget(self.mem_ps, 2, 1)

        gl.addWidget(QLabel("mem-path:"), 3, 0)
        self.mem_path = QLineEdit(self._default_mem_path())
        gl.addWidget(self.mem_path, 3, 1)
        self._add(box)

        self.mem_state = QLabel("")
        self.mem_state.setWordWrap(True)
        self._add(self.mem_state)

        row = QHBoxLayout()
        b = QPushButton("Allocate now (and verify)")
        b.setToolTip("Write the pool size and read back what the kernel gave. "
                     "Optional here; the launch also allocates before starting.")
        b.clicked.connect(self._alloc_now)
        row.addWidget(b)
        row.addStretch()
        holder = QWidget(); holder.setLayout(row)
        self._add(holder)

        self.mem_log = QPlainTextEdit()
        self.mem_log.setReadOnly(True)
        self.mem_log.setFont(QFont(MONO, 9))
        self.mem_log.setMaximumHeight(90)
        self._add(self.mem_log)

        self.mem_gib.valueChanged.connect(self._mem_refresh)
        self.mem_ps.currentIndexChanged.connect(self._mem_refresh)
        self.mem_hp.stateChanged.connect(self._mem_refresh)
        self._mem_refresh()

        initial = (self._current_gib(), self.cfg.data.get('memory', {}).get('hugepages', True),
                   self.cfg.data.get('memory', {}).get('pagesize', 2*1024**2), self._default_mem_path())
        def commit():
            selection = (self.mem_gib.value(), self.mem_hp.isChecked(),
                         self.mem_ps.currentData() or 2*1024**2, self.mem_path.text().strip())
            if selection != initial: self._apply_memory(*selection)
            self.changed.emit()
            return True
        self.next_action = commit

    def _default_mem_path(self):
        ram = self._ram_obj() or {}
        path = ram.get("mem-path") or self.cfg.data.get("memory", {}).get("mem_path", "")
        # A captured template carries the source machine's libvirt-managed path,
        # which is neither present nor a hugetlbfs mount on a fresh host. Offer a
        # clean default instead so this box is not asked to reuse another's.
        if not path or "libvirt" in path:
            return "/dev/hugepages/vmstart2"
        return path

    def _current_gib(self):
        m = self.cfg.simple.get("m", "")
        v = m.split("=")[-1] if "=" in m else m
        try:
            if v.endswith("k"):
                return max(1, int(v[:-1]) // (1024 * 1024))
            if v.endswith("G"):
                return int(v[:-1])
            return max(1, int(v) // (1024 ** 3))
        except Exception:
            return 0

    def _mem_refresh(self):
        psize = self.mem_ps.currentData() or 2 * 1024 * 1024
        pages = (self.mem_gib.value() * 1024 ** 3) // psize
        pool = hostinfo.hugepage_pools().get(psize)
        if not self.mem_hp.isChecked():
            self.mem_state.setText("Hugepages off: guest uses ordinary anonymous "
                                   "memory (slower first boot).")
            return
        have = f"{pool['nr']} allocated, {pool['free']} free" if pool else "no pool yet"
        self.mem_state.setText(
            f"Needs <b>{pages}</b> × {_size_name(psize)}.  Pool now: {have}.")

    def _alloc_now(self):
        import subprocess
        psize = self.mem_ps.currentData() or 2 * 1024 * 1024
        pages = (self.mem_gib.value() * 1024 ** 3) // psize
        pool = hostinfo.hugepage_pools().get(psize)
        if not pool:
            self.mem_log.setPlainText(f"no {_size_name(psize)} pool on this kernel")
            return
        script = (f"echo {pages} > {pool['sysfs']}; sync; "
                  f"echo 3 > /proc/sys/vm/drop_caches; "
                  f"echo 1 > /proc/sys/vm/compact_memory 2>/dev/null; "
                  f"echo {pages} > {pool['sysfs']}")
        argv, env, ok = sudo_command(["sh", "-c", script],
                                    prompt="vmstart_2: allocate hugepages (root)")
        if not ok:
            self.mem_log.setPlainText("allocating hugepages needs root and no password "
                                      "prompt is available.")
            return
        try:
            subprocess.run(argv, check=True, capture_output=True, timeout=180, env=env)
        except Exception as e:
            self.mem_log.setPlainText(f"allocation failed: {e}")
            return
        got = (hostinfo.hugepage_pools().get(psize) or {}).get("nr", 0)
        self.mem_log.setPlainText(
            f"{'OK' if got >= pages else 'SHORT'}: requested {pages}, got {got} "
            f"({got * psize // 1024**3} GiB)")
        self._mem_refresh()

    def _apply_memory(self, gib, use_hp, psize, path):
        want = gib * 1024 ** 3
        ram = self._ram_obj()
        if ram is not None:
            ram["size"] = want
            ram["prealloc"] = True
            if use_hp:
                ram["qom-type"] = "memory-backend-file"
                ram["mem-path"] = path
                ram.pop("share", None)
                ram.pop("discard-data", None)
            else:
                ram["qom-type"] = "memory-backend-ram"
                ram.pop("mem-path", None)
        self.cfg.simple["m"] = f"size={gib * 1024 * 1024}k"
        m = self.cfg.data.setdefault("memory", {})
        m.update({"hugepages": use_hp, "pagesize": psize, "mem_path": path})

    # =====================================================================
    # Step 3: CPU cores
    # =====================================================================
    def _step_cores(self):
        topo = hostinfo.cpu_topology()
        total = topo["cores"]
        threads = topo["threads"]
        l3 = topo["l3_to_cores"]
        self._note(
            f"This CPU has <b>{total} physical cores</b> / {threads} threads"
            f"{' (SMT on)' if topo['smt'] else ''}. Whole cores are handed to the "
            "guest — never half of an SMT pair, which is what causes stutter. "
            + (f"It has {len(l3)} L3 groups (CCDs); the guest is kept inside one "
               "to avoid cross-CCD latency." if len(l3) > 1 else ""), "#ccc")

        box = QGroupBox("Split")
        gl = QGridLayout(box)
        gl.addWidget(QLabel("Cores to LEAVE for the host:"), 0, 0)
        self.leave = QSpinBox()
        self.leave.setRange(1, max(1, total - 1))
        prev = self._state().get("leave_cores")
        self.leave.setValue(prev if prev else (8 if total > 12 else max(1, total // 4)))
        gl.addWidget(self.leave, 0, 1)

        if len(l3) > 1:
            gl.addWidget(QLabel("Prefer L3/CCD group:"), 1, 0)
            self.ccd = QComboBox()
            self.ccd.addItem("auto (first group)", None)
            for k in l3:
                self.ccd.addItem(f"L3 {k}", k)
            gl.addWidget(self.ccd, 1, 1)
        else:
            self.ccd = None
        self._add(box)

        self.core_preview = QPlainTextEdit()
        self.core_preview.setReadOnly(True)
        self.core_preview.setFont(QFont(MONO, 9))
        self.core_preview.setMinimumHeight(160)
        self._add(self.core_preview)

        self.leave.valueChanged.connect(self._cores_refresh)
        if self.ccd:
            self.ccd.currentIndexChanged.connect(self._cores_refresh)
        self._cores_refresh()

        def commit():
            self._apply_pinning()
            self._state()["leave_cores"] = self.leave.value()
            self.changed.emit()
            return True
        self.next_action = commit

    def _cores_refresh(self):
        prefer = self.ccd.currentData() if self.ccd else None
        sp = hostinfo.suggest_pinning(self.leave.value(), prefer)
        topo = hostinfo.cpu_topology()
        threads = 2 if topo["smt"] else 1
        gc = sp["guest_cores"]
        lines = [
            f"guest gets  : {len(gc)} cores  ->  {len(sp['vcpupin'])} vCPUs "
            f"({len(gc)} x {threads} threads)",
            f"guest cores : {gc}",
            f"host cores  : {sp['host_cores']}",
            f"emulatorpin : {sp['emulatorpin'] or '(none)'}",
            f"iothreadpin : {', '.join(sp['iothreadpin']) or '(none)'}",
            "",
            "vcpu -> host cpu:",
        ]
        lines += [f"  vcpu {e['vcpu']:>2} -> cpu {e['cpuset']:>2}  (core {e['core']})"
                  for e in sp["vcpupin"]]
        self.core_preview.setPlainText("\n".join(lines))

    def _apply_pinning(self):
        prefer = self.ccd.currentData() if self.ccd else None
        sp = hostinfo.suggest_pinning(self.leave.value(), prefer)
        topo = hostinfo.cpu_topology()
        smt = topo["smt"]
        threads = 2 if smt else 1
        cores = len(sp["guest_cores"])
        existing = self.cfg.data.get('pinning', {})
        if existing.get('vcpupin') == sp['vcpupin'] and existing.get('smt') == smt:
            return
        plan = {
            "vcpus": sp["vcpus"],
            "guest_cores": sp["guest_cores"],
            "vcpupin": sp["vcpupin"],
            "smt": smt,
            "emulatorpin": sp["emulatorpin"],
            "iothreadpin": sp["iothreadpin"],
            "host_cpus": sorted(c for core in sp["host_cores"]
                                for c in topo["core_to_cpus"].get(core, [])),
            "vcpusched": {"scheduler": "rr", "priority": 1},
            "emulatorsched": {"scheduler": "fifo", "priority": 10},
            "iothreadsched": {"scheduler": "fifo", "priority": 10},
            # rr/fifo above are throttled to 95% of every period unless this is
            # -1, which is the whole point of asking for them. Stated here so
            # the wizard's plan is complete rather than relying on the fallback
            # the CPU Pinning tab applies to older configs.
            "rt_runtime_us": -1,
        }
        # Hardware placement may change; retain the captured scheduling policy.
        for key in ('vcpusched', 'emulatorsched', 'iothreadsched', 'rt_runtime_us'):
            if key in existing: plan[key] = existing[key]
        self.cfg.data["pinning"] = dict(existing, **plan)
        self.cfg.smp["topology"] = {"sockets": "1", "dies": "1", "clusters": "1",
                                    "cores": str(max(1, cores)), "threads": str(threads)}
        self.cfg.smp["vcpus"] = str(max(1, cores) * threads)

    # =====================================================================
    # Step 4: GPU passthrough
    # =====================================================================
    def _step_gpu(self):
        self.host_gpus = hostinfo.gpus()
        self.host_pci = hostinfo.pci_devices()
        self._note(
            "Pick the GPU to hand to the guest. Every function on the card (video "
            "plus its HDMI-audio, USB-C, etc.) is passed together, because they "
            "share an IOMMU group and cannot be split.", "#ccc")

        box = QGroupBox("GPU")
        gl = QGridLayout(box)
        gl.addWidget(QLabel("Card:"), 0, 0)
        self.gpu_combo = QComboBox()
        self.gpu_combo.addItem('Skip GPU passthrough — use a virtual display', None)
        for g in self.host_gpus:
            fns = ", ".join(f["slot"].rsplit(".", 1)[-1] for f in g["functions"])
            self.gpu_combo.addItem(f"{g['slot']}  {g['device']}   (functions {fns})",
                                   g["slot"])
        gl.addWidget(self.gpu_combo, 0, 1, 1, 3)

        gl.addWidget(QLabel("Patched vBIOS:"), 1, 0)
        self.gpu_rom = QLineEdit()
        configured = next((d for d in self.cfg.devices
                           if d.get('driver') == 'vfio-pci' and not d.get('_disabled')
                           and self._baseline_pci_matches(d.get('host', ''))
                           and any(d.get('host', '').rsplit('.', 1)[0] == g['slot'].rsplit('.', 1)[0]
                                   for g in self.host_gpus)), {})
        for index in range(1, self.gpu_combo.count()):
            if self.gpu_combo.itemData(index).rsplit('.', 1)[0] == configured.get('host', '').rsplit('.', 1)[0]:
                self.gpu_combo.setCurrentIndex(index)
                break
        # Start empty instead of inheriting a captured/saved machine's ROM.
        # Keep only choices made in this wizard when navigating Back/Next.
        self.gpu_rom.setText(self._gpu_rom_choices.get(self.gpu_combo.currentData(), ''))
        self.gpu_combo.currentIndexChanged.connect(self._gpu_rom_selection_changed)
        self.gpu_rom.textChanged.connect(self._remember_gpu_rom)
        self.gpu_rom.setPlaceholderText("Optional — Browse for a ROM or use AutoDump")
        gl.addWidget(self.gpu_rom, 1, 1)
        self.gpu_browse = QPushButton("Browse…")
        self.gpu_browse.clicked.connect(self._browse_rom)
        gl.addWidget(self.gpu_browse, 1, 2)
        self.gpu_autodump = QPushButton("AutoDump")
        self.gpu_autodump.setToolTip("Read and validate the selected GPU's vBIOS, strip any pre-header, and fill its ROM path.")
        self.gpu_autodump.clicked.connect(self._auto_dump_rom)
        gl.addWidget(self.gpu_autodump, 1, 3)
        gl.setColumnStretch(1, 1)
        self.gpu_rom_status = QLabel()
        self.gpu_rom_status.setObjectName('muted')
        self.gpu_rom_status.setWordWrap(True)
        self.gpu_rom_status.hide()
        gl.addWidget(self.gpu_rom_status, 2, 1, 1, 3)
        self._add(box)

        self.gpu_info = QPlainTextEdit()
        self.gpu_info.setReadOnly(True)
        self.gpu_info.setFont(QFont(MONO, 9))
        self.gpu_info.setMaximumHeight(150)
        self._add(self.gpu_info)
        self.gpu_combo.currentIndexChanged.connect(self._gpu_refresh)
        self._gpu_refresh()

        if not self.host_gpus:
            self._note("No GPU found on this host.", "#e06c75")

        def commit():
            if self._gpu_dump_token is not None:
                return False
            slot = self.gpu_combo.currentData()
            if not slot:
                for dev in self.cfg.devices:
                    if dev.get('driver') == 'vfio-pci': dev['_disabled'] = True
                return True
            self._apply_gpu(slot, self.gpu_rom.text().strip())
            self.changed.emit()
            return True
        self.next_action = commit

    def _baseline_pci_matches(self, slot):
        from pathlib import Path
        saved = self._state().get('baseline_pci', {}).get(slot)
        if not saved: return not self._state().get('baseline_pci')
        try:
            device = Path('/sys/bus/pci/devices')/slot
            return all((device/name).read_text().strip() == value for name,value in saved.items())
        except OSError:
            return False

    def _gpu_refresh(self):
        slot = self.gpu_combo.currentData()
        g = next((x for x in self.host_gpus if x["slot"] == slot), None)
        for widget in (self.gpu_rom, self.gpu_browse, self.gpu_autodump):
            widget.setEnabled(bool(g) and self._gpu_dump_token is None)
        if not g:
            self.gpu_info.setPlainText("")
            return
        grp = g.get("iommu_group", "?")
        members = g.get("group_members", [])
        lines = [f"IOMMU group {grp}:"]
        for m in members:
            hd = next((d for d in self.host_pci if d["slot"] == m), None)
            lines.append(f"  {m}  {hd['device'] if hd else ''} "
                         f"[{hd['class'] if hd else ''}]")
        others = [m for m in members
                  if not any(m == f["slot"] for f in g["functions"])]
        bridges = [m for m in others if hostinfo.pci_is_bridge(m)]
        extra = [m for m in others if m not in bridges]
        if bridges:
            lines += ["", "• Group also holds bridge(s): " + ", ".join(bridges),
                      "  A root port / bridge here is FINE — vfio lets it stay put, "
                      "so no ACS override is needed for it."]
        if extra:
            lines += ["", "⚠ This group also contains non-bridge devices that are "
                          "NOT part of the GPU:", "  " + ", ".join(extra),
                      "Those must be passed too, or you need an ACS-override kernel. "
                      "Add them on the PCI/USB tab, or the launch will refuse."]
        elif not bridges:
            lines += ["", "✓ Group holds only this GPU's own functions — clean to "
                          "pass."]
        else:
            lines += ["", "✓ Only GPU functions + a bridge in this group — clean to "
                          "pass."]
        self.gpu_info.setPlainText("\n".join(lines))

    def _remember_gpu_rom(self, text):
        slot = self.gpu_combo.currentData()
        if slot:
            self._gpu_rom_choices[slot] = text

    def _gpu_rom_selection_changed(self):
        self.gpu_rom.setText(self._gpu_rom_choices.get(self.gpu_combo.currentData(), ''))
        self.gpu_rom_status.clear()
        self.gpu_rom_status.hide()

    def _browse_rom(self):
        p, _ = QFileDialog.getOpenFileName(self, "Select patched vBIOS", os.path.expanduser("~"),
                                           "ROM (*.rom *.bin);;All files (*)")
        if p:
            self.gpu_rom.setText(p)

    def _auto_dump_rom(self):
        slot = self.gpu_combo.currentData()
        if not slot or self._gpu_dump_token is not None:
            return
        capture = getattr(self, 'capture_gpu_rom', None)
        self.gpu_rom_status.show()
        if capture is None:
            self.gpu_rom_status.setText('AutoDump is unavailable. Browse for a ROM instead.')
            return
        token = self._gpu_dump_token = object()
        controls = (self.gpu_combo, self.gpu_rom, self.gpu_browse, self.gpu_autodump,
                    self.btn_back, self.btn_next, self.btn_startover)
        for widget in controls:
            widget.setEnabled(False)
        self.gpu_rom_status.setText('Reading and preparing this GPU’s vBIOS…')

        def done(path):
            # A rebuilt step/profile must never receive an old GPU's result.
            if self._gpu_dump_token is not token:
                return
            self._gpu_dump_token = None
            for widget in controls:
                widget.setEnabled(True)
            if path and self.gpu_combo.currentData() == slot:
                self.gpu_rom.setText(path)
                self.gpu_rom_status.setText('vBIOS automatically dumped and validated. Its path is ready for Next.')
            else:
                self.gpu_rom_status.setText('AutoDump did not complete. Retry or Browse for a ROM.')

        try:
            capture(slot, done)
        except Exception as error:
            done(None)
            self.gpu_rom_status.setText(str(error))

    def _apply_gpu(self, slot, rom):
        gpu = next((g for g in self.host_gpus if g["slot"] == slot), None)
        if not gpu:
            return
        active = [d for d in self.cfg.devices if d.get('driver') == 'vfio-pci' and not d.get('_disabled')]
        functions = {f['slot'] for f in gpu['functions']}
        if functions.issubset({d.get('host') for d in active}) and all(
                d.get('romfile', '') == rom for d in active if d.get('host') == slot):
            return
        # Clear any GPU passthrough already in the config (the captured template
        # carries the other machine's card) so the wizard's choice is the only one.
        for d in self.cfg.devices:
            if d.get("driver") == "vfio-pci" and not d.get("_disabled"):
                d["_disabled"] = True
        # Audio function first so it does not land as guest function 0. Each
        # function goes on its OWN guest root port at slot 0x0 — that is why the
        # addresses are all 0x0 and do not collide: the buses (pci.5, pci.6, …)
        # differ. A fresh port is created if the config runs out.
        for f in sorted(gpu["functions"], key=lambda x: x["slot"], reverse=True):
            dev = {"driver": "vfio-pci", "host": f["slot"],
                   "id": self._next_dev_id("hostdev"),
                   "bus": self._ensure_root_port(), "addr": "0x0"}
            if rom and f['slot'] == gpu['slot']:
                dev["romfile"] = rom
            self.cfg.devices.append(dev)

    # =====================================================================
    # Step 5: USB devices
    # =====================================================================
    def _step_usb(self):
        self.host_usb = hostinfo.usb_devices()
        self._note(
            "Tick the USB devices to hand to the guest — your keyboard, mouse and "
            "anything else it needs directly. They are passed by vendor:product "
            "id, which survives replugging into another port.", "#ccc")

        box = QGroupBox("USB devices on this host")
        vl = QVBoxLayout(box)
        self.usb_boxes = []
        already = self._existing_usb_ids()
        for u in self.host_usb:
            cb = QCheckBox(f"{u['label']}   (bus {u['bus']} dev {u['device']})")
            if (u["vendor_id"], u["product_id"]) in already:
                cb.setChecked(True)
            self.usb_boxes.append((cb, u))
            vl.addWidget(cb)
        if not self.host_usb:
            vl.addWidget(QLabel("No non-hub USB devices found."))
        self._add(box)
        self._note("Tip: don't pass the only keyboard/mouse if you still need to "
                   "control the host while the VM runs.", "#888")

        def commit():
            self._apply_usb()
            self.changed.emit()
            return True
        self.next_action = commit

    def _existing_usb_ids(self):
        out = set()
        for d in self.cfg.devices:
            if d.get("driver") == "usb-host" and not d.get("_disabled"):
                vid, pid = d.get("vendorid"), d.get("productid")
                try:
                    out.add((f"{int(str(vid), 0):04x}", f"{int(str(pid), 0):04x}"))
                except (TypeError, ValueError):
                    pass
        return out

    def _apply_usb(self):
        selected = {(u['vendor_id'], u['product_id']) for cb,u in self.usb_boxes if cb.isChecked()}
        if selected == self._existing_usb_ids(): return
        # Rebuild the usb-host set from the ticks: disable the old, add the chosen.
        for d in self.cfg.devices:
            if d.get("driver") == "usb-host" and not d.get("_disabled"):
                d["_disabled"] = True
        usb_bus = self._ensure_usb_controller()   # add an xHCI if none exists
        port = 1
        for cb, u in self.usb_boxes:
            if not cb.isChecked():
                continue
            dev = {"driver": "usb-host", "id": self._next_dev_id("hostdev"),
                   "bus": usb_bus,
                   "vendorid": int(u["vendor_id"], 16),
                   "productid": int(u["product_id"], 16),
                   "port": str(port)}
            self.cfg.devices.append(dev)
            port += 1

    # =====================================================================
    # Step 6: Drives
    # =====================================================================
    def _step_drives(self):
        self.host_disks = hostinfo.block_devices()
        self._note(
            "Tick the drives to give the guest as raw block devices (best "
            "performance and the closest thing to bare metal). Choose how each "
            "path is written: the by-id path is stable across reboots and kernel "
            "upgrades; the /dev node is shorter but can move.", "#ccc")

        box = QGroupBox("Whole disks on this host")
        gl = QGridLayout(box)
        for c, h in enumerate(("use", "disk", "path (what actually gets passed)",
                               "boot")):
            gl.addWidget(QLabel(f"<b>{h}</b>"), 0, c)
        self.disk_rows = []
        attached = self._attached_disk_targets()
        existing_boot = self._existing_bootindex()   # disk target -> bootindex
        for i, d in enumerate(self.host_disks, start=1):
            cb = QCheckBox()
            # Two identical 500 GB twins differ only by serial, so show the exact
            # by-id string that goes into the config, not just model+size.
            disc = os.path.basename(d["preferred"]) if d["by_id"] else d["dev"]
            label = QLabel(f"{d['dev']}  •  {d['size_h']}  •  {d['model'] or '?'}"
                           + ("  •  ⚠ host system disk" if _looks_like_root(d) else ""))
            idlbl = QLabel(disc)
            idlbl.setStyleSheet("color:#888;")

            style = QComboBox()
            if d["by_id"]:
                style.addItem("by-id (stable)", d["preferred"])
            style.addItem("/dev node (moves between boots!)", d["dev"])
            if not d["by_id"]:
                style.setStyleSheet("color:#e5c07b;")

            boot = QSpinBox()
            boot.setRange(0, 20)
            boot.setSpecialValueText("—")   # 0 == not in the boot order
            # Pre-fill from the config, and pre-tick if already attached.
            pre = None
            for tgt in (d["preferred"], d["dev"], *d["by_id"]):
                if tgt in attached:
                    cb.setChecked(True)
                    pre = existing_boot.get(tgt, pre)
                    break
            boot.setValue(pre or 0)

            devcol = QWidget()
            dv = QVBoxLayout(devcol)
            dv.setContentsMargins(0, 0, 0, 0)
            dv.setSpacing(0)
            dv.addWidget(label)
            dv.addWidget(idlbl)
            gl.addWidget(cb, i, 0)
            gl.addWidget(devcol, i, 1)
            gl.addWidget(style, i, 2)
            gl.addWidget(boot, i, 3)
            self.disk_rows.append((cb, style, boot, d))
        if not self.host_disks:
            gl.addWidget(QLabel("No disks enumerated."), 1, 0, 1, 4)
        self._add(box)
        self._note(
            "The grey line under each disk is the exact path written to the config "
            "— for two identical drives it is the only thing that tells them apart. "
            "<b>Boot</b>: 1 = tried first (put your OS or Ventoy disk here), 2 = next, "
            "'—' = not in the boot order.", "#ccc")
        self._note(
            "The wizard keeps your selected physical disks and their existing options. "
            "Firmware, OpenCore and support media are retained. "
            "New drives are added as SATA (ide-hd) with a random serial; "
            "change the front-end on the Disks tab if you want virtio.", "#ccc")
        self._note(
            "⚠ Do not pass the disk the host itself boots from unless you know "
            "what you are doing — the guest writing to a mounted host filesystem "
            "will corrupt it. A disk with no stable by-id can only be passed by its "
            "/dev node, which may point at a different disk after a reboot.", "#e5c07b")

        def commit():
            # QEMU refuses to start if two devices share a bootindex, so catch it
            # here rather than after the desktop is already torn down.
            picks = [boot.value() for cb, style, boot, d in self.disk_rows
                     if cb.isChecked() and boot.value() > 0]
            dupes = {v for v in picks if picks.count(v) > 1}
            if dupes:
                QMessageBox.warning(
                    self, "Duplicate boot order",
                    f"Boot order value(s) {sorted(dupes)} are used by more than one "
                    f"disk. Each disk needs a unique boot number (or '—').")
                return False
            self._reconcile_host_disks()
            self._apply_drives()
            self.changed.emit()
            self.config_reloaded.emit()   # disks tab must rebuild its cards
            return True
        self.next_action = commit

    def _reconcile_host_disks(self):
        """Keep boot media and existing disk options when Next is unchanged."""
        selected = {}
        for cb, style, boot, disk in self.disk_rows:
            if cb.isChecked():
                for path in (disk['preferred'], disk['dev'], *disk['by_id']):
                    selected[path] = (style.currentData(), boot.value())
        removed = set()
        for block in self.cfg.blockdevs:
            filename = block.get('filename', '')
            if block.get('_disabled') or not filename.startswith('/dev/'): continue
            if filename in selected:
                path, bootindex = selected[filename]
                block['filename'] = path
                nodes = {block.get('node-name')}
                for _ in range(len(self.cfg.blockdevs)):
                    nodes.update(b.get('node-name') for b in self.cfg.blockdevs if b.get('file') in nodes)
                for dev in self.cfg.devices:
                    if dev.get('drive') in nodes:
                        if bootindex: dev['bootindex'] = bootindex
                        else: dev.pop('bootindex', None)
            else:
                block['_disabled'] = True
                removed.add(block.get('node-name'))
        for _ in range(len(self.cfg.blockdevs)):
            for block in self.cfg.blockdevs:
                if block.get('file') in removed:
                    block['_disabled'] = True
                    removed.add(block.get('node-name'))
        for dev in self.cfg.devices:
            if dev.get('drive') in removed: dev['_disabled'] = True

    def _attached_disk_targets(self):
        out = set()
        for b in self.cfg.blockdevs:
            if b.get("_disabled"):
                continue
            fn = b.get("filename")
            if fn:
                out.add(fn)
        return out

    def _existing_bootindex(self):
        """Map each currently-attached disk's filename -> its bootindex, so the
        wizard can pre-fill the boot spinboxes from what is already configured."""
        node_boot = {}
        for d in self.cfg.devices:
            if d.get("_disabled") or not d.get("drive"):
                continue
            bi = d.get("bootindex")
            if bi is not None:
                node_boot[d["drive"]] = bi
        for _ in range(len(self.cfg.blockdevs)):
            for block in self.cfg.blockdevs:
                if block.get('node-name') in node_boot and isinstance(block.get('file'), str):
                    node_boot[block['file']] = node_boot[block['node-name']]
        out = {}
        for b in self.cfg.blockdevs:
            if b.get("_disabled"):
                continue
            fn, node = b.get("filename"), b.get("node-name")
            if fn and node in node_boot:
                out[fn] = node_boot[node]
        return out

    # Front-ends and controllers that represent a guest disk/optical drive. The
    # OVMF pflash pair is NOT here: it is firmware, identified by node-name, and
    # kept. Everything else the captured template carried is a clone leftover.
    _DISK_DRIVERS = {"ide-hd", "ide-cd", "nvme", "nvme-ns", "scsi-hd", "scsi-cd",
                     "virtio-blk-pci", "usb-storage"}

    def _clear_all_disks(self):
        """Disable every guest disk (blockdev + front-end) except OVMF firmware,
        so the drive step is authoritative and no stale disk survives it."""
        for b in self.cfg.blockdevs:
            if b.get("_disabled") and not b.get("_inactive"):
                continue
            node = str(b.get("node-name", ""))
            if "pflash" in node:              # OVMF CODE / VARS — firmware, keep
                continue
            b["_disabled"] = True
            b.pop("_inactive", None)
        for d in self.cfg.devices:
            if d.get("_disabled") and not d.get("_inactive"):
                continue
            if d.get("driver") in self._DISK_DRIVERS or d.get("drive"):
                d["_disabled"] = True
                d.pop("_inactive", None)

    def _apply_drives(self):
        attached = self._attached_disk_targets()
        for cb, style, boot, d in self.disk_rows:
            if not cb.isChecked():
                continue
            target = style.currentData()
            # _clear_all_disks ran first, so anything still attached is either
            # firmware or a disk added earlier this same pass; skip duplicates.
            if any(a in attached for a in (d["preferred"], d["dev"], *d["by_id"])):
                continue
            # Same numbering and the same slot reuse as the Disks tab, so the
            # two never disagree about which names are free. _clear_all_disks
            # just turned every disk into a tombstone, and claim_slot below
            # takes those slots back rather than shadowing them with duplicates.
            n = model.free_index(self.cfg.blockdevs, self.cfg.devices)
            bd = {"driver": "host_device", "filename": target, "aio": "threads",
                  "node-name": f"vmstart2-{n}-storage", "read-only": False,
                  "discard": "unmap", "cache": {"direct": True, "no-flush": False}}
            dev = {"driver": "ide-hd", "bus": self._free_ide_port(),
                   "drive": bd["node-name"], "id": f"vmstart2-disk{n}",
                   "write-cache": "on", "serial": randomize.serial(11)}
            if boot.value() > 0:
                dev["bootindex"] = boot.value()
            model.claim_slot(self.cfg.blockdevs, "node-name", bd["node-name"], bd)
            model.claim_slot(self.cfg.devices, "id", dev["id"], dev)
            attached.add(target)

    def _free_ide_port(self):
        used = set()
        for d in self.cfg.devices:
            if d.get("driver") == "ide-hd" and not d.get("_disabled"):
                b = str(d.get("bus", ""))
                if b.startswith("ide.") and b[4:].isdigit():
                    used.add(int(b[4:]))
        n = 0
        while n in used:
            n += 1
        return f"ide.{n}"

    # =====================================================================
    # Step 7: Vendor tuning
    # =====================================================================
    def _step_tune(self):
        if self.cfg.profile == "macos":
            self._note("The Mac profile keeps its own CPU and firmware configuration. "
                       "OpenCore, CPU model, RAM size and USB controller work together. "
                       "Change CPU settings on CPU features. Use Mac & OpenCore for boot arguments, "
                       "Mac identity, security and synchronizing the memory description after changing RAM.")
            self._note("Host vendor tuning is not applied to the Mac guest.")
            return
        vendor = self._state().get("vendor", hostinfo.cpu_vendor())
        self._note(
            "Final vendor-specific touches to the CPU model. The guest is given "
            "the host CPU with the hypervisor hidden; the flags below are the ones "
            "that actually differ between Intel and AMD.", "#ccc")

        feats = VENDOR_FEATURES[vendor]
        box = QGroupBox(f"CPU model for {vendor.upper()}")
        vl = QVBoxLayout(box)
        vl.addWidget(QLabel("cpu = host," + ",".join(f"{k}={v}" for k, v in feats)))
        if vendor == "amd":
            vl.addWidget(QLabel("• <b>svm</b> + topoext ON — AMD virtualisation and "
                                "correct core/thread topology (vmx and the Intel "
                                "flags are removed)."))
        else:
            vl.addWidget(QLabel("• <b>vmx</b> + ssbd ON — Intel VT-x, swapped in for "
                                "AMD's svm; the AMD-only flags (svm/topoext/amd-ssbd) "
                                "are removed so QEMU accepts the model."))
        vl.addWidget(QLabel("• hypervisor / kvm / kvmclock / pmu OFF — hides the most "
                            "obvious 'I am a VM' tells."))
        self._add(box)

        self.tune_apply = QCheckBox("Apply these CPU flags (recommended)")
        self.tune_apply.setChecked(True)
        self._add(self.tune_apply)

        # Custom KVM-module rebuild. This is the user's patched-KVM tooling; it is
        # NOT forced off — the checkbox simply reflects the current config so the
        # AMD box keeps rebuilding as before. We only surface why it may fail on a
        # given machine and let the operator decide.
        tools = self.cfg.data.get("tools", {})
        self.kvm_build = None
        if tools.get("kvm_build"):
            self._add(_hline())
            managed = tools.get('kvm_build', '').endswith('/module-tool.sh')
            kbox = QGroupBox("Custom KVM module" if managed else "Custom KVM module rebuild")
            kl = QVBoxLayout(kbox)
            self.kvm_build = QCheckBox("Use the custom KVM module automatically when compatible" if managed else "Rebuild the custom KVM module on launch")
            self.kvm_build.setChecked(bool(tools.get("kvm_build_enabled")))
            kl.addWidget(self.kvm_build)
            path = tools.get("kvm_build", "")
            kl.addWidget(QLabel(f"script: {path}"))
            for h in self._kvm_build_hints(path):
                l = QLabel(h)
                l.setWordWrap(True)
                l.setStyleSheet("color:#e5c07b;")
                kl.addWidget(l)
            keep = QLabel("Standard KVM is used automatically when the custom module cannot run on this CPU/kernel. "
                          "Your preference is kept; a matching build is prepared on the next compatible launch."
                          if managed else "Leave this ON where the patched module belongs (your AMD "
                          "box); turn it OFF on a machine you are not using that build "
                          "on. The setting is saved either way — nothing is hardcoded.")
            keep.setWordWrap(True)
            keep.setStyleSheet("color:#888;")
            kl.addWidget(keep)
            self._add(kbox)

        self._note(
            "Machine-level options (Q35, SMM/Secure-Boot, timers) are the same for "
            "both vendors and are already set; adjust them on the Machine tab if "
            "needed.", "#888")

        def commit():
            if self.tune_apply.isChecked():
                self._apply_vendor_cpu(vendor)
            if self.kvm_build is not None:
                self.cfg.data.setdefault("tools", {})["kvm_build_enabled"] = \
                    self.kvm_build.isChecked()
            self.changed.emit()
            self.config_reloaded.emit()
            return True
        self.next_action = commit

    def _kvm_build_hints(self, path):
        """Non-binding warnings about whether the KVM rebuild will succeed here."""
        import edition_runtime
        if edition_runtime.managed_module(self.cfg):
            import module_policy
            reason=module_policy.unavailable()
            return [reason+'. Standard KVM is used automatically; you can continue.'] if reason else []
        hints = []
        if path and not os.path.isfile(path):
            hints.append("⚠ This build script does not exist on this machine, so the "
                         "rebuild would fail immediately.")
        try:
            import subprocess
            lsmod = subprocess.run(["lsmod"], capture_output=True, text=True,
                                   timeout=5).stdout
            for line in lsmod.splitlines():
                p = line.split()
                if len(p) >= 3 and p[0] == "kvm" and p[2].strip() not in ("0", ""):
                    hints.append("⚠ The base 'kvm' module is in use right now, so a "
                                 "reload fails with 'Module kvm is in use' until every "
                                 "VM/KVM consumer is stopped — this is what aborted the "
                                 "launch. Stop other VMs, or turn this off here.")
                    break
        except Exception:
            pass
        return hints

    def _apply_vendor_cpu(self, vendor):
        if self.cfg.profile == "macos":
            return
        cpu = self.cfg.data.setdefault("cpu", {})
        cpu["model"] = "host"
        from collections import OrderedDict
        cpu["features"] = OrderedDict(VENDOR_FEATURES[vendor])

    # =====================================================================
    # Step 8: Finish
    # =====================================================================
    def _step_done(self):
        vendor = self._state().get("vendor", hostinfo.cpu_vendor())
        gpus = [d.get("host") for d in self.cfg.devices
                if d.get("driver") == "vfio-pci" and not d.get("_disabled")]
        usb = [d for d in self.cfg.devices
               if d.get("driver") == "usb-host" and not d.get("_disabled")]
        disks = [b.get("filename") for b in self.cfg.blockdevs
                 if b.get("driver") == "host_device" and not b.get("_disabled")
                 and b.get("filename")]
        pin = self.cfg.data.get("pinning", {})
        iommu = hostinfo.iommu_active()

        self._note("<b>Setup complete.</b> Here is what the wizard built:", "#98c379")
        summary = QPlainTextEdit()
        summary.setReadOnly(True)
        summary.setFont(QFont(MONO, 10))
        summary.setMinimumHeight(230)
        lines = [
            f"vendor       : {vendor.upper()}",
            f"IOMMU        : {'ACTIVE (' + str(iommu['groups']) + ' groups)' if iommu['active'] else 'NOT ACTIVE — reboot / enable in BIOS'}",
            f"guest RAM    : {self._current_gib()} GiB "
            f"({'hugepages' if self.cfg.data.get('memory', {}).get('hugepages') else 'plain'})",
            f"vCPUs        : {self.cfg.smp.get('vcpus')} "
            f"({self.cfg.smp.get('topology', {}).get('cores')} cores x "
            f"{self.cfg.smp.get('topology', {}).get('threads')} threads)",
            f"GPU funcs    : {', '.join(gpus) or '(none)'}",
            f"USB devices  : {len(usb)}",
            f"drives       : {len(disks)}",
        ]
        tools = self.cfg.data.get("tools", {})
        if tools.get("kvm_build"):
            lines.append(f"KVM rebuild  : {'ON' if tools.get('kvm_build_enabled') else 'off'}")
        for d in disks:
            lines.append(f"   - {d}")
        summary.setPlainText("\n".join(lines))
        self._add(summary)

        network = self.cfg.data.get('network', {})
        bridge = network.get('bridge', '')
        self.use_nat = None
        if network.get('mode') == 'tap' and bridge and bridge not in hostinfo.net_bridges():
            self.bridge_notice = QLabel(f'Bridge {bridge} is missing. Create it from your connected Ethernet adapter, or use NAT below.')
            self.bridge_notice.setWordWrap(True)
            self._add(self.bridge_notice)
            self.btn_create_bridge = QPushButton('Create Bridge')
            self.btn_create_bridge.setToolTip('Preserves the wired connection’s IP/DNS settings and restores it if bridge activation fails.')
            self.btn_create_bridge.clicked.connect(lambda: self.create_bridge.emit(bridge))
            self._add(self.btn_create_bridge)
            self.use_nat = QCheckBox(f'Use NAT networking — bridge {bridge} is unavailable on this PC')
            self.use_nat.setChecked(True)
            self._add(self.use_nat)
            self._note('Shares the host internet connection without creating a bridge. You can change it later under Machine & network.')

        problems = self.cfg.validate()
        if problems:
            p = QPlainTextEdit()
            p.setReadOnly(True)
            p.setFont(QFont(MONO, 9))
            p.setMaximumHeight(90)
            p.setPlainText("\n".join(f"[{s}] {m}" for s, m in problems))
            self._add(QLabel("Config check:"))
            self._add(p)

        row = QHBoxLayout()
        b1 = QPushButton("Go to Launch Procedure")
        b1.clicked.connect(lambda: self.goto_tab.emit("Launch Procedure"))
        row.addWidget(b1)
        b2 = QPushButton("Open Command Preview")
        b2.clicked.connect(lambda: self.goto_tab.emit("Command Preview"))
        row.addWidget(b2)
        row.addStretch()
        holder = QWidget(); holder.setLayout(row)
        self._add(holder)

        self.btn_next.setText("Finish")
        def finish():
            if self.use_nat is not None and self.use_nat.isChecked():
                from network_config import configure
                configure(self.cfg, 'user')
            self._state()["complete"] = True
            self.finished.emit()
            return True
        self.next_action = finish


def _size_name(n):
    if n >= 1024 ** 3:
        return f"{n // 1024 ** 3} GiB"
    if n >= 1024 ** 2:
        return f"{n // 1024 ** 2} MiB"
    return f"{n} B"


def _looks_like_root(disk):
    """Best-effort flag for the disk the host is running from, so the drive step
    can warn before someone hands their live system disk to the guest."""
    try:
        src = os.path.realpath("/dev/root")
    except Exception:
        src = ""
    name = disk.get("name", "")
    # Cheap heuristic: the disk backing '/' shows up in /proc/mounts partitions.
    try:
        for line in open("/proc/mounts"):
            dev, mnt = line.split()[0], line.split()[1]
            if mnt == "/" and name and os.path.basename(dev).startswith(name):
                return True
    except Exception:
        pass
    return False
