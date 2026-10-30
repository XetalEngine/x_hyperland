#!/usr/bin/env python3
"""Config model for vmstart_2: load / edit / validate / emit a QEMU command line.

The template is captured from the live domain's /proc/<pid>/cmdline, so what
this edits is exactly what libvirt launched. Everything the UI touches goes
through here, which keeps the coupling rules in one place instead of scattered
across widgets.
"""

import json
import os
import re
import shlex
from collections import OrderedDict

from portable import data_root
APP_DIR = str(data_root())
PRESET_DIR = os.path.join(APP_DIR, "presets")
TEMPLATE = os.path.join(PRESET_DIR, "win10-template.json")
LAST_STATE = os.path.join(APP_DIR, "last-session.json")
SMBIOS_DEFAULT = os.path.join(PRESET_DIR, "smbios-default.json")


# --------------------------------------------------------------------------
# CPU feature catalogue. Shown as require/disable dropdowns with a one-line
# explanation, because "ssbd=off" on its own tells you nothing about what it
# costs you.
# --------------------------------------------------------------------------
CPU_FEATURES = OrderedDict([
    ("svm",            "AMD virtualisation extensions. Present on every real Ryzen, so hiding it is itself odd. AMD-only: enabling it on an Intel host makes QEMU refuse to start."),
    ("vmx",            "Intel VT-x virtualisation extensions. The Intel counterpart of svm. Intel-only; do not set on an AMD host."),
    ("topoext",        "AMD topology extensions. Needed for cores/threads to be reported correctly. AMD-only."),
    ("invtsc",         "Invariant TSC. Constant rate across P-states; every modern CPU has it."),
    ("rdtscp",         "RDTSCP instruction. Reads TSC plus CPU id atomically."),
    ("rdpid",          "Read Processor ID. Executes natively regardless of the CPUID bit."),
    ("hypervisor",     "THE hypervisor-present bit (1.ECX[31]). Must be off."),
    ("kvm",            "KVM paravirt CPUID leaves at 0x4000_0000 ('KVMKVMKVM'). Must be off."),
    ("kvmclock",       "KVM paravirtual clocksource. Publishes KVM leaves. Must be off."),
    ("pmu",            "Virtual performance counters. Off hides them, but native CPUID still advertises PerfMonV2."),
    ("ssbd",           "Intel spelling of Spec Store Bypass Disable (7.0.EDX[31]). Reads 0 on AMD."),
    ("amd-ssbd",       "AMD Spec Store Bypass Disable (8000_0008.EBX[24]). Host advertises it."),
    ("virt-ssbd",      "Virtualised SSBD. Hypervisor-only feature; real CPUs do not set it."),
    ("vmx-vnmi",       "Intel VMX capability. Inert on an AMD host."),
    ("host-cache-info", "Report the host's real cache hierarchy rather than a synthetic one."),
    ("l3-cache",       "Expose an L3 cache in the CPU model."),
    ("migratable",     "Allow only migration-safe features. Off is required for invtsc."),
    ("aes",            "AES-NI instructions. Absence on a modern CPU is anomalous."),
    ("x2apic",         "Extended APIC. Normal on modern hardware."),
    ("hv-vendor-id",   "Hyper-V vendor string. Any value here proves a hypervisor."),
])

FEATURE_CHOICES = ["on", "off"]


def free_index(blockdevs, devices, node_fmt="vmstart2-{n}-storage",
               id_fmt="vmstart2-disk{n}", start=1):
    """Lowest n not reserved by an active or retained inactive disk.

    Removal marks rather than deletes, so counting tombstones too made the
    numbering climb past every disk ever created. A tombstone's name can be
    reclaimed by claim_slot below. Active disks reserve their names; inactive disks
    keep their names so adding a disk cannot overwrite a saved attachment.
    """
    nodes = {b.get("node-name") for b in blockdevs if not b.get("_disabled") or b.get("_inactive")}
    ids = {d.get("id") for d in devices if not d.get("_disabled") or d.get("_inactive")}
    n = start
    while node_fmt.format(n=n) in nodes or id_fmt.format(n=n) in ids:
        n += 1
    return n


