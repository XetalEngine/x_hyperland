"""Read OpenCore images and publish validated, independent boot-file versions.

The selected image and variable store are never written. A failed operation
only leaves/removes its own staging directory; the preset changes last.
"""

import copy
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import struct
import subprocess
import tempfile
import uuid
import zlib

APPLE_GUID = "7C436110-AB2A-4BBB-A880-FE41995C9F82"
ESP_GUID = uuid.UUID("C12A7328-F81F-11D2-BA4B-00A0C93EC93B").bytes_le
CONFIG = "EFI/OC/config.plist"
from portable import component_path
BUNDLES = component_path('opencore') / 'validators'


def sha(path):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(*args, timeout=60):
    env = dict(os.environ, LC_ALL="C", MTOOLSRC="/dev/null")
    env.pop("MTOOLS_SKIP_CHECK", None)
    result = subprocess.run([str(x) for x in args], capture_output=True, env=env, timeout=timeout)
    if result.returncode:
        message = (result.stderr or result.stdout).decode(errors="replace")[-6000:]
        raise ValueError(f"{Path(args[0]).name} failed: {message}")
    return result.stdout


def stopped():
    """Fail closed while any QEMU system VM is starting/running on this host."""
    for proc in Path("/proc").glob("[0-9]*/comm"):
        try:
            name = proc.read_text().strip()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise ValueError("Cannot check running VMs; close them before editing OpenCore.") from exc
        if name.startswith("qemu-system"):
            raise ValueError("Shut down the VM before editing or restoring OpenCore.")
    import virtual_gpu
    if virtual_gpu.service_active():
        raise ValueError("Wait for the VM launch/cleanup to finish before editing OpenCore.")


def regular(path, limit):
    path = Path(path).expanduser()
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Select a regular image file, not a disk device or symlink: {path}")
    size = path.stat().st_size
    if not 0 < size <= limit:
        raise ValueError(f"Unsupported file size: {path.name}")
    return path.resolve()


def partition(image):
    """Locate one ESP in a fully checked primary/backup 512-byte-sector GPT."""
    image = regular(image, 4 * 1024**3)
    size = image.stat().st_size
    if size % 512:
        raise ValueError("OpenCore editor requires a raw GPT disk image with 512-byte sectors.")
    sectors = size // 512
    with image.open("rb") as stream:
        def header(lba):
            stream.seek(lba * 512)
            raw = bytearray(stream.read(512))
            if raw[:8] != b"EFI PART":
                raise ValueError("Use a writable GPT OpenCore .img; an ISO or qcow2 cannot be edited here.")
            length, checksum = struct.unpack_from("<II", raw, 12)
            if not 92 <= length <= 512:
                raise ValueError("Invalid GPT header length.")
            raw[16:20] = b"\0" * 4
            if zlib.crc32(raw[:length]) != checksum:
                raise ValueError("GPT header checksum failed.")
            current, other, first, last = struct.unpack_from("<QQQQ", raw, 24)
            entries_lba, count, entry_size, entries_crc = struct.unpack_from("<QIII", raw, 72)
            if (current != lba or not 0 < other < sectors or not 2 <= first <= last < sectors - 1
                    or not 1 <= count <= 4096 or not 128 <= entry_size <= 4096
                    or count * entry_size > 1024**2 or entries_lba < 2
                    or entries_lba * 512 + count * entry_size > size):
                raise ValueError("Invalid GPT geometry.")
            stream.seek(entries_lba * 512)
            entries = stream.read(count * entry_size)
            if zlib.crc32(entries) != entries_crc:
                raise ValueError("GPT partition-array checksum failed.")
            return other, first, last, bytes(raw[56:72]), entry_size, entries

        a, b = header(1), header(sectors - 1)
        if a[0] != sectors - 1 or b[0] != 1 or a[1:] != b[1:]:
            raise ValueError("Primary and backup GPT disagree.")
        found, ranges = [], []
        for pos in range(0, len(a[5]), a[4]):
            entry = a[5][pos:pos + a[4]]
            if entry[:16] == b"\0" * 16:
                continue
            start, end = struct.unpack_from("<QQ", entry, 32)
            if not a[1] <= start <= end <= a[2] or any(start <= hi and end >= lo for lo, hi in ranges):
                raise ValueError("Invalid or overlapping GPT partitions.")
            ranges.append((start, end))
            if entry[:16] == ESP_GUID:
                found.append((start * 512, (end - start + 1) * 512))
        if len(found) != 1:
            raise ValueError("The OpenCore image must contain exactly one EFI System Partition.")
        return found[0]


