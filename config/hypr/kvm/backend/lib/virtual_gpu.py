"""Virtual-display launch plans. The shared VM configuration is never modified.

This path deliberately does not call the single-GPU script generators. It uses
the same systemd unit to prevent the two launch modes opening the same VM twice.
"""

import copy
import errno
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid

import launcher
import console_window
import ovmf_display
import smbios
from model import VMConfig

UNIT = "vmstart2-vm"
MODELS = {
    "VGA": ("Standard VGA", "Broad guest compatibility; a good starting point."),
    "bochs-display": ("Bochs (UEFI)", "Simple framebuffer for UEFI guests; not for legacy BIOS."),
    "qxl-vga": ("QXL", "Designed for SPICE; guest QXL drivers improve the desktop experience."),
    "virtio-vga": ("VirtIO VGA (2D)", "Best with guest VirtIO GPU drivers, commonly available on Linux."),
}
GRAPHICS = set(MODELS) | {"qxl", "virtio-gpu-pci", "virtio-vga-gl", "virtio-gpu-gl-pci",
                         "cirrus-vga", "vmware-svga", "secondary-vga", "ati-vga", "ramfb"}


def mac_input_controller(cfg):
    return "xhci" if cfg.data.get("_meta", {}).get("macos_release") == "tahoe" else "ehci"


def options(cfg):
    defaults = dict(model="VGA", server="vnc", port=5901, width=1600, height=900,
                    auto_open=True, floating=True, remember_console_size=True, input=True, clipboard=False, file_transfer=False,
                    audio=False, keep_usb=False, keep_pci=False, memory="preset",
                    network="preset", pinning=True, realtime=False, uefi_resolution=True,
                    input_controller=mac_input_controller(cfg) if cfg.profile == "macos" else "xhci",
                    guest_os=cfg.profile)
    defaults.update(cfg.data.get("virtual_gpu") or {})
    return defaults


def _spec(raw, positional="type"):
    """Read the JSON or key=value notation accepted by this app's model."""
    if not raw:
        return {}
    if raw.lstrip().startswith("{"):
        return json.loads(raw)
    # QEMU doubles commas inside values. Preserve them through the split.
    parts = raw.replace(",,", "\0").split(",")
    out = {}
    for i, part in enumerate(parts):
        part = part.replace("\0", ",")
        if "=" in part:
            k, v = part.split("=", 1)
            out[k] = v
        elif i == 0:
            out[positional] = part
        else:
            out[part] = "on"
    return out


def _flag(cfg, key, value):
    cfg.simple[key] = value
    if [key, None] not in [list(e) for e in cfg.data.setdefault("order", [])]:
        cfg.data["order"].append([key, None])


def _drop(cfg, *keys):
    for key in keys:
        cfg.simple.pop(key, None)
    cfg.data["order"] = [e for e in cfg.data.get("order", []) if not (e[1] is None and e[0] in keys)]


def _slot(host):
    host = str(host or "").lower()
    if re.fullmatch(r"[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]", host):
        host = "0000:" + host
    if not re.fullmatch(r"[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]", host):
        raise ValueError(f"Cannot identify PCI address {host!r} for Virtual GPU mode")
    return host


def pci_class(slot):
    try:
        return int(Path(f"/sys/bus/pci/devices/{slot}/class").read_text().strip(), 16) >> 16
    except (OSError, ValueError):
        return None


def display_properties(opts):
    """Advertise the preferred mode and provide enough 32-bit framebuffer RAM."""
    width, height = int(opts["width"]), int(opts["height"])
    props = dict(xres=width, yres=height)
    required_mb = (width * height * 4 + 1024**2 - 1) // 1024**2
    video_mb = max(16, 1 << (required_mb - 1).bit_length())
    if opts["model"] == "qxl-vga":
        # QXL's primary surface and its command storage share the RAM BAR.
        props.update(vgamem_mb=max(32, video_mb), ram_size_mb=max(64, video_mb * 2),
                     vram_size_mb=max(64, video_mb * 2))
    else:
        props["edid"] = True
        if opts["model"] == "VGA":
            props["vgamem_mb"] = video_mb
        elif opts["model"] == "bochs-display":
            props["vgamem"] = video_mb * 1024**2
    return props