def disk_slot(device):
    """Return ((family, controller), slot) for an explicit SATA/NVMe slot.

    SATA includes optical drives and named controllers such as ``sata.2``.
    NVMe namespace numbers belong to their controller, not a global pool.
    Unassigned or malformed placements have no slot to reuse.
    """
    bus = str(device.get("bus") or "")
    driver = device.get("driver")
    if driver in ("ide-hd", "ide-cd"):
        match = re.fullmatch(r"(.+)\.([0-9]+)", bus)
        if match:
            return ("ide", match[1]), int(match[2])
    elif driver == "nvme-ns" and bus:
        try:
            nsid = int(device.get("nsid", 0))
        except (TypeError, ValueError):
            return None
        if nsid > 0:
            return ("nvme", bus), nsid
    return None


def disk_controller(device):
    """Controller of an assigned disk, or the remembered inactive attachment."""
    slot = disk_slot(device)
    if slot:
        return slot[0]
    if device.get("driver") in ("ide-hd", "ide-cd") and device.get("_inactive_controller"):
        return "ide", device["_inactive_controller"]
    if device.get("driver") == "nvme-ns" and device.get("bus"):
        return "nvme", device["bus"]
    return None


def fill_removed_disk_slot(devices, removed):
    """Move the highest remaining slot into a removed disk's vacant slot.

    Only one disk on the same controller moves. Its identity, backing node and
    boot priority stay attached to it. Do not reorder the underlying lists:
    the recorded command line addresses their entries by index.
    """
    placement = disk_slot(removed)
    if placement is None:
        return
    group, slot = placement
    candidates = []
    for device in devices:
        if device is removed or device.get("_disabled"):
            continue
        other = disk_slot(device)
        if other is None or other[0] != group:
            continue
        if other[1] == slot:
            # A shared IDE bus (or an already duplicated assignment) is not
            # vacant. Moving another device here would create a collision.
            return
        if other[1] > slot:
            candidates.append((other[1], device))
    if not candidates:
        return
    replacement = max(candidates, key=lambda item: item[0])[1]
    if group[0] == "nvme":
        replacement["nsid"] = slot
    else:
        replacement["bus"] = removed["bus"]


def set_disk_active(cfg, blockdev, device, active):
    """Retain an inactive disk, or append it to its controller's active slots.

    _disabled keeps both halves out of validation and emission; _inactive
    distinguishes a saved attachment from a removal tombstone. Its positive
    value on the device also records the order of the inactive cards.
    """
    if active == (not device.get("_disabled")):
        return
    if not active:
        position = max((d.get("_inactive", 0) for d in cfg.devices), default=0) + 1
        blockdev.update(_disabled=True, _inactive=True)
        device.update(_disabled=True, _inactive=position)
        fill_removed_disk_slot(cfg.devices, device)
        controller = disk_controller(device)
        if controller and controller[0] == "ide":
            device["_inactive_controller"] = controller[1]
            device.pop("bus", None)
        elif controller and controller[0] == "nvme":
            device.pop("nsid", None)
        return
    if not device.get("_inactive"):
        raise ValueError("This disk was removed. Add it again before activating it.")

    # Work out all assignments before changing either dict, so a full or
    # missing controller leaves the saved inactive disk untouched.
    live = [d for d in cfg.devices if not d.get("_disabled") and d is not device]
    updates = {}
    moves = []
    if device.get("driver") in ("ide-hd", "ide-cd", "nvme-ns"):
        group = disk_controller(device)
        if group is None:
            raise ValueError("Choose a controller before activating this disk.")
        family, controller = group
        ctrl = next((d for d in live if d.get("id") == controller), None)
        if family == "nvme" and (ctrl is None or ctrl.get("driver") != "nvme"):
            raise ValueError(f"NVMe controller '{controller}' is no longer available.")
        if family == "ide" and controller != "ide" and ctrl is None:
            raise ValueError(f"SATA controller '{controller}' is no longer available.")
        peers = [(slot[1], d) for d in live if (slot := disk_slot(d)) and slot[0] == group]
        occupied = dict(peers)
        if len(occupied) != len(peers):
            raise ValueError(f"Active disks on '{controller}' have duplicate slots. Resolve them before activating another disk.")
        start = 1 if family == "nvme" else 0
        slot = start + len(peers)
        if family == "nvme":
            if slot > 256:
                raise ValueError(f"No namespace is available after the active disks on '{controller}'.")
            updates["nsid"] = slot
        else:
            if slot >= 6 and (controller == "ide" or ctrl.get("driver") == "ich9-ahci"):
                raise ValueError(f"No SATA port is available after the active disks on '{controller}'. "
                                 "Deactivate another disk or choose a different controller.")
            updates["bus"] = f"{controller}.{slot}"

        # Imported / older inactive setups may already have holes. Fill each
        # with the highest occupied slot before appending the returning disk.
        # Count occupied ports rather than rejecting a free controller because
        # its last numbered port is still in use.
        for gap in range(start, slot):
            if gap not in occupied:
                moved = occupied.pop(max(occupied))
                occupied[gap] = moved
                moves.append((moved, {"nsid": gap} if family == "nvme"
                              else {"bus": f"{controller}.{gap}"}))

    # Preserve the saved boot priority unless another active device now owns
    # it. A duplicate bootindex makes QEMU refuse to start.
    boots = {int(d["bootindex"]) for d in live if d.get("bootindex") is not None}
    if device.get("bootindex") is not None and int(device["bootindex"]) in boots:
        updates["bootindex"] = max(boots, default=0) + 1
    for moved, assignment in moves:
        moved.update(assignment)
    device.update(updates)
    device.pop("_inactive_controller", None)
    for item in (device, blockdev):
        item.pop("_disabled", None)
        item.pop("_inactive", None)


