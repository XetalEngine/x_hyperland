"""Offline driver preparation only uses disposable boot images and fake PCI identities."""
import copy
import json
from pathlib import Path

import pytest

from test_opencore import disk
from test_opencore_ui import editor
from test_ui_navigation import app, settle
import nvidia_offline as nv
import opencore as oc


@pytest.fixture
def setup(disk, monkeypatch):
    cfg, *_ = disk
    cfg.data["machine"] = {"type": "q35"}
    cfg.devices[0]["bus"] = "ide.0"
    cfg.devices.extend([{"driver": "vfio-pci", "host": "0000:01:00.0"},
                        {"driver": "vfio-pci", "host": "0000:01:00.1"}])
    monkeypatch.setattr(nv.gpu_inventory, "identity", lambda slot: {"vendor": "0x10de", "device": "0x2684"})
    monkeypatch.setattr(nv.gpu_inventory, "pci_class", lambda slot: 0x030000 if slot.endswith(".0") else 0x040300)
    root = Path(cfg.root) / "macos/NVIDIA-Offline"
    payload = root / "Payloads/2.5.3"
    payload.mkdir(parents=True)
    catalog = payload / "nvidia_gsp_ids.json"
    catalog.write_text(json.dumps({"ids": {"2684": "GeForce RTX 4090"}}))
    archive = root / "archive.json"
    archive.write_text(json.dumps({"version": nv.VERSION, "files": {str(catalog.relative_to(root)): oc.sha(catalog)}}))
    iso = root / "test.iso"
    iso.write_bytes(b"disposable installer payload")
    (root / "media.json").write_text(json.dumps({"version": nv.VERSION, "archive_sha256": oc.sha(archive),
                                                "iso": iso.name, "sha256": oc.sha(iso)}))
    return cfg, root


def test_prepare_copies_and_checks_boot_files_attaches_readonly_disc_and_restores(setup):
    cfg, root = setup
    before = copy.deepcopy(cfg.data)
    original = oc.inspect(cfg)
    events = []
    directory = nv.prepare(cfg, lambda n, _: events.append(n))
    current = oc.inspect(cfg)
    assert events == [5, 20, 40, 70, 100]
    assert current.image != original.image and current.variables != original.variables
    assert current.image.parent == current.variables.parent == directory
    assert oc.sha(original.image) == current.image_hash == original.image_hash
    assert oc.sha(original.variables) == current.vars_hash == original.vars_hash
    assert current.config == original.config
    device = next(d for d in cfg.devices if d.get("id") == nv.MEDIA_ID)
    assert device == dict(driver="ide-cd", drive=nv.MEDIA_ID, id=nv.MEDIA_ID, bus="ide.1")
    block = next(b for b in cfg.blockdevs if b["node-name"] == nv.MEDIA_ID)
    assert block["read-only"] is True and block["filename"] == str(root / "test.iso")
    assert json.loads((directory / "preset-before.json").read_text()) == before
    prepared = copy.deepcopy(cfg.data)
    assert nv.prepare(cfg) == directory and cfg.data == prepared
    assert list(directory.parent.iterdir()) == [directory]
    nv.restore(cfg)
    assert cfg.data == before
    assert current.image.exists()  # restoration never deletes a boot version


@pytest.mark.parametrize("failure", ["copy", "changed-preset", "changed-source", "publish", "fsync"])
def test_failed_prepare_never_selects_partial_setup(setup, monkeypatch, failure):
    cfg, _ = setup
    original = oc.inspect(cfg)
    before = copy.deepcopy(cfg.data)
    def fail(*_):
        raise OSError("simulated failure")
    if failure == "copy":
        monkeypatch.setattr(nv.shutil, "copyfile", fail)
    if failure == "publish":
        monkeypatch.setattr(Path, "rename", fail)
    if failure == "fsync":
        monkeypatch.setattr(oc, "_fsync_tree", fail)
    def progress(n, _):
        if n == 70 and failure == "changed-preset":
            cfg.data["user-change"] = True
        if n == 70 and failure == "changed-source":
            original.variables.write_bytes(b"externally modified")
    with pytest.raises((ValueError, OSError)):
        nv.prepare(cfg, progress)
    expected = dict(before)
    if failure == "changed-preset":
        expected["user-change"] = True
    assert cfg.data == expected
    assert not list((Path(cfg.root) / "macos/nvidia-setups").iterdir())
    assert oc.sha(original.image) == original.image_hash
    if failure != "changed-source":
        assert oc.sha(original.variables) == original.vars_hash