def resolution_note(opts):
    if opts.get("guest_os") == "macos":
        return ("Standard VGA provides the Mac console without Metal acceleration. "
                "The preferred size is a request; macOS chooses its display mode. "
                "UEFI display changes use this Mac profile's own NVRAM.")
    note = "The preferred mode applies at the next boot; the guest selects its actual resolution. "
    if opts["model"] in ("VGA", "bochs-display"):
        return note + ("Apply preferred size to UEFI updates its saved display mode for Windows Basic Display. "
                       "For an adjustable Windows desktop, use SPICE + QXL and install the guest tools.")
    if opts["server"] == "spice":
        return note + ("Install the guest display driver and SPICE agent to resize with the console window. "
                       "Select an exact size in the guest's Display settings; viewer auto-resize can override it.")
    return note + "Install the guest display driver and select the size in the guest's Display settings."


def firmware_display_plan(vm, opts):
    if not opts["uefi_resolution"] or opts["model"] not in ("VGA", "bochs-display"):
        return None
    node = vm.data.get("machine", {}).get("opts", {}).get("pflash1")
    if not node:
        return None
    nodes = {d.get("node-name"): d for d in vm.blockdevs if not d.get("_disabled")}
    seen = set()
    while isinstance(node, str) and node not in seen:
        seen.add(node)
        item = nodes.get(node, {})
        if item.get("read-only") in (True, "on"):
            break
        if item.get("driver") == "file" and item.get("filename"):
            return dict(path=item["filename"], width=int(opts["width"]), height=int(opts["height"]))
        if item.get("driver") != "raw":
            break
        node = item.get("file")
    raise ValueError("Cannot locate a writable raw UEFI variable file; disable Apply preferred size to UEFI")


