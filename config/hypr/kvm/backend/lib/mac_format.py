#!/usr/bin/env python3
"""Prepare exactly one disk with Apple's native tools in isolated Recovery.

The normal launcher and this worker share the same systemd unit. The target is
held open by identity, but is not attached until the diskless guest checks in.
Guest disk discovery, a second host check, and a one-time permit precede erase.
No Linux APFS writer, host handoff hook, or existing guest NVRAM is used.
"""

import argparse
import copy
import csv
import fcntl
from http.server import BaseHTTPRequestHandler, HTTPServer
import io
import json
import os
from pathlib import Path
import plistlib
import queue
import re
import secrets
import shlex
import shutil
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
from urllib.parse import parse_qs, urlsplit

import macos_profile
from model import VMConfig
import virtual_gpu

MIN_SIZE = 32 * 1024**3
PHASES = ("checking", "booting", "tools", "formatting", "verifying", "finishing", "done")


def run(*args, timeout=20):
    result = subprocess.run([str(a) for a in args], capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip() or f"{args[0]} failed")
    return result.stdout


def flatten(device):
    yield device
    for child in device.get("children") or []:
        yield from flatten(child)


def inspect_target(filename):
    """Read-only inspection, repeated as root immediately before granting erase."""
    path = Path(filename).expanduser()
    real = path.resolve(strict=True)
    info = real.stat()
    result = dict(path=str(path.absolute()), realpath=str(real), labels=[], partitions=[])
    if stat.S_ISBLK(info.st_mode):
        tree = json.loads(run("lsblk", "--json", "--bytes", "--paths", "--output",
            "NAME,TYPE,SIZE,MODEL,SERIAL,RO,FSTYPE,LABEL,MOUNTPOINTS,LOG-SEC,PHY-SEC", real))["blockdevices"]
        if len(tree) != 1 or tree[0]["type"] != "disk":
            raise ValueError("Select a whole physical disk, not a partition, optical disc or mapped device.")
        disk = tree[0]
        if disk.get("ro"):
            raise ValueError("This disk is read only.")
        for item in flatten(disk):
            if any(item.get("mountpoints") or []):
                raise ValueError(f"{item['name']} is mounted or active as swap. Unmount it before formatting.")
            if item["type"] not in ("disk", "part"):
                raise ValueError(f"{item['name']} is in use by {item['type']}.")
            holders = Path("/sys/class/block") / Path(item["name"]).name / "holders"
            if not holders.is_dir() or any(holders.iterdir()):
                raise ValueError(f"Cannot establish that {item['name']} is unused; check its block-device holders.")
            result["partitions"].append(item["name"])
            if item.get("label"):
                result["labels"].append(item["label"])
        zfs = [d for d in flatten(disk) if d.get("fstype") == "zfs_member"]
        if zfs:
            if shutil.which("zpool"):
                imported = run("zpool", "status", "-P", "-L")
                if any(re.search(r"(?<!\S)" + re.escape(p) + r"(?!\S)", imported)
                       for p in result["partitions"]):
                    raise ValueError("This disk belongs to an imported ZFS pool. Export the pool first.")
            elif Path("/proc/spl/kstat/zfs").exists():
                pools = [p for p in Path("/proc/spl/kstat/zfs").iterdir() if p.is_dir()]
                if pools:
                    raise ValueError("Cannot check imported ZFS pools without the zpool command.")
        result.update(kind="block", size=int(disk["size"]), model=(disk.get("model") or "Disk").strip(),
                      serial=(disk.get("serial") or "").strip(),
                      logical_sector=int(disk["log-sec"]), physical_sector=int(disk["phy-sec"]),
                      identity=["block", info.st_rdev, int(disk["size"]), disk.get("serial") or ""])
    elif stat.S_ISREG(info.st_mode):
        if real.suffix.lower() not in (".img", ".raw"):
            raise ValueError("Select a whole physical disk or a raw .img/.raw installation disk.")
        if info.st_nlink != 1:
            raise ValueError("Hard-linked image files are not supported for formatting.")
        if not shutil.which("losetup"):
            raise ValueError("Install losetup before formatting raw images.")
        if run("losetup", "--noheadings", "--output", "NAME", "--associated", real).strip():
            raise ValueError("This image is attached to a loop device. Detach it before formatting.")
        with real.open("rb") as handle:
            if handle.read(4) == b"QFI\xfb":
                raise ValueError("This is a QCOW2 image. Mac Format currently accepts raw images only.")
        result.update(kind="file", size=info.st_size, model="Raw virtual disk", serial="",
                      logical_sector=512, physical_sector=512,
                      identity=["file", info.st_dev, info.st_ino, info.st_size])
    else:
        raise ValueError("Select a whole physical disk or a raw installation image.")
    if result["size"] < MIN_SIZE:
        raise ValueError("The installation disk must be at least 32 GiB.")
    return result


