#!/usr/bin/env python3
"""Host enumeration for vmstart_2.

Everything the UI offers as a dropdown or an auto-preset is discovered here,
so the widgets never hardcode this machine. Pure reads, nothing is modified.
"""

import glob
import json
import os
import re
import subprocess
from collections import OrderedDict, defaultdict


def _run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=15).stdout
    except Exception:
        return ""


# --------------------------------------------------------------------- cpu ---
def cpu_topology():
    """Per-logical-CPU topology from lscpu -e, grouped by physical core and L3.

    L3 id is what separates CCDs on Ryzen, which matters on an X3D part: only
    one die carries the stacked cache, and a gaming guest wants to sit on it.
    """
    # lscpu has no "L3" column (it prints L1d:L1i:L2:L3 as one CACHE field), so
    # take the L3 grouping from sysfs, which is authoritative and vendor
    # neutral. On a 7950X3D this is what separates the two CCDs, and only one
    # of them carries the stacked cache.
    out = _run(["lscpu", "-e=CPU,CORE,SOCKET,NODE", "-J"])
    cpus = []
    if out:
        try:
            for e in json.loads(out).get("cpus", []):
                n = int(e.get("cpu"))
                cpus.append({
                    "cpu": n,
                    "core": int(e.get("core")) if e.get("core") not in (None, "") else -1,
                    "socket": int(e.get("socket") or 0),
                    "node": int(e.get("node") or 0),
                    "l3": _l3_key(n),
                })
        except Exception:
            cpus = []

    if not cpus:  # fall back to sysfs entirely
        for p in sorted(glob.glob("/sys/devices/system/cpu/cpu[0-9]*"),
                        key=lambda x: int(re.sub(r"\D", "", os.path.basename(x)))):
            n = int(re.sub(r"\D", "", os.path.basename(p)))
            try:
                core = int(open(f"{p}/topology/core_id").read())
            except Exception:
                core = -1
            cpus.append({"cpu": n, "core": core, "socket": 0, "node": 0, "l3": _l3_key(n)})

    cores = defaultdict(list)
    for c in cpus:
        cores[c["core"]].append(c["cpu"])
    l3groups = defaultdict(set)
    for c in cpus:
        if c["l3"] != "":
            l3groups[c["l3"]].add(c["core"])

    return {
        "cpus": cpus,
        "threads": len(cpus),
        "cores": len(cores),
        "smt": any(len(v) > 1 for v in cores.values()),
        "core_to_cpus": {k: sorted(v) for k, v in sorted(cores.items())},
        "l3_to_cores": {k: sorted(v) for k, v in sorted(l3groups.items())},
        "model": _cpu_model(),
    }


def _l3_key(cpu):
    """Identify which L3 domain (CCD on Ryzen) a logical CPU belongs to.

    Uses the shared_cpu_list of the level-3 cache, which is stable and does not
    depend on lscpu's column set.
    """
    for idx in glob.glob(f"/sys/devices/system/cpu/cpu{cpu}/cache/index*"):
        try:
            if open(f"{idx}/level").read().strip() == "3":
                return open(f"{idx}/shared_cpu_list").read().strip()
        except Exception:
            continue
    return ""


def _cpu_model():
    for line in open("/proc/cpuinfo"):
        if line.startswith("model name"):
            return line.split(":", 1)[1].strip()
    return "unknown"


# ------------------------------------------------------------------ vendor ---
def cpu_vendor():
    """'intel', 'amd' or 'unknown', from the CPUID vendor string.

    This is what decides intel_iommu vs amd_iommu on the kernel command line and
    vmx vs svm in the CPU model, so it is read from the hardware rather than
    assumed from whichever machine the config was captured on.
    """
    try:
        for line in open("/proc/cpuinfo"):
            if line.startswith("vendor_id"):
                v = line.split(":", 1)[1].strip()
                if v == "GenuineIntel":
                    return "intel"
                if v == "AuthenticAMD":
                    return "amd"
                return "unknown"
    except Exception:
        pass
    return "unknown"


