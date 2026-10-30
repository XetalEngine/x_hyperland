#!/usr/bin/env python3
"""Passthrough and machine tabs for vmstart_2.

PassthroughTab covers vfio-pci and usb-host devices: add, remove and re-address
anything, chosen from what the host actually has rather than typed from memory.
MachineTab covers the -machine option bag, -global overrides and the loose
top-level flags, each with what it costs you to change it.
"""

import os
import re

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
                             QCheckBox, QComboBox, QPushButton, QLineEdit,
                             QScrollArea, QGridLayout, QFormLayout, QFileDialog,
                             QPlainTextEdit, QSpinBox)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QFont

import hostinfo
from uiutil import guard_all

MONO = "Monospace"

# -machine options, with the detection or behaviour consequence spelled out.
# -machine options. Third element None means a free-text value rather than a
# dropdown. Validated against `qemu -machine <type>,help` -- an option QEMU does
# not have is rejected at startup, after the display is already gone.
MACHINE_OPTS = [
    ("usb",             ["on", "off"],  "Built-in USB controller. Off when a qemu-xhci is added explicitly."),
    ("vmport",          ["on", "off", "auto"], "VMware backdoor port 0x5658. ON is a direct virtualisation tell. Keep off."),
    ("smm",             ["on", "off", "auto"], "System Management Mode. Required for Secure Boot with OVMF."),
    ("kernel_irqchip",  ["on", "off", "split"], "In-kernel interrupt controller. 'on' is fastest; 'split' is needed for some passthrough setups."),
    ("i8042",           ["on", "off"],  "Legacy PS/2 keyboard and mouse controller. Off removes an emulated-device tell, but the guest then needs USB input."),
    ("pit",             ["on", "off", "auto"], "i8254 programmable interval timer. Every real PC has one; absence is anomalous."),
    ("pic",             ["on", "off", "auto"], "i8259 legacy interrupt controller. Present on real hardware."),
    ("hpet",            ["on", "off"],  "High Precision Event Timer. Present on real boards."),
    ("acpi",            ["on", "off", "auto"], "ACPI support. Required by modern guest operating systems."),
    ("sata",            ["on", "off"],  "Built-in ICH9 AHCI controller. Off removes every ide-hd disk with it."),
    ("smbus",           ["on", "off"],  "System Management Bus. Real boards have one; it is how DIMM SPD is read."),
    ("fd-bootchk",      ["on", "off"],  "Floppy boot signature check. Legacy, harmless either way."),
    ("graphics",        ["on", "off"],  "Whether the machine claims a graphics adapter."),
    ("mem-merge",       ["on", "off"],  "Kernel samepage merging of guest RAM. Off avoids a timing side channel and is pointless with hugepages."),
    ("dump-guest-core", ["on", "off"],  "Include guest RAM in a QEMU core dump. Off saves disk."),
    ("suppress-vmdesc", ["on", "off"],  "Omit the self-describing migration blob."),
    ("default-bus-bypass-iommu", ["on", "off"], "Let devices bypass the virtual IOMMU by default."),
    ("aux-ram-share",   ["on", "off"],  "Share auxiliary RAM regions."),
    ("x-oem-id",        None,
     "ACPI OEM ID, up to 6 characters, written into every table QEMU generates. "
     "The default is 'BOCHS', which no real board reports. This host's firmware "
     "uses 'ALASKA'."),
    ("x-oem-table-id",  None,
     "ACPI OEM Table ID, up to 8 characters. The default is 'BXPC'. This host's "
     "firmware uses 'A M I'."),
    ("smbios-entry-point-type", ["32", "64"],
     "SMBIOS entry point version. Modern boards use 64."),
    ("max-ram-below-4g", None,
     "Size of the memory window below the 4 GiB boundary. Affects the memory map "
     "the guest sees."),
    ("firmware",        None, "Firmware image, when not supplied via pflash."),
]

# Loose top-level flags, with what each one costs you. Anything in the config
# that is NOT listed here still gets a row: see _build, which walks cfg.simple
# and adds whatever it does not recognise. A flag reaching the command line
# without a control is the failure this avoids.
SIMPLE_OPTS = [
    ("accel",           "Accelerator. 'kvm' is hardware virtualisation; 'tcg' is pure emulation and roughly 50x slower."),
    ("name",            "Process name and thread debug naming. debug-threads=on is what lets the launcher find vCPU threads to pin."),
    ("uuid",            "Domain UUID. Ignored for SMBIOS purposes when -smbios file= is present, because the blob wins."),
    ("smbios",          "QEMU SMBIOS options: file= loads a blob; type= supplies inline fields. OpenCore supplies the Mac identity."),
    ("rtc",             "RTC base and drift correction. Match the guest operating system's clock configuration."),
    ("boot",            "Boot menu and strictness."),
    ("display",         "QEMU's own display. 'none' when the GPU is passed through."),
    ("audiodev",        "Audio backend. driver=none emits no host audio; the guest hears through the passed-through GPU or codec."),
    ("watchdog-action", "What QEMU does when a watchdog fires."),
    ("qmp",             "QMP control socket. The launcher uses this to notice a guest that has stopped but not exited."),
    ("mon",             "Human monitor. Points at a chardev; the launcher rewrites libvirt's inherited fd into a socket path."),
    ("msg",             "QEMU message formatting."),
]

# Flags that are generated from structured data on another tab. They are shown
# here for completeness but not editable: to_argv rebuilds them from that data,
# so anything typed here would be silently thrown away.
OWNED_ELSEWHERE = {
    "machine":    "the machine type and option dropdowns above",
    "cpu":        "the CPU Features tab",
    "smp":        "the CPU Pinning tab (generated from the selected cores)",
    "m":          "the Memory tab",
    "overcommit": "the Memory tab (mem-lock checkbox)",
    "netdev":     "the Networking section above",
    "tpmdev":     "the TPM tab and Paths & Tools",
}