@pytest.mark.parametrize("failure", ["running", "windows", "old-gpu", "no-gpu", "two-gpus", "missing-disc", "corrupt-disc",
                                     "corrupt-catalog", "archive-changed", "disc-escape", "ports-full", "implicit-bus", "id-collision"])
def test_preparation_refuses_incompatible_or_incomplete_setups(setup, monkeypatch, failure):
    cfg, root = setup
    if failure == "running":
        monkeypatch.setattr(oc, "stopped", lambda: (_ for _ in ()).throw(ValueError("running VM")))
    elif failure == "windows":
        cfg.data["_meta"]["profile"] = "windows"
    elif failure == "old-gpu":
        monkeypatch.setattr(nv.gpu_inventory, "identity", lambda _: {"vendor": "0x10de", "device": "0x1b80"})
    elif failure == "no-gpu":
        cfg.devices[:] = cfg.devices[:1]
    elif failure == "two-gpus":
        cfg.devices.append({"driver": "vfio-pci", "host": "0000:02:00.0"})
    elif failure == "missing-disc":
        (root / "test.iso").unlink()
    elif failure == "corrupt-disc":
        (root / "test.iso").write_bytes(b"corrupt")
    elif failure == "corrupt-catalog":
        (root / "Payloads/2.5.3/nvidia_gsp_ids.json").write_text("{}")
    elif failure == "archive-changed":
        (root / "archive.json").write_text("{}")
    elif failure == "disc-escape":
        p = root / "media.json"
        data = json.loads(p.read_text()); data["iso"] = "../../source.img"
        p.write_text(json.dumps(data))
    elif failure == "ports-full":
        cfg.devices.extend({"driver": "ide-hd", "bus": f"ide.{n}"} for n in range(1, 6))
    elif failure == "implicit-bus":
        cfg.devices[0].pop("bus")
    elif failure == "id-collision":
        cfg.devices.append({"id": nv.MEDIA_ID, "driver": "ide-hd"})
    before = copy.deepcopy(cfg.data)
    with pytest.raises(ValueError):
        nv.prepare(cfg)
    assert cfg.data == before
    assert not (Path(cfg.root) / "macos/nvidia-setups").exists()


def test_extra_ahci_controller_gets_its_own_free_port(setup):
    cfg, _ = setup
    cfg.devices.extend({"driver": "ide-hd", "bus": f"ide.{n}"} for n in range(1, 6))
    cfg.devices.append({"driver": "ich9-ahci", "id": "sata"})
    assert nv.free_sata_bus(cfg) == "sata.0"


def test_corrupt_rollback_is_refused(setup):
    cfg, _ = setup
    directory = nv.prepare(cfg)
    (directory / "preset-before.json").write_text("{}")
    before = copy.deepcopy(cfg.data)
    with pytest.raises(ValueError, match="checksum"):
        nv.restore(cfg)
    assert cfg.data == before


def test_gui_preserves_pending_opencore_edits(editor, monkeypatch):
    monkeypatch.setattr(nv, "prepare", lambda *_: pytest.fail("Must not prepare with pending changes"))
    editor.timeout.setValue(3)
    assert not editor.prepare_nvidia()
    assert editor.dirty and "pending" in editor.nvidia_state.text()


def test_gui_preparation_notifies_owner_and_updates_copy(setup, app, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    from tabs_opencore import OpenCoreTab
    cfg, _ = setup
    widget = OpenCoreTab(cfg)
    applied = []
    widget.applied.connect(lambda: applied.append(True))
    monkeypatch.setattr(QMessageBox, "information", lambda *_: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: pytest.fail(str(args)))
    assert widget.prepare_nvidia()
    assert applied == [True] and widget.nvidia_restore.isEnabled()
    assert not widget.dirty and not widget.busy
    widget.arguments_page.deleteLater()
    widget.deleteLater()
    settle(app)