def virt_flag():
    """The hardware-virtualisation CPU flag this host actually advertises.

    Intel exposes 'vmx', AMD exposes 'svm'. Returned so the wizard can enable
    the right one and tell the user to turn it on in firmware when neither is
    present (the usual reason KVM will not start on a fresh machine).
    """
    try:
        for line in open("/proc/cpuinfo"):
            if line.startswith("flags"):
                flags = set(line.split(":", 1)[1].split())
                if "vmx" in flags:
                    return "vmx"
                if "svm" in flags:
                    return "svm"
                return ""
    except Exception:
        pass
    return ""


def iommu_active():
    """Whether the kernel has live IOMMU groups, and what kind.

    An empty (or absent) /sys/kernel/iommu_groups is the signature of a host
    where IOMMU was never turned on: either the kernel command line lacks
    {intel,amd}_iommu, or VT-d / AMD-Vi is disabled in firmware. vfio cannot
    bind anything until this is populated, so the wizard blocks on it.
    """
    base = "/sys/kernel/iommu_groups"
    groups = []
    try:
        groups = [g for g in os.listdir(base) if g.isdigit()]
    except Exception:
        pass
    # DMAR = Intel VT-d, IVRS = AMD-Vi. Presence of the ACPI table means the
    # firmware exposes an IOMMU even if the kernel has not been told to use it.
    fw = "none"
    if os.path.exists("/sys/firmware/acpi/tables/DMAR"):
        fw = "intel-vt-d"
    elif os.path.exists("/sys/firmware/acpi/tables/IVRS"):
        fw = "amd-vi"
    dmesg_hint = ""
    return {
        "active": len(groups) > 0,
        "groups": len(groups),
        "firmware_table": fw,
        "dmesg": dmesg_hint,
    }


def total_ram_gib():
    """Installed RAM in whole GiB, for sizing the guest allocation."""
    try:
        for line in open("/proc/meminfo"):
            if line.startswith("MemTotal"):
                kb = int(line.split()[1])
                return kb // 1024 // 1024
    except Exception:
        pass
    return 0


def suggest_pinning(leave_cores_for_host=8, prefer_l3_group=None):
    """Pick guest cores and lay out vcpupin.

    Whole physical cores are allocated, never half of an SMT pair: splitting a
    core between host and guest is what produces the stutter people blame on
    the hypervisor. Cores are taken from one L3 group first so the guest stays
    on a single CCD.
    """
    topo = cpu_topology()
    core_to_cpus = topo["core_to_cpus"]
    all_cores = [c for c in core_to_cpus if c >= 0]
    total = len(all_cores)
    guest_n = max(0, total - int(leave_cores_for_host))

    groups = topo["l3_to_cores"]
    ordered = []
    if groups:
        keys = list(groups.keys())
        if prefer_l3_group in groups:
            keys.remove(prefer_l3_group)
            keys.insert(0, prefer_l3_group)
        for k in keys:
            ordered += [c for c in groups[k] if c in core_to_cpus]
    else:
        ordered = sorted(all_cores)

    guest_cores = ordered[:guest_n]
    host_cores = [c for c in ordered if c not in guest_cores]

    vcpupin, vcpu = [], 0
    for core in guest_cores:
        for cpu in core_to_cpus[core]:        # thread 0 then its sibling
            vcpupin.append({"vcpu": vcpu, "cpuset": str(cpu), "core": core})
            vcpu += 1

    host_cpus = sorted(c for core in host_cores for c in core_to_cpus[core])
    return {
        "total_cores": total,
        "guest_cores": guest_cores,
        "host_cores": host_cores,
        "vcpus": len(vcpupin),
        "vcpupin": vcpupin,
        "emulatorpin": ",".join(str(c) for c in host_cpus[-2:]) if host_cpus else "",
        "iothreadpin": [",".join(str(c) for c in host_cpus[-4:-2])] if len(host_cpus) >= 4 else [],
        "l3_groups": {k: v for k, v in groups.items()},
    }


