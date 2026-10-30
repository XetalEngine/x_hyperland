"""Disk removal regressions using synthetic configs and disposable image files."""

import copy
import json
import os
from pathlib import Path
import sys
import uuid

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtTest import QSignalSpy
from PyQt6.QtWidgets import QApplication, QLabel

import hostinfo
import model
from tabs_disks import DisksTab


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def make_tab(app, monkeypatch, tmp_path):
    monkeypatch.setattr(hostinfo, "block_devices", lambda: [])
    monkeypatch.setattr(hostinfo, "block_device_labels", lambda: {})
    tabs = []

    def create(sata=(), namespaces=(), profile="windows"):
        cfg = model.VMConfig({
            "_meta": {"binary": "/test/qemu", "profile": profile},
            "machine": {"type": "q35", "opts": {}},
        })
        for bus in dict.fromkeys(port.rsplit(".", 1)[0] for port in sata):
            if bus != "ide":
                cfg.devices.append({"driver": "ich9-ahci", "id": bus})
        for ctrl in dict.fromkeys(ctrl for ctrl, _ in namespaces):
            cfg.devices.append({"driver": "nvme", "id": ctrl, "serial": ctrl + "-SERIAL"})
        specs = ([dict(driver="ide-hd", bus=port) for port in sata]
                 + [dict(driver="nvme-ns", bus=ctrl, nsid=nsid) for ctrl, nsid in namespaces])
        for n, spec in enumerate(specs, 1):
            image = tmp_path / f"disk-{len(tabs)}-{n}.img"
            image.write_bytes(bytes(4096))
            node = f"vmstart2-{n}-storage"
            cfg.blockdevs.append({"driver": "file", "filename": str(image), "node-name": node})
            dev = dict(spec, id=f"vmstart2-disk{n}", drive=node, bootindex=n)
            if dev["driver"] == "nvme-ns":
                dev["uuid"] = str(uuid.UUID(int=n))
            else:
                dev["serial"] = f"SERIAL{n}"
            cfg.devices.append(dev)
        cfg.data["order"] = ([["machine", None]]
                             + [["blockdev", i] for i in range(len(cfg.blockdevs))]
                             + [["device", i] for i in range(len(cfg.devices))])
        tab = DisksTab(cfg)
        tabs.append(tab)
        return tab

    yield create
    for tab in tabs:
        tab.deleteLater()
    app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def emitted(cfg, flag):
    argv = cfg.to_argv()
    return [json.loads(argv[i + 1]) for i, value in enumerate(argv[:-1]) if value == flag]


def assert_round_trip(cfg, tmp_path):
    before = cfg.to_argv()
    cfg.compact()
    path = tmp_path / "saved.json"
    cfg.save(str(path))
    assert model.VMConfig.load(path).to_argv() == before


@pytest.mark.parametrize("removed_port", range(6))
def test_sata_remove_moves_only_highest_port_and_keeps_disk_identity(make_tab, tmp_path, removed_port):
    tab = make_tab(sata=[f"ide.{n}" for n in range(6)], namespaces=[("nvme0", 1)])
    cfg = tab.cfg
    before = copy.deepcopy(cfg.data)
    devices = list(cfg.devices)
    backends = list(cfg.blockdevs)
    removed = next(row for row in tab.rows if row.dev.get("bus") == f"ide.{removed_port}")
    changes = QSignalSpy(tab.changed)

    removed.btn_remove.click()

    expected = before
    expected["blockdevs"][removed_port]["_disabled"] = True
    expected["devices"][removed_port + 1]["_disabled"] = True
    if removed_port < 5:
        expected["devices"][6]["bus"] = f"ide.{removed_port}"
    assert cfg.data == expected
    assert all(a is b for a, b in zip(cfg.devices, devices))
    assert all(a is b for a, b in zip(cfg.blockdevs, backends))
    assert len(changes) == 1
    assert [row.busline.text() for row in tab.rows if row.dev["driver"] == "ide-hd"] == [
        f"ide.{n}" for n in range(5)]
    assert tab.lbl_count.text() == "6 disks"
    assert tab.warn.toPlainText() == "No disk problems found."
    assert removed.dev["id"] not in {d.get("id") for d in emitted(cfg, "-device")}
    assert removed.bd["node-name"] not in {b["node-name"] for b in emitted(cfg, "-blockdev")}
    assert_round_trip(cfg, tmp_path)


