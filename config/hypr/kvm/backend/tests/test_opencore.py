"""Boot-image transactions use disposable GPT/FAT files, never the user's disks."""

import copy
import json
from pathlib import Path
import plistlib
import shutil
import struct
import sys
import uuid
import zlib

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import opencore as oc
from model import VMConfig


def make_disk(path, esp):
    sectors, start, end = 131072, 2048, 129023
    entries = bytearray(128 * 128)
    entries[:16] = oc.ESP_GUID
    entries[16:32] = uuid.uuid4().bytes_le
    struct.pack_into("<QQ", entries, 32, start, end)
    identity = uuid.uuid4().bytes_le
    def header(lba, other, table):
        raw = bytearray(512)
        struct.pack_into("<8sIIIIQQQQ16sQIII", raw, 0, b"EFI PART", 0x10000, 92, 0, 0,
                         lba, other, 34, sectors - 34, identity, table, 128, 128, zlib.crc32(entries))
        struct.pack_into("<I", raw, 16, zlib.crc32(raw[:92]))
        return raw
    with path.open("wb") as stream:
        stream.truncate(sectors * 512)
        mbr = bytearray(512)
        mbr[450] = 0xee
        struct.pack_into("<II", mbr, 454, 1, sectors - 1)
        mbr[510:] = b"\x55\xaa"
        stream.write(mbr)
        stream.write(header(1, sectors - 1, 2))
        stream.write(entries)
        stream.seek(start * 512)
        with esp.open("rb") as source:
            shutil.copyfileobj(source, stream)
        stream.seek((sectors - 33) * 512)
        stream.write(entries)
        stream.write(header(sectors - 1, 1, sectors - 33))


@pytest.fixture
def disk(tmp_path, monkeypatch):
    for tool in ("mkfs.fat", "mcopy", "mtype", "fsck.fat", "cp"):
        if not shutil.which(tool):
            pytest.skip(f"Image integration test requires {tool}")
    monkeypatch.setattr(oc, "stopped", lambda: None)
    tree = tmp_path / "tree"
    for folder in ("BOOT", "OC/Drivers", "OC/Kexts/Test.kext/Contents/MacOS", "OC/ACPI", "OC/Tools"):
        (tree / "EFI" / folder).mkdir(parents=True, exist_ok=True)
    files = {"EFI/BOOT/BOOTx64.efi": b"boot binary", "EFI/OC/OpenCore.efi": b"test OpenCore binary",
             "EFI/OC/Drivers/OpenRuntime.efi": b"runtime binary", "EFI/OC/ACPI/Test.aml": b"ACPI",
             "EFI/OC/Kexts/Test.kext/Contents/MacOS/Test": b"test executable",
             "EFI/OC/Kexts/Test.kext/Contents/Info.plist": plistlib.dumps({"CFBundleIdentifier": "test"}),
             "EFI/OC/Tools/Test.efi": b"tool", "EFI/OC/preserve.bin": bytes(range(256))}
    for name, value in files.items():
        (tree / name).write_bytes(value)
    (tree / "nvram-backup.txt").write_text("Preserve files outside EFI too.")
    config = {
        "#Comment": "Preserve this comment without presenting it as a setting.",
        "ACPI": {"Add": [{"Enabled": True, "Path": "Test.aml"}]}, "Booter": {},
        "Kernel": {"Add": [{"Enabled": True, "BundlePath": "Test.kext",
                            "PlistPath": "Contents/Info.plist", "ExecutablePath": "Contents/MacOS/Test"}]},
        "Misc": {"Boot": {"Timeout": 8, "ShowPicker": True}, "Security": {"SecureBootModel": "Disabled", "Vault": "Optional"},
                 "Tools": [{"Enabled": True, "Path": "Test.efi"}]},
        "NVRAM": {"Add": {oc.APPLE_GUID: {"boot-args": "-v custom=keep", "csr-active-config": b"\x43\x0a\0\0"}},
                  "Delete": {oc.APPLE_GUID: []}},
        "PlatformInfo": {"CustomMemory": True, "Memory": {"Devices": [{"Size": 1024}, {"Size": 1024}]},
                         "Generic": {"SystemProductName": "iMac20,1", "SystemSerialNumber": "TESTSERIAL",
                                     "MLB": "TESTMLB", "ROM": b"\x11\x22\x33\x44\x55\x66",
                                     "SystemUUID": str(uuid.uuid4())}},
        "UEFI": {"Drivers": [{"Enabled": True, "Path": "OpenRuntime.efi"}]},
        "UnknownFutureKey": {"Boolean": True, "Bytes": b"\0\xff", "Number": 17},
    }
    (tree / oc.CONFIG).write_bytes(plistlib.dumps(config, sort_keys=False))
    bundle = tmp_path / "validators/test"
    bundle.mkdir(parents=True)
    validator = bundle / "ocvalidate"
    validator.write_text("#!/bin/sh\nprintf 'Test schema accepted\\n'\n")
    validator.chmod(0o755)
    (bundle / "manifest.json").write_text(json.dumps({
        "version": "test", "opencore_sha256": oc.sha(tree / "EFI/OC/OpenCore.efi"),
        "ocvalidate_sha256": oc.sha(validator)}))
    esp = tmp_path / "esp.img"
    with esp.open("wb") as stream:
        stream.truncate((129023 - 2048 + 1) * 512)
    oc.run("mkfs.fat", "-F", "32", esp)
    oc.run("mcopy", "-s", "-i", esp, tree / "EFI", tree / "nvram-backup.txt", "::/")
    image, variables = tmp_path / "source.img", tmp_path / "vars.fd"
    make_disk(image, esp)
    variables.write_bytes(b"unchanged test variable store")
    cfg = VMConfig({"_meta": {"profile": "macos"}, "tools": {"opencore_validators": str(bundle.parent)},
                    "objects": [{"id": "pc.ram", "size": 2 * 1024**3}],
                    "devices": [{"id": "opencore-boot", "driver": "ide-hd", "drive": "oc"}],
                    "blockdevs": [{"driver": "file", "node-name": "oc", "filename": str(image)},
                                  {"driver": "file", "node-name": "libvirt-pflash1-storage", "filename": str(variables)}]}, root=tmp_path)
    return cfg, tree, bundle