def prepare(cfg, settings=None, workdir="/tmp/vmstart2-virtual-preview", token="preview"):
    """Return a self-contained runtime plan using a deep copy of the preset."""
    opts = options(cfg)
    opts.update(settings or {})
    if opts["model"] not in MODELS or opts["server"] not in ("spice", "vnc"):
        raise ValueError("Choose a supported virtual graphics card and console server")
    port = int(opts["port"])
    if not 1024 <= port <= 65535 or (opts["server"] == "vnc" and port < 5900):
        raise ValueError("Use a port from 1024–65535 (5900–65535 for VNC)")
    if not (640 <= int(opts["width"]) <= 4096 and 480 <= int(opts["height"]) <= 4096):
        raise ValueError("Display width must be 640–4096 and height 480–4096 pixels")
    if opts["memory"] not in ("preset", "ordinary") or opts["network"] not in ("preset", "user", "off"):
        raise ValueError("Unknown virtual memory or networking option")
    if opts["input_controller"] not in ("xhci", "ehci"):
        raise ValueError("Choose a USB 2 EHCI or USB 3 XHCI input controller")

    vm = VMConfig(copy.deepcopy(cfg.data))
    vm.sync()
    removed = []
    # Normalise raw device entries before making decisions about passthrough.
    for dev in vm.devices:
        if dev.get("_raw") and not dev.get("_disabled"):
            parsed = _spec(dev["_raw"], "driver")
            dev.update(parsed)
            dev.pop("_raw", None)
    pci = [d for d in vm.devices if d.get("driver") == "vfio-pci" and not d.get("_disabled")]
    classes = {_slot(d.get("host")): pci_class(_slot(d.get("host"))) for d in pci}
    gpu_bases = {s.rsplit(".", 1)[0] for s, cls in classes.items() if cls == 3}
    for base in {s.rsplit(".", 1)[0] for s in classes}:
        if any(pci_class(f"{base}.{n}") == 3 for n in range(8)):
            gpu_bases.add(base)
    gpu_bases.update(_slot(d["host"]).rsplit(".", 1)[0] for d in pci
                     if d.get("romfile") and classes[_slot(d["host"])] is None)
    gpu_location = {}
    for dev in vm.devices:
        if dev.get("_disabled"):
            continue
        driver = dev.get("driver", "")
        omit = driver in GRAPHICS
        if driver == "vfio-pci":
            slot = _slot(dev.get("host"))
            is_gpu = slot.rsplit(".", 1)[0] in gpu_bases
            if opts["keep_pci"] and not is_gpu and classes[slot] is None:
                raise ValueError(f"Cannot classify PCI device {slot}; disable non-GPU PCI passthrough or reconnect it")
            omit = is_gpu or not opts["keep_pci"]
            if classes[slot] == 3 and not gpu_location:
                gpu_location = {k: dev[k] for k in ("bus", "addr") if k in dev}
        if driver == "usb-host" and not opts["keep_usb"]:
            omit = True
        if omit:
            dev["_disabled"] = True
            removed.append(dev.get("id", driver))

    for c in vm.data.get("chardevs", []):
        if c.get("_raw"):
            c.setdefault("id", _spec(c["_raw"]).get("id"))
    used = {d.get("id") for d in vm.devices + vm.objects + vm.data.get("chardevs", [])}

    def fresh(base):
        name, n = base, 1
        while name in used:
            name = f"{base}{n}"
            n += 1
        used.add(name)
        return name

    def device(driver, **fields):
        item = dict(driver=driver, **fields)
        vm.devices.append(item)
        return item

    monitor = _spec(vm.simple.get("mon", "")).get("chardev")
    old_agents = {d["chardev"] for d in vm.devices if d.get("name") == "com.redhat.spice.0" and d.get("chardev")}
    for c in vm.data.get("chardevs", []):
        if (monitor and c.get("id") == monitor) or c.get("id") in old_agents or "spicevmc" in c.get("_raw", ""):
            c["_disabled"] = True
            for d in vm.devices:
                if d.get("chardev") == c.get("id"):
                    d["_disabled"] = True
    for d in vm.devices:
        if d.get("name") == "com.redhat.spice.0":
            d["_disabled"] = True
    # External config files can introduce another GPU, inherited monitor, or a
    # network helper behind our back. Ask for those settings in the editor.
    for flag in ("readconfig", "net", "nic", "add-fd", "run-with"):
        if flag in vm.simple:
            raise ValueError(f"Virtual GPU mode cannot supervise -{flag}; use the structured device/network settings")
    _drop(vm, "display", "vga", "spice", "vnc", "nographic", "qmp", "qmp-pretty",
          "mon", "monitor", "daemonize", "pidfile", "S", "no-shutdown", "no-reboot", "incoming")
    _flag(vm, "display", "none")
    _flag(vm, "vga", "none")
    _flag(vm, "qmp", f"unix:{workdir}/qmp.sock,server=on,wait=off")
    device(opts["model"], id=fresh("virtual-display"), **display_properties(opts), **gpu_location)
    agent_chardev = None
    if opts["server"] == "spice":
        _flag(vm, "spice", f"addr=127.0.0.1,port={port},disable-ticketing=on,"
              f"disable-copy-paste={'off' if opts['clipboard'] else 'on'},"
              f"disable-agent-file-xfer={'off' if opts['file_transfer'] else 'on'}")
        # Resizing and pointer integration need this channel even when sharing
        # is disabled. The server's two policy flags still control sharing.
        serial = next((d for d in vm.devices if d.get("driver") in ("virtio-serial-pci", "virtio-serial")
                       and not d.get("_disabled") and d.get("id")), None)
        if not serial:
            serial = device("virtio-serial-pci", id=fresh("virtual-serial"))
        agent_chardev = fresh("virtual-agent")
        vm.data.setdefault("chardevs", []).append({"id": agent_chardev,
            "_raw": f"spicevmc,id={agent_chardev},name=vdagent"})
        device("virtserialport", id=fresh("virtual-agent-port"), bus=serial["id"] + ".0",
               chardev=agent_chardev, name="com.redhat.spice.0")
        if opts["audio"]:
            # Reuse any existing virtual sound devices and audio backend id.
            audio = _spec(vm.simple.get("audiodev", ""), "driver")
            audio_id = audio.get("id") or fresh("virtual-audio")
            _flag(vm, "audiodev", json.dumps({"driver": "spice", "id": audio_id}))
            if not any(d.get("audiodev") == audio_id and not d.get("_disabled") for d in vm.devices):
                hda = device("ich9-intel-hda", id=fresh("virtual-hda"))
                device("hda-output", id=fresh("virtual-sound"), bus=hda["id"] + ".0", audiodev=audio_id)
    else:
        _flag(vm, "vnc", f"127.0.0.1:{port - 5900}")
    if opts["input"]:
        controllers = ("usb-ehci", "ich9-usb-ehci1") if opts["input_controller"] == "ehci" else ("qemu-xhci", "nec-usb-xhci")
        usb = next((d for d in vm.devices if d.get("driver") in controllers
                    and not d.get("_disabled") and d.get("id")), None)
        if not usb:
            usb = device(controllers[0], id=fresh("virtual-usb"))
        for driver in ("usb-kbd", "usb-tablet"):
            existing = [d for d in vm.devices if d.get("driver") == driver and not d.get("_disabled")]
            if existing:
                for dev in existing:
                    if dev.get("bus") != usb["id"] + ".0":
                        dev["bus"] = usb["id"] + ".0"
                        dev.pop("port", None)
            else:
                device(driver, id=fresh("virtual-" + driver), bus=usb["id"] + ".0")

    tap = None
    net = _spec(vm.simple.get("netdev", ""))
    if opts["network"] == "off":
        _drop(vm, "netdev")
        for d in vm.devices:
            if d.get("netdev"):
                d["_disabled"] = True
    elif net:
        if opts["network"] == "user":
            net = dict(type="user", id=net.get("id", "hostnet0"))
        elif net.get("type") in ("tap", "bridge"):
            name = "v2v" + re.sub(r"[^a-z0-9]", "", token.lower())[:11]
            bridge = net.get("br") or vm.network.get("bridge", "")
            tap = dict(name=name, bridge=bridge)
            for key in ("fd", "fds", "vhostfd", "vhostfds", "br", "helper"):
                net.pop(key, None)
            net.update(type="tap", ifname=name, script="no", downscript="no")
        elif net.get("type") not in ("user", "socket", "stream", "dgram"):
            raise ValueError(f"Unsupported virtual-mode network backend: {net.get('type')}")
        _flag(vm, "netdev", json.dumps(net))

    huge = None
    ram = next((o for o in vm.objects if o.get("id") == "pc.ram" and not o.get("_disabled")), None)
    if ram:
        if opts["memory"] == "ordinary":
            ram.pop("_raw", None)
            ram["qom-type"] = "memory-backend-ram"
            for key in ("mem-path", "align", "offset", "pmem", "readonly", "rom", "discard-data",
                        "hugetlb", "hugetlbsize", "seal"):
                ram.pop(key, None)
        else:
            pages, size, pool = launcher._hugepages(vm)
            if pages:
                pages = (int(ram["size"]) + size - 1) // size
                huge = dict(pages=pages, size=size, pool=pool, mount=f"{workdir}/memory")
                if vm.profile == "macos":
                    huge["mount"] = ram.get("mem-path", "")
                if ram.get("qom-type") == "memory-backend-file":
                    ram.pop("_raw", None)
                    ram["mem-path"] = huge["mount"]

    tpm = launcher._tpm(vm)
    if tpm:
        old = tpm["sock"]
        tpm["original_sock"] = old
        tpm["sock"] = f"{workdir}/tpm.sock"
        for char in vm.data.get("chardevs", []):
            if char.get("path") == old and not char.get("_disabled"):
                char["path"] = tpm["sock"]
                char["_raw"] = f"socket,id={char['id']},path={tpm['sock']}"

    # Appended chardevs/objects must precede their device consumers. Compact
    # also removes every disabled entry from recorded emission order.
    vm.compact()
    order = vm.data["order"]
    for bucket, items in (("chardev", vm.data.get("chardevs", [])), ("object", vm.objects)):
        order[:] = [e for e in order if e[0] != bucket]
        order[:0] = [[bucket, i] for i in range(len(items))]
    return dict(config=vm.data, options=opts, argv=vm.to_argv(True) + ["-S"], removed=removed,
                workdir=workdir, qmp=f"{workdir}/qmp.sock", agent_chardev=agent_chardev,
                tap=tap, huge=huge, tpm=tpm, firmware_display=firmware_display_plan(vm, opts),
                pinning=copy.deepcopy(vm.data.get("pinning", {})) if opts["pinning"] else {},
                iothreads=launcher.iothread_ids(vm), uid=os.getuid(), gid=os.getgid())