def media(cfg):
    if cfg.profile != "macos":
        raise ValueError("OpenCore editing belongs to the Mac profile.")
    blocks = {b.get("node-name"): b for b in cfg.blockdevs if not b.get("_disabled")}
    selected = cfg.data.get("_meta", {}).get("opencore_boot_device")
    if selected == "":
        raise ValueError("Select the OpenCore image disk in Paths & tools before editing.")
    boot = [d for d in cfg.devices if d.get("id") == (selected or "opencore-boot") and not d.get("_disabled")]
    if not boot and not selected:
        hint = cfg.data.get("_meta", {}).get("writable_opencore", {}).get("image")
        boot = [d for d in cfg.devices if not d.get("_disabled")
                and blocks.get(d.get("drive"), {}).get("filename") == hint] if hint else []
    if len(boot) != 1 or boot[0].get("driver") == "ide-cd":
        raise ValueError("Select a writable OpenCore boot disk in Paths & tools or Disks & storage.")
    node = boot[0].get("drive")
    seen = set()
    while node in blocks:
        if node in seen:
            raise ValueError("Cyclic OpenCore block-device graph.")
        seen.add(node)
        if blocks[node].get("driver") not in ("file", "raw") or blocks[node].get("read-only"):
            raise ValueError("The OpenCore disk must be a writable raw image, not an overlay or read-only disk.")
        if "filename" in blocks[node]:
            break
        node = blocks[node].get("file")
    image = blocks.get(node)
    nvram = blocks.get("libvirt-pflash1-storage")
    if not image or not nvram:
        raise ValueError("The OpenCore boot image and private OVMF variable store must both be selected.")
    if image.get("read-only") or nvram.get("read-only"):
        raise ValueError("Select writable boot media and NVRAM for this Mac preset.")
    return (node, regular(image.get("filename", ""), 4 * 1024**3),
            nvram["node-name"], regular(nvram.get("filename", ""), 16 * 1024**2))


def plist(image, offset):
    raw = run("mtype", "-i", f"{image}@@{offset}", "::/" + CONFIG)
    if len(raw) > 4 * 1024**2:
        raise ValueError("OpenCore config is unexpectedly large.")
    value = plistlib.loads(raw)
    if not isinstance(value, dict) or any(k not in value for k in
            ("ACPI", "Booter", "Kernel", "Misc", "NVRAM", "PlatformInfo", "UEFI")):
        raise ValueError("This is not a complete OpenCore config.plist.")
    return value


@dataclass
class Snapshot:
    image_node: str
    image: Path
    vars_node: str
    variables: Path
    image_hash: str
    vars_hash: str
    offset: int
    length: int
    config: dict


def inspect(cfg):
    stopped()
    node, image, vars_node, variables = media(cfg)
    offset, length = partition(image)
    image_hash, vars_hash = sha(image), sha(variables)
    config = plist(image, offset)
    if sha(image) != image_hash or sha(variables) != vars_hash:
        raise ValueError("Boot files changed during inspection; reload them with the VM stopped.")
    return Snapshot(node, image, vars_node, variables, image_hash, vars_hash, offset, length, config)


def check_snapshot(cfg, snapshot):
    stopped()
    if media(cfg) != (snapshot.image_node, snapshot.image, snapshot.vars_node, snapshot.variables):
        raise ValueError("Boot paths changed; reload OpenCore before saving.")
    if sha(snapshot.image) != snapshot.image_hash or sha(snapshot.variables) != snapshot.vars_hash:
        raise ValueError("Boot files changed since loading; reload OpenCore before saving.")


def arguments(config):
    return config["NVRAM"]["Add"].get(APPLE_GUID, {}).get("boot-args", "")


def set_arguments(config, value):
    if not isinstance(value, str) or any(c in value for c in "\0\r\n") or len(value.encode()) > 1024:
        raise ValueError("Boot arguments must be one line, at most 1024 bytes.")
    config["NVRAM"]["Add"].setdefault(APPLE_GUID, {})["boot-args"] = value.strip()
    deletes = config["NVRAM"].setdefault("Delete", {}).setdefault(APPLE_GUID, [])
    if "boot-args" not in deletes:
        deletes.append("boot-args")


def prepare_changes(before, after):
    """Make edited Apple variables take effect even when NVRAM has old values."""
    value = copy.deepcopy(after)
    for key in ("boot-args", "csr-active-config"):
        old = before["NVRAM"]["Add"].get(APPLE_GUID, {}).get(key)
        new = value["NVRAM"]["Add"].get(APPLE_GUID, {}).get(key)
        if old != new:
            deleted = value["NVRAM"].setdefault("Delete", {}).setdefault(APPLE_GUID, [])
            if key not in deleted:
                deleted.append(key)
    return value


