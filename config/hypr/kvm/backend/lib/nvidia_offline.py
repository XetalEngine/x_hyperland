"""Prepare local NVIDIA media and independent boot files; never run an installer on the host."""

import copy
import json
from pathlib import Path
import re
import shutil
import tempfile
import uuid

import gpu_inventory
import opencore

VERSION = "2.5.3"
MEDIA_ID = "vmstart2-nvidia-offline"


def local_file(root, relative, limit=2 * 1024**3):
    path = Path(root) / relative
    if not relative or Path(relative).is_absolute() or not path.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError("An NVIDIA bundle path leaves its archive directory.")
    return opencore.regular(path, limit)


def bundle(cfg):
    """Authenticate the local ISO and card table against the archived manifests."""
    root = Path(cfg.root).resolve() / "macos/NVIDIA-Offline"
    if root.is_symlink() or not root.resolve().is_relative_to(Path(cfg.root).resolve()):
        raise ValueError("Keep the NVIDIA archive inside this vmstart2 installation.")
    try:
        record = json.loads(local_file(root, "media.json", 4 * 1024**2).read_text())
        archive_path = local_file(root, "archive.json", 4 * 1024**2)
        archive = json.loads(archive_path.read_text())
        if record["version"] != VERSION or archive["version"] != VERSION:
            raise ValueError("Unexpected NVIDIA archive version.")
        if opencore.sha(archive_path) != record["archive_sha256"]:
            raise ValueError("The archive changed since the installer disc was built.")
        iso = local_file(root, record["iso"])
        if opencore.sha(iso) != record["sha256"]:
            raise ValueError("The NVIDIA installer disc failed its checksum check.")
        name = f"Payloads/{VERSION}/nvidia_gsp_ids.json"
        catalog = local_file(root, name, 4 * 1024**2)
        if opencore.sha(catalog) != archive["files"][name]:
            raise ValueError("The supported-GPU table failed its checksum check.")
        ids = json.loads(catalog.read_text())["ids"]
        if not ids or not all(re.fullmatch(r"[0-9A-F]{4}", key) for key in ids):
            raise ValueError("Invalid NVIDIA supported-GPU table.")
        return iso, record, ids
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("The offline NVIDIA bundle is incomplete. Restore macos/NVIDIA-Offline "
                         "or build its disc with scripts/build_nvidia_offline.py.") from exc


def selected_gpu(cfg, ids):
    cards = []
    for device in cfg.devices:
        if device.get("driver") != "vfio-pci" or device.get("_disabled"):
            continue
        slot = str(device.get("host", ""))
        if re.fullmatch(r"[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7]", slot):
            slot = "0000:" + slot
        identity = gpu_inventory.identity(slot)
        if identity["vendor"] == "0x10de" and gpu_inventory.pci_class(slot) >> 16 == 3:
            cards.append((slot, identity["device"].removeprefix("0x").upper()))
    if len(cards) != 1:
        raise ValueError("Assign exactly one NVIDIA display GPU under PCI & USB devices first. "
                         "Use Single GPU or Dual GPU for installation; Virtual GPU alone cannot accelerate NVIDIA.")
    slot, device_id = cards[0]
    if device_id not in ids:
        raise ValueError(f"NVIDIA {device_id} is not in this release's supported-card table. "
                         "This installer targets Turing and newer, not every NVIDIA GPU.")
    return {"slot": slot, "device_id": device_id, "name": ids[device_id]}


def free_sata_bus(cfg):
    live = [d for d in cfg.devices if not d.get("_disabled")]
    # q35 has one device per AHCI port. A second explicit controller also has
    # six ports; never invent ide.6 or put two drives on an occupied port.
    buses = []
    machine = str(cfg.data.get("machine", {}).get("type", ""))
    if "q35" in machine:
        buses += [f"ide.{n}" for n in range(6)]
    for device in live:
        if device.get("driver") == "ich9-ahci" and device.get("id"):
            buses += [f"{device['id']}.{n}" for n in range(6)]
    used = {d.get("bus") for d in live}
    if any(d.get("driver") in ("ide-hd", "ide-cd") and not d.get("bus") for d in live):
        raise ValueError("Set an explicit SATA bus for existing disks before adding the NVIDIA installer.")
    try:
        return next(bus for bus in buses if bus not in used)
    except StopIteration as exc:
        raise ValueError("No free AHCI/SATA port is available for the installer disc.") from exc


def prepared(cfg, iso, checksum):
    meta = cfg.data.get("_meta", {}).get("nvidia_offline", {})
    if meta.get("version") != VERSION or meta.get("iso_sha256") != checksum:
        return False
    try:
        _, image, _, variables = opencore.media(cfg)
    except ValueError:
        return False
    if str(image) != meta.get("image") or str(variables) != meta.get("nvram"):
        return False
    blocks = [b for b in cfg.blockdevs if not b.get("_disabled") and b.get("node-name") == MEDIA_ID]
    devices = [d for d in cfg.devices if not d.get("_disabled") and d.get("id") == MEDIA_ID]
    return (len(blocks) == len(devices) == 1 and blocks[0].get("filename") == str(iso)
            and blocks[0].get("read-only") is True and devices[0].get("drive") == MEDIA_ID
            and devices[0].get("driver") == "ide-cd")