@pytest.mark.parametrize("removed_nsid", [1, 2, 3, 10])
def test_nvme_removal_uses_highest_numeric_namespace_on_same_controller(make_tab, tmp_path, removed_nsid):
    tab = make_tab(sata=["ide.0"], namespaces=[("nvme0", n) for n in (3, 10, 2, 1)] + [("nvme1", 20)])
    cfg = tab.cfg
    before = copy.deepcopy(cfg.data)
    removed = next(row for row in tab.rows
                   if row.dev.get("bus") == "nvme0" and row.dev.get("nsid") == removed_nsid)
    highest = next(row for row in tab.rows if row.dev.get("nsid") == 10)
    expected = before
    expected["blockdevs"][cfg.blockdevs.index(removed.bd)]["_disabled"] = True
    expected["devices"][cfg.devices.index(removed.dev)]["_disabled"] = True
    if removed_nsid < 10:
        expected["devices"][cfg.devices.index(highest.dev)]["nsid"] = removed_nsid

    removed.btn_remove.click()

    assert cfg.data == expected
    rows = [row for row in tab.rows if row.dev.get("bus") == "nvme0"]
    assert [row.nsid.value() for row in rows] == [1, 2, 3]
    summary = ", ".join(f"{row.dev['id']} (ns{row.dev['nsid']})" for row in rows)
    assert summary in [label.text() for label in tab.ctrl_cards[0].findChildren(QLabel)]
    assert next(row for row in tab.rows if row.dev.get("bus") == "nvme1").nsid.value() == 20
    argv_devs = emitted(cfg, "-device")
    ctrl_index = next(i for i, dev in enumerate(argv_devs) if dev.get("id") == "nvme0")
    assert all(i > ctrl_index for i, dev in enumerate(argv_devs) if dev.get("bus") == "nvme0")
    assert_round_trip(cfg, tmp_path)


@pytest.mark.parametrize("optical", ["removed", "replacement"])
def test_named_sata_controller_includes_optical_drives_and_stays_separate(make_tab, optical):
    tab = make_tab(sata=["ide.5", "sata.0", "sata.1", "sata.2"], profile="macos")
    removed = next(row for row in tab.rows if row.dev.get("bus") == "sata.1")
    replacement = next(row for row in tab.rows if row.dev.get("bus") == "sata.2")
    (removed if optical == "removed" else replacement).dev["driver"] = "ide-cd"
    before = copy.deepcopy(replacement.dev)
    tab.remove_disk(removed)
    assert replacement.dev == dict(before, bus="sata.1")
    assert [row.busline.text() for row in tab.rows] == ["ide.5", "sata.0", "sata.1"]
    assert next(row for row in tab.rows if row.dev is replacement.dev).frontend.currentText() == before["driver"]


@pytest.mark.parametrize("family", ["sata", "nvme"])
def test_disabled_highest_slot_is_not_reused(make_tab, family):
    tab = (make_tab(sata=["ide.0", "ide.1", "ide.2"])
           if family == "sata" else make_tab(namespaces=[("nvme0", n) for n in (1, 2, 3)]))
    removed, replacement, disabled = tab.rows
    disabled.dev["_disabled"] = disabled.bd["_disabled"] = True
    before = copy.deepcopy(disabled.dev)
    tab.remove_disk(removed)
    assert disabled.dev == before
    assert len(tab.rows) == 1
    assert tab.rows[0].dev is replacement.dev
    assert model.disk_slot(replacement.dev)[1] == (0 if family == "sata" else 1)


@pytest.mark.parametrize("compact", [False, True])
def test_repeated_remove_and_add_keeps_slots_sorted_and_references_valid(make_tab, tmp_path, compact):
    tab = make_tab(sata=["ide.0", "ide.1", "ide.2", "ide.3"])
    for cycle in range(6):
        tab.rows[1].btn_remove.click()
        if compact:
            tab.cfg.compact()
        tab.add_disk()
        new = next(row for row in tab.rows if not row.bd.get("filename"))
        path = tmp_path / f"added-{cycle}.img"
        path.write_bytes(bytes(4096))
        new.bd.update(driver="file", filename=str(path))
        tab.reload()
        assert [row.busline.text() for row in tab.rows] == [f"ide.{n}" for n in range(4)]
        assert [tab.grid.getItemPosition(tab.grid.indexOf(row))[:2] for row in tab.rows] == sorted(
            tab.grid.getItemPosition(tab.grid.indexOf(row))[:2] for row in tab.rows)
        devices = emitted(tab.cfg, "-device")
        blocks = emitted(tab.cfg, "-blockdev")
        assert len({dev["id"] for dev in devices}) == len(devices) == 4
        assert len({bd["node-name"] for bd in blocks}) == len(blocks) == 4
        assert {dev["drive"] for dev in devices} == {bd["node-name"] for bd in blocks}
        assert tab.warn.toPlainText() == "No disk problems found."
    assert_round_trip(tab.cfg, tmp_path)


@pytest.mark.parametrize("device", [
    dict(driver="ide-hd", bus=""),
    dict(driver="ide-hd", bus="ide.invalid"),
    dict(driver="nvme-ns", bus="nvme0", nsid=None),
    dict(driver="nvme-ns", bus="nvme0", nsid="invalid"),
    dict(driver="nvme-ns", bus="nvme0", nsid=0),
    dict(driver="virtio-blk-pci", bus="pcie.0"),
])
def test_unassigned_or_other_frontend_removal_does_not_move_disks(device):
    remaining = [dict(driver="ide-hd", bus="ide.5"), dict(driver="nvme-ns", bus="nvme0", nsid=9)]
    before = copy.deepcopy(remaining)
    model.fill_removed_disk_slot([device, *remaining], device)
    assert remaining == before


def test_shared_ide_bus_is_not_treated_as_vacant():
    removed = dict(driver="ide-hd", bus="ide.0", unit=0, _disabled=True)
    remaining = [dict(driver="ide-hd", bus="ide.0", unit=1), dict(driver="ide-hd", bus="ide.1", unit=0)]
    before = copy.deepcopy(remaining)
    model.fill_removed_disk_slot([removed, *remaining], removed)
    assert remaining == before
