"""Explicit additional devices for Dual GPU; discovery never detaches hardware."""

from pathlib import Path
import os
import re

import gpu_inventory as gi
import hostinfo
import input_devices


def _under(path, root):
    return path.resolve().is_relative_to(root.resolve())


def pci_supported(slot):
    cls = gi.pci_class(slot)
    # Storage/system controllers and graphics stay out of this desktop mode.
    return cls >> 16 in (2, 4, 7) or cls >> 8 == 0x0c03


def discover_pci():
    return [dict(slot=d["slot"], identity=gi.identity(d["slot"]),
                 name=d["device"], group=gi.group(d["slot"]),
                 kind=d["class"], driver=gi.driver(d["slot"]))
            for d in hostinfo.pci_devices() if pci_supported(d["slot"])]


def inspect_usb(port):
    if not re.fullmatch(r"\d+-\d+(?:\.\d+)*", str(port)):
        raise ValueError("Choose a physical USB device, not a root hub")
    path = gi.SYS / "bus/usb/devices" / port
    identity = {key: gi.read(path / key) for key in ("idVendor", "idProduct", "serial")}
    if not all(re.fullmatch(r"[0-9a-fA-F]{4}", identity[k]) for k in ("idVendor", "idProduct")):
        raise ValueError(f"USB device {port} is disconnected; refresh devices")
    return dict(port=port, identity=identity,
                name=gi.read(path / "product") or f"{identity['idVendor']}:{identity['idProduct']}",
                hub=gi.read(path / "bDeviceClass") == "09",
                hostbus=int(gi.read(path / "busnum")), hostaddr=int(gi.read(path / "devnum")),
                hostport=port.split("-", 1)[1])


def discover_usb():
    result = []
    for path in sorted((gi.SYS / "bus/usb/devices").glob("*")):
        if not re.fullmatch(r"\d+-\d+(?:\.\d+)*", path.name):
            continue
        try:
            result.append(inspect_usb(path.name))
        except (OSError, ValueError):
            continue
    return result


def _usb_node(device):
    return gi.DEV / f"bus/usb/{device['hostbus']:03}/{device['hostaddr']:03}"


def _open_users(nodes):
    names = {str(p.resolve()) for p in nodes}
    if not names:
        return [], True
    users, complete = [], True
    for proc in gi.PROC.glob("[0-9]*"):
        try:
            targets = []
            for fd in (proc / "fd").iterdir():
                try:
                    targets.append(os.readlink(fd).removesuffix(" (deleted)"))
                except (FileNotFoundError, ProcessLookupError):
                    continue
            targets.extend(line.split(None, 5)[5].removesuffix(" (deleted)")
                           for line in (proc / "maps").read_text().splitlines()
                           if len(line.split(None, 5)) == 6)
            if any(str(Path(p).resolve()) in names for p in targets if p.startswith("/")):
                users.append(f"{gi.read(proc / 'comm', 'process')} (PID {proc.name})")
        except (FileNotFoundError, ProcessLookupError):
            continue
        except OSError:
            if proc.exists():
                complete = False
    return users, complete


def _host_use(roots, inputs, strict):
    """Protect mounted storage, live networking and the selected evdev devices."""
    for dev in inputs:
        entry = input_devices.SYS / Path(dev["node"]).name / "device"
        if any(_under(entry, root) for root in roots):
            raise ValueError(f"{dev['name']} is selected for evdev and physical passthrough; choose one input method")
    for net in (gi.SYS / "class/net").glob("*"):
        if any(_under(net / "device", root) for root in roots):
            try:
                up = int((net / "flags").read_text().strip(), 16) & 1
            except (OSError, ValueError):
                up = True
            if up:
                raise ValueError(f"Linux network interface {net.name} is active; disconnect it before passthrough")
    disks = [d for d in (gi.SYS / "class/block").glob("*")
             if any(_under(d, root) for root in roots)]
    if not disks:
        return []
    numbers = {gi.read(d / "dev") for d in disks}
    processes = [gi.PROC / "self"]
    if strict:
        processes += list(gi.PROC.glob("[0-9]*"))
    for proc in processes:
        try:
            mounts = (proc / "mountinfo").read_text().splitlines()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise ValueError("Cannot verify storage mounts before passthrough") from exc
        if any(len(line.split()) > 2 and line.split()[2] in numbers for line in mounts):
            raise ValueError("Selected device contains mounted Linux storage; unmount it first")
    swaps = gi.read(gi.PROC / "swaps")
    for disk in disks:
        if list((disk / "holders").glob("*")) or str(gi.DEV / disk.name) in swaps:
            raise ValueError(f"{disk.name} is used by Linux swap or another block device")
    return [gi.DEV / disk.name for disk in disks]