@lru_cache(maxsize=8)
def _capabilities(binary, stamp):
    devices = subprocess.run([binary, "-device", "help"], capture_output=True, text=True, timeout=10)
    helptext = subprocess.run([binary, "-help"], capture_output=True, text=True, timeout=10)
    return {"devices": set(re.findall(r'name "([^"]+)"', devices.stdout + devices.stderr)),
            "spice": "-spice " in helptext.stdout, "vnc": "-vnc " in helptext.stdout}


def capabilities(binary):
    return _capabilities(binary, os.stat(binary).st_mtime_ns)


@lru_cache(maxsize=8)
def _guest_device_ids(binary, stamp):
    """Inspect a paused, diskless machine; patched QEMU can change PCI IDs."""
    drivers = capabilities(binary)["devices"] & {"qxl-vga", "virtio-serial-pci", "bochs-display"}
    argv = [binary, "-machine", "q35,accel=tcg", "-m", "64M", "-nodefaults",
            "-display", "none", "-S", "-qmp", "stdio"]
    # QXL must be console zero when probing alongside another display.
    for driver in sorted(drivers, key=lambda driver: (driver != "qxl-vga", driver)):
        argv += ["-device", f"{driver},id={driver}"]
    commands = [{"execute": c, "id": c} for c in ("qmp_capabilities", "query-pci", "quit")]
    result = subprocess.run(argv, input="\n".join(json.dumps(c) for c in commands) + "\n",
                            capture_output=True, text=True, timeout=10)
    for line in result.stdout.splitlines():
        try:
            reply = json.loads(line)
        except ValueError:
            continue
        if reply.get("id") == "query-pci" and "return" in reply:
            return {d["qdev_id"]: d["id"] for bus in reply["return"] for d in bus.get("devices", [])
                    if d.get("qdev_id") in drivers}
    raise RuntimeError("Could not inspect virtual device PCI IDs")