def validate_name(name):
    name = name.strip()
    if not name or len(name.encode("utf-8")) > 127 or any(ord(c) < 32 or c in "/:" for c in name):
        raise ValueError("Use a volume name of 1–127 UTF-8 bytes without slashes, colons or control characters.")
    return name


def check_identity(expected, actual):
    if actual["identity"] != expected["identity"] or actual["realpath"] != expected["realpath"]:
        raise ValueError("The selected drive changed since it was reviewed. Close this dialog and select it again.")


def installation_port(cfg, device):
    """Use the Mac preset's AHCI controller, without moving any other disk."""
    used = {d.get("bus") for d in cfg.devices if d is not device and not d.get("_disabled")}
    controllers = [d["id"] for d in cfg.devices if d.get("driver") == "ich9-ahci"
                   and d.get("id") and not d.get("_disabled")]
    for controller in controllers or ["ide"]:
        for port in range(6):
            bus = f"{controller}.{port}"
            if bus not in used:
                return bus
    raise ValueError("The Mac preset has no free SATA port. Remove an unused disk before formatting.")


def apply_format_result(cfg, block, device, result):
    """Update only the reviewed disk, after successful native verification."""
    if cfg.profile != "macos":
        raise ValueError("Mac Format cannot change the Windows profile.")
    if (os.path.realpath(block.get("filename", "")) != result["target"]["realpath"]
            or result.get("filesystem") != "APFS" or result.get("scheme") != "GUID Partition Map"):
        raise ValueError("The format result does not match this disk.")
    bus = installation_port(cfg, device)
    used = {int(d["bootindex"]) for d in cfg.devices if d is not device
            and not d.get("_disabled") and d.get("bootindex")}
    boot = max([1] + [int(d["bootindex"]) for d in cfg.devices
                     if d.get("driver") == "ide-cd" and not d.get("_disabled") and d.get("bootindex")]) + 1
    while boot in used:
        boot += 1
    identity = {k: device[k] for k in ("id", "serial", "model", "wwn", "rotation_rate") if k in device}
    device.clear()
    device.update(identity, driver="ide-hd", drive=block["node-name"], bus=bus, bootindex=boot,
                  **{"write-cache": "on", "logical_block_size": result["target"]["logical_sector"],
                     "physical_block_size": result["target"]["physical_sector"]})
    block.update(driver="host_device" if result["target"]["kind"] == "block" else "file",
                 aio="threads", discard="unmap", cache={"direct": True, "no-flush": False},
                 **{"read-only": False, "_mac_format": copy.deepcopy(result)})


def source_file(cfg, node):
    nodes = {b.get("node-name"): b for b in cfg.blockdevs if not b.get("_disabled")}
    seen = set()
    while isinstance(node, str) and node not in seen:
        seen.add(node)
        block = nodes.get(node, {})
        if block.get("filename"):
            return Path(block["filename"]).resolve(strict=True)
        node = block.get("file")
    raise ValueError("Cannot locate the prepared Mac firmware or recovery ISO.")