# --------------------------------------------------------------------- pci ---
def pci_devices():
    """All PCI devices with class, driver and IOMMU group."""
    devs = []
    for line in _run(["lspci", "-Dnnmm"]).splitlines():
        m = re.match(r'^(\S+)\s+"([^"]*)"\s+"([^"]*)"\s+"([^"]*)"', line)
        if not m:
            continue
        slot, cls, vendor, device = m.groups()
        drv = ""
        p = f"/sys/bus/pci/devices/{slot}/driver"
        if os.path.islink(p):
            drv = os.path.basename(os.path.realpath(p))
        grp = ""
        g = f"/sys/bus/pci/devices/{slot}/iommu_group"
        if os.path.islink(g):
            grp = os.path.basename(os.path.realpath(g))
        devs.append({"slot": slot, "class": cls, "vendor": vendor,
                     "device": device, "driver": drv, "iommu_group": grp})
    return devs


def pci_is_bridge(slot):
    """True if a PCI slot is a bridge (base class 0x06: host/PCI/PCIe bridges).

    This matters for IOMMU-group viability: the kernel's vfio driver explicitly
    ALLOWS a bridge to stay in a passed-through group bound to its normal driver
    (vfio_dev_driver_allowed() returns true for PCI_HEADER_TYPE_BRIDGE). So a
    root port sharing the GPU's group is fine and must NOT be treated as a device
    that has to be passed too — only the endpoint functions do.
    """
    try:
        cls = int(open(f"/sys/bus/pci/devices/{slot}/class").read().strip(), 16)
        return ((cls >> 16) & 0xff) == 0x06
    except Exception:
        return False


def gpus():
    """VGA/3D controllers plus the audio function sharing their bus:slot.

    They must be passed together: the pair normally shares an IOMMU group, so
    taking one without the other fails.
    """
    devs = pci_devices()
    out = []
    for d in devs:
        if re.search(r"VGA compatible|3D controller|Display controller", d["class"], re.I):
            base = d["slot"].rsplit(".", 1)[0]
            functions = [x for x in devs if x["slot"].startswith(base + ".")]
            out.append({**d, "functions": functions,
                        "group_members": [x["slot"] for x in devs
                                          if x["iommu_group"] and x["iommu_group"] == d["iommu_group"]]})
    return out


# ------------------------------------------------------------------ block ---
def block_device_labels():
    """Filesystem labels by device, including labels on each device's children.

    Whole disks usually have no label of their own: the names belong to their
    partitions. Keep the source paths so the UI can identify those volumes.
    """
    try:
        devices = json.loads(_run([
            "lsblk", "--json", "--paths", "--tree", "--output", "NAME,LABEL",
        ])).get("blockdevices", [])
    except (ValueError, TypeError):
        return {}

    by_device = {}

    def collect(device):
        labels = {}
        path = os.path.realpath(device["name"])
        if device.get("label"):
            labels[path] = device["label"]
        for child in device.get("children") or []:
            labels.update(collect(child))
        by_device[path] = labels
        return labels

    for device in devices or []:
        collect(device)
    return by_device


def block_devices():
    """Whole disks with their stable by-id paths."""
    out = []
    for name in sorted(os.listdir("/sys/block")):
        if re.match(r"^(loop|ram|zram|dm-|sr)", name):
            continue
        path = f"/dev/{name}"
        try:
            size = int(open(f"/sys/block/{name}/size").read()) * 512
        except Exception:
            size = 0
        model = ""
        for f in (f"/sys/block/{name}/device/model", f"/sys/block/{name}/device/name"):
            if os.path.isfile(f):
                model = open(f).read().strip()
                break
        byid = [p for p in glob.glob("/dev/disk/by-id/*")
                if os.path.realpath(p) == path and "-part" not in p]
        # Prefer the alias that names the model and serial. wwn- and nvme-eui.
        # point at the same disk but are opaque hex, so a config written with
        # one is unreadable when you come back to it a year later.
        byid.sort(key=lambda p: (("wwn-" in p or "-eui." in p), len(p)))
        out.append({"dev": path, "name": name, "size": size,
                    "size_h": _human(size), "model": model,
                    "by_id": byid, "preferred": byid[0] if byid else path,
                    "rotational": _read_int(f"/sys/block/{name}/queue/rotational")})
    return out


def _read_int(p):
    try:
        return int(open(p).read().strip())
    except Exception:
        return None


def _human(n):
    for u in ("B", "K", "M", "G", "T"):
        if n < 1024:
            return f"{n:.0f}{u}"
        n /= 1024
    return f"{n:.1f}P"