def sync_memory(config, cfg):
    size = next(int(o["size"]) for o in cfg.objects if o.get("id") == "pc.ram") // 1024**2
    platform = config["PlatformInfo"]
    memory = platform.get("Memory", {})
    devices = memory.get("Devices", [])
    populated = [d for d in devices if d.get("Size", 0) > 0]
    if not populated or size < len(populated):
        raise ValueError("This OpenCore image has no usable custom memory slots to synchronize.")
    per_slot, extra = divmod(size, len(populated))
    for n, dev in enumerate(populated):
        dev["Size"] = per_slot + (1 if n < extra else 0)
    # SMBIOS Type 16 uses bytes; individual DIMM sizes above use MiB. Keep
    # capacity consistent when growing RAM without lowering a larger limit.
    memory["MaxCapacity"] = max(memory.get("MaxCapacity", 0), size * 1024**2)
    platform["CustomMemory"] = True


def memory_note(config, cfg):
    platform = config.get("PlatformInfo", {})
    actual = next(int(o["size"]) for o in cfg.objects if o.get("id") == "pc.ram") // 1024**2
    if not platform.get("CustomMemory"):
        return f"VM memory: {actual} MiB. OpenCore custom memory description is disabled."
    described = sum(d.get("Size", 0) for d in platform.get("Memory", {}).get("Devices", []))
    return (f"VM memory: {actual} MiB; OpenCore describes {described} MiB. "
            + ("Matched." if actual == described else "Use Sync memory before applying this configuration."))


def changes(before, after, prefix=""):
    """Stable, typed differences for the review dialog; never dump whole blobs."""
    if before == after:
        return []
    if type(before) is type(after) and isinstance(before, dict) and before.keys() == after.keys():
        return [line for key in before for line in changes(before[key], after[key], f"{prefix}/{key}")]
    if type(before) is type(after) and isinstance(before, list) and len(before) == len(after):
        return [line for n, (a, b) in enumerate(zip(before, after)) for line in changes(a, b, f"{prefix}/{n}")]
    def display(value):
        return value.hex() if isinstance(value, bytes) else repr(value)
    return [f"{prefix}: {display(before)} → {display(after)}"]


def _safe_relative(value):
    path = Path(str(value).replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"Invalid EFI path: {value}")
    return path


def validate(config, tree, cfg):
    """Validate required files, references and the version-matched OC schema."""
    for name in ["EFI/BOOT/BOOTx64.efi", "EFI/OC/OpenCore.efi", CONFIG]:
        if not (tree / name).is_file():
            raise ValueError(f"Required boot file missing: {name}")
    if config["Misc"]["Security"].get("Vault", "Optional") != "Optional":
        raise ValueError("This editor cannot sign an OpenCore vault; keep Vault set to Optional.")
    for section, group, field, folder in [
        ("ACPI", "Add", "Path", "ACPI"), ("Kernel", "Add", "BundlePath", "Kexts"),
        ("UEFI", "Drivers", "Path", "Drivers"), ("Misc", "Tools", "Path", "Tools"),
    ]:
        for entry in config[section][group]:
            if not isinstance(entry, dict) or not entry.get("Enabled"):
                continue
            target = tree / "EFI/OC" / folder / _safe_relative(entry[field])
            if not target.exists():
                raise ValueError(f"Enabled {section} entry has no file: {entry[field]}")
            if section == "Kernel":
                for key in ("ExecutablePath", "PlistPath"):
                    if entry.get(key) and not (target / _safe_relative(entry[key])).is_file():
                        raise ValueError(f"Kext file missing: {entry[field]}/{entry[key]}")
    drivers = config["UEFI"]["Drivers"]
    if not any(d.get("Enabled") and d.get("Path") == "OpenRuntime.efi" for d in drivers if isinstance(d, dict)):
        raise ValueError("Keep OpenRuntime.efi enabled for this VM's boot firmware.")
    platform = config["PlatformInfo"]
    if platform.get("CustomMemory") and "Matched." not in memory_note(config, cfg):
        raise ValueError(memory_note(config, cfg))
    generic = platform.get("Generic", {})
    if generic.get("SystemUUID"):
        uuid.UUID(generic["SystemUUID"])
    if not isinstance(generic.get("ROM"), bytes) or len(generic["ROM"]) != 6:
        raise ValueError("The Mac ROM identity must contain exactly six bytes.")
    value = config["NVRAM"]["Add"].get(APPLE_GUID, {}).get("csr-active-config")
    if value is not None and (not isinstance(value, bytes) or len(value) != 4):
        raise ValueError("SIP csr-active-config must contain four bytes.")
    args = arguments(config)
    set_arguments(copy.deepcopy(config), args)  # also validate advanced-tree edits
    for arg in args.split():
        if arg.startswith("nvrmsettle=") and not re.fullmatch(r"nvrmsettle=\d{1,6}", arg):
            raise ValueError("NVIDIA startup delay must be a non-negative number of milliseconds.")
    bundle_root = Path(cfg.data.get("tools", {}).get("opencore_validators") or BUNDLES)
    digest = sha(tree / "EFI/OC/OpenCore.efi")
    for manifest in sorted(bundle_root.glob("*/manifest.json")):
        record = json.loads(manifest.read_text())
        if record.get("opencore_sha256") != digest:
            continue
        binary = manifest.parent / "ocvalidate"
        if sha(binary) != record["ocvalidate_sha256"]:
            raise ValueError("OpenCore validator checksum mismatch; restore the matching validator bundle.")
        result = run(binary, tree / CONFIG).decode(errors="replace")
        return f"OpenCore {record['version']}: " + result.strip()
    raise ValueError("No validator matches this OpenCore binary. Select its matching validator bundle in Paths & tools.")