def prepare_job(cfg, filename, name):
    if cfg.profile != "macos":
        raise ValueError("Mac Format is available only in the Mac profile.")
    target = inspect_target(filename)
    optical = [d for d in cfg.devices if not d.get("_disabled") and d.get("driver") == "ide-cd"]
    candidates = [source_file(cfg, d.get("drive")) for d in optical]
    candidates = [p for p in candidates if p.suffix.lower() == ".iso"]
    if len(candidates) != 1:
        raise ValueError("Attach exactly one prepared macOS Recovery/OpenCore ISO before using Mac Format.")
    opts = cfg.data.get("machine", {}).get("opts", {})
    code = source_file(cfg, opts.get("pflash0"))
    variables = source_file(cfg, opts.get("pflash1"))
    template = variables.with_name("OVMF_VARS.template.fd")
    if template.is_file():
        variables = template
    if code.stat().st_size + variables.stat().st_size != 4 * 1024**2:
        raise ValueError("Mac Format needs the prepared matching 4 MiB OVMF firmware pair.")
    for name_ in ("tesseract", "lsblk"):
        if not shutil.which(name_):
            raise ValueError(f"Install {name_} before using Mac Format.")
    ocr_data = Path(cfg.root) / "macos/ocr"
    if not (ocr_data / "eng.traineddata").is_file():
        ocr_data = None
        if "eng" not in run("tesseract", "--list-langs").splitlines():
            raise ValueError("Install tesseract-data-eng before using Mac Format.")
    binary = Path(cfg.data["_meta"]["binary"]).resolve(strict=True)
    return dict(target=target, label=validate_name(name), iso=str(candidates[0]),
                code=str(code), variables=str(variables), binary=str(binary),
                cpu=copy.deepcopy(cfg.data["cpu"]), smp=copy.deepcopy(cfg.data["smp"]),
                ram=next(int(o["size"]) for o in cfg.objects if o.get("id") == "pc.ram"),
                release=cfg.data.get("_meta", {}).get("macos_release", "high-sierra"),
                profile_root=str(cfg.root), ocr_data=str(ocr_data) if ocr_data else "")


def helper_config(job, work):
    factory = macos_profile.tahoe_configuration if job["release"] == "tahoe" else macos_profile.configuration
    cfg = VMConfig(factory(job["profile_root"], job["iso"], job["binary"], {}), root=job["profile_root"])
    cfg.data["cpu"] = copy.deepcopy(job["cpu"])
    cfg.data["smp"] = copy.deepcopy(job["smp"])
    cfg.objects[0]["size"] = int(job["ram"])
    for b in cfg.blockdevs:
        if b.get("node-name") == "libvirt-pflash0-storage":
            b["filename"] = job["code"]
        elif b.get("node-name") == "libvirt-pflash1-storage":
            b["filename"] = str(work / "OVMF_VARS.fd")
    # User networking keeps the helper off the host bridge. It never inherits
    # any guest data disks or passthrough from the active preset.
    cfg.simple["netdev"] = '{"type":"user","id":"hostnet0"}'
    cfg.data["network"] = dict(mode="user", bridge="", ifname="")
    return cfg


def guest_candidate(data, size):
    disks = data.get("AllDisksAndPartitions", [])
    if not disks:
        return None
    if len(disks) != 1:
        raise ValueError("Recovery reported more than one external physical disk; refusing to erase.")
    disk = disks[0]
    identifier = disk.get("DeviceIdentifier", "")
    if not re.fullmatch(r"disk\d+", identifier) or disk.get("Size") != size:
        raise ValueError("The Recovery disk does not match the selected drive's exact size.")
    return identifier


def verify_guest_info(data, identifier, size, logical_sector=512):
    if (data.get("DeviceIdentifier") != identifier or data.get("WholeDisk") is not True
            or data.get("TotalSize") != size or data.get("BusProtocol") != "USB"
            or data.get("Writable") is not True or data.get("WritableMedia") is not True
            or data.get("Internal") is not False or data.get("DeviceBlockSize") != logical_sector):
        raise ValueError("The Recovery disk identity is not the expected writable whole USB disk.")


def verify_apfs(layout, apfs, disk, label):
    disks = layout.get("AllDisksAndPartitions", [])
    if len(disks) != 1 or disks[0].get("DeviceIdentifier") != disk or disks[0].get("Content") != "GUID_partition_scheme":
        raise ValueError("macOS did not report the expected GUID partition map.")
    partitions = disks[0].get("Partitions", [])
    if not any(p.get("Content") == "EFI" for p in partitions):
        raise ValueError("The new GUID disk has no EFI system partition.")
    stores = {p.get("DeviceIdentifier") for p in partitions if p.get("Content") == "Apple_APFS"}
    matches = []
    for container in apfs.get("Containers", []):
        physical = {p.get("DeviceIdentifier") for p in container.get("PhysicalStores", [])}
        if physical and physical.issubset(stores):
            for volume in container.get("Volumes", []):
                if volume.get("Name") == label:
                    matches.append((container, volume))
    if len(matches) != 1:
        raise ValueError("The new APFS volume was not found on the selected disk.")
    container, volume = matches[0]
    if not re.fullmatch(r"disk\d+s\d+", volume.get("DeviceIdentifier", "")):
        raise ValueError("Invalid APFS volume identifier.")
    return dict(label=label, filesystem="APFS", scheme="GUID Partition Map",
                volume=volume["DeviceIdentifier"], volume_uuid=volume.get("APFSVolumeUUID", ""),
                container_uuid=container.get("APFSContainerUUID", ""))