def guest_device_ids(binary):
    return _guest_device_ids(binary, os.stat(binary).st_mtime_ns)


def service_active():
    try:
        r = subprocess.run(["systemctl", "show", UNIT, "--property=ActiveState", "--value"],
                           capture_output=True, text=True, timeout=5)
        return r.stdout.strip() in ("active", "activating", "deactivating", "reloading")
    except (OSError, subprocess.TimeoutExpired):
        return False


def probe_console_port(port):
    """Match QEMU's reusable listener without rejecting TCP TIME_WAIT sockets."""
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(("127.0.0.1", int(port)))
        # Still reject a live listener (including a wildcard listener). This
        # never uses SO_REUSEPORT, which could share another server's port.
        probe.listen(1)


def preflight(plan):
    vm = VMConfig(plan["config"])
    out = vm.validate()
    opts, binary = plan["options"], plan["argv"][0]
    try:
        caps = capabilities(binary)
        for driver in {d["driver"] for d in vm.devices if d.get("driver") in GRAPHICS | {
                "qemu-xhci", "nec-usb-xhci", "usb-ehci", "isa-applesmc", "usb-kbd", "usb-tablet", "ich9-intel-hda", "hda-output", "virtserialport", "virtio-serial-pci"}}:
            if driver not in caps["devices"]:
                out.append(("error", f"This QEMU build has no {driver} device"))
        if not caps[opts["server"]]:
            out.append(("error", f"This QEMU build has no {opts['server'].upper()} server"))
    except (OSError, subprocess.SubprocessError) as exc:
        out.append(("error", f"Cannot inspect QEMU: {exc}"))
    if service_active():
        out.append(("error", "A VM is already running or stopping. Shut it down before changing launch mode."))
    try:
        probe_console_port(opts["port"])
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            out.append(("error", f"Console port {opts['port']} has an active listener; close it or choose another port"))
        else:
            out.append(("error", f"Cannot check console port {opts['port']}: {exc}"))
    for dev in vm.devices:
        if dev.get("driver") == "vfio-pci":
            slot = _slot(dev["host"])
            driver = os.path.basename(os.path.realpath(f"/sys/bus/pci/devices/{slot}/driver"))
            if driver != "vfio-pci":
                out.append(("error", f"PCI {slot} is using {driver}. Virtual mode never rebinds host devices; "
                            "disable non-GPU PCI passthrough or prepare it separately."))
    if plan["tap"]:
        br = plan["tap"]["bridge"]
        if br and not os.path.isdir(f"/sys/class/net/{br}/bridge"):
            out.append(("error", f"Bridge {br} is unavailable; select User networking (NAT) or configure the bridge"))
    if plan["huge"]:
        if plan["config"].get("_meta", {}).get("profile") == "macos":
            out.extend(launcher.mac_memory.checks(plan["config"]))
        elif not os.path.isfile(plan["huge"]["pool"]):
            out.append(("error", "The preset's hugepage pool is unavailable; choose ordinary RAM or configure hugepages"))
        else:
            out.append(("ok", "Preset hugepages will be allocated without stopping the desktop; allocation failure stops this launch"))
    if plan.get("firmware_display"):
        if not ovmf_display.available():
            out.append(("error", "Install virt-firmware to update the UEFI display preference, "
                        "or disable Apply preferred size to UEFI and select the resolution in firmware setup."))
        else:
            out.append(("ok", "The saved OVMF display preference will use the requested size. "
                        "This is shared with Single GPU; a firmware backup is saved before any change."))
    if plan["tpm"]:
        tpm = plan["tpm"]
        if not os.path.isfile(tpm["binary"]) or not os.access(tpm["binary"], os.X_OK):
            out.append(("error", f"swtpm is not executable: {tpm['binary']}"))
        if not tpm["state"]:
            out.append(("error", "Set the existing swtpm state directory in Paths & tools"))
    elif "emulator" in vm.simple.get("tpmdev", ""):
        out.append(("error", "The TPM emulator has no usable socket configuration"))
    for key in ("bios", "kernel", "initrd"):
        if vm.simple.get(key) and not os.path.isfile(vm.simple[key]):
            out.append(("error", f"Missing {key}: {vm.simple[key]}"))
    blob = smbios.blob_path(vm.simple.get("smbios", ""))
    if blob is not None and not os.path.isfile(blob):
        out.append(("error", f"Missing smbios file: {blob}"))
    for key in ("drive",):
        raw = vm.simple.get(key, "")
        match = re.search(r"(?:^|,)file=([^,]+)", raw)
        if match and not os.path.exists(match.group(1)):
            out.append(("error", f"Missing {key} file: {match.group(1)}"))
    if opts["model"] == "bochs-display":
        out.append(("warn", "Bochs requires UEFI firmware; choose Standard VGA for legacy BIOS guests"))
    if opts["keep_usb"] or opts["keep_pci"]:
        out.append(("warn", "Enabled physical passthrough devices will be unavailable to Linux while the guest uses them"))
    if not viewer_command(opts):
        name = "remote-viewer (virt-viewer) or spicy (spice-gtk)" if opts["server"] == "spice" else "vncviewer or remote-viewer"
        out.append(("warn", f"No {name} installed; install a viewer or connect another local client"))
    if opts["server"] == "vnc" and any(opts[k] for k in ("clipboard", "file_transfer", "audio")):
        out.append(("warn", "SPICE features are selected but this launch uses VNC. Choose SPICE server to use them."))
    if opts["server"] == "spice":
        try:
            ids = guest_device_ids(binary)
            expected = {"virtio-serial-pci": 0x1af4}
            if opts["model"] == "qxl-vga":
                expected["qxl-vga"] = 0x1b36
            for driver, vendor in expected.items():
                actual = ids.get(driver, {}).get("vendor")
                if actual is not None and actual != vendor:
                    out.append(("warn", f"This QEMU reports {driver} vendor {actual:04x}, but standard guest drivers "
                                f"expect {vendor:04x}. SPICE guest tools alone cannot fix this mismatch; "
                                "use a build with compatible virtual-device PCI IDs or matching guest drivers."))
        except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
            out.append(("warn", f"Cannot verify SPICE device driver compatibility: {exc}"))
        out.append(("warn", "SPICE clipboard, file transfer and resizing require guest tools inside the VM "
                    "(Windows: SPICE agent + VirtIO Serial + QXL display driver; Linux: spice-vdagent + display driver)."))
    out.append(("warn", resolution_note(opts)))
    out.append(("ok", "Virtual display on localhost; start and revert scripts are skipped"))
    return out