# Flags that take no value at all: present or absent.
BOOL_FLAGS = [
    ("no-user-config", "Ignore the system qemu.conf. Keeps the command line the only source of configuration."),
    ("nodefaults",     "Do not add QEMU's default devices. Without it you get an emulated VGA, serial and floppy the guest can see."),
    ("no-shutdown",    "Park in the 'shutdown' runstate instead of exiting. libvirt needs it; standalone launches strip it, because nothing would ever issue 'quit' and the VM would hang forever holding the GPU."),
    ("no-reboot",      "Exit instead of resetting when the guest reboots."),
    ("S",              "Start paused. libvirt uses this and then issues 'cont'; standalone launches strip it."),
]


class PassthroughTab(QScrollArea):
    """vfio-pci and usb-host devices, added and removed from host enumeration."""

    changed = pyqtSignal()

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.setWidgetResizable(True)
        self.pci_rows, self.usb_rows = [], []
        # (combo, class filter) for every PCI picker, so Rescan host can rebuild
        # each one. Registering them here rather than naming them individually
        # means a new category cannot be added and silently left stale.
        self._pci_pickers = []
        self._rescan()
        self._build()
        self.reload()
        guard_all(self)

    def _rescan(self):
        self.host_pci = hostinfo.pci_devices()
        self.host_gpus = hostinfo.gpus()
        self.host_usb = hostinfo.usb_devices()
        self.pci_label = {}
        for d in self.host_pci:
            self.pci_label[d["slot"]] = (f"{d['slot']}  {d['device']}  [{d['class']}]  "
                                         f"driver={d['driver'] or 'none'}  group={d['iommu_group'] or '?'}")

    # ------------------------------------------------------------- build ---
    def _build(self):
        w = QWidget()
        self.setWidget(w)
        lay = QVBoxLayout(w)

        lay.addWidget(QLabel(
            "Devices handed straight to the guest. A PCI function can only be passed "
            "if its whole IOMMU group goes with it, so the group members are shown "
            "next to each choice."))

        if self.cfg.profile == "macos":
            lay.addWidget(self._mac_usb_controls())

        # ---- adders on the left, what they added on the right ---------------
        # One unfiltered dropdown of every PCI function on the machine is
        # accurate and nearly unusable: 60-odd entries, most of them bridges,
        # and the two or three you ever pass buried among them. These are the
        # same list filtered by what the device IS, which is how you think
        # about it -- "pass the GPU", not "pass 0000:01:00.0". The unfiltered
        # one stays, because anything can be passed and a filter that hides a
        # legitimate choice is worse than a long list.
        #
        # The adders are narrow and the lists wide, because a list row carries
        # six controls and a dropdown carries one. Closed, these combos show a
        # truncated line; open, the popup is sized to its longest entry (see
        # _wide_popup) and overhangs the card, which is the only moment the
        # full string actually has to be readable.
        addcol = QVBoxLayout()
        addcol.setSpacing(6)

        gbox = QGroupBox("Add a GPU   (adds every function at once)")
        gl = QGridLayout(gbox)
        gl.setContentsMargins(8, 4, 8, 6)
        self.gpu_combo = QComboBox()
        for g in self.host_gpus:
            fns = ", ".join(f["slot"].rsplit(":", 1)[-1] for f in g["functions"])
            self.gpu_combo.addItem(f"{g['slot']}  {g['device']}   (functions {fns})", g["slot"])
        self._wide_popup(self.gpu_combo)
        gl.addWidget(QLabel("GPU:"), 0, 0)
        gl.addWidget(self.gpu_combo, 0, 1, 1, 2)

        self.rom = QLineEdit()
        self.rom.setPlaceholderText("optional vBIOS ROM file")
        gl.addWidget(QLabel("ROM:"), 1, 0)
        gl.addWidget(self.rom, 1, 1)
        b = QPushButton("Browse...")
        b.setFixedWidth(80)
        b.clicked.connect(self._browse_rom)
        gl.addWidget(b, 1, 2)

        add = QPushButton("Add this GPU")
        add.clicked.connect(self._add_gpu)
        gl.addWidget(add, 2, 0, 1, 3)
        gl.setColumnStretch(1, 1)
        addcol.addWidget(gbox)

        self.audio_new = self._add_card(
            addcol, "Add a PCI audio device", ("0403", "0401", "0480"),
            "A graphics card's audio function comes with the GPU. This is "
            "normally for the motherboard's own codec.",
            full="On-board and add-in audio. A graphics card's audio function is "
                 "part of its IOMMU group and is added with the GPU, so what you "
                 "usually want here is the motherboard's own controller.")

        self.usbc_new = self._add_card(
            addcol, "Add a PCI USB controller", ("0c03",),
            "The whole controller moves. The host loses every port on it.",
            warn="Not every board resets one cleanly, and an ACS patched kernel "
                 "makes it worse. If it misbehaves, use usb-host below.",
            full="A whole host controller, so every port on it moves to the guest "
                 "at once and the host loses them until it is given back.\n\n"
                 "Not every board does this cleanly, and an ACS patched kernel "
                 "makes it worse: the group splits look viable and the device "
                 "still fails to reset.")

        self.pci_new = self._add_card(
            addcol, "Add any PCI device   (unfiltered)", None,
            "Everything, bridges included. For anything not in a category above.",
            full="Every PCI function on the machine, bridges included. Use this "
                 "when what you want is not in one of the categories above.")

        self.pci_box = QGroupBox("Assigned PCI devices (vfio-pci)")
        self.pci_lay = QVBoxLayout(self.pci_box)

        # ---- USB ------------------------------------------------------------
        ubox = QGroupBox("Add a USB device")
        uv = QVBoxLayout(ubox)
        uv.setContentsMargins(8, 4, 8, 6)
        unote = QLabel("Individual devices. The host keeps the port.")
        ubox.setToolTip("Individual devices rather than a whole controller. The "
                        "host keeps the port; only this device moves.")
        unote.setWordWrap(True)
        unote.setStyleSheet("color: #888;")
        uv.addWidget(unote)

        self.usb_new = QComboBox()
        for u in self.host_usb:
            self.usb_new.addItem(f"bus {u['bus']} dev {u['device']}   {u['label']}", u)
        self._wide_popup(self.usb_new)
        uv.addWidget(self.usb_new)

        self.usb_by = QComboBox()
        self.usb_by.addItem("by vendor:product id (survives replug)", "id")
        self.usb_by.addItem("by host device node (this port only)", "node")
        self._wide_popup(self.usb_by)
        uv.addWidget(self.usb_by)

        b = QPushButton("Add selected")
        b.clicked.connect(self._add_usb)
        uv.addWidget(b)
        uv.addStretch()

        addcol.addWidget(ubox)

        b = QPushButton("Rescan host")
        b.clicked.connect(self._do_rescan)
        addcol.addWidget(b)
        addcol.addStretch()

        self.usb_box = QGroupBox("Assigned USB devices (usb-host)")
        self.usb_lay = QVBoxLayout(self.usb_box)

        self.warn = QPlainTextEdit()
        self.warn.setReadOnly(True)
        self.warn.setFont(QFont(MONO, 10))
        self.warn.setMinimumHeight(90)

        # Two columns, each packed from the top. The lists were centred against
        # the adders while the adder column overflowed and scrolled; now that it
        # fits, centring only opened gaps between the three panels on the right,
        # which read as missing content rather than as breathing room.
        rightcol = QVBoxLayout()
        rightcol.setSpacing(6)
        rightcol.addWidget(self.pci_box)
        rightcol.addWidget(self.usb_box)
        rightcol.addWidget(self.warn, 1)

        cols = QHBoxLayout()
        cols.setSpacing(10)
        lw = QWidget()
        addcol.setContentsMargins(0, 0, 0, 0)
        lw.setLayout(addcol)
        cols.addWidget(lw, 34)
        cols.addLayout(rightcol, 66)
        lay.addLayout(cols, 1)


        lay.addStretch()

    def _browse_rom(self):
        p, _ = QFileDialog.getOpenFileName(self, "Select ROM file", os.path.expanduser("~"),
                                           "ROM (*.rom *.bin);;All files (*)")
        if p:
            self.rom.setText(p)

    def _do_rescan(self):
        self._rescan()

        for combo, classes in self._pci_pickers:
            keep = combo.currentData()
            combo.clear()
            for slot, label in self.pci_label.items():
                if classes is not None and not self._pci_class_matches(slot, classes):
                    continue
                combo.addItem(label, slot)
            if not combo.count():
                combo.addItem("none of these on this machine", None)
                combo.setEnabled(False)
            else:
                combo.setEnabled(True)
                # Hold the previous choice if it is still present, so a rescan
                # run to pick up one new device does not reset the selection.
                i = combo.findData(keep)
                if i >= 0:
                    combo.setCurrentIndex(i)
            self._wide_popup(combo)

        keep = self.gpu_combo.currentData()
        self.gpu_combo.clear()
        for g in self.host_gpus:
            fns = ", ".join(f["slot"].rsplit(":", 1)[-1] for f in g["functions"])
            self.gpu_combo.addItem(f"{g['slot']}  {g['device']}   (functions {fns})", g["slot"])
        i = self.gpu_combo.findData(keep)
        if i >= 0:
            self.gpu_combo.setCurrentIndex(i)
        self._wide_popup(self.gpu_combo)

        self.usb_new.clear()
        for u in self.host_usb:
            self.usb_new.addItem(f"bus {u['bus']} dev {u['device']}   {u['label']}", u)
        self._wide_popup(self.usb_new)
        self.reload()

    # ------------------------------------------------------------ reload ---
    def reload(self):
        for r in self.pci_rows + self.usb_rows:
            r.setParent(None)
        self.pci_rows, self.usb_rows = [], []

        for dev in self.cfg.devices:
            if dev.get("_disabled"):
                continue
            if dev.get("driver") == "vfio-pci":
                w = self._pci_row(dev)
                self.pci_rows.append(w)
                self.pci_lay.addWidget(w)
            elif dev.get("driver") == "usb-host":
                w = self._usb_row(dev)
                self.usb_rows.append(w)
                self.usb_lay.addWidget(w)
        self._check()

    def _pci_row(self, dev):
        w = QWidget()
        g = QGridLayout(w)
        g.setContentsMargins(0, 0, 0, 0)

        # Two rows per device, not three. The identity line carries everything
        # you only read, the edit line everything you can change.
        host = dev.get("host", "")
        text = self.pci_label.get(host, f"{host}  (not present on this host)")

        # The IOMMU group members used to own a third row. They belong with
        # "group=NN" on the description anyway -- it is the same fact, and
        # reading it needs no control next to it.
        grp = [d for d in self.host_pci
               if d["iommu_group"] and d["slot"] != host
               and d["iommu_group"] == next((x["iommu_group"] for x in self.host_pci
                                             if x["slot"] == host), None)]
        if grp:
            text += "   shares group with: " + ", ".join(d["slot"] for d in grp)
        lbl = QLabel(text)
        lbl.setWordWrap(True)

        g.addWidget(QLabel(dev.get("id", "?")), 0, 0)
        g.addWidget(lbl, 0, 1, 1, 5)

        rm = QPushButton("Remove")
        rm.clicked.connect(lambda: self._remove(dev))
        g.addWidget(rm, 0, 6)

        bus = QLineEdit(str(dev.get("bus", "")))
        bus.setPlaceholderText("automatic")
        bus.textChanged.connect(lambda t, d=dev: self._set(d, "bus", t))
        addr = QLineEdit(str(dev.get("addr", "")))
        addr.setPlaceholderText("auto")
        addr.textChanged.connect(lambda t, d=dev: self._set(d, "addr", t))
        # These hold "pci.5" and "0x0". Sized to their contents rather than to
        # whatever is left over, which is what freed the width for the romfile.
        bus.setMaximumWidth(110)
        addr.setMaximumWidth(80)

        rom = QLineEdit(str(dev.get("romfile", "")))
        rom.setPlaceholderText("romfile (optional)")
        rom.textChanged.connect(lambda t, d=dev: self._set(d, "romfile", t))
        br = QPushButton("...")
        br.setMaximumWidth(32)
        br.clicked.connect(lambda _, e=rom: self._pick_rom(e))

        mf = QCheckBox("multifunction")
        mf.setChecked(bool(dev.get("multifunction")))
        mf.stateChanged.connect(lambda s, d=dev: self._set(d, "multifunction", bool(s)))

        g.addWidget(QLabel("guest bus:"), 1, 0)
        g.addWidget(bus, 1, 1)
        g.addWidget(QLabel("addr:"), 1, 2)
        g.addWidget(addr, 1, 3)
        g.addWidget(mf, 1, 4)
        g.addWidget(rom, 1, 5)
        g.addWidget(br, 1, 6)

        # Only the romfile grows; everything else keeps the width it needs.
        g.setColumnStretch(5, 1)
        return w

    def _usb_row(self, dev):
        w = QWidget()
        g = QGridLayout(w)
        g.setContentsMargins(0, 0, 0, 0)

        if "hostdevice" in dev:
            what = dev["hostdevice"]
            live = os.path.exists(what)
            note = "  (bus path: moves when anything is replugged)"
        else:
            # The values are stored as the uint32 QEMU wants, so compare
            # numerically and render as hex. Comparing the stored int against
            # a "0x03f0" string always failed, which is why a device sitting
            # in front of you reported NOT PRESENT.
            vid, pid = dev.get("vendorid"), dev.get("productid")
            try:
                vid_i = int(str(vid), 0)
                pid_i = int(str(pid), 0)
            except (TypeError, ValueError):
                vid_i = pid_i = None
            what = (f"{vid_i:04x}:{pid_i:04x}" if vid_i is not None
                    else f"{vid}:{pid}")
            match = next((u for u in self.host_usb
                          if vid_i is not None
                          and int(u["vendor_id"], 16) == vid_i
                          and int(u["product_id"], 16) == pid_i), None)
            live = match is not None
            note = f"  {match['name']}" if match else ""
        g.addWidget(QLabel(dev.get("id", "?")), 0, 0)
        lbl = QLabel(f"{what}   {'present' if live else 'NOT PRESENT'}{note}")
        lbl.setWordWrap(True)
        lbl.setStyleSheet("" if live else "color: #e5c07b;")
        g.addWidget(lbl, 0, 1, 1, 3)

        port = QLineEdit(str(dev.get("port", "")))
        port.setPlaceholderText("auto")
        port.setMaximumWidth(60)
        port.textChanged.connect(lambda t, d=dev: self._set(d, "port", t))
        g.addWidget(QLabel("guest port:"), 0, 4)
        g.addWidget(port, 0, 5)

        rm = QPushButton("Remove")
        rm.clicked.connect(lambda: self._remove(dev))
        g.addWidget(rm, 0, 6)
        return w

    def _pick_rom(self, edit):
        p, _ = QFileDialog.getOpenFileName(self, "Select ROM file", os.path.expanduser("~"),
                                           "ROM (*.rom *.bin);;All files (*)")
        if p:
            edit.setText(p)

    # ---------------------------------------------------------- mutation ---
    def _set(self, dev, key, val):
        if val in ("", None, False):
            dev.pop(key, None)
        else:
            dev[key] = val
        self._check()
        self.changed.emit()

    def _remove(self, dev):
        dev["_disabled"] = True
        self.reload()
        self.changed.emit()

    def _next_id(self, prefix):
        # Removed devices are marked, not deleted, and a tombstone must not keep
        # its name reserved or the counter climbs past every device ever added.
        used = {d.get("id") for d in self.cfg.devices if not d.get("_disabled")}
        n = 0
        while f"{prefix}{n}" in used:
            n += 1
        return f"{prefix}{n}"

    def _mac_usb_controls(self):
        group = QGroupBox("Mac input compatibility")
        form = QFormLayout(group)
        controllers = [d for d in self.cfg.devices if not d.get("_disabled") and
                       d.get("driver") in ("nec-usb-xhci", "qemu-xhci", "usb-ehci", "ich9-usb-ehci1")]
        self.mac_usb_ports = {}
        self.mac_input_buses = {}
        for dev in controllers:
            ident = dev.get("id", "")
            form.addRow("USB controller", QLabel(f"{ident} · {dev['driver']}"))
            if dev["driver"] in ("nec-usb-xhci", "qemu-xhci"):
                for key, label in (("p2", "USB 2 ports"), ("p3", "USB 3 ports")):
                    spin = QSpinBox()
                    spin.setRange(0, max(15, int(dev.get(key, 4))))
                    spin.setValue(int(dev.get(key, 4)))
                    spin.setToolTip("Keep enough ports for the keyboard, tablet and passed USB devices. "
                                    "macOS normally supports up to 15 ports per controller; retain your working allocation.")
                    spin.valueChanged.connect(lambda value, d=dev, k=key: (d.__setitem__(k, value), self.changed.emit()))
                    self.mac_usb_ports[(ident, key)] = spin
                    form.addRow(f"{ident} {label}", spin)
        for dev in self.cfg.devices:
            if dev.get("_disabled") or dev.get("driver") not in ("usb-kbd", "usb-tablet"):
                continue
            combo = QComboBox()
            combo.addItem("Automatic", "")
            for controller in controllers:
                bus = controller.get("id", "") + ".0"
                combo.addItem(bus, bus)
            current = dev.get("bus", "")
            if combo.findData(current) < 0:
                combo.addItem(current, current)
            combo.setCurrentIndex(combo.findData(current))
            def select(_index, d=dev, widget=combo):
                if widget.currentData():
                    d["bus"] = widget.currentData()
                else:
                    d.pop("bus", None)
                self.changed.emit()
            combo.currentIndexChanged.connect(select)
            self.mac_input_buses[dev.get("id", dev["driver"])] = combo
            form.addRow("Virtual keyboard bus" if dev["driver"] == "usb-kbd" else "Virtual tablet bus", combo)
        smc = any(d.get("driver") == "isa-applesmc" and not d.get("_disabled") for d in self.cfg.devices)
        form.addRow("Apple SMC", QLabel("Configured" if smc else "Missing — load a prepared Mac preset"))
        note = QLabel("These are the preset's guest USB ports and input devices. Virtual GPU has its own "
                      "viewer input controller. Keep the working controller and routing when using physical input.")
        note.setWordWrap(True)
        form.addRow(note)
        return group

    def _free_root_port(self):
        """Find a pcie-root-port with nothing attached to it."""
        ports = [d["id"] for d in self.cfg.devices
                 if d.get("driver") == "pcie-root-port" and not d.get("_disabled")]
        taken = {d.get("bus") for d in self.cfg.devices if not d.get("_disabled")}
        for p in ports:
            if p not in taken:
                return p
        return ""

    def _new_pci_device(self, slot):
        # QEMU accepts both 01:00.0 and 0000:01:00.0 for the same function.
        normalized = slot.lower().removeprefix("0000:")
        if any(d.get("driver") == "vfio-pci" and not d.get("_disabled")
               and str(d.get("host", "")).lower().removeprefix("0000:") == normalized
               for d in self.cfg.devices):
            return None
        dev = {"driver": "vfio-pci", "host": slot, "id": self._next_id("hostdev")}
        bus = self._free_root_port()
        if bus:
            dev.update(bus=bus, addr="0x0")
        # Presets without spare root ports use QEMU's automatic placement.
        # An empty bus string is a literal invalid bus, not the default bus.
        return dev

    def _wide_popup(self, combo):
        """Let the open popup overhang the combo, sized to its longest entry.

        The adders are deliberately narrow, which truncates these strings when
        closed -- and closed they only need to identify the current choice. The
        popup is the moment the whole line matters, so it is measured against
        the real text rather than inheriting the combo's width.
        """
        combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(12)
        fm = combo.fontMetrics()
        widest = max((fm.horizontalAdvance(combo.itemText(i))
                      for i in range(combo.count())), default=0)
        if widest:
            # Scrollbar and frame, or the last character sits under the bar.
            combo.view().setMinimumWidth(widest + 40)

    def _add_card(self, column, title, classes, tip, warn=None, full=None):
        """One filtered "add a PCI device" card.

        classes is a tuple of PCI class codes as they appear in lspci's
        bracketed suffix, or None for no filter at all.
        """
        box = QGroupBox(title)
        box.setToolTip(full or tip)
        v = QVBoxLayout(box)
        v.setContentsMargins(8, 2, 8, 4)
        v.setSpacing(4)

        note = QLabel(tip)
        note.setWordWrap(True)
        note.setStyleSheet("color: #888;")
        v.addWidget(note)

        # A caveat that can cost a failed launch belongs on the card, not in a
        # tooltip nobody hovers before clicking Add.
        if warn:
            wl = QLabel(warn)
            wl.setWordWrap(True)
            wl.setStyleSheet("color: #e5c07b;")
            v.addWidget(wl)

        combo = QComboBox()
        combo.setToolTip(full or tip)
        for slot, label in self.pci_label.items():
            if classes is not None and not self._pci_class_matches(slot, classes):
                continue
            combo.addItem(label, slot)
        self._wide_popup(combo)
        self._pci_pickers.append((combo, classes))
        v.addWidget(combo)

        # The card title already says what this adds.
        b = QPushButton("Add selected")
        if not combo.count():
            # An empty category is said out loud rather than shown as a live
            # control that silently does nothing when clicked.
            combo.addItem("none of these on this machine", None)
            combo.setEnabled(False)
            b.setEnabled(False)
        b.clicked.connect(lambda _, c=combo: self._add_pci(c))
        v.addWidget(b)
        column.addWidget(box)
        return combo

    def _pci_class_matches(self, slot, classes):
        cls = next((d["class"] for d in self.host_pci if d["slot"] == slot), "")
        # lspci -nnmm renders the class as "Audio device [0403]".
        code = cls.rsplit("[", 1)[-1].rstrip("]").lower() if "[" in cls else ""
        return code in classes

    def _add_pci(self, combo=None):
        combo = combo if combo is not None else self.pci_new
        slot = combo.currentData()
        if not slot:
            return
        dev = self._new_pci_device(slot)
        if dev is None:
            return
        self.cfg.devices.append(dev)
        self.reload()
        self.changed.emit()

    def _add_gpu(self):
        slot = self.gpu_combo.currentData()
        gpu = next((g for g in self.host_gpus if g["slot"] == slot), None)
        if not gpu:
            return
        rom = self.rom.text().strip()
        for f in sorted(gpu["functions"], key=lambda x: x["slot"], reverse=True):
            dev = self._new_pci_device(f["slot"])
            if dev is None:
                continue
            if rom and f["slot"] == gpu["slot"]:
                dev["romfile"] = rom
            self.cfg.devices.append(dev)
        self.reload()
        self.changed.emit()

    def _add_usb(self):
        u = self.usb_new.currentData()
        if not u:
            return
        dev = {"driver": "usb-host", "id": self._next_id("hostdev")}
        controller = next((d for d in self.cfg.devices if not d.get("_disabled")
                           and d.get("id") and d.get("driver") in (
                               "qemu-xhci", "nec-usb-xhci", "usb-ehci", "ich9-usb-ehci1")), None)
        if controller:
            dev["bus"] = controller["id"] + ".0"
        if self.usb_by.currentData() == "id":
            # Integers, not "0x03f0" strings. QEMU declares these as uint32,
            # and the JSON -device form is strictly typed: a string there is
            # rejected with "Parameter 'productid' expects uint64" and the VM
            # never starts. The old key=value syntax accepted the hex string,
            # which is why this looks like it should work.
            dev["vendorid"] = int(u["vendor_id"], 16)
            dev["productid"] = int(u["product_id"], 16)
        else:
            dev["hostdevice"] = f"/dev/bus/usb/{int(u['bus']):03d}/{int(u['device']):03d}"
        # Let QEMU select a free port, including ports occupied implicitly by
        # the preset's virtual keyboard/tablet. usb.0 may not exist at all.
        self.cfg.devices.append(dev)
        self.reload()
        self.changed.emit()

    # ------------------------------------------------------------- check ---
    def _check(self):
        msgs = []
        groups, buses, ports = {}, {}, {}
        host_by_slot = {d["slot"]: d for d in self.host_pci}

        passed = [d for d in self.cfg.devices
                  if d.get("driver") == "vfio-pci" and not d.get("_disabled")]
        passed_slots = {d.get("host") for d in passed}

        for d in passed:
            slot = d.get("host", "")
            hd = host_by_slot.get(slot)
            if not hd:
                msgs.append(f"{d.get('id')}: {slot} is not present on this host")
                continue
            if hd["driver"] not in ("vfio-pci", ""):
                msgs.append(f"{d.get('id')}: {slot} is still bound to '{hd['driver']}'; "
                            f"it must be detached to vfio-pci before launch")
            g = hd["iommu_group"]
            if g:
                members = {x["slot"] for x in self.host_pci if x["iommu_group"] == g}
                # A PCI bridge / root port may stay in the group bound to its own
                # driver (vfio allows it), so it is not counted as missing.
                missing = {m for m in (members - passed_slots)
                           if not hostinfo.pci_is_bridge(m)}
                if missing:
                    msgs.append(f"{d.get('id')}: IOMMU group {g} also contains "
                                f"{', '.join(sorted(missing))} - the group must be passed whole")
                groups.setdefault(g, []).append(slot)
            key = (d.get("bus"), d.get("addr"))
            if d.get("bus") and key in buses:
                msgs.append(f"{d.get('id')} and {buses[key]} share guest address "
                            f"{key[0]}:{key[1]}")
            buses[key] = d.get("id")
            rf = d.get("romfile")
            if rf and not os.path.isfile(rf):
                msgs.append(f"{d.get('id')}: romfile {rf} does not exist")

        for d in self.cfg.devices:
            if d.get("driver") != "usb-host" or d.get("_disabled"):
                continue
            p = str(d.get("port", ""))
            if p and p in ports:
                msgs.append(f"{d.get('id')} and {ports[p]} share guest USB port {p}")
            ports[p] = d.get("id")
            hd = d.get("hostdevice")
            if hd and not os.path.exists(hd):
                msgs.append(f"{d.get('id')}: {hd} is gone; the device moved or was "
                            f"unplugged. Pass it by vendor:product id instead.")

        self.warn.setPlainText("\n".join(msgs) if msgs else "No passthrough problems found.")