def _tree(image, offset, destination):
    destination.mkdir()
    run("mcopy", "-s", "-i", f"{image}@@{offset}", "::/*", destination)
    return {str(p.relative_to(destination)): sha(p) for p in destination.rglob("*") if p.is_file()}


def _check_fat_copy(esp):
    """Repair only the disposable ESP copy; the caller then verifies every file."""
    def check(option):
        result = subprocess.run(["fsck.fat", option, str(esp)], capture_output=True,
                                env=dict(os.environ, LC_ALL="C"), timeout=60)
        output = (result.stdout + result.stderr).decode(errors="replace")
        if result.returncode not in (0, 1):
            raise ValueError("FAT check failed: " + output[-6000:])
        return result.returncode, output
    code, output = check("-n")
    if not code:
        return output
    _, repaired = check("-a")
    code, verified = check("-n")
    if code:
        raise ValueError("The copied EFI filesystem could not be verified: " + verified[-6000:])
    return "FAT metadata checked/repaired on the NEW copy only:\n" + output + repaired + verified


def _fsync_tree(directory):
    for path in directory.rglob("*"):
        if path.is_file():
            with path.open("rb") as stream:
                os.fsync(stream.fileno())
    for subdir in sorted((p for p in directory.rglob("*") if p.is_dir()), reverse=True):
        _fsync_directory(subdir)
    _fsync_directory(directory)