def selection(opts, gpu, inputs=(), strict=False):
    pci, usb = [], []
    selected = opts.get("pci_devices", [])
    slots = [d.get("slot", "") for d in selected]
    if len(slots) != len(set(slots)):
        raise ValueError("A PCI device is selected more than once")
    allowed = set(slots) | set(gpu["functions"])
    for item, slot in zip(selected, slots):
        if not re.fullmatch(r"[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]", slot):
            raise ValueError("Invalid additional PCI address")
        if slot in gpu["functions"]:
            raise ValueError(f"{slot} is already selected in Guest GPU")
        if not pci_supported(slot):
            raise ValueError(f"{slot}: choose audio, USB, an unused network card, or a serial controller")
        identity, group = gi.identity(slot), gi.group(slot)
        if not item.get("identity") or identity != item["identity"] or not all(identity.values()):
            raise ValueError(f"{slot}: PCI identity changed; refresh and select the device again")
        members = gi.group_members(slot)
        if not group or not members:
            raise ValueError(f"{slot}: no usable IOMMU group")
        missing = [s for s in members if s not in allowed and gi.pci_class(s) >> 16 != 6]
        if missing:
            raise ValueError(f"{slot}: IOMMU group also needs {', '.join(missing)}; select every endpoint in that group")
        root = gi.PCI / slot
        nodes = _host_use([root], inputs, strict)
        # Include USB children of a selected controller in ownership checks.
        nodes += [_usb_node(d) for d in discover_usb()
                  if _under(gi.SYS / 'bus/usb/devices' / d['port'], root)]
        users, complete = gi.device_users([slot])
        if gi.pci_class(slot) >> 16 == 4:
            # An explicitly selected sound card can leave the sound server.
            # ALSA disconnects these handles on driver removal; never kill it.
            users = [u for u in users if not re.fullmatch(r"(?:wireplumber|pipewire|pulseaudio) \(PID \d+\)", u)]
        other, inspected = _open_users(nodes)
        if users or other:
            raise ValueError(f"{slot}: in use by " + ", ".join((users + other)[:4]))
        if strict and not (complete and inspected):
            raise ValueError(f"{slot}: cannot inspect all device users")
        pci.append(dict(slot=slot, identity=identity, group=group))
    for item in opts.get("usb_devices", []):
        dev = inspect_usb(item.get("port", ""))
        if dev["hub"]:
            raise ValueError("Select USB devices individually, or pass their entire PCI USB controller")
        if dev["identity"] != item.get("identity"):
            raise ValueError(f"USB {dev['port']}: device identity changed; refresh and select it again")
        if any(d["port"] == dev["port"] for d in usb):
            raise ValueError("A USB device is selected more than once")
        root = gi.SYS / "bus/usb/devices" / dev["port"]
        if any(_under(root, gi.PCI / slot) for slot in slots):
            raise ValueError(f"USB {dev['port']} is already included by its selected PCI controller")
        nodes = _host_use([root], inputs, strict) + [_usb_node(dev)]
        users, complete = _open_users(nodes)
        if users:
            raise ValueError(f"USB {dev['port']}: in use by " + ", ".join(users[:4]))
        if strict and not complete:
            raise ValueError(f"USB {dev['port']}: cannot inspect all device users")
        usb.append(dev)
    return dict(pci=pci, usb=usb)


def usb_properties(dev):
    return dict(hostbus=dev["hostbus"], hostport=dev["hostport"],
                vendorid=int(dev["identity"]["idVendor"], 16),
                productid=int(dev["identity"]["idProduct"], 16))


def verify_plan(plan, strict=False):
    actual = selection(plan["options"], plan["gpu"], plan.get("input_devices", []), strict)
    if actual != plan.get("extra_devices", dict(pci=[], usb=[])):
        raise RuntimeError("USB/PCI devices changed since launch was prepared; refresh devices")
    devices = [d for d in plan["config"]["devices"] if d.get("driver") == "usb-host" and not d.get("_disabled")]
    expected = [usb_properties(d) for d in actual["usb"]]
    properties = [{k: v for k, v in d.items() if k not in ("driver", "id", "bus")} for d in devices]
    if properties != expected:
        raise RuntimeError("The launch plan includes unexpected USB passthrough devices")
    return actual