def _order_devices_by_bus(argv):
    """Emit every -device after the device that provides its bus.

    QEMU creates devices in command line order and fails outright on a forward
    reference -- "Bus 'nvme0' not found" -- so an NVMe namespace listed before
    its controller kills the launch. Which entry lands where depends on list
    positions that the editor is free to reshuffle (a reused tombstone sits
    where the dead entry was, an appended one goes last), so this cannot be left
    to the order things happen to be created in.

    The sort is stable: a device only moves when something it depends on would
    otherwise come later, so a command line that was already correct is emitted
    byte for byte unchanged. Buses that no device provides -- pcie.0, ide.N,
    usb.0 and friends come from the machine -- are not constraints.
    """
    slots, entries = [], []
    for i, a in enumerate(argv):
        if a == "-device" and i + 1 < len(argv) and not argv[i + 1].startswith("-"):
            payload = argv[i + 1]
            try:
                d = json.loads(payload)
            except (ValueError, TypeError):
                d = {}
            slots.append(i + 1)
            entries.append((payload, d.get("id"), d.get("bus")))

    provided = {e[1] for e in entries if e[1]}
    emitted, pending, out = set(), list(entries), []
    while pending:
        progressed = False
        for e in list(pending):
            bus = e[2]
            # No bus, or a bus nothing here provides (machine-supplied), or a
            # provider already emitted -> safe to place now.
            if not bus or bus not in provided or bus in emitted:
                out.append(e)
                if e[1]:
                    emitted.add(e[1])
                pending.remove(e)
                progressed = True
        if not progressed:
            # A cycle, which QEMU could not honour either. Leave the remainder
            # in their original order rather than inventing one.
            out.extend(pending)
            break

    for slot, e in zip(slots, out):
        argv[slot] = e[0]
    return argv


def claim_slot(pool, key, name, fields):
    """Take the slot called `name`, reusing a tombstone if one already holds it.

    Appending instead would leave two entries sharing a name, one dead and one
    live. Every lookup that matches by name then picks whichever comes first,
    which is how deleting a disk once retired the dead copy and left the live
    blockdev emitted with no device and no filename -- QEMU then refuses to
    start on "the 'host_device' block driver requires a file name".

    Reusing the tombstone's own dict also preserves its position in the list,
    so the recorded emission order keeps pointing at the right item.
    """
    if any(x.get(key) == name and x.get("_inactive") for x in pool):
        raise ValueError(f"'{name}' belongs to an inactive disk; its settings must be retained.")
    slot = next((x for x in pool
                 if x.get(key) == name and x.get("_disabled")), None)
    if slot is None:
        slot = {}
        pool.append(slot)
    slot.clear()
    slot.update(fields)
    return slot

# Which flags only make sense on one vendor's silicon, so the editor can group
# them. svm/vmx are the obvious pair, but the SSBD spelling and the topology and
# VMX-capability extensions are vendor-specific too. Anything not listed here is
# vendor-neutral and belongs in the shared section.
FEATURE_VENDOR = {
    "svm": "amd", "topoext": "amd", "amd-ssbd": "amd", "virt-ssbd": "amd",
    "vmx": "intel", "ssbd": "intel", "vmx-vnmi": "intel",
}