# -------------------------------------------------------------------- usb ---
def usb_devices():
    out = []
    for line in _run(["lsusb"]).splitlines():
        m = re.match(r"Bus (\d+) Device (\d+): ID ([0-9a-f]{4}):([0-9a-f]{4})\s*(.*)", line)
        if m:
            bus, dev, vid, pid, name = m.groups()
            if vid == "1d6b":         # root hubs
                continue
            out.append({"bus": bus, "device": dev, "vendor_id": vid,
                        "product_id": pid, "name": name.strip(),
                        "label": f"{vid}:{pid}  {name.strip() or 'unknown'}"})
    return out


# --------------------------------------------------------------- misc host ---
def net_bridges():
    return sorted(os.path.basename(p) for p in glob.glob("/sys/class/net/*")
                  if os.path.isdir(os.path.join(p, "bridge")))


def tpm_devices():
    return sorted(os.path.basename(p) for p in glob.glob("/dev/tpm*"))


def hugepages():
    info = {}
    for line in open("/proc/meminfo"):
        if line.startswith(("HugePages_", "Hugepagesize")):
            k, v = line.split(":", 1)
            info[k.strip()] = v.strip()
    return info


def hugepage_pools():
    """Every hugepage size the kernel actually has a pool for.

    Read from sysfs rather than assumed: /proc/meminfo only reports the default
    size, so a host with both a 2M and a 1G pool looks single-sized there.
    """
    out = {}
    for d in sorted(glob.glob("/sys/kernel/mm/hugepages/hugepages-*kB")):
        try:
            kb = int(re.search(r"hugepages-(\d+)kB", d).group(1))
        except Exception:
            continue
        out[kb * 1024] = {
            "nr": _read_int(f"{d}/nr_hugepages") or 0,
            "free": _read_int(f"{d}/free_hugepages") or 0,
            "surplus": _read_int(f"{d}/surplus_hugepages") or 0,
            "sysfs": f"{d}/nr_hugepages",
        }
    return out


def hugetlbfs_mounts():
    """Mounted hugetlbfs filesystems and the page size each was mounted with.

    A mem-path only gets the page size of the filesystem it lives on. Pointing
    a 1G-backed guest at a 2M mount silently gives it 2M pages.
    """
    out = []
    try:
        for line in open("/proc/mounts"):
            parts = line.split()
            if len(parts) < 4 or parts[2] != "hugetlbfs":
                continue
            size = None
            mm = re.search(r"pagesize=(\d+)([KMG]?)", parts[3])
            if mm:
                mult = {"": 1, "K": 1024, "M": 1024 ** 2, "G": 1024 ** 3}[mm.group(2)]
                size = int(mm.group(1)) * mult
            out.append({"mount": parts[1], "pagesize": size, "opts": parts[3]})
    except Exception:
        pass
    return out


def mount_for(path):
    """The hugetlbfs mount a mem-path would land in, if any."""
    best = None
    for mnt in hugetlbfs_mounts():
        m = mnt["mount"].rstrip("/") or "/"
        if path == m or path.startswith(m + "/"):
            if best is None or len(m) > len(best["mount"]):
                best = mnt
    return best


def ovmf_firmwares():
    seen, out = set(), []
    for pat in ("/usr/share/OVMF/**/*.fd", "/usr/share/edk2/**/*.fd",
                str(__import__("portable").component_path("ovmf") / "*.fd")):
        for p in glob.glob(pat, recursive=True):
            if "CODE" in os.path.basename(p).upper() and p not in seen:
                seen.add(p)
                out.append(p)
    return sorted(out)


def summary():
    t = cpu_topology()
    return OrderedDict([
        ("cpu", t["model"]),
        ("cores/threads", f"{t['cores']}/{t['threads']} smt={t['smt']}"),
        ("l3 groups", {k: v for k, v in t["l3_to_cores"].items()}),
        ("gpus", [f"{g['slot']} {g['device']}" for g in gpus()]),
        ("disks", len(block_devices())),
        ("usb", len(usb_devices())),
        ("bridges", net_bridges()),
        ("tpm", tpm_devices()),
    ])


if __name__ == "__main__":
    print(json.dumps(summary(), indent=2))