class Monitor(virtual_gpu.QMP):
    def execute(self, command, arguments=None):
        request = {"execute": command, "id": command}
        if arguments is not None:
            request["arguments"] = arguments
        self.file.write(json.dumps(request).encode() + b"\n")
        self.file.flush()
        while True:
            reply = self._read()
            if reply.get("id") == command:
                if "error" in reply:
                    raise RuntimeError(reply["error"].get("desc", str(reply["error"])))
                return reply.get("return")


def qcode(character):
    if character.isascii() and character.isalnum():
        return (["shift"] if character.isupper() else []) + [character.lower()]
    plain = {" ": "spc", "-": "minus", "=": "equal", ".": "dot", "/": "slash",
             "'": "apostrophe", ";": "semicolon", "[": "bracket_left", "]": "bracket_right"}
    shifted = {":": "semicolon", "|": "backslash", "_": "minus", '"': "apostrophe"}
    if character in plain:
        return [plain[character]]
    if character in shifted:
        return ["shift", shifted[character]]
    raise ValueError(f"Unsupported bootstrap keystroke: {character!r}")


def type_command(qmp, command):
    for keys in [qcode(c) for c in command] + [["ret"]]:
        qmp.execute("send-key", {"keys": [{"type": "qcode", "data": k} for k in keys], "hold-time": 20})
        time.sleep(.035)


def click(qmp, x, y, width=1280, height=720):
    qmp.execute("input-send-event", {"events": [
        {"type": "abs", "data": {"axis": "x", "value": round(x / (width-1) * 32767)}},
        {"type": "abs", "data": {"axis": "y", "value": round(y / (height-1) * 32767)}}]})
    for down in (True, False):
        qmp.execute("input-send-event", {"events": [{"type": "btn", "data": {"down": down, "button": "left"}}]})
        time.sleep(.1)


def recognized_words(qmp, work, ocr_data=""):
    picture = work / "recovery.ppm"
    qmp.execute("screendump", {"filename": str(picture)})
    data_args = ["--tessdata-dir", ocr_data] if ocr_data else []
    raw = run("tesseract", picture, "stdout", *data_args, "-l", "eng", "--psm", "11",
              "-c", "tessedit_create_tsv=1", timeout=15)
    words = []
    for item in csv.DictReader(io.StringIO(raw), delimiter="\t"):
        if item.get("text", "").strip():
            words.append(dict(text=item["text"].strip(), x=int(item["left"])+int(item["width"])/2,
                              y=int(item["top"])+int(item["height"])/2))
    return words