def edit(snapshot):
    config = copy.deepcopy(snapshot.config)
    config["Misc"]["Boot"]["Timeout"] = 5
    return config


def test_publish_checks_real_fat_and_preserves_source_and_unknown_values(disk):
    cfg, tree, _ = disk
    before = copy.deepcopy(cfg.data)
    snap = oc.inspect(cfg)
    config = edit(snap)
    config["NVRAM"]["Add"][oc.APPLE_GUID]["boot-args"] += " nvrmsettle=10000"
    events = []
    version = oc.publish(cfg, snap, config, lambda n, message: events.append(n))
    after = oc.inspect(cfg)
    assert events == [10, 25, 40, 60, 80, 100]
    assert oc.sha(snap.image) == snap.image_hash
    assert oc.sha(snap.variables) == snap.vars_hash
    assert after.image.parent == after.variables.parent == version
    assert after.config == oc.prepare_changes(snap.config, config)
    assert after.config["UnknownFutureKey"] == snap.config["UnknownFutureKey"]
    assert after.vars_hash == snap.vars_hash
    assert json.loads((version / "preset-before.json").read_text()) == before
    assert "boot-args" in after.config["NVRAM"]["Delete"][oc.APPLE_GUID]
    assert "Test schema accepted" in (version / "validation.txt").read_text()
    assert not list(version.parent.glob(".staging-*"))
    oc.rollback(cfg)
    assert cfg.data == before