def viewer_command(opts):
    port = int(opts["port"])
    if opts["server"] == "vnc" and shutil.which("vncviewer"):
        return [shutil.which("vncviewer"), f"127.0.0.1::{port}"]
    if shutil.which("remote-viewer"):
        return [shutil.which("remote-viewer"), f"{opts['server']}://127.0.0.1:{port}"]
    if opts["server"] == "spice" and shutil.which("spicy"):
        return [shutil.which("spicy"), "--host=127.0.0.1", f"--port={port}"]
    return None


def open_viewer(opts, remember_size=False):
    cmd = viewer_command(opts)
    if not cmd:
        raise RuntimeError("Install virt-viewer (remote-viewer) or spice-gtk (spicy) for SPICE; "
                           "use vncviewer / remote-viewer for VNC")
    viewer = console_window.launch(cmd, floating=opts.get('floating', True))
    if remember_size and viewer is not None:
        try:
            console_window.observe(viewer.pid, Path(launcher.RUN_DIR) / f"virtual-console-{Path(cmd[0]).name}.json")
        except OSError:
            pass  # Remembering the size is optional; the console is already open.


def current_path():
    return Path(launcher.RUN_DIR) / "virtual-current.json"


def current_run():
    try:
        return json.loads(current_path().read_text())
    except (OSError, ValueError):
        return {}