class Session:
    def __init__(self, job, work, emit):
        self.job, self.work, self.emit = job, work, emit
        self.token = secrets.token_hex(24)
        self.events = queue.Queue()
        self.hello = False
        self.attached = False
        self.disk = None
        self.info = None
        self.permitted = False
        self.layout = None
        self.result = None
        self.completed = False
        self.error = None
        self.bootstrap_served = False
        session = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def reply(self, data, status=200):
                data = data.encode() if isinstance(data, str) else data
                self.send_response(status)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def route(self):
                path = urlsplit(self.path).path
                prefix = "/" + session.token + "/"
                return path[len(prefix):] if path.startswith(prefix) else None

            def do_GET(self):
                route = self.route()
                if route == "bootstrap":
                    if session.bootstrap_served:
                        self.reply("Bootstrap already consumed", 409)
                        return
                    session.bootstrap_served = True
                    template = Path(__file__).with_name("mac_format_guest.sh").read_text()
                    self.reply(template.replace("__BASE__", shlex.quote(session.url)).replace(
                        "__LABEL__", shlex.quote(job["label"])))
                elif route == "selection":
                    self.reply("abort" if session.error else session.disk or "wait")
                elif route == "permit":
                    self.reply("abort" if session.error else "ERASE:"+session.disk if session.permitted else "wait")
                elif route == "volume":
                    self.reply(session.result["volume"] if session.result else "abort")
                else:
                    self.reply("Not found", 404)

            def do_POST(self):
                route = self.route()
                if route not in ("event", "disks", "info", "layout", "apfs"):
                    self.reply("Not found", 404)
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 1024*1024:
                        raise ValueError("Invalid response size")
                    data = self.rfile.read(length)
                    if route == "event":
                        values = parse_qs(data.decode())
                        stage, message = values.get("stage", [""])[0], values.get("message", [""])[0]
                        if stage == "hello":
                            if session.hello:
                                raise ValueError("Duplicate Recovery session")
                            session.hello = True
                        elif stage == "error":
                            session.error = message
                        elif stage == "complete":
                            if not session.permitted or not session.result:
                                raise ValueError("Unexpected completion from Recovery")
                            session.completed = True
                        session.events.put((stage, message))
                    else:
                        value = plistlib.loads(data)
                        if not isinstance(value, dict):
                            raise ValueError("Invalid Recovery response")
                        (work / (route+".plist")).write_bytes(data)
                        if route == "disks":
                            if session.attached:
                                candidate = guest_candidate(value, job["target"]["size"])
                                if candidate:
                                    if session.disk and session.disk != candidate:
                                        raise ValueError("Recovery target changed")
                                    session.disk = candidate
                        elif route == "info":
                            if not session.disk:
                                raise ValueError("No selected Recovery disk")
                            verify_guest_info(value, session.disk, job["target"]["size"],
                                              job["target"].get("logical_sector", 512))
                            session.info = value
                        elif route == "layout":
                            if not session.permitted:
                                raise ValueError("Unexpected partition map")
                            session.layout = value
                        elif route == "apfs":
                            if not session.permitted or not session.layout:
                                raise ValueError("Unexpected APFS result")
                            session.result = verify_apfs(session.layout, value, session.disk, job["label"])
                    self.reply("ok")
                except Exception as error:
                    session.error = str(error)
                    self.reply(str(error), 400)

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://10.0.2.2:{self.server.server_port}/{self.token}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self):
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def assert_no_openers(target, allowed=()):
    """Root worker checks physical disks AND their partitions, or the exact image."""
    paths = [target["realpath"]] + target.get("partitions", [])
    identities = set()
    for path in paths:
        try:
            s = os.stat(path)
            identities.add(("block", s.st_rdev) if stat.S_ISBLK(s.st_mode) else ("file", s.st_dev, s.st_ino))
        except FileNotFoundError:
            pass
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit() or int(proc.name) in {os.getpid(), *allowed}:
            continue
        try:
            descriptors = list((proc / "fd").iterdir())
        except FileNotFoundError:
            continue
        except PermissionError as error:
            raise ValueError("Cannot inspect other processes; run the formatter with administrator rights.") from error
        for descriptor in descriptors:
            try:
                s = descriptor.stat()
            except (FileNotFoundError, ProcessLookupError):
                continue
            key = ("block", s.st_rdev) if stat.S_ISBLK(s.st_mode) else ("file", s.st_dev, s.st_ino)
            if key in identities:
                raise ValueError(f"The selected drive is open in process {proc.name}. Close it before formatting.")