class VMConfig:
    def __init__(self, data=None, root=None):
        self.data = data if data is not None else self.load_template()
        self.root = root or APP_DIR

    @property
    def profile(self):
        return self.data.get("_meta", {}).get("profile", "windows")

    # ---------------------------------------------------------------- io ---
    @staticmethod
    def load_template(profile="windows", root=None):
        import profiles
        path = TEMPLATE if profile == "windows" and root is None else profiles.paths(root or APP_DIR, profile).template
        with open(path) as f:
            return json.load(f)

    @classmethod
    def load(cls, path, root=None):
        with open(path) as f:
            return cls(json.load(f), root=root)

    def save(self, path):
        from settings_defaults import atomic_write
        os.makedirs(os.path.dirname(path), exist_ok=True)
        atomic_write(path, (json.dumps(self.data, indent=2) + "\n").encode())

    # ------------------------------------------------------------ access ---
    @property
    def simple(self):
        return self.data.setdefault("simple", OrderedDict())

    @property
    def cpu_features(self):
        return self.data.setdefault("cpu", {}).setdefault("features", OrderedDict())

    @property
    def smp(self):
        return self.data.setdefault("smp", {"vcpus": "1", "topology": {}})

    @property
    def devices(self):
        return self.data.setdefault("devices", [])

    @property
    def blockdevs(self):
        return self.data.setdefault("blockdevs", [])

    @property
    def objects(self):
        return self.data.setdefault("objects", [])

    @property
    def smbios(self):
        """SMBIOS patch set, seeded from the preset when absent.

        Treats an empty dict as absent. A widget that only wanted to read a
        field once created one with setdefault(), which then looked like a
        deliberately empty configuration and wiped the whole patch list.
        """
        sm = self.data.get("smbios")
        if not sm:
            try:
                import profiles
                path = (SMBIOS_DEFAULT if self.profile == "windows" else
                        profiles.paths(self.root, self.profile).presets / "smbios-default.json")
                with open(path) as f:
                    sm = json.load(f)
            except Exception:
                sm = {"template_blob": "", "output_blob": "",
                      "system_uuid": "", "patches": []}
            self.data["smbios"] = sm
        return sm

    @property
    def network(self):
        """Host networking vmstart_2 has to set up itself.

        libvirt created the tap device and handed QEMU an inherited file
        descriptor. Nothing inherits anything here, so the tap is created by
        name in the start hook and referenced by name on the command line.
        """
        n = self.data.setdefault("network", {})
        n.setdefault("mode", "tap")
        n.setdefault("ifname", "vm2tap0")
        n.setdefault("bridge", _default_bridge())
        return n

    @property
    def acpitables(self):
        return self.data.setdefault("acpitables", [])

    @property
    def globals(self):
        return self.data.setdefault("globals", [])

    def device_by_id(self, dev_id):
        for d in self.devices:
            if d.get("id") == dev_id:
                return d
        return None

    # -------------------------------------------------------------- sync ---
    def sync(self):
        """Push derived values so coupled fields cannot drift apart.

        Returns a list of human-readable descriptions of what was corrected.
        """
        fixed = []

        # -m size and the memory-backend-file object must describe the same RAM.
        msize = self.simple.get("m", "")
        want = _parse_size(msize)
        if want:
            for o in self.objects:
                if o.get("id") == "pc.ram" and str(o.get("size")) != str(want):
                    fixed.append(f"pc.ram size {o.get('size')} -> {want} to match -m {msize}")
                    o["size"] = want

        # vcpu count must equal the topology product, or QEMU refuses to start.
        topo = self.smp.get("topology", {})
        prod = 1
        for k in ("sockets", "dies", "clusters", "cores", "threads"):
            try:
                prod *= int(topo.get(k, 1) or 1)
            except ValueError:
                prod = 0
        if prod and str(self.smp.get("vcpus")) != str(prod):
            fixed.append(f"vcpus {self.smp.get('vcpus')} -> {prod} to match topology")
            self.smp["vcpus"] = str(prod)

        return fixed

    def validate(self):
        """Return a list of (severity, message) problems that sync cannot fix."""
        problems = []

        topo = self.smp.get("topology", {})
        try:
            prod = 1
            for k in ("sockets", "dies", "clusters", "cores", "threads"):
                prod *= int(topo.get(k, 1) or 1)
            if str(self.smp.get("vcpus")) != str(prod):
                problems.append(("error", f"vcpus {self.smp.get('vcpus')} != topology product {prod}"))
        except ValueError:
            problems.append(("error", "topology contains a non-numeric value"))

        # A disabled item is never emitted, so it must never be validated:
        # removing a device is done by marking it, and a stale mark otherwise
        # keeps reporting a missing file for a disk that is no longer on the
        # command line at all.
        live_devices = [d for d in self.devices if not d.get("_disabled")]
        live_blockdevs = [b for b in self.blockdevs if not b.get("_disabled")]

        # These fail when QEMU creates devices. Catch them before a Single GPU
        # launch hands the host display over to VFIO.
        passed_pci = {}
        usb_off = str(self.data.get("machine", {}).get("opts", {}).get("usb", "")).lower() in (
            "off", "false", "no")
        explicit_usb = any(d.get("id") == "usb" for d in live_devices)
        for d in live_devices:
            if "bus" in d and not str(d["bus"]).strip():
                problems.append(("error", f"device {d.get('id')} has an empty guest bus; "
                                 "choose a bus or remove the bus override for automatic placement"))
            if d.get("driver") == "vfio-pci":
                host = str(d.get("host", "")).lower()
                if re.fullmatch(r"[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]", host):
                    host = "0000:" + host
                if host and host in passed_pci:
                    problems.append(("error", f"PCI device {host} is assigned more than once "
                                     f"({passed_pci[host]} and {d.get('id')}); remove the duplicate"))
                passed_pci[host] = d.get("id")
            if (usb_off and not explicit_usb and d.get("bus") == "usb.0"
                    and d.get("driver", "").startswith("usb-")):
                problems.append(("error", f"device {d.get('id')} uses usb.0, but built-in USB is "
                                 "disabled; select an existing USB controller bus"))

        # Every drive= reference must point at a blockdev that exists.
        nodes = {b.get("node-name") for b in live_blockdevs if b.get("node-name")}
        for d in live_devices:
            drv = d.get("drive")
            if drv and drv not in nodes:
                problems.append(("error", f"device {d.get('id')} references missing blockdev '{drv}'"))

        # A device hanging off another device's bus needs that device present.
        # Emission order is handled for us, but a bus nothing provides is a real
        # error QEMU reports as "Bus 'x' not found". Machine-supplied buses
        # (pcie.0, ide.N, usb.N, scsi.N...) have no device behind them, so only
        # buses that look like a device id are checked.
        dev_ids = {d.get("id") for d in live_devices if d.get("id")}
        dead_ids = {d.get("id") for d in self.devices
                    if d.get("_disabled") and d.get("id")} - dev_ids
        for d in live_devices:
            bus = d.get("bus")
            if bus and bus in dead_ids:
                problems.append(("error",
                                 f"device {d.get('id')} sits on bus '{bus}', which "
                                 f"has been removed"))

        # A blockdev that opens a host path needs one. QEMU refuses outright:
        # "The 'host_device' block driver requires a file name". Format nodes
        # such as driver=raw chain to another node instead and have none, so
        # only the drivers that actually open a path are checked.
        for b in live_blockdevs:
            if b.get("driver") in ("host_device", "file") and not b.get("filename"):
                problems.append(("error",
                                 f"blockdev {b.get('node-name')} has no filename; "
                                 f"QEMU will refuse to start"))

        # Two live blockdevs cannot share a node-name: whichever a lookup finds
        # first wins, and the other is edited by nothing while still emitted.
        seen_nodes = {}
        for b in live_blockdevs:
            n = b.get("node-name")
            if not n:
                continue
            if n in seen_nodes:
                problems.append(("error", f"two live blockdevs share node-name '{n}'"))
            seen_nodes[n] = b

        # Duplicate disk serials are a giveaway and confuse Windows.
        seen = {}
        for d in live_devices:
            s = d.get("serial")
            if s:
                if s in seen:
                    problems.append(("warn", f"serial {s} used by both {seen[s]} and {d.get('id')}"))
                seen[s] = d.get("id")

        # Files referenced on the command line must exist.
        for t in self.acpitables:
            p = t.split("=", 1)[1] if "=" in t else t
            if not os.path.isfile(p):
                problems.append(("error", f"ACPI table missing: {p}"))
        for b in live_blockdevs:
            fn = b.get("filename")
            if fn and not os.path.exists(fn):
                problems.append(("error", f"blockdev file missing: {fn}"))

        # These are Windows profile preferences; the Mac master enables KVM.
        if self.profile != "macos":
            for feat, why in (("hypervisor", "exposes the hypervisor-present bit"),
                              ("kvm", "publishes KVM CPUID leaves"),
                              ("kvmclock", "publishes the KVM clocksource")):
                if self.cpu_features.get(feat) == "on":
                    problems.append(("warn", f"cpu feature '{feat}' is on: {why}"))

        return problems

    # -------------------------------------------------------------- emit ---
    def _buckets(self):
        """The six lists that data['order'] indexes into, by flag name."""
        return {
            "object":    self.objects,
            "blockdev":  self.blockdevs,
            "device":    self.devices,
            "chardev":   self.data.setdefault("chardevs", []),
            "global":    self.globals,
            "acpitable": self.acpitables,
        }

    def compact(self):
        """Delete every tombstone and renumber data['order'] to match.

        Removal marks rather than deletes because data['order'] addresses each
        argument by its index in one of these lists, and deleting from the
        middle would silently repoint every later entry at the wrong item. That
        is safe but it accumulates: names stay reserved, duplicate node-names
        become possible, and lookups that match by name can pick a dead entry.

        Renumbering removes the reason to keep them. Survivors are kept by
        identity and in their existing relative order, so live dicts that
        widgets already hold stay valid, and the emitted command line does not
        change. Retained inactive disks survive compaction and remain omitted
        from the command line. Returns the number of entries dropped.
        """
        remap, removed = {}, 0
        for flag, items in self._buckets().items():
            mapping, keep = {}, []
            for old, it in enumerate(items):
                if isinstance(it, dict) and it.get("_disabled") and not it.get("_inactive"):
                    removed += 1
                    continue
                mapping[old] = len(keep)
                keep.append(it)
            remap[flag] = mapping
            items[:] = keep              # in place: data[...] stays the same list

        new_order = []
        for entry in self.data.get("order", []):
            flag, idx = entry[0], entry[1]
            if idx is None:
                new_order.append([flag, None])
                continue
            mapping = remap.get(flag)
            if mapping is None:
                new_order.append([flag, idx])       # not a bucket we compact
            elif idx in mapping:
                new_order.append([flag, mapping[idx]])
            # an entry pointing at a purged item is dropped with it
        self.data["order"] = new_order
        return removed

    def to_argv(self, standalone=True):
        """Build the QEMU argv.

        standalone=True strips the pieces that only work when libvirt launches
        the process: the inherited monitor fd, libvirt's secret object, and the
        paused start it uses to attach.
        """
        argv = [self.data["_meta"]["binary"]]

        def add(flag, val=None):
            argv.append("-" + flag)
            if val is not None:
                argv.append(val)

        buckets = {
            "object": self.objects,
            "blockdev": self.blockdevs,
            "device": self.devices,
            "chardev": self.data.get("chardevs", []),
            "global": self.globals,
            "acpitable": self.acpitables,
        }

        # Walk the recorded emission order so the output matches the captured
        # command line argument for argument. QEMU tolerates reordering, but a
        # generator that cannot reproduce its own input is not worth trusting.
        for flag, idx in self.data.get("order", []):
            if idx is None:
                if standalone and flag == "S":
                    continue
                if standalone and flag == "no-shutdown":
                    # libvirt passes -no-shutdown so QEMU parks in the
                    # 'shutdown' runstate instead of exiting, and libvirtd then
                    # issues 'quit' over QMP once it has seen the event. With no
                    # management layer here nobody ever issues it: QEMU lives
                    # on holding the GPU, wait() never returns, and the revert
                    # hook never runs.
                    continue
                v = self.simple.get(flag)
                if standalone and flag == "netdev" and v and '"fd"' in v:
                    v = self._standalone_netdev(v)
                if flag == "machine":
                    v = _join_kv(self.data["machine"]["type"], self.data["machine"]["opts"])
                elif flag == "cpu":
                    v = _join_kv(self.data["cpu"]["model"], self.cpu_features)
                elif flag == "smp":
                    v = _join_kv(self.smp["vcpus"], self.smp["topology"])
                add(flag, v)
                continue

            items = buckets.get(flag, [])
            if idx >= len(items):
                continue                      # item deleted in the UI
            item = items[idx]
            # Removing a device marks it rather than deleting it. Deleting from
            # the middle of a list would shift every later index and silently
            # repoint the recorded order at the wrong device.
            if isinstance(item, dict) and item.get("_disabled"):
                continue

            if flag in ("global", "acpitable"):
                add(flag, item)
            elif flag == "chardev":
                raw = item.get("_raw", "")
                if standalone and "fd=" in raw:
                    # fd 32 is inherited from libvirtd and cannot exist here.
                    raw = raw.replace("fd=32", "path=/tmp/vmstart2-monitor.sock")
                add(flag, raw)
            else:
                if standalone and flag == "object" and item.get("qom-type") == "secret":
                    continue                  # libvirt's master key store
                add(flag, _emit(item))

        # Anything the UI appended beyond the recorded order goes last.
        recorded = {}
        for flag, idx in self.data.get("order", []):
            if idx is not None:
                recorded[flag] = max(recorded.get(flag, -1), idx)
        for flag, items in buckets.items():
            for i in range(recorded.get(flag, -1) + 1, len(items)):
                it = items[i]
                if isinstance(it, dict) and it.get("_disabled"):
                    continue
                if flag in ("global", "acpitable"):
                    add(flag, it)
                elif flag == "chardev":
                    add(flag, it.get("_raw", ""))
                else:
                    add(flag, _emit(it))

        return _order_devices_by_bus(argv)

    def _standalone_netdev(self, raw):
        """Replace libvirt's inherited-fd tap with one referenced by name.

        fd=33 was opened by libvirtd and passed across the exec. Under systemd
        that descriptor does not exist, and QEMU exits with
        "Can't use file descriptor 33: Bad file descriptor".
        """
        try:
            spec = json.loads(raw)
        except Exception:
            return raw
        if spec.get("type") != "tap" or "fd" not in spec:
            return raw
        net = self.network
        spec.pop("fd", None)
        spec.pop("fds", None)
        spec["ifname"] = net["ifname"]
        # The tap already exists and is already enslaved to the bridge, so
        # QEMU must not try to run the distro's ifup/ifdown helpers.
        spec["script"] = "no"
        spec["downscript"] = "no"
        return json.dumps(spec, separators=(",", ":"))

    def to_script(self, standalone=True):
        argv = self.to_argv(standalone)
        out = [shlex.quote(argv[0]) + " \\"]
        i = 1
        while i < len(argv):
            a = argv[i]
            if a.startswith("-") and i + 1 < len(argv) and not argv[i + 1].startswith("-"):
                out.append(f"  {a} {shlex.quote(argv[i+1])} \\")
                i += 2
            else:
                out.append(f"  {a} \\")
                i += 1
        out[-1] = out[-1].rstrip(" \\")
        return "\n".join(out)


def _emit(obj):
    """Objects captured as JSON go back out as JSON; kv ones as kv."""
    if "_raw" in obj:
        return obj["_raw"]
    return json.dumps({k: v for k, v in obj.items() if not k.startswith("_")},
                      separators=(",", ":"))


def _join_kv(positional, kv):
    parts = [positional] if positional else []
    parts += [f"{k}={v}" for k, v in kv.items()]
    return ",".join(parts)


def _default_bridge():
    """First bridge on the host, so this is not hardcoded to one machine."""
    import glob as _glob
    for p in sorted(_glob.glob("/sys/class/net/*")):
        if os.path.isdir(os.path.join(p, "bridge")):
            return os.path.basename(p)
    return "br0"


def _parse_size(s):
    """'33554432k' -> bytes."""
    if not s:
        return None
    s = s.strip()
    if s.startswith("size="):
        s = s[5:]
    mult = 1
    if s and s[-1].lower() in "kmgt":
        mult = {"k": 1024, "m": 1024**2, "g": 1024**3, "t": 1024**4}[s[-1].lower()]
        s = s[:-1]
    try:
        return int(s) * mult
    except ValueError:
        return None