@pytest.mark.parametrize("failure", ["validator", "write", "fat", "changed-preset", "changed-source", "publish"])
def test_failed_transaction_never_selects_new_paths_or_changes_boot_files(disk, monkeypatch, failure):
    cfg, _, bundle = disk
    before = copy.deepcopy(cfg.data)
    snap = oc.inspect(cfg)
    original_run = oc.run
    if failure == "validator":
        (bundle / "ocvalidate").write_text("#!/bin/sh\nexit 1\n")
        record = json.loads((bundle / "manifest.json").read_text())
        record["ocvalidate_sha256"] = oc.sha(bundle / "ocvalidate")
        (bundle / "manifest.json").write_text(json.dumps(record))
    def fail_run(*args, **kwargs):
        if failure == "write" and args[:2] == ("mcopy", "-o"):
            raise ValueError("Injected IO failure")
        return original_run(*args, **kwargs)
    monkeypatch.setattr(oc, "run", fail_run)
    if failure == "fat":
        monkeypatch.setattr(oc, "_check_fat_copy", lambda *_: (_ for _ in ()).throw(ValueError("Injected FAT failure")))
    if failure == "publish":
        monkeypatch.setattr(Path, "rename", lambda *_: (_ for _ in ()).throw(OSError("Injected rename failure")))
    def progress(n, _message):
        if n == 80 and failure == "changed-preset":
            cfg.data["external-change"] = True
        if n == 80 and failure == "changed-source":
            snap.variables.write_bytes(b"external change")
    with pytest.raises((ValueError, OSError)):
        oc.publish(cfg, snap, edit(snap), progress)
    assert cfg.blockdevs == before["blockdevs"]
    assert oc.sha(snap.image) == snap.image_hash
    assert snap.variables.read_bytes() == (b"external change" if failure == "changed-source" else b"unchanged test variable store")
    assert not list((Path(cfg.root) / "macos/opencore-versions").iterdir())


@pytest.mark.parametrize("offset", [512 + 16, 1024 + 18, 64 * 1024**2 - 512 + 16])
def test_corrupt_gpt_is_rejected(disk, offset):
    cfg, *_ = disk
    image = oc.media(cfg)[1]
    with image.open("r+b") as stream:
        stream.seek(offset)
        old = stream.read(1)
        stream.seek(offset)
        stream.write(bytes([old[0] ^ 1]))
    with pytest.raises(ValueError, match="checksum"):
        oc.inspect(cfg)


@pytest.mark.parametrize("field,value,message", [
    ("Driver", "../outside.efi", "Invalid EFI path"),
    ("Kext", "Missing.kext", "has no file"),
    ("RAM", 999, "Sync memory"),
    ("SIP", b"\0", "four bytes"),
    ("ROM", b"\0", "six bytes"),
    ("Args", "-v\nnew", "one line"),
    ("Args", "nvrmsettle=bad", "milliseconds"),
    ("Vault", "Secure", "cannot sign"),
])
def test_invalid_edits_are_rejected(disk, field, value, message):
    cfg, tree, _ = disk
    config = copy.deepcopy(oc.inspect(cfg).config)
    if field == "Driver": config["UEFI"]["Drivers"][0]["Path"] = value
    if field == "Kext": config["Kernel"]["Add"][0]["BundlePath"] = value
    if field == "RAM": config["PlatformInfo"]["Memory"]["Devices"][0]["Size"] = value
    if field == "SIP": config["NVRAM"]["Add"][oc.APPLE_GUID]["csr-active-config"] = value
    if field == "ROM": config["PlatformInfo"]["Generic"]["ROM"] = value
    if field == "Args": config["NVRAM"]["Add"][oc.APPLE_GUID]["boot-args"] = value
    if field == "Vault": config["Misc"]["Security"]["Vault"] = value
    with pytest.raises(ValueError, match=message):
        oc.validate(config, tree, cfg)


@pytest.mark.parametrize("target", ["EFI/OC/OpenCore.efi", "validator"])
def test_validator_must_match_both_binaries(disk, target):
    cfg, tree, bundle = disk
    config = oc.inspect(cfg).config
    (bundle / "ocvalidate" if target == "validator" else tree / target).write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum mismatch|No validator matches"):
        oc.validate(config, tree, cfg)