def format_disk(job, work, emit):
    current = inspect_target(job["target"]["path"])
    check_identity(job["target"], current)
    assert_no_openers(current)
    flags = os.O_RDWR | os.O_NOFOLLOW
    if current["kind"] == "block":
        flags |= os.O_EXCL
    fd = os.open(current["realpath"], flags)
    child = session = log = None
    qmp = None
    permitted = False
    stop = threading.Event()
    previous_handlers = {}
    for sig in (signal.SIGTERM, signal.SIGINT):
        previous_handlers[sig] = signal.signal(sig, lambda *_: stop.set())
    try:
        opened = os.fstat(fd)
        expected = current["identity"]
        if current["kind"] == "file":
            if ["file", opened.st_dev, opened.st_ino, opened.st_size] != expected:
                raise ValueError("The image changed while opening it")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        elif opened.st_rdev != expected[1]:
            raise ValueError("The physical disk changed while opening it")
        check_identity(current, inspect_target(current["path"]))
        emit("checking", "Drive identity and exclusive access checked")
        shutil.copyfile(job["variables"], work / "OVMF_VARS.fd")
        session = Session(job, work, emit)
        session.start()
        cfg = helper_config(job, work)
        with socket.socket() as port:
            port.bind(("127.0.0.1", 0))
            number = port.getsockname()[1]
        plan = virtual_gpu.prepare(cfg, dict(server="vnc", port=number if number >= 5900 else 5901,
            width=1280, height=720, network="preset", pinning=False, uefi_resolution=False,
            clipboard=False, file_transfer=False, audio=False), str(work), "mac-format")
        if plan["tap"] or plan["tpm"] or plan["huge"]:
            raise ValueError("Unexpected host resource in the formatting helper")
        if "-S" not in plan["argv"]:
            raise ValueError("The formatting helper must start paused before the target is disconnected")
        controller = next(d for d in plan["config"]["devices"] if d.get("driver") in
            ("nec-usb-xhci", "qemu-xhci", "usb-ehci", "ich9-usb-ehci1"))
        # This QEMU build disables device hotplug. Create a USB BOT bridge
        # while the VM is paused, and disconnect it before any guest code runs.
        # Its runtime 'attached' property reconnects the reviewed disk only
        # after the authenticated Recovery handshake.
        args = plan["argv"] + ["-add-fd", f"fd={fd},set=7,opaque=mac-format-target",
            "-blockdev", json.dumps({"driver": "host_device" if current["kind"] == "block" else "file",
                "node-name": "format-target", "filename": "/dev/fdset/7", "read-only": False,
                "cache": {"direct": False, "no-flush": False}}),
            "-device", json.dumps({"driver": "usb-bot", "id": "format-target-usb",
                "bus": controller["id"]+".0", "serial": "VMFMT"+session.token[:15]}),
            "-device", json.dumps({"driver": "scsi-hd", "id": "format-target-disk",
                "bus": "format-target-usb.0", "drive": "format-target", "scsi-id": 0, "lun": 0,
                "removable": False, "logical_block_size": current["logical_sector"],
                "physical_block_size": current["physical_sector"]})]
        log = (work / "qemu.log").open("w")
        child = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                 pass_fds=(fd,))
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if child.poll() is not None:
                raise RuntimeError("The temporary Recovery VM could not start. See qemu.log.")
            if Path(plan["qmp"]).exists():
                qmp = Monitor(plan["qmp"], timeout=10)
                break
            time.sleep(.1)
        if qmp is None:
            raise TimeoutError("The formatting VM did not expose its monitor")
        usb_path = "/machine/peripheral/format-target-usb"
        qmp.execute("qom-set", {"path": usb_path, "property": "attached", "value": False})
        if qmp.execute("qom-get", {"path": usb_path, "property": "attached"}) is not False:
            raise ValueError("The target could not be disconnected before booting Recovery")
        qmp.execute("cont")
        emit("booting", "Starting macOS Recovery; this can take a few minutes")
        deadline = time.monotonic() + 480
        next_picture = 0
        terminal_stage = "utilities"
        typed_at = None
        while not session.completed:
            now = time.monotonic()
            if child.poll() is not None:
                raise RuntimeError("The temporary Recovery VM stopped before formatting completed")
            if now >= deadline:
                raise TimeoutError("Recovery did not complete this step before the timeout")
            if (stop.is_set() or (work/"cancel").exists()) and not permitted:
                raise InterruptedError("Cancelled before erasing the drive")
            if stop.is_set() and permitted:
                raise InterruptedError("Formatting was interrupted; the drive may need to be formatted again")
            if session.error:
                raise RuntimeError(session.error)
            while not session.events.empty():
                stage, message = session.events.get_nowait()
                if stage not in ("hello", "complete"):
                    emit(stage, message)
            if session.hello and not session.attached:
                emit("tools", "Apple disk tools connected; attaching the selected drive")
                qmp.execute("qom-set", {"path": usb_path, "property": "attached", "value": True})
                session.attached = True
                deadline = now + 120
            if session.info and not permitted:
                check_identity(current, inspect_target(current["path"]))
                assert_no_openers(current, allowed=(child.pid,))
                if stop.is_set() or (work/"cancel").exists():
                    raise InterruptedError("Cancelled before erasing the drive")
                emit("formatting", "Drive matched in macOS; creating GUID + APFS", irreversible=True)
                permitted = session.permitted = True
                deadline = now + 900
            if not session.hello and not session.bootstrap_served and now >= next_picture:
                words = recognized_words(qmp, work, job.get("ocr_data", ""))
                if terminal_stage == "utilities":
                    word = next((w for w in words if w["text"].strip(".") == "Utilities" and w["y"] < 55), None)
                    if word:
                        emit("tools", "Opening native disk tools in Recovery")
                        click(qmp, word["x"], word["y"])
                        terminal_stage = "terminal"
                elif terminal_stage == "terminal":
                    word = next((w for w in words if w["text"].strip(".") == "Terminal" and 25 < w["y"] < 350), None)
                    if word:
                        click(qmp, word["x"], word["y"])
                        terminal_stage = "type"
                elif terminal_stage == "type":
                    # Only a successful authenticated callback can cause the
                    # selected disk to be attached. These keys cannot erase it.
                    type_command(qmp, f"curl -fs '{session.url}/bootstrap' | bash")
                    typed_at = now
                    terminal_stage = "sent"
                next_picture = time.monotonic() + 3
            if typed_at and not session.hello and now-typed_at > 60:
                raise TimeoutError("Recovery's terminal did not connect to the formatter; the drive was not erased")
            time.sleep(.2)
        emit("finishing", "APFS verified; closing Recovery and refreshing the host drive list")
        qmp.execute("quit")
        child.wait(timeout=15)
        qmp.close()
        qmp = None
        os.fsync(fd)
        os.close(fd)
        fd = None
        if current["kind"] == "block":
            run("blockdev", "--rereadpt", current["realpath"])
            if shutil.which("udevadm"):
                run("udevadm", "settle", "--timeout=15")
        result = dict(session.result, target=current, formatted_at=time.strftime("%Y-%m-%d %H:%M:%S"))
        (work/"result.json").write_text(json.dumps(result, indent=2)+"\n")
        emit("done", f"{job['label']} is ready for the macOS installer", result=result)
        return result
    finally:
        if qmp is not None:
            try:
                if child and child.poll() is None:
                    qmp.execute("quit")
            except Exception:
                pass
            qmp.close()
        if child and child.poll() is None:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
        if session:
            session.close()
        if log:
            log.close()
        if fd is not None:
            os.close(fd)
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--run", type=Path, help="run a reviewed format job")
    action.add_argument("--submit", type=Path, help="reserve the shared VM unit and run a reviewed format job")
    args = parser.parse_args()
    if args.submit:
        if virtual_gpu.service_active():
            print(json.dumps(dict(stage="error", message="Shut down the current VM before formatting.")), flush=True)
            return 1
        subprocess.run(["systemctl", "reset-failed", virtual_gpu.UNIT], capture_output=True, timeout=10)
        os.execvp("systemd-run", ["systemd-run", "--quiet", "--collect", "--wait", "--pipe",
            "--unit", virtual_gpu.UNIT, "--description=vmstart_2 native Mac disk format",
            "--property=KillMode=mixed", "--property=TimeoutStopSec=120", "--service-type=exec",
            sys.executable, "-u", str(Path(__file__).resolve()), "--run", str(args.submit.resolve())])
    work = args.run.resolve().parent
    owner = args.run.stat()
    job = json.loads(args.run.read_text())
    if job.get("confirmed") is not True:
        parser.error("The erase operation has not been confirmed")
    job["label"] = validate_name(job["label"])
    def emit(stage, message, **extra):
        print(json.dumps(dict(stage=stage, message=message, **extra)), flush=True)
    try:
        format_disk(job, work, emit)
    except Exception as error:
        emit("error", str(error))
        return 1
    finally:
        if os.geteuid() == 0:
            for path in work.iterdir():
                if path.is_file() and not path.is_symlink():
                    os.chown(path, owner.st_uid, owner.st_gid)
                    path.chmod(0o600)
    return 0


if __name__ == "__main__":
    sys.exit(main())