def _fsync_directory(directory):
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def publish(cfg, snapshot, edited, progress=lambda *_: None):
    """Publish a new version and only then select its paths in the in-memory preset."""
    check_snapshot(cfg, snapshot)
    edited = prepare_changes(snapshot.config, edited)
    if edited == snapshot.config:
        raise ValueError("No OpenCore changes to apply.")
    for command in ("mcopy", "mtype", "fsck.fat", "cp"):
        if not shutil.which(command):
            raise ValueError(f"Install {command} before saving OpenCore changes.")
    root = Path(cfg.root).resolve() / "macos/opencore-versions"
    if root.is_symlink() or not root.resolve().is_relative_to(Path(cfg.root).resolve()):
        raise ValueError("The OpenCore versions directory must be inside this vmstart2 installation.")
    root.mkdir(parents=True, exist_ok=True)
    version = uuid.uuid4().hex
    stage = Path(tempfile.mkdtemp(prefix=".staging-", dir=root))
    final = root / version
    before = copy.deepcopy(cfg.data)
    try:
        progress(10, "Reading the existing EFI files")
        original = stage / "original"
        original_files = _tree(snapshot.image, snapshot.offset, original)
        candidate = stage / "candidate"
        shutil.copytree(original, candidate)
        (candidate / CONFIG).write_bytes(plistlib.dumps(edited, sort_keys=False))
        progress(25, "Validating OpenCore settings and referenced files")
        report = validate(edited, candidate, cfg)
        image, variables = stage / "OpenCore.img", stage / "OVMF_VARS.fd"
        progress(40, "Copying boot image and private NVRAM")
        run("cp", "--reflink=auto", "--sparse=always", "--no-clobber", snapshot.image, image)
        shutil.copyfile(snapshot.variables, variables)
        if sha(image) != snapshot.image_hash or sha(variables) != snapshot.vars_hash:
            raise ValueError("A boot file changed during copying; nothing was applied.")
        run("mcopy", "-o", "-i", f"{image}@@{snapshot.offset}", candidate / CONFIG, "::/" + CONFIG)
        progress(60, "Checking partition table, FAT filesystem and file contents")
        if partition(image) != (snapshot.offset, snapshot.length) or plist(image, snapshot.offset) != edited:
            raise ValueError("Written boot image failed its read-back check.")
        esp = stage / "check-esp.img"
        with image.open("rb") as src, esp.open("xb") as dst:
            src.seek(snapshot.offset)
            remaining = snapshot.length
            while remaining:
                chunk = src.read(min(4 * 1024**2, remaining))
                if not chunk:
                    raise ValueError("Incomplete EFI partition copy.")
                dst.write(chunk)
                remaining -= len(chunk)
        report += "\n\n" + _check_fat_copy(esp)
        with esp.open("rb") as src, image.open("r+b") as dst:
            dst.seek(snapshot.offset)
            shutil.copyfileobj(src, dst, 4 * 1024**2)
        esp.unlink()
        if partition(image) != (snapshot.offset, snapshot.length):
            raise ValueError("Partition geometry changed while checking the copied filesystem.")
        readback = stage / "readback"
        written_files = _tree(image, snapshot.offset, readback)
        if original_files.keys() != written_files.keys() or any(
                original_files[p] != written_files[p] for p in original_files if p != CONFIG):
            raise ValueError("A file other than config.plist changed; nothing was applied.")
        if written_files[CONFIG] != sha(candidate / CONFIG):
            raise ValueError("OpenCore config checksum mismatch after writing.")
        progress(80, "Keeping the previous setup and preparing the new version")
        new = copy.deepcopy(before)
        for block in new["blockdevs"]:
            if block.get("node-name") == snapshot.image_node:
                block["filename"] = str(final / image.name)
            elif block.get("node-name") == snapshot.vars_node:
                block["filename"] = str(final / variables.name)
        new.setdefault("_meta", {}).setdefault("writable_opencore", {}).update(
            image=str(final / image.name), nvram=str(final / variables.name))
        new["_meta"]["opencore_editor"] = {"version": str(final), "rollback": str(final / "preset-before.json")}
        (stage / "preset-before.json").write_text(json.dumps(before, indent=2) + "\n")
        (stage / "preset-after.json").write_text(json.dumps(new, indent=2) + "\n")
        (stage / "config-before.plist").write_bytes(plistlib.dumps(snapshot.config, sort_keys=False))
        (stage / "config-after.plist").write_bytes(plistlib.dumps(edited, sort_keys=False))
        (stage / "validation.txt").write_text(report + "\n")
        (stage / "manifest.json").write_text(json.dumps({
            "source_image": str(snapshot.image), "source_image_sha256": snapshot.image_hash,
            "source_nvram": str(snapshot.variables), "source_nvram_sha256": snapshot.vars_hash,
            "image_sha256": sha(image), "nvram_sha256": sha(variables),
            "preset_before_sha256": sha(stage / "preset-before.json"),
            "changes": changes(snapshot.config, edited), "efi_files_checked": len(written_files),
        }, indent=2) + "\n")
        for directory in (original, candidate, readback):
            shutil.rmtree(directory)
        check_snapshot(cfg, snapshot)
        if cfg.data != before:
            raise ValueError("Preset changed during validation; reload before applying.")
        _fsync_tree(stage)
        stage.rename(final)
        _fsync_directory(root)
        cfg.data.clear()
        cfg.data.update(new)
        progress(100, "Validated version selected; save your setup to remember it")
        return final
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def rollback(cfg):
    stopped()
    path = Path(cfg.data.get("_meta", {}).get("opencore_editor", {}).get("rollback", ""))
    root = Path(cfg.root).resolve() / "macos/opencore-versions"
    if (not root.resolve().is_relative_to(Path(cfg.root).resolve()) or path.is_symlink()
            or not path.resolve().is_relative_to(root.resolve()) or not path.is_file()):
        raise ValueError("No editor-created previous setup is available.")
    from model import VMConfig
    manifest = json.loads((path.parent / "manifest.json").read_text())
    if sha(path) != manifest["preset_before_sha256"]:
        raise ValueError("The saved previous preset changed; restore it from your backup.")
    previous = VMConfig(json.loads(path.read_text()), root=cfg.root)
    snapshot = inspect(previous)
    if (str(snapshot.image) != manifest["source_image"]
            or str(snapshot.variables) != manifest["source_nvram"]
            or snapshot.image_hash != manifest["source_image_sha256"]
            or snapshot.vars_hash != manifest["source_nvram_sha256"]):
        raise ValueError("The previous boot files changed outside this editor; automatic rollback was not applied.")
    cfg.data.clear()
    cfg.data.update(previous.data)