class MachineTab(QScrollArea):
    """-machine options, -global overrides and the loose top-level flags."""

    changed = pyqtSignal()

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.readonly_rows = []
        self.setWidgetResizable(True)
        self._loading = True
        self._build()
        self._load_net()
        self._loading = False
        self._push_machine()      # surface the warnings on load, not only on edit
        self.check_coverage()
        guard_all(self)

    def _build(self):
        w = QWidget()
        self.setWidget(w)
        lay = QVBoxLayout(w)

        mbox = QGroupBox("Machine")
        mv = QVBoxLayout(mbox)

        # Machine type and Extra stay full width; the flag list in between is the
        # long part, so it goes two per row to halve the scrolling.
        topf = QFormLayout()
        self.mtype = QLineEdit(self.cfg.data["machine"]["type"])
        self.mtype.textChanged.connect(self._push_machine)
        topf.addRow("Machine type:", self.mtype)
        mv.addLayout(topf)

        og = QGridLayout()
        og.setColumnStretch(0, 1)
        og.setColumnStretch(1, 1)
        self.mwidgets = {}
        opts = self.cfg.data["machine"]["opts"]
        for i, (name, choices, desc) in enumerate(MACHINE_OPTS):
            row = QHBoxLayout()
            lbl = QLabel(name + ":")
            lbl.setMinimumWidth(150)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            lbl.setToolTip(desc)
            if choices is None:
                w2 = QLineEdit(str(opts.get(name, "")))
                w2.setFixedWidth(150)
                w2.textEdited.connect(self._push_machine)
            else:
                w2 = QComboBox()
                w2.addItem("(not set)", None)
                for v in choices:
                    w2.addItem(v, v)
                cur = opts.get(name)
                w2.setCurrentText(cur if cur in choices else "(not set)")
                w2.currentIndexChanged.connect(self._push_machine)
            w2.setToolTip(desc)
            # No visible copy of desc. It is already the tooltip on both the
            # label and the control, and at half width it wrapped to three or
            # four lines -- twenty-three times, which was most of this tab.
            row.addWidget(lbl)
            row.addWidget(w2, 1)
            holder = QWidget()
            holder.setLayout(row)
            og.addWidget(holder, i // 2, i % 2)
            self.mwidgets[name] = w2
        options_box = QGroupBox("Machine options")
        options_layout = QVBoxLayout(options_box)
        options_layout.addLayout(og)

        botf = QFormLayout()
        self.mpass = QLineEdit()
        self.mpass.setPlaceholderText("extra machine options, key=value,key=value")
        self.mpass.textChanged.connect(self._push_machine)
        botf.addRow("Extra:", self.mpass)
        options_layout.addLayout(botf)
        lay.addWidget(mbox)

        # ---- globals ---------------------------------------------------------
        gbox = QGroupBox("-global overrides")
        gl = QVBoxLayout(gbox)
        gl.addWidget(QLabel(
            "Raw QOM property overrides, one per line. host-x86_64-cpu.model-id "
            "rewrites the CPU brand string the guest reads from CPUID 8000_0002-4."))
        self.globals_edit = QPlainTextEdit()
        self.globals_edit.setFont(QFont(MONO, 10))
        self.globals_edit.setPlainText("\n".join(self.cfg.globals))
        self.globals_edit.setMaximumHeight(140)
        self.globals_edit.textChanged.connect(self._push_globals)
        gl.addWidget(self.globals_edit)

        # ---- networking -------------------------------------------------------
        nbox = QGroupBox("Networking")
        nf = QFormLayout(nbox)
        nf.addRow(QLabel(
            "libvirt created the tap device and passed QEMU an inherited file "
            "descriptor. This launcher creates it by name instead, so the tap "
            "and the bridge are set here."))
        net = self.cfg.network
        self.net_if = QLineEdit(net.get("ifname", ""))
        self.net_if.setToolTip("Tap device created by the start hook and removed "
                               "by revert.")
        self.net_if.textEdited.connect(self._push_net)
        nf.addRow("Tap interface:", self.net_if)

        self.net_br = QComboBox()
        self.net_br.setEditable(True)
        for b in hostinfo.net_bridges():
            self.net_br.addItem(b, b)
        self.net_br.setEditText(net.get("bridge", ""))
        self.net_br.setToolTip("Host bridge the tap is enslaved to. Blank leaves "
                               "the tap unbridged and the guest with no network.")
        self.net_br.currentTextChanged.connect(self._push_net)
        nf.addRow("Host bridge:", self.net_br)

        self.net_mac = QLineEdit()
        self.net_mac.setToolTip("Guest NIC MAC. The first three bytes are the "
                                "vendor OUI; a random one that is not a real OUI "
                                "is itself a signal.")
        self.net_mac.textEdited.connect(self._push_mac)
        macrow = QHBoxLayout()
        macrow.setContentsMargins(0, 0, 0, 0)
        macrow.addWidget(self.net_mac, 1)
        mb = QPushButton("Regen")
        mb.setFixedWidth(70)
        mb.setToolTip("New MAC keeping the existing vendor OUI")
        mb.clicked.connect(self._regen_mac)
        macrow.addWidget(mb)
        mh = QWidget(); mh.setLayout(macrow)
        nf.addRow("NIC MAC:", mh)

        self.net_model = QLineEdit()
        self.net_model.setToolTip("QEMU NIC device model, e.g. e1000e. virtio-net "
                                  "is faster but paravirtual and visible as such.")
        self.net_model.textEdited.connect(self._push_mac)
        nf.addRow("NIC model:", self.net_model)

        self.net_raw = QLineEdit()
        self.net_raw.setToolTip("The -netdev argument as it will be emitted.")
        self.net_raw.setReadOnly(True)
        nf.addRow("-netdev:", self.net_raw)
        lay.addWidget(nbox)
        lay.addWidget(options_box)
        lay.addWidget(gbox)

        # ---- simple flags -----------------------------------------------------
        sbox = QGroupBox("Top-level flags")
        sf = QGridLayout(sbox)
        for c, st in ((1, 1), (4, 1)):
            sf.setColumnStretch(c, st)
        self.swidgets = {}
        known = {n for n, _ in SIMPLE_OPTS} | {n for n, _ in BOOL_FLAGS}
        # Anything in the config this file does not know about still gets a row,
        # so a flag can never reach the command line without a control.
        extra = [(k, "Not in the built-in catalogue. Edited as raw text.")
                 for k in self.cfg.simple
                 if k not in known and k not in OWNED_ELSEWHERE
                 and self.cfg.simple.get(k) is not None]
        owned = [(k, "") for k in self.cfg.simple if k in OWNED_ELSEWHERE]
        catalogue = [(n, d) for n, d in SIMPLE_OPTS if n not in OWNED_ELSEWHERE]
        for i, (name, desc) in enumerate(catalogue + extra + owned):
            e = QLineEdit(str(self.cfg.simple.get(name, "") or ""))
            marker = ""
            if name in OWNED_ELSEWHERE:
                desc = "Built from " + OWNED_ELSEWHERE[name] + "."
                # Kept visible for these: that the field is read-only is state,
                # not help, and a greyed box with no reason given reads as broken.
                marker = "from " + OWNED_ELSEWHERE[name].split("(")[0].strip()
                e.setReadOnly(True)
                e.setStyleSheet("color: #888;")
                self.readonly_rows.append(name)
            e.setToolTip(desc)
            e.textEdited.connect(self._push_simple)

            lbl = QLabel("-" + name + ":")
            lbl.setToolTip(desc)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            ml = QLabel(marker)
            ml.setWordWrap(True)
            ml.setStyleSheet("color: #888;")
            ml.setToolTip(desc)

            col, r = (i % 2) * 3, i // 2
            sf.addWidget(lbl, r, col)
            sf.addWidget(e, r, col + 1)
            sf.addWidget(ml, r, col + 2)
            self.swidgets[name] = e
        lay.addWidget(sbox)

        # ---- boolean flags ------------------------------------------------------
        bbox = QGroupBox("Switches (no value)")
        bf = QHBoxLayout(bbox)
        self.bwidgets = {}
        for name, desc in BOOL_FLAGS:
            c = QCheckBox(f"-{name}")
            c.setToolTip(desc)
            c.setChecked(name in self.cfg.simple)
            c.stateChanged.connect(self._push_bools)
            bf.addWidget(c)
            self.bwidgets[name] = c
        bf.addStretch()
        lay.addWidget(bbox)

        # ---- completeness --------------------------------------------------------
        cbox = QGroupBox("Coverage")
        cl = QVBoxLayout(cbox)
        cl.addWidget(QLabel(
            "Every argument the launcher will emit, and where it is edited. "
            "Anything listed as unreachable is a gap in this app, not in QEMU."))
        self.coverage = QPlainTextEdit()
        self.coverage.setReadOnly(True)
        self.coverage.setFont(QFont(MONO, 9))
        self.coverage.setMinimumHeight(180)
        cl.addWidget(self.coverage)
        b = QPushButton("Re-check coverage")
        b.clicked.connect(self.check_coverage)
        cl.addWidget(b)
        lay.addWidget(cbox)

        self.note = QLabel("")
        self.note.setWordWrap(True)
        lay.addWidget(self.note)
        lay.addStretch()

    def _push_machine(self):
        if self._loading:
            return
        self.cfg.data["machine"]["type"] = self.mtype.text().strip()
        opts = self.cfg.data["machine"]["opts"]
        for name, c in self.mwidgets.items():
            v = c.text().strip() if isinstance(c, QLineEdit) else c.currentData()
            if not v:
                opts.pop(name, None)
            else:
                opts[name] = v
        for pair in self.mpass.text().split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                opts[k.strip()] = v.strip()

        warn = []
        if self.cfg.profile != "macos" and opts.get("x-oem-id", "") in ("", "BOCHS"):
            warn.append("ACPI OEM ID is QEMU's default 'BOCHS'; no real board "
                        "reports that. This host's firmware uses 'ALASKA'.")
        if self.cfg.profile != "macos" and (opts.get("pit") == "off" or opts.get("pic") == "off"):
            warn.append("A PC without an i8254 PIT or i8259 PIC does not exist.")
        if self.cfg.profile != "macos" and opts.get("smm") == "off":
            warn.append("smm=off breaks Secure Boot under OVMF.")
        if opts.get("vmport") == "on":
            warn.append("vmport=on exposes the VMware backdoor port and is detectable.")
        if opts.get("i8042") == "off":
            warn.append("i8042=off means no PS/2 input; the guest needs a USB keyboard.")
        self.note.setText("  ".join(warn))
        self.changed.emit()

    def _push_globals(self):
        if self._loading:
            return
        self.cfg.data["globals"] = [l.strip() for l in
                                    self.globals_edit.toPlainText().splitlines() if l.strip()]
        self.changed.emit()

    def _push_simple(self):
        if self._loading:
            return
        for name, e in self.swidgets.items():
            if name in self.readonly_rows:
                continue                 # owned by another tab; see OWNED_ELSEWHERE
            t = e.text().strip()
            if t:
                self.cfg.simple[name] = t
            elif name in self.cfg.simple and self.cfg.simple[name] is not None:
                self.cfg.simple[name] = ""
        self.changed.emit()
        self.check_coverage()

    def _push_bools(self):
        """Valueless switches are stored as a key with a None value."""
        if self._loading:
            return
        for name, c in self.bwidgets.items():
            if c.isChecked():
                self.cfg.simple[name] = None
            else:
                self.cfg.simple.pop(name, None)
        self.changed.emit()
        self.check_coverage()

    # ------------------------------------------------------------- network ---
    def _nic(self):
        for d in self.cfg.devices:
            if d.get("netdev") and not d.get("_disabled"):
                return d
        return None

    def _load_net(self):
        nic = self._nic() or {}
        self.net_mac.setText(str(nic.get("mac", "")))
        self.net_model.setText(str(nic.get("driver", "")))
        self._refresh_netdev()

    def _push_net(self, *_):
        if self._loading:
            return
        net = self.cfg.network
        net["ifname"] = self.net_if.text().strip()
        net["bridge"] = self.net_br.currentText().strip()
        self._refresh_netdev()
        self.changed.emit()

    def _refresh_netdev(self):
        """Show the argument as it will actually be emitted.

        The stored value still carries libvirt's fd=33; the standalone rewrite
        happens at emit time, so showing the stored form here would be a lie.
        """
        argv = self.cfg.to_argv(True)
        try:
            self.net_raw.setText(argv[argv.index("-netdev") + 1])
        except ValueError:
            self.net_raw.setText("(no netdev)")
        for name in self.readonly_rows:
            if name in self.swidgets:
                self.swidgets[name].setText(str(self.cfg.simple.get(name, "") or ""))

    def _push_mac(self, *_):
        if self._loading:
            return
        nic = self._nic()
        if not nic:
            return
        mac = self.net_mac.text().strip()
        if mac:
            nic["mac"] = mac
        model = self.net_model.text().strip()
        if model:
            nic["driver"] = model
        self.changed.emit()

    def _regen_mac(self):
        """New MAC, same vendor OUI.

        The first three bytes identify the card's maker. Randomising them gives
        an OUI that belongs to nobody, which is a stronger signal than the
        address it replaced.
        """
        import random
        cur = self.net_mac.text().strip()
        parts = cur.split(":")
        if len(parts) == 6:
            oui = parts[:3]
        else:
            oui = ["52", "54", "00"]        # QEMU's own range, as a fallback
        new = ":".join(oui + ["%02x" % random.randint(0, 255) for _ in range(3)])
        self.net_mac.setText(new)
        self._push_mac()

    # ------------------------------------------------------------ coverage ---
    def check_coverage(self):
        """Map every emitted argument to the control that edits it."""
        reach = {
            "machine": "Machine tab, type and option dropdowns",
            "global": "Machine tab, -global editor",
            "cpu": "CPU Features tab",
            "smp": "CPU Pinning tab, generated from the core selection",
            "m": "Memory tab", "overcommit": "Memory tab",
            "object": "Memory tab (pc.ram); iothreads from CPU Pinning",
            "blockdev": "Disks tab", "device": "Disks and PCI / USB tabs",
            "acpitable": "Paths & Tools tab",
            "smbios": "SMBIOS tab and Paths & Tools",
            "tpmdev": "TPM tab (identity), Paths & Tools (socket)",
            "chardev": "Paths & Tools (TPM socket), Machine tab (-mon)",
            "netdev": "Machine tab, Networking",
        }
        if self.cfg.profile == "macos":
            reach.update(smbios="OpenCore identity (QEMU compatibility flags remain in this preset)",
                         chardev="Machine tab (-mon), serial/console devices")
        argv = self.cfg.to_argv(True)
        seen, i = [], 1
        while i < len(argv):
            a = argv[i]
            if not a.startswith("-"):
                i += 1
                continue
            val = argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith("-") else None
            seen.append(a[1:])
            i += 2 if val is not None else 1

        known = {n for n, _ in SIMPLE_OPTS} | {n for n, _ in BOOL_FLAGS}
        order, lines, gaps = [], [], []
        for f in seen:
            if f not in order:
                order.append(f)
        for f in order:
            n = seen.count(f)
            if f in reach:
                where = reach[f]
            elif f in known or f in self.swidgets:
                where = "Machine tab, top-level flags"
            else:
                where = "NOT REACHABLE"
                gaps.append(f)
            lines.append(f"  -{f:<16} x{n:<3} {where}")
        head = (f"{len(order)} distinct arguments, all reachable."
                if not gaps else
                f"{len(gaps)} argument(s) have no control: {', '.join(gaps)}")
        self.coverage.setPlainText(head + "\n\n" + "\n".join(lines))
        return gaps