@pytest.mark.parametrize("capacity", [None, 2 * 1024**3, 64 * 1024**3])
def test_memory_sync_preserves_slot_identity_and_valid_capacity(disk, capacity):
    cfg, *_ = disk
    config = oc.inspect(cfg).config
    memory = config["PlatformInfo"]["Memory"]
    if capacity is not None:
        memory["MaxCapacity"] = capacity
    for index, device in enumerate(memory["Devices"]):
        device.update(Speed=2400, SerialNumber=f"slot-{index}")
    before = copy.deepcopy(memory["Devices"])
    cfg.objects[0]["size"] = 3 * 1024**3
    oc.sync_memory(config, cfg)
    assert [d["Size"] for d in config["PlatformInfo"]["Memory"]["Devices"]] == [1536, 1536]
    assert memory["MaxCapacity"] == max(capacity or 0, 3 * 1024**3)
    for old, new in zip(before, memory["Devices"]):
        assert {k: v for k, v in old.items() if k != "Size"} == {k: v for k, v in new.items() if k != "Size"}
    # Reducing the installed RAM must not erase the existing capacity limit.
    cfg.objects[0]["size"] = 2 * 1024**3
    oc.sync_memory(config, cfg)
    assert memory["MaxCapacity"] == max(capacity or 0, 3 * 1024**3)
    assert "Matched." in oc.memory_note(config, cfg)


def test_dirty_fat_metadata_is_repaired_only_on_the_copy(disk):
    cfg, *_ = disk
    image = oc.media(cfg)[1]
    offset, _ = oc.partition(image)
    with image.open("r+b") as stream:
        stream.seek(offset + 65)  # FAT32 dirty flag
        stream.write(b"\x01")
        stream.seek(offset + 512 + 488)  # FAT32 free-space hint
        stream.write(struct.pack("<I", 0))
    snap = oc.inspect(cfg)
    version = oc.publish(cfg, snap, edit(snap))
    assert oc.sha(image) == snap.image_hash
    assert "NEW copy only" in (version / "validation.txt").read_text()
    assert oc.inspect(cfg).config["Misc"]["Boot"]["Timeout"] == 5


def test_filesystem_repair_cannot_change_other_files(disk, monkeypatch):
    cfg, *_ = disk
    snap = oc.inspect(cfg)
    before = copy.deepcopy(cfg.data)
    corrupt = Path(cfg.root) / "changed.txt"
    corrupt.write_text("Unexpected repair data")
    check = oc._check_fat_copy
    def damage(esp):
        report = check(esp)
        oc.run("mcopy", "-o", "-i", esp, corrupt, "::/nvram-backup.txt")
        return report
    monkeypatch.setattr(oc, "_check_fat_copy", damage)
    with pytest.raises(ValueError, match="other than config.plist"):
        oc.publish(cfg, snap, edit(snap))
    assert cfg.data == before
    assert oc.sha(snap.image) == snap.image_hash


def test_stale_paths_readonly_symlink_and_disk_device_are_rejected(disk):
    cfg, *_ = disk
    snap = oc.inspect(cfg)
    link = Path(cfg.root) / "link.img"
    link.symlink_to(snap.image)
    for path in (str(link), "/dev/null"):
        cfg.blockdevs[0]["filename"] = path
        with pytest.raises(ValueError, match="regular image"):
            oc.media(cfg)
    cfg.blockdevs[0]["filename"] = str(snap.image)
    cfg.blockdevs[0]["read-only"] = True
    with pytest.raises(ValueError, match="writable raw"):
        oc.media(cfg)
    cfg.blockdevs[0].pop("read-only")
    new_path = Path(cfg.root) / "replacement.img"
    shutil.copyfile(snap.image, new_path)
    cfg.blockdevs[0]["filename"] = str(new_path)
    with pytest.raises(ValueError, match="Boot paths changed"):
        oc.publish(cfg, snap, edit(snap))


@pytest.mark.parametrize("target", ["preset", "image", "variables"])
def test_rollback_refuses_changed_backups(disk, target):
    cfg, *_ = disk
    snap = oc.inspect(cfg)
    version = oc.publish(cfg, snap, edit(snap))
    selected = copy.deepcopy(cfg.data)
    if target == "preset":
        (version / "preset-before.json").write_text("{}")
    elif target == "variables":
        snap.variables.write_bytes(b"external change")
    else:
        with snap.image.open("r+b") as stream:
            stream.write(b"changed unused MBR bytes")
    with pytest.raises(ValueError, match="changed"):
        oc.rollback(cfg)
    assert cfg.data == selected


def test_running_qemu_blocks_inspection(tmp_path, monkeypatch):
    comm = tmp_path / "comm"
    comm.write_text("qemu-system-x86")
    monkeypatch.setattr(Path, "glob", lambda *_: [comm])
    with pytest.raises(ValueError, match="Shut down"):
        oc.stopped()
