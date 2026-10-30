#!/usr/bin/env python3
"""Rich editor tabs for vmstart_2.

Kept out of vmstart2.py so each tab can grow without that file becoming
unreadable.
"""

import os

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
                             QCheckBox, QComboBox, QSpinBox, QPushButton, QFormLayout,
                             QPlainTextEdit, QScrollArea, QGridLayout, QLineEdit,
                             QRadioButton, QButtonGroup)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

import hostinfo
import launcher
from uiutil import guard_all, sudo_command

MONO = "Monospace"

# libvirt's <vcpusched>/<emulatorsched> scheduler values, with the trade-off
# spelled out: fifo/rr are real-time and need sched_rt_runtime_us=-1 or the
# kernel throttles them to 95% of each period and the guest stutters.
SCHEDULERS = [
    ("fifo",  "Real time, runs until it yields. Needs RT throttling disabled."),
    ("rr",    "Real time, round robin between equal priorities. Usual choice for vCPUs."),
    ("batch", "Non real time, throughput biased, coarser preemption."),
    ("idle",  "Only runs when nothing else wants the CPU."),
    ("other", "Normal CFS scheduling. No priority applied."),
]


class PinningTab(QScrollArea):
    """Per-CCD core selection with everything the pinning actually needs."""

    changed = pyqtSignal()

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.core_boxes = {}          # physical core id -> QCheckBox
        self.topo = hostinfo.cpu_topology()
        self.setWidgetResizable(True)
        self._build()
        self.recalc()
        guard_all(self)

    # ------------------------------------------------------------- build ---
    def _build(self):
        w = QWidget()
        self.setWidget(w)
        lay = QVBoxLayout(w)

        lay.addWidget(QLabel(
            "Tick the physical cores to hand to the guest. Cores are grouped by L3 "
            "domain, which is the CCD boundary on Ryzen: keeping a guest inside one "
            "group avoids cross CCD latency, and on an X3D part only one group has "
            "the stacked cache."))

        # --- SMT ---------------------------------------------------------
        smt_box = QGroupBox("Threads")
        sl = QHBoxLayout(smt_box)
        self.smt_mode = QComboBox()
        self.smt_mode.addItem("Both threads of each core (SMT on)", "both")
        self.smt_mode.addItem("First thread only (guest sees no SMT)", "single")
        self.smt_mode.currentIndexChanged.connect(self.recalc)
        sl.addWidget(QLabel("Per selected core:"))
        sl.addWidget(self.smt_mode, 1)
        lay.addWidget(smt_box)

        # --- one column per L3 group ------------------------------------
        groups_row = QHBoxLayout()
        l3 = self.topo["l3_to_cores"]
        if not l3:
            l3 = {"all": sorted(self.topo["core_to_cpus"].keys())}
        for gi, (key, cores) in enumerate(l3.items()):
            gb = QGroupBox(f"CCD {gi}   (L3 {key})")
            gl = QVBoxLayout(gb)

            btns = QHBoxLayout()
            for label, val in (("All", True), ("None", False)):
                b = QPushButton(label)
                b.clicked.connect(lambda _, c=cores, v=val: self._set_group(c, v))
                btns.addWidget(b)
            gl.addLayout(btns)

            grid = QGridLayout()
            for i, core in enumerate(sorted(cores)):
                cpus = self.topo["core_to_cpus"].get(core, [])
                cb = QCheckBox(f"core {core}   (cpu {', '.join(map(str, cpus))})")
                cb.stateChanged.connect(self.recalc)
                self.core_boxes[core] = cb
                grid.addWidget(cb, i, 0)
            gl.addLayout(grid)
            gl.addStretch()
            groups_row.addWidget(gb, 1)
        # The result panel joins this row as a third column further down. The
        # CCD lists are tall and narrow -- eight checkboxes against a lot of
        # empty width -- so the space beside them is exactly where the pinning
        # table wants to be, and it lines up with the cores that produced it.
        #
        # This row also takes the tab's spare height. It used to go to the
        # pinning panel at the bottom; with that panel moved up here, nothing
        # claimed it and the slack pooled inside the two cards below instead,
        # which left them a third empty.
        lay.addLayout(groups_row, 1)

        # --- emulator / iothread placement -------------------------------
        # Keep placement fields aligned and independent of the cache explanation.
        place = QGroupBox("Emulator and I/O threads")
        pv = QVBoxLayout(place)
        note = QLabel(
            "These carry device emulation and disk submission. Put them on cores the "
            "guest does NOT own, or they steal time from pinned vCPUs.")
        note.setWordWrap(True)
        pv.addWidget(note)

        prow = QFormLayout()

        self.emu_mode = QComboBox()
        self.emu_mode.addItem("Host leftover cores (recommended)", "leftover")
        self.emu_mode.addItem("Other CCD, if one is free", "othergroup")
        self.emu_mode.addItem("Manual cpuset", "manual")
        self.emu_mode.currentIndexChanged.connect(self.recalc)
        prow.addRow("Emulator placement:", self.emu_mode)

        self.emu_manual = QLineEdit()
        self.emu_manual.setPlaceholderText("e.g. 15,31")
        self.emu_manual.setToolTip(
            "Only used when placement is set to Manual cpuset.")
        self.emu_manual.textChanged.connect(self.recalc)
        prow.addRow("Manual cpuset:", self.emu_manual)

        self.io_count = QSpinBox()
        self.io_count.setRange(0, 8)
        self.io_count.setValue(2)
        self.io_count.setFixedWidth(70)
        self.io_count.setToolTip(
            "How many '-object iothread' entries the command line carries. "
            "Changing this adds or removes them, and each one gets its own "
            "host CPU and the I/O thread policy set below.\n\n"
            "An iothread only does work for a device that names it "
            "(iothread=<id> on a virtio-blk or virtio-scsi device); one that "
            "nothing references is created, pinned, and then idle.")
        self.io_count.valueChanged.connect(self.recalc)
        prow.addRow("I/O threads:", self.io_count)
        pv.addLayout(prow)
        pv.addStretch()

        midrow = QHBoxLayout()
        midrow.setSpacing(8)
        midrow.addWidget(place, 1)

        # --- guest cache topology -----------------------------------------
        topo_box = QGroupBox("Guest cache topology")
        tf = QVBoxLayout(topo_box)
        intro = QLabel(
            "A Ryzen CCD is an L3 domain, and moving a thread across that "
            "boundary costs far more than moving it within one. QEMU describes "
            "the guest as a single L3 domain no matter how the cores were "
            "picked, so a guest spanning two CCDs cannot see the split and "
            "schedules across it freely. Turning this on maps one guest die "
            "per CCD and tells the guest its L3 follows the die.")
        intro.setWordWrap(True)
        tf.addWidget(intro)

        self.chk_l3 = QCheckBox("Describe the L3 split to the guest")
        self.chk_l3.setToolTip(
            "Emits dies=N on -smp and smp-cache.0.cache=l3,smp-cache.0.topology=die "
            "on -machine. Needs topoext on the CPU, which this config already sets.\n\n"
            "Off changes nothing at all: the command line is byte for byte what it "
            "was before.")
        self.chk_l3.stateChanged.connect(self.recalc)
        tf.addWidget(self.chk_l3)

        self.l3_note = QLabel("")
        self.l3_note.setWordWrap(True)
        tf.addWidget(self.l3_note)
        tf.addStretch()
        midrow.addWidget(topo_box, 1)
        lay.addLayout(midrow)

        # --- scheduling ---------------------------------------------------
        sched = QGroupBox("Scheduling")
        sv = QVBoxLayout(sched)
        for attr, label, policy, priority in (
                ("vcpu", "vCPU threads", "rr", 1),
                ("emu", "Emulator threads", "fifo", 10),
                ("io", "I/O threads", "fifo", 10)):
            srow = QHBoxLayout()
            combo, spin = self._sched_row(srow, label, policy, priority)
            setattr(self, attr + "_sched", combo)
            setattr(self, attr + "_prio", spin)
            srow.addStretch()
            sv.addLayout(srow)

        # --- RT throttling ------------------------------------------------
        # The kernel lets real-time policies have at most sched_rt_runtime_us
        # of every sched_rt_period_us and then forces them off the CPU. At the
        # stock 950000 of 1000000 that is a 50 ms hole punched in the vCPUs
        # twenty times a second, which the guest feels as a stutter. -1 removes
        # the cap, and is what this always did; a quota keeps the host's escape
        # hatch if an RT thread runs away, at the cost of that stutter.
        trow = QHBoxLayout()
        trow.setSpacing(6)
        self.rt_mode = QComboBox()
        self.rt_mode.addItem("Disable throttling (-1)", "disable")
        self.rt_mode.addItem("Cap RT threads at a quota", "quota")
        self.rt_mode.addItem("Leave the host value alone", "leave")
        self.rt_mode.setFixedWidth(230)
        self.rt_mode.setItemData(
            0, "echo -1 > /proc/sys/kernel/sched_rt_runtime_us. RT threads run "
               "as long as they want. Recommended for passthrough, and what "
               "this tool did before this dropdown existed.",
            Qt.ItemDataRole.ToolTipRole)
        self.rt_mode.setItemData(
            1, "Write a quota instead. The kernel still throttles the guest, "
               "but a runaway RT thread cannot lock the host out entirely.",
            Qt.ItemDataRole.ToolTipRole)
        self.rt_mode.setItemData(
            2, "Write nothing. Whatever the host is booted with applies, and "
               "the launch only warns if that would throttle the guest.",
            Qt.ItemDataRole.ToolTipRole)
        self.rt_mode.currentIndexChanged.connect(self.recalc)

        self.rt_quota = QSpinBox()
        self.rt_quota.setRange(1000, launcher.RT_PERIOD_US)
        self.rt_quota.setSingleStep(10000)
        self.rt_quota.setValue(950000)
        self.rt_quota.setSuffix(" us")
        self.rt_quota.setFixedWidth(110)
        self.rt_quota.setToolTip(
            f"Microseconds of every {launcher.RT_PERIOD_US} us period that real-time "
            f"threads may hold a CPU. The kernel default is 950000.")
        self.rt_quota.valueChanged.connect(self.recalc)

        rt_label, quota_label = QLabel("RT throttling:"), QLabel("quota:")
        # The whole row only means something under fifo/rr, so it is greyed as
        # a unit rather than sitting there looking like a live setting.
        self._rt_row = [rt_label, self.rt_mode, quota_label, self.rt_quota]
        trow.addWidget(rt_label)
        trow.addWidget(self.rt_mode)
        trow.addWidget(quota_label)
        trow.addWidget(self.rt_quota)
        trow.addStretch()
        sv.addLayout(trow)

        # Full width and hidden unless it applies, rather than squeezed into a
        # form's value column where it wrapped to four lines.
        self.rt_warn = QLabel("")
        self.rt_warn.setWordWrap(True)
        self.rt_warn.setStyleSheet("color: #e5c07b;")
        self.rt_warn.setVisible(False)
        sv.addWidget(self.rt_warn)
        lay.addWidget(sched)

        # --- result --------------------------------------------------------
        res = QGroupBox("Generated pinning")
        rl = QVBoxLayout(res)
        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        rl.addWidget(self.summary)
        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setFont(QFont(MONO, 10))
        self.view.setMinimumHeight(220)
        rl.addWidget(self.view, 1)
        groups_row.addWidget(res, 2)

        self._preselect()

    def _sched_row(self, row, label, default, prio):
        """One scheduler + priority pair, appended to a shared horizontal row.

        The policy description used to sit beside each pair as a visible label,
        which cost three rows and a lot of width to repeat what hovering the
        dropdown says. It is now the tooltip on each item and on the combo
        itself, so it follows the current selection.
        """
        combo = QComboBox()
        for name, desc in SCHEDULERS:
            combo.addItem(name, name)
            combo.setItemData(combo.count() - 1, desc, Qt.ItemDataRole.ToolTipRole)
        combo.setCurrentText(default)
        combo.setFixedWidth(90)
        combo.setToolTip(dict(SCHEDULERS)[default])
        combo.currentTextChanged.connect(
            lambda t, c=combo: c.setToolTip(dict(SCHEDULERS).get(t, "")))
        combo.currentIndexChanged.connect(self.recalc)

        spin = QSpinBox()
        spin.setRange(0, 99)
        spin.setValue(prio)
        spin.setFixedWidth(58)
        spin.setToolTip("Real-time priority. Ignored by batch, idle and other.")
        spin.valueChanged.connect(self.recalc)

        name = QLabel(label + ":")
        name.setMinimumWidth(130)
        row.addWidget(name)
        row.addWidget(combo)
        row.addWidget(QLabel("prio:"))
        row.addWidget(spin)
        row.addSpacing(20)
        return combo, spin

    def _preselect(self):
        """Start from whatever the loaded config already pins."""
        plan = self.cfg.data.get("pinning", {})
        single = not plan.get("smt", self.cfg.smp.get("topology", {}).get("threads", "2") == "2")
        self.smt_mode.blockSignals(True)
        self.smt_mode.setCurrentIndex(self.smt_mode.findData("single" if single else "both"))
        self.smt_mode.blockSignals(False)
        for prefix, key in (("vcpu", "vcpusched"), ("emu", "emulatorsched"), ("io", "iothreadsched")):
            saved = plan.get(key, {})
            for widget, value in ((getattr(self, prefix + "_sched"), saved.get("scheduler")),
                                  (getattr(self, prefix + "_prio"), saved.get("priority"))):
                if value is not None:
                    widget.blockSignals(True)
                    if isinstance(widget, QComboBox):
                        widget.setCurrentText(value)
                    else:
                        widget.setValue(int(value))
                    widget.blockSignals(False)
        pinned = set()
        for e in self.cfg.data.get("pinning", {}).get("vcpupin", []):
            try:
                pinned.add(int(e.get("core", -1)))
            except (TypeError, ValueError):
                pass
        if not pinned:
            l3 = self.topo["l3_to_cores"]
            first = list(l3.values())[0] if l3 else sorted(self.core_boxes)[:8]
            pinned = set(first)
        for core, cb in self.core_boxes.items():
            cb.blockSignals(True)
            cb.setChecked(core in pinned)
            cb.blockSignals(False)

        # Restore the cache-topology choice with the rest of the session. It
        # defaults off, so a config written before this existed comes back
        # emitting exactly what it emitted before.
        self.chk_l3.blockSignals(True)
        self.chk_l3.setChecked(bool(self.cfg.data.get("pinning", {}).get("l3_topology")))
        self.chk_l3.blockSignals(False)

        # The I/O thread count is the number of iothread objects the config
        # already carries, not the spinbox default. Without this, opening the
        # tab on a config with four of them would tombstone two on the first
        # recalc -- the widget would be overwriting the config it is meant to
        # be showing.
        self.io_count.blockSignals(True)
        self.io_count.setValue(min(self.io_count.maximum(),
                                   len(launcher.iothread_ids(self.cfg))))
        self.io_count.blockSignals(False)

        # Same for the RT throttling choice. launcher.rt_runtime() supplies the
        # -1 for a config written before the key existed, so those come back
        # emitting the same sysctl write they always did.
        rt = launcher.rt_runtime(self.cfg.data.get("pinning", {}))
        for w in (self.rt_mode, self.rt_quota):
            w.blockSignals(True)
        if rt is None:
            self.rt_mode.setCurrentIndex(self.rt_mode.findData("leave"))
        elif rt < 0:
            self.rt_mode.setCurrentIndex(self.rt_mode.findData("disable"))
        else:
            self.rt_mode.setCurrentIndex(self.rt_mode.findData("quota"))
            self.rt_quota.setValue(max(self.rt_quota.minimum(),
                                       min(self.rt_quota.maximum(), rt)))
        for w in (self.rt_mode, self.rt_quota):
            w.blockSignals(False)

    def _sync_iothreads(self, n):
        """Make the config hold exactly n live '-object iothread' entries.

        This spinbox used to be half cosmetic: it decided how many cpusets to
        compute while the command line kept whatever iothread objects it was
        captured with, so asking for four still produced two threads and two
        of the cpusets addressed nothing.

        Removal tombstones rather than deletes, which is how every other list
        in this config drops an entry, and a tombstone is revived before a new
        id is minted so the ids do not climb every time the number is nudged.
        """
        objs = self.cfg.objects
        mine = [o for o in objs if o.get("qom-type") == "iothread"]
        live = [o for o in mine if not o.get("_disabled")]

        for o in live[n:]:
            o["_disabled"] = True
        need = n - len(live)
        if need > 0:
            dead = [o for o in mine if o.get("_disabled")][:need]
            for o in dead:
                o.pop("_disabled", None)
            for _ in range(need - len(dead)):
                taken = {o.get("id") for o in objs}
                i = 1
                while f"iothread{i}" in taken:
                    i += 1
                # Appended rather than slotted into data["order"], which puts it
                # last on the command line. QEMU creates every -object before it
                # realises any -device, so position does not matter here.
                objs.append({"qom-type": "iothread", "id": f"iothread{i}"})

        return [o.get("id") for o in objs
                if o.get("qom-type") == "iothread" and not o.get("_disabled")]

    def _set_group(self, cores, value):
        for c in cores:
            if c in self.core_boxes:
                self.core_boxes[c].blockSignals(True)
                self.core_boxes[c].setChecked(value)
                self.core_boxes[c].blockSignals(False)
        self.recalc()

    # ------------------------------------------------------------- logic ---
    def selected_cores(self):
        return sorted(c for c, cb in self.core_boxes.items() if cb.isChecked())

    def recalc(self):
        c2c = self.topo["core_to_cpus"]
        guest_cores = self.selected_cores()
        single = self.smt_mode.currentData() == "single"

        vcpupin, vcpu = [], 0
        for core in guest_cores:
            cpus = c2c.get(core, [])
            for cpu in (cpus[:1] if single else cpus):
                vcpupin.append({"vcpu": vcpu, "cpuset": str(cpu), "core": core})
                vcpu += 1

        guest_cpus = {int(e["cpuset"]) for e in vcpupin}
        leftover = sorted(c for core, cpus in c2c.items() for c in cpus
                          if c not in guest_cpus and core >= 0)

        mode = self.emu_mode.currentData()
        # Now that the cpuset box shares a row with the placement dropdown, grey
        # it out unless it is the one being used -- otherwise the row reads as
        # three equal settings when only two apply.
        self.emu_manual.setEnabled(mode == "manual")
        if mode == "othergroup":
            # Every CPU of an L3 group the guest does not touch at all. Sorted,
            # because the group is stored per core and the two SMT siblings of
            # a core are far apart in CPU numbering.
            other = sorted(c for cores in self.topo["l3_to_cores"].values()
                           if not set(cores) & set(guest_cores)
                           for core in cores for c in c2c.get(core, []))
            pool = other or leftover
        else:
            pool = leftover

        if mode == "manual":
            emu = self.emu_manual.text().strip()
        else:
            emu = ",".join(map(str, pool[-2:]))

        # One CPU per I/O thread, taken from the top of the pool downwards so
        # they sit beside the emulator and away from cpu0, which the host uses
        # for interrupts. The pool is always host CPUs, never the emulator's own
        # and never the manual cpuset, so the two do not fight each other.
        emu_set = {x.strip() for x in emu.split(",") if x.strip()}
        free = [c for c in pool if str(c) not in emu_set] or pool
        io_pins = ([str(free[-1 - (i % len(free))]) for i in range(self.io_count.value())]
                   if free else [])

        # The objects the launch script will actually find threads for. Kept in
        # step here so the count in this tab is the count QEMU creates.
        iothreads = self._sync_iothreads(self.io_count.value())

        # How many host L3 domains the selection actually touches. One die per
        # touched CCD, so a guest inside a single CCD stays dies=1 and nothing
        # changes -- there is no split to describe.
        l3 = self.topo["l3_to_cores"] or {}
        spanned = [k for k, cores in l3.items() if set(cores) & set(guest_cores)]
        want_l3 = self.chk_l3.isChecked()
        dies = len(spanned) if want_l3 else 1
        t = 1 if single else 2

        # The topology product must come out at the vCPU count, and cores are
        # split evenly across dies. An uneven split cannot be expressed by
        # -smp at all, so it is refused rather than silently rounded.
        vcpus = len(vcpupin)
        cores_per_die = (vcpus // t) // dies if dies else 0
        if dies > 1 and cores_per_die * t * dies != vcpus:
            self.l3_note.setText(
                f"<b>Cannot split evenly.</b> {vcpus} vCPUs across {dies} CCDs "
                f"does not divide into whole cores per die, so -smp could not "
                f"describe it. Even the core count per CCD, or leave this off.")
            dies, want_l3 = 1, False
        elif want_l3 and dies > 1:
            self.l3_note.setText(
                f"Guest will see <b>{dies} dies x {cores_per_die} cores x "
                f"{t} threads</b>, one L3 per die. Adds "
                f"<code>dies={dies}</code> to -smp and "
                f"<code>smp-cache.0.cache=l3,smp-cache.0.topology=die</code> to -machine.")
        elif want_l3:
            self.l3_note.setText(
                "Selected cores all sit in one CCD, so there is no L3 split to "
                "describe and nothing is emitted. This matters once cores from "
                "both CCDs are ticked.")
        else:
            self.l3_note.setText(
                "Off. The guest sees one L3 domain covering every vCPU, which is "
                "QEMU's default and what this VM has always run with.")

        rt_mode = self.rt_mode.currentData()
        rt_runtime = {"disable": -1, "leave": None}.get(rt_mode, self.rt_quota.value())
        rt_on = bool({self.vcpu_sched.currentText(), self.emu_sched.currentText(),
                      self.io_sched.currentText()} & {"fifo", "rr"})
        for w in self._rt_row:
            w.setEnabled(rt_on)
        self.rt_quota.setEnabled(rt_on and rt_mode == "quota")

        self.plan = {
            "vcpus": len(vcpupin),
            "rt_runtime_us": rt_runtime,
            "cache_dies": dies if want_l3 else 1,
            "l3_topology": want_l3,
            "guest_cores": guest_cores,
            "vcpupin": vcpupin,
            "smt": not single,
            "emulatorpin": emu,
            "iothreadpin": io_pins,
            "host_cpus": leftover,
            "vcpusched": {"scheduler": self.vcpu_sched.currentText(), "priority": self.vcpu_prio.value()},
            "emulatorsched": {"scheduler": self.emu_sched.currentText(), "priority": self.emu_prio.value()},
            "iothreadsched": {"scheduler": self.io_sched.currentText(), "priority": self.io_prio.value()},
        }
        self.cfg.data["pinning"] = self.plan

        threads = 1 if single else 2
        self.summary.setText(
            f"<b>{len(vcpupin)} vCPUs</b> from {len(guest_cores)} physical cores "
            f"({'SMT on, 2 threads' if not single else 'one thread'} per core) &nbsp;|&nbsp; "
            f"guest topology <b>{max(1, len(vcpupin)//threads)} cores x {threads} threads</b> "
            f"&nbsp;|&nbsp; {len(leftover)} host CPUs left")

        if not rt_on:
            self.rt_warn.setText("")
        elif rt_runtime is None:
            self.rt_warn.setText(
                "Real time policy selected and the host value left alone. If "
                "kernel.sched_rt_runtime_us is not -1 the kernel throttles these "
                "threads and the guest stutters; the launch checks and warns.")
        elif rt_runtime < 0:
            self.rt_warn.setText(
                "Real time policy selected. The start hook writes "
                "kernel.sched_rt_runtime_us = -1, so these threads are never "
                "throttled, and the revert hook puts the old value back.")
        else:
            share = rt_runtime * 100 / launcher.RT_PERIOD_US
            self.rt_warn.setText(
                f"Real time policy selected. The start hook writes "
                f"kernel.sched_rt_runtime_us = {rt_runtime}, so these threads get "
                f"{share:g}% of each {launcher.RT_PERIOD_US} us period and are held off "
                f"the CPU for the remaining {launcher.RT_PERIOD_US - rt_runtime} us. "
                f"Expect that as a periodic stutter in the guest.")
        self.rt_warn.setVisible(rt_on)

        rows = [f"{'vcpu':>5} {'host cpu':>9} {'phys core':>10}", "  " + "-" * 30]
        rows += [f"{e['vcpu']:>5} {e['cpuset']:>9} {e['core']:>10}" for e in vcpupin]
        rows += ["",
                 f"emulatorpin  : {emu or '(none)'}",
                 f"iothreadpin  : {', '.join(io_pins) or '(none)'}"]
        # Which object each cpuset belongs to, because that pairing is what the
        # launch script does and it is not obvious from a bare list of CPUs.
        rows += [f"               {iot} -> cpu {cpu}"
                 for iot, cpu in zip(iothreads, io_pins)]
        rows += [f"host cpus    : {leftover}",
                 "",
                 f"vcpusched    : {self.plan['vcpusched']['scheduler']} prio {self.plan['vcpusched']['priority']}",
                 f"emulatorsched: {self.plan['emulatorsched']['scheduler']} prio {self.plan['emulatorsched']['priority']}",
                 f"iothreadsched: {self.plan['iothreadsched']['scheduler']} prio {self.plan['iothreadsched']['priority']}"]
        if rt_on:
            rows += [f"rt_runtime_us: {'(host value left alone)' if rt_runtime is None else rt_runtime}"]
        if guest_cpus & set(int(x) for x in emu.split(",") if x.strip().isdigit()):
            rows += ["", "WARNING: emulator shares a CPU with a pinned vCPU."]
        self.view.setPlainText("\n".join(rows))
        self.changed.emit()


class MemoryTab(QScrollArea):
    """RAM size, hugepage backing and the allocation that must be verified."""

    changed = pyqtSignal()

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.setWidgetResizable(True)
        self._loading = True
        self._build()
        self._loading = False
        self.recalc()
        guard_all(self)

    # ------------------------------------------------------------- state ---
    def mem(self):
        """Memory settings the launcher reads.

        Stored explicitly instead of inferred from mem-path. Guessing the page
        size from the path meant the UI could say '1 GiB' while the launch
        script allocated from the 2M pool.
        """
        m = self.cfg.data.setdefault("memory", {})
        ram = self._ram_obj() or {}
        m.setdefault("hugepages", bool(ram.get("mem-path")))
        m.setdefault("pagesize", 2 * 1024 * 1024)
        m.setdefault("mem_path", ram.get("mem-path", "/dev/hugepages/vmstart2"))
        return m

    def _ram_obj(self):
        for o in self.cfg.objects:
            if o.get("id") == "pc.ram":
                return o
        return None

    # ------------------------------------------------------------- build ---
    def _build(self):
        w = QWidget()
        self.setWidget(w)
        lay = QVBoxLayout(w)
        mem = self.mem()

        g = QGroupBox("Guest RAM")
        f = QFormLayout(g)
        self.gb = QSpinBox()
        self.gb.setRange(1, 1024)
        self.gb.setSuffix(" GiB")
        self.gb.setValue(self._current_gib())
        self.gb.valueChanged.connect(self.recalc)
        f.addRow("Size:", self.gb)
        self.lbl_host_ram = QLabel("")
        f.addRow("Host has:", self.lbl_host_ram)
        lay.addWidget(g)

        hp = QGroupBox("Hugepage backing")
        if self.cfg.profile == "macos":
            note = QLabel("After changing VM RAM, open Mac & OpenCore and sync the custom memory description "
                          "before applying the new boot configuration.")
            note.setWordWrap(True)
            lay.addWidget(note)
        hf = QFormLayout(hp)
        # Let the field column take the available width so the mem-path box and
        # the status labels use it instead of being squeezed and wrapping.
        hf.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.use_hp = QCheckBox("Back guest RAM with hugepages")
        self.use_hp.setChecked(bool(mem["hugepages"]))
        self.use_hp.setToolTip("Fewer TLB misses and no page-fault storm at boot. "
                               "Off falls back to ordinary anonymous memory.")
        if self.cfg.profile == "macos":
            self.use_hp.setText("Use static hugepages")
            self.use_hp.setToolTip("Use an existing pool, or enable temporary allocation for this VM run. "
                                   "Ordinary RAM can already use transparent hugepages; measure both before choosing.")
        self.use_hp.stateChanged.connect(self.recalc)
        hf.addRow(self.use_hp)
        if self.cfg.profile == "macos":
            self.temporary_hp = QCheckBox("Allocate 2 MiB pages for this run; release added pages afterward")
            self.temporary_hp.setChecked(bool(mem.get("temporary", False)))
            self.temporary_hp.setToolTip("Reserve pages before GPU handoff, then restore the previous pool size after QEMU exits. "
                                         "Uses a private mount under macos/run; no persistent host changes.")
            self.temporary_hp.toggled.connect(self._temporary_changed)
            hf.addRow(self.temporary_hp)

        self.pagesize = QComboBox()
        pools = hostinfo.hugepage_pools()
        for size in sorted(pools):
            self.pagesize.addItem(_size_name(size), size)
        if not pools:
            self.pagesize.addItem("2 MiB", 2 * 1024 * 1024)
        idx = self.pagesize.findData(mem["pagesize"])
        self.pagesize.setCurrentIndex(idx if idx >= 0 else 0)
        self.pagesize.currentIndexChanged.connect(self.recalc)
        hf.addRow("Page size:", self.pagesize)

        self.mem_path = QLineEdit(mem["mem_path"])
        self.mem_path.setToolTip("Directory on a hugetlbfs mount. The page size "
                                 "the guest gets is the one that mount was made "
                                 "with, not the dropdown above.")
        self.mem_path.textEdited.connect(self.recalc)
        hf.addRow("mem-path:", self.mem_path)

        # These are short single-line status strings. Word-wrap made them wrap to
        # two lines inside a form row that stays one line tall, clipping the
        # second line; the field column is wide enough to hold them unwrapped.
        self.lbl_mount = QLabel("")
        hf.addRow("Mount:", self.lbl_mount)

        self.lbl_pages = QLabel("")
        hf.addRow("Pages required:", self.lbl_pages)
        self.lbl_hp_state = QLabel("")
        hf.addRow("Pool right now:", self.lbl_hp_state)

        row = QHBoxLayout()
        for text, slot, tip in (
                ("Allocate now (and verify)", self._allocate,
                 "Write the pool size and read back what the kernel actually gave"),
                ("Free hugepages", self._free, "Return the pool to zero"),
                ("Refresh", self.recalc, "Re-read the pools")):
            if self.cfg.profile == "macos" and text != "Refresh":
                continue
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch()
        holder = QWidget()
        holder.setLayout(row)
        hf.addRow(holder)

        self.alloc_log = QPlainTextEdit()
        self.alloc_log.setReadOnly(True)
        self.alloc_log.setFont(QFont(MONO, 10))
        self.alloc_log.setMaximumHeight(110)
        hf.addRow(self.alloc_log)
        lay.addWidget(hp)

        opts = QGroupBox("Backend options")
        of = QFormLayout(opts)
        self.prealloc = QCheckBox("prealloc  (touch every page up front; avoids first-touch stalls)")
        self.prealloc.setChecked(True)
        self.share = QCheckBox("share  (shared mapping; needed for vhost-user)")
        self.locked = QCheckBox("mem-lock  (mlock guest RAM, never swapped)")
        self.discard = QCheckBox("discard-data  (release pages back on shutdown)")
        self.balloon = QCheckBox("memballoon  (paravirtual device; a virtualisation tell)")
        if self.cfg.profile == "macos":
            ram = self._ram_obj() or {}
            self.prealloc.setChecked(bool(ram.get("prealloc", False)))
            self.share.setChecked(bool(ram.get("share", False)))
            self.discard.setChecked(bool(ram.get("discard-data", False)))
            self.locked.setChecked("mem-lock=on" in self.cfg.simple.get("overcommit", ""))
            self.balloon.hide()
        for c in (self.prealloc, self.share, self.locked, self.discard, self.balloon):
            c.stateChanged.connect(self.recalc)
            of.addRow(c)
        lay.addWidget(opts)

        if self.cfg.profile == "macos":
            self.capture = QCheckBox("Record performance diagnostics during Single GPU runs")
            self.capture.setChecked(bool(self.cfg.data.get("performance", {}).get("capture", False)))
            self.capture.setToolTip("Record QEMU memory mappings, thread affinity, CPU activity and PCIe link state for up to "
                                    "30 minutes. Reports stay in macos/performance/reports. No host tuning or guest changes.")
            self.capture.toggled.connect(self._capture_changed)
            lay.addWidget(self.capture)

        self.note = QLabel("")
        self.note.setWordWrap(True)
        lay.addWidget(self.note)
        lay.addStretch()

    def _current_gib(self):
        m = self.cfg.simple.get("m", "")
        v = m.split("=")[-1] if "=" in m else m
        try:
            if v.endswith("k"):
                return max(1, int(v[:-1]) // (1024 * 1024))
            if v.endswith("M"):
                return max(1, int(v[:-1]) // 1024)
            if v.endswith("G"):
                return int(v[:-1])
            return max(1, int(v) // (1024 ** 3))
        except Exception:
            return 32

    # ------------------------------------------------------------- logic ---
    def recalc(self):
        if self._loading:
            return
        gib = self.gb.value()
        psize = self.pagesize.currentData() or 2 * 1024 * 1024
        want = gib * 1024 ** 3
        pages = want // psize
        use = self.use_hp.isChecked()
        path = self.mem_path.text().strip()

        mem = self.mem()
        mem.update({"hugepages": use, "pagesize": psize, "mem_path": path})
        if self.cfg.profile == "macos":
            mem["temporary"] = self.temporary_hp.isChecked()
            self.temporary_hp.setEnabled(use)

        self.pagesize.setEnabled(use)
        self.mem_path.setEnabled(use)
        self.lbl_pages.setText(f"{pages} x {_size_name(psize)}" if use else "n/a")

        # --- object -------------------------------------------------------
        ram = self._ram_obj()
        if ram is not None:
            ram["size"] = want
            ram["prealloc"] = bool(self.prealloc.isChecked())
            if use:
                # Restore the file backend. Unchecking used to only delete
                # mem-path, which left a memory-backend-file with nowhere to
                # map from and no way to get hugepages back.
                ram["qom-type"] = "memory-backend-file"
                ram["mem-path"] = path
                if self.share.isChecked():
                    ram["share"] = True
                else:
                    ram.pop("share", None)
                if self.discard.isChecked():
                    ram["discard-data"] = True
                else:
                    ram.pop("discard-data", None)
            else:
                # memfd when the mapping must be shared, plain ram otherwise.
                ram["qom-type"] = ("memory-backend-memfd" if self.share.isChecked()
                                   else "memory-backend-ram")
                ram.pop("mem-path", None)
                ram.pop("discard-data", None)
                if self.share.isChecked():
                    ram["share"] = True
                else:
                    ram.pop("share", None)

        self.cfg.simple["m"] = f"size={gib * 1024 * 1024}k"
        self.cfg.simple["overcommit"] = "mem-lock=" + ("on" if self.locked.isChecked() else "off")

        # --- host state ----------------------------------------------------
        pools = hostinfo.hugepage_pools()
        pool = pools.get(psize)
        total = free = 0
        if pool:
            total, free = pool["nr"], pool["free"]
            self.lbl_hp_state.setText(
                f"{_size_name(psize)} pool: {total} allocated, {free} free"
                + (f"   ({free * psize // 1024**3} GiB available)" if free else ""))
        else:
            self.lbl_hp_state.setText(f"the kernel has no {_size_name(psize)} pool")

        try:
            kb = int(next(l.split()[1] for l in open("/proc/meminfo")
                          if l.startswith("MemTotal")))
            self.lbl_host_ram.setText(f"{kb // 1024 // 1024} GiB total")
        except Exception:
            self.lbl_host_ram.setText("?")

        warn = []
        mnt = hostinfo.mount_for(path) if use and path else None
        if use:
            if not mnt:
                self.lbl_mount.setText("no hugetlbfs mount contains this path")
                warn.append(f"{path} is not on a hugetlbfs mount, so QEMU gets "
                            f"ordinary pages. Mounted: "
                            f"{', '.join(m['mount'] for m in hostinfo.hugetlbfs_mounts()) or 'none'}.")
            else:
                self.lbl_mount.setText(
                    f"{mnt['mount']}  (pagesize {_size_name(mnt['pagesize'] or 0)})")
                if mnt["pagesize"] and mnt["pagesize"] != psize:
                    # The mount decides, not the dropdown.
                    warn.append(
                        f"{mnt['mount']} was mounted with "
                        f"{_size_name(mnt['pagesize'])} pages, but "
                        f"{_size_name(psize)} is selected. The mount wins: "
                        f"remount it with pagesize={_size_name(psize).replace(' ','')} "
                        f"or pick {_size_name(mnt['pagesize'])} here.")
            if pool and total < pages:
                warn.append(f"{pages} pages needed, {total} in the pool. The launch "
                            f"allocates them and stops if it comes up short.")
            if not pool:
                warn.append("Selected page size has no kernel pool; allocation will fail.")
        else:
            self.lbl_mount.setText("hugepages off")
            warn.append("Without hugepages the guest takes a TLB-miss penalty and "
                        "a long first-touch stall.")

        if self.balloon.isChecked():
            warn.append("memballoon is a paravirtual device and is visible in the guest.")
        if self.share.isChecked() and not use:
            warn.append("share needs memory-backend-memfd, which is what will be used.")
        if self.cfg.profile == "macos":
            findings = launcher.mac_memory.checks(launcher.mac_memory.spec(self.cfg))
            warn = [message for _severity, message in findings]
            if not use:
                self.lbl_mount.setText("Static pages off; transparent pages may still be used")
            if use and self.temporary_hp.isChecked():
                self.lbl_mount.setText("Private hugetlbfs prepared for this run")
                self.alloc_log.setPlainText("Temporary allocation runs before GPU handoff. Added pages and the private mount are "
                                           "released after QEMU exits, including launch failures. Existing pools are preserved.")
            else:
                self.alloc_log.setPlainText("Existing-pool mode leaves host memory resources unchanged. "
                                           "The launch stops before GPU handoff if the pool or mount is unavailable.")
        self.note.setText("  ".join(warn))
        self.changed.emit()

    def _capture_changed(self, checked):
        self.cfg.data.setdefault("performance", {})["capture"] = bool(checked)
        self.changed.emit()

    def _temporary_changed(self, checked):
        if checked:
            self.pagesize.setCurrentIndex(self.pagesize.findData(2 * 1024**2))
            self.mem_path.setText(str(launcher.mac_memory.TEMP_ROOT / "hugepages-2M"))
        self.recalc()

    # ---------------------------------------------------------- allocate ---
    def _allocate(self):
        if self.cfg.profile == "macos":
            return
        import subprocess
        psize = self.pagesize.currentData() or 2 * 1024 * 1024
        pages = (self.gb.value() * 1024 ** 3) // psize
        pool = hostinfo.hugepage_pools().get(psize)
        if not pool:
            self.alloc_log.setPlainText(f"no {_size_name(psize)} pool on this kernel")
            return
        sysfs = pool["sysfs"]
        # Drop caches and compact between attempts: the usual reason a request
        # comes up short is fragmentation, not genuine memory pressure.
        script = (f"echo {pages} > {sysfs}; sync; echo 3 > /proc/sys/vm/drop_caches; "
                  f"echo 1 > /proc/sys/vm/compact_memory 2>/dev/null; "
                  f"echo {pages} > {sysfs}")
        argv, env, ok = sudo_command(["sh", "-c", script],
                                    prompt="vmstart_2: allocate hugepages (root)")
        if not ok:
            self.alloc_log.setPlainText("allocating hugepages needs root and no password "
                                        "prompt is available (install ksshaskpass or "
                                        "enable passwordless sudo).")
            return
        try:
            subprocess.run(argv, check=True, capture_output=True, timeout=180, env=env)
        except Exception as e:
            self.alloc_log.setPlainText(f"allocation failed: {e}")
            return
        got = (hostinfo.hugepage_pools().get(psize) or {}).get("nr", 0)
        if got >= pages:
            self.alloc_log.setPlainText(
                f"OK: requested {pages}, got {got} ({got * psize // 1024**3} GiB) "
                f"in the {_size_name(psize)} pool")
        else:
            self.alloc_log.setPlainText(
                f"SHORT: requested {pages}, got {got} ({got * psize // 1024**3} GiB). "
                f"Memory is too fragmented. Free page cache or reboot before launching.")
        self.recalc()

    def _free(self):
        if self.cfg.profile == "macos":
            return
        import subprocess
        psize = self.pagesize.currentData() or 2 * 1024 * 1024
        pool = hostinfo.hugepage_pools().get(psize)
        if not pool:
            return
        argv, env, ok = sudo_command(["sh", "-c", f"echo 0 > {pool['sysfs']}"],
                                    prompt="vmstart_2: free hugepages (root)")
        if not ok:
            self.alloc_log.setPlainText("freeing hugepages needs root and no password "
                                        "prompt is available.")
            return
        try:
            subprocess.run(argv, check=True, capture_output=True, timeout=60, env=env)
            self.alloc_log.setPlainText(f"{_size_name(psize)} pool released")
        except Exception as e:
            self.alloc_log.setPlainText(f"free failed: {e}")
        self.recalc()


def _size_name(n):
    if n >= 1024 ** 3:
        return f"{n // 1024 ** 3} GiB"
    if n >= 1024 ** 2:
        return f"{n // 1024 ** 2} MiB"
    return f"{n} B"