def status(run=None):
    run = current_run() if run is None else run
    try:
        return json.loads((Path(run["workdir"]) / "status.json").read_text())
    except (KeyError, OSError, ValueError):
        pass
    if not run.get("workdir"):
        return {}
    try:
        submitted = (Path(run["workdir"]) / "plan.json").stat().st_mtime
    except OSError:
        return dict(state="failed", message="The previous launch files are no longer available. Launch again to create a new run.")
    # A service can fail before Python creates status.json (for example, an
    # import error). Never leave the desktop waiting indefinitely in that case.
    if time.time() - submitted < 20:
        return dict(state="pending", message="Starting the VM supervisor…")
    if service_active():
        return dict(state="pending", message="The launch service has not reported progress. Check the launch output below.")
    return dict(state="failed", message="Launch failed before the VM supervisor reported readiness. See the launch output below.")


def runtime_log_properties(workdir):
    # Capture interpreter/import errors too, before the runtime redirects its
    # own output. The submitting user already owns this private log file.
    log = str(Path(workdir) / "output.log").replace('%', '%%')
    return [f"--property=StandardOutput=append:{log}", f"--property=StandardError=append:{log}"]


def read_log(run):
    try:
        with open(Path(run["workdir"]) / "output.log", "rb") as handle:
            handle.seek(0, 2)
            handle.seek(max(0, handle.tell() - 160000))
            return handle.read().decode(errors="replace")
    except (KeyError, OSError):
        return ""


def launch(cfg):
    """Submit an isolated snapshot; no start/revert hooks are read or written."""
    if service_active():
        raise RuntimeError("A VM is already running or stopping")
    workdir = tempfile.mkdtemp(prefix="vmstart2-virtual-")
    plan = prepare(cfg, workdir=workdir, token=uuid.uuid4().hex)
    payload = Path(workdir) / "plan.json"
    payload.write_text(json.dumps(plan, indent=2))
    payload.chmod(0o600)
    (Path(workdir) / "output.log").touch(mode=0o600)
    runtime = str(Path(__file__).with_name("virtual_runtime.py"))
    # Exactly the same unit as Single GPU: systemd atomically rejects another
    # launch before either runtime can touch disks, TPM state, or host devices.
    prefix = [] if os.geteuid() == 0 else ["sudo", "-n"]
    subprocess.run(prefix + ["systemctl", "reset-failed", UNIT], capture_output=True, timeout=10)
    result = subprocess.run(prefix + ["systemd-run", "--unit", UNIT,
                            "--description=vmstart_2 virtual GPU guest", "--property=KillMode=mixed",
                            "--property=TimeoutStopSec=120", "--service-type=exec", *runtime_log_properties(workdir),
                            sys.executable, runtime, str(payload)],
                            capture_output=True, text=True, timeout=20)
    if result.returncode:
        raise RuntimeError((result.stdout + result.stderr).strip() or "systemd-run failed")
    run = dict(workdir=workdir, options=plan["options"], qmp=plan["qmp"], agent_chardev=plan["agent_chardev"])
    current_path().parent.mkdir(parents=True, exist_ok=True)
    current_path().write_text(json.dumps(run))
    return run