def prepare(cfg, progress=lambda *_: None):
    if cfg.profile != "macos":
        raise ValueError("The offline NVIDIA installer belongs to the Mac profile.")
    opencore.stopped()
    before = copy.deepcopy(cfg.data)
    progress(5, "Verifying the local installer disc and supported GPU table")
    iso, record, ids = bundle(cfg)
    card = selected_gpu(cfg, ids)
    if prepared(cfg, iso, record["sha256"]):
        progress(100, "This preset already has the offline installer and separate boot files")
        return Path(cfg.data["_meta"]["nvidia_offline"]["directory"])
    if any(b.get("node-name") == MEDIA_ID for b in cfg.blockdevs) or any(d.get("id") == MEDIA_ID for d in cfg.devices):
        raise ValueError("This preset contains a changed NVIDIA installer attachment. Restore its previous "
                         "setup or remove that attachment before preparing another copy.")
    bus = free_sata_bus(cfg)
    progress(20, "Checking the selected writable OpenCore disk and private NVRAM")
    snapshot = opencore.inspect(cfg)
    root = Path(cfg.root).resolve() / "macos/nvidia-setups"
    if root.is_symlink() or not root.resolve().is_relative_to(Path(cfg.root).resolve()):
        raise ValueError("Keep NVIDIA setup copies inside this vmstart2 installation.")
    root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".staging-", dir=root))
    final = root / uuid.uuid4().hex
    try:
        progress(40, "Copying OpenCore and NVRAM into a separate setup")
        image, variables = stage / "OpenCore.img", stage / "OVMF_VARS.fd"
        opencore.run("cp", "--reflink=auto", "--sparse=always", "--no-clobber", snapshot.image, image)
        shutil.copyfile(snapshot.variables, variables)
        if opencore.sha(image) != snapshot.image_hash or opencore.sha(variables) != snapshot.vars_hash:
            raise ValueError("A boot-file copy failed checksum verification.")
        if opencore.partition(image) != (snapshot.offset, snapshot.length):
            raise ValueError("The copied OpenCore partition table failed verification.")
        progress(70, "Recording the previous setup and attaching the verified installer disc")
        new = copy.deepcopy(before)
        for block in new["blockdevs"]:
            if block.get("node-name") == snapshot.image_node:
                block["filename"] = str(final / image.name)
            elif block.get("node-name") == snapshot.vars_node:
                block["filename"] = str(final / variables.name)
        new["blockdevs"].append({"driver": "file", "filename": str(iso), "node-name": MEDIA_ID, "read-only": True})
        new["devices"].append({"driver": "ide-cd", "drive": MEDIA_ID, "id": MEDIA_ID, "bus": bus})
        meta = new.setdefault("_meta", {})
        meta.setdefault("writable_opencore", {}).update(image=str(final / image.name), nvram=str(final / variables.name))
        (stage / "preset-before.json").write_text(json.dumps(before, indent=2) + "\n")
        meta["nvidia_offline"] = dict(version=VERSION, directory=str(final), image=str(final / image.name),
                                      nvram=str(final / variables.name), iso=str(iso), iso_sha256=record["sha256"],
                                      gpu=card, rollback_sha256=opencore.sha(stage / "preset-before.json"))
        (stage / "preset-after.json").write_text(json.dumps(new, indent=2) + "\n")
        (stage / "manifest.json").write_text(json.dumps(dict(
            source_image=str(snapshot.image), source_image_sha256=snapshot.image_hash,
            source_nvram=str(snapshot.variables), source_nvram_sha256=snapshot.vars_hash,
            iso_sha256=record["sha256"], gpu=card), indent=2) + "\n")
        opencore.check_snapshot(cfg, snapshot)
        if cfg.data != before or selected_gpu(cfg, ids) != card:
            raise ValueError("The preset or selected GPU changed during preparation; nothing was applied.")
        opencore._fsync_tree(stage)
        stage.rename(final)
        opencore._fsync_directory(root)
        cfg.data.clear()
        cfg.data.update(new)
        progress(100, "Installer prepared. Save current setup, then run Install-NVIDIA.command inside macOS")
        return final
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def restore(cfg):
    """Restore only the recorded preset, never overwrite boot files or guest OS data."""
    if cfg.profile != "macos":
        raise ValueError("Select the Mac profile first.")
    opencore.stopped()
    meta = cfg.data.get("_meta", {}).get("nvidia_offline", {})
    directory = Path(meta.get("directory", ""))
    root = Path(cfg.root).resolve() / "macos/nvidia-setups"
    if (root.is_symlink() or not root.resolve().is_relative_to(Path(cfg.root).resolve())
            or directory.is_symlink() or not directory.resolve().is_relative_to(root.resolve())):
        raise ValueError("No local NVIDIA setup backup is selected.")
    backup = opencore.regular(directory / "preset-before.json", 4 * 1024**2)
    if opencore.sha(backup) != meta.get("rollback_sha256"):
        raise ValueError("The previous preset failed checksum verification.")
    from model import VMConfig
    old = VMConfig(json.loads(backup.read_text()), root=cfg.root)
    opencore.media(old)  # The previous boot files must still be present.
    cfg.data.clear()
    cfg.data.update(old.data)