class QMP:
    """Small synchronous QMP client used by the runtime and desktop controls."""
    def __init__(self, path, timeout=2):
        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.settimeout(timeout)
        try:
            self.sock.connect(path)
            self.file = self.sock.makefile("rwb")
            greeting = self._read()
            if "QMP" not in greeting:
                raise RuntimeError("Invalid QMP greeting")
            self.execute("qmp_capabilities")
        except Exception:
            self.close()
            raise

    def _read(self):
        line = self.file.readline()
        if not line:
            raise RuntimeError("QEMU closed its monitor")
        return json.loads(line)

    def execute(self, command):
        self.file.write(json.dumps({"execute": command, "id": command}).encode() + b"\n")
        self.file.flush()
        while True:
            reply = self._read()
            if reply.get("id") != command:
                continue
            if "error" in reply:
                raise RuntimeError(reply["error"].get("desc", str(reply["error"])))
            return reply.get("return")

    def close(self):
        if getattr(self, "file", None):
            self.file.close()
        self.sock.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def control(run, command):
    if command not in ("system_powerdown", "system_reset", "quit"):
        raise ValueError("Unsupported VM control")
    with QMP(run["qmp"]) as qmp:
        qmp.execute(command)


def integration_checks(run):
    """Check the active guest, independently of edits for the next launch."""
    opts = run.get("options", {})
    if opts.get("server") != "spice":
        return [("warn", "This guest was launched with VNC. Shut it down and choose SPICE + QXL "
                         "for clipboard, file transfer and guest resizing.")]
    with QMP(run["qmp"]) as qmp:
        spice = qmp.execute("query-spice")
        chars = qmp.execute("query-chardev")
    out = []
    connected = spice.get("enabled") and bool(spice.get("channels"))
    out.append(("ok" if connected else "warn", "SPICE viewer connected" if connected else
                "No SPICE viewer connected; use Open console"))
    agent_id = run.get("agent_chardev", "virtual-agent")
    agent = next((c for c in chars if c.get("label") == agent_id), None)
    if agent and agent.get("frontend-open"):
        out.append(("ok", "Guest opened the SPICE agent channel. Clipboard and resizing also need "
                    "a running agent in the logged-in desktop session."))
    else:
        out.append(("warn", "Guest SPICE agent channel is not open. Install/start SPICE Guest Tools "
                    "and the VirtIO Serial driver in Windows, or spice-vdagent in Linux, then sign in."))
    for key, label in (("clipboard", "Clipboard sharing"), ("file_transfer", "File transfer"), ("audio", "SPICE audio")):
        out.append(("ok" if opts.get(key) else "warn", f"{label}: {'enabled' if opts.get(key) else 'disabled'} for this run"))
    out.append(("warn", resolution_note(opts)))
    return out


def preview(cfg):
    plan = prepare(cfg)
    lines = ["# Virtual GPU launch (temporary paths shown below)",
             "# Same guest disks, CPU, RAM size, firmware, identity and TPM state.",
             "# Start / revert scripts are never invoked.",
             "# QEMU starts paused; the runtime applies affinity, then resumes it."]
    if plan.get("firmware_display"):
        display = plan["firmware_display"]
        lines.append(f"# Before boot: set the existing shared OVMF display preference to "
                     f"{display['width']}x{display['height']}; back up firmware before editing.")
    lines += ["", shlex.join(plan["argv"])]
    return "\n".join(lines)
