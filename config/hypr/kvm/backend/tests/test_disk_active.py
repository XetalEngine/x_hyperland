"""Retained inactive disks must survive saves without being opened by QEMU."""

import copy
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QSignalSpy, QTest
from PyQt6.QtWidgets import QMessageBox

from test_disk_removal import app, make_tab, emitted
from test_ui_navigation import window, settle
import model


@pytest.mark.parametrize("profile,prefix", [("windows", "ide"), ("macos", "sata")])
def test_inactive_disk_survives_save_and_returns_after_active_disks(make_tab, tmp_path, profile, prefix):
    tab = make_tab(sata=[f"{prefix}.{n}" for n in range(4)], profile=profile)
    row = tab.rows[1]
    saved_device, saved_block = copy.deepcopy(row.dev), copy.deepcopy(row.bd)
    last_device = tab.rows[-1].dev
    spy = QSignalSpy(tab.changed)
    row.active.setChecked(False)

    assert len(spy) == 1
    assert tab.rows[-1].dev is row.dev
    assert not tab.rows[-1].active.isChecked()
    assert tab.rows[-1].title().startswith("Inactive")
    assert [r.busline.text() for r in tab.rows[:-1]] == [f"{prefix}.{n}" for n in range(3)]
    assert last_device["bus"] == f"{prefix}.1"
    assert tab.lbl_count.text() == "3 active · 1 inactive"
    assert row.dev["id"] not in {dev["id"] for dev in emitted(tab.cfg, "-device")}
    assert saved_block["node-name"] not in {bd["node-name"] for bd in emitted(tab.cfg, "-blockdev")}
    assert tab.warn.toPlainText() == "No disk problems found."

    command = tab.cfg.to_argv()
    assert tab.cfg.compact() == 0
    path = tmp_path / "inactive.json"
    tab.cfg.save(path)
    tab.cfg = model.VMConfig.load(path)
    tab.reload()
    assert tab.cfg.to_argv() == command
    assert len(tab.rows) == 4
    inactive = tab.rows[-1]
    assert not inactive.active.isChecked()
    inactive.active.setChecked(True)
    assert all(r.active.isChecked() for r in tab.rows)
    assert tab.rows[-1].dev == dict(saved_device, bus=f"{prefix}.3")
    assert tab.rows[-1].bd == saved_block
    assert len(emitted(tab.cfg, "-blockdev")) == 4


def test_nvme_reactivation_keeps_controller_and_identity_and_appends_namespace(make_tab):
    tab = make_tab(sata=["ide.0"], namespaces=[("nvme0", n) for n in (1, 2, 3)] + [("nvme1", 20)])
    row = next(r for r in tab.rows if r.dev.get("bus") == "nvme0" and r.dev.get("nsid") == 1)
    device, block = copy.deepcopy(row.dev), copy.deepcopy(row.bd)
    other = copy.deepcopy(next(r.dev for r in tab.rows if r.dev.get("bus") == "nvme1"))
    row.active.setChecked(False)
    assert tab.rows[-1].dev["id"] == device["id"]
    assert [r.nsid.value() for r in tab.rows if r.active.isChecked() and r.dev.get("bus") == "nvme0"] == [1, 2]
    tab.rows[-1].active.setChecked(True)
    restored = next(r for r in tab.rows if r.dev["id"] == device["id"])
    assert restored.dev == dict(device, nsid=3)
    assert restored.bd == block
    assert next(r.dev for r in tab.rows if r.dev.get("bus") == "nvme1") == other


def test_new_disk_cannot_reuse_inactive_disk_names_or_settings(make_tab):
    tab = make_tab(sata=["ide.0", "ide.1"])
    original = tab.rows[0].dev
    tab.rows[0].active.setChecked(False)
    stored = copy.deepcopy(tab.rows[-1].dev), copy.deepcopy(tab.rows[-1].bd)
    assert model.free_index(tab.cfg.blockdevs, tab.cfg.devices) == 3
    tab.add_disk()
    assert tab.rows[-1].dev == stored[0]
    assert tab.rows[-1].bd == stored[1]
    assert {r.dev["id"] for r in tab.rows} == {f"vmstart2-disk{n}" for n in (1, 2, 3)}
    with pytest.raises(ValueError, match="inactive disk"):
        model.claim_slot(tab.cfg.devices, "id", original["id"], {"driver": "ide-hd"})
    tab.rows[-1].active.setChecked(True)
    assert tab.rows[-1].dev is original
    assert original["bus"] == "ide.2"


def test_removing_an_inactive_card_does_not_change_active_slots(make_tab):
    tab = make_tab(sata=[f"ide.{n}" for n in range(4)])
    tab.rows[1].active.setChecked(False)
    active = [copy.deepcopy(r.dev) for r in tab.rows[:-1]]
    removed = tab.rows[-1].dev
    tab.rows[-1].btn_remove.click()
    assert [r.dev for r in tab.rows] == active
    assert tab.cfg.compact() == 2
    assert all(d is not removed for d in tab.cfg.devices)


def test_inactive_cards_follow_deactivation_order_and_do_not_validate_missing_paths(make_tab):
    tab = make_tab(sata=[f"ide.{n}" for n in range(4)])
    last = tab.rows[-1].dev
    first = tab.rows[0].dev
    tab.rows[-1].active.setChecked(False)
    tab.rows[0].active.setChecked(False)
    assert [r.dev for r in tab.rows[-2:]] == [last, first]
    for row in tab.rows[-2:]:
        row.path.setEditText("/missing/inactive-disk")
        row._on_path()
    assert tab.warn.toPlainText() == "No disk problems found."
    assert not any("inactive-disk" in msg for _, msg in tab.cfg.validate())
    assert "/missing/inactive-disk" not in tab.cfg.to_script()


def test_reactivation_preserves_boot_priority_unless_it_was_reused(make_tab):
    tab = make_tab(sata=["ide.0", "ide.1", "ide.2"])
    tab.rows[0].active.setChecked(False)
    tab.rows[0].dev["bootindex"] = 1
    tab.rows[-1].active.setChecked(True)
    assert tab.rows[-1].dev["bootindex"] == 3
    assert len({r.dev["bootindex"] for r in tab.rows}) == 3


def test_full_controller_keeps_disk_inactive_without_inventing_ide6(make_tab, monkeypatch):
    tab = make_tab(sata=[f"ide.{n}" for n in range(7)])
    tab.rows[-1].active.setChecked(False)
    before = copy.deepcopy(tab.cfg.data)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[-1]))
    spy = QSignalSpy(tab.changed)
    tab.rows[-1].active.setChecked(True)
    assert warnings and "No SATA port" in warnings[0]
    assert tab.cfg.data == before
    assert not tab.rows[-1].active.isChecked()
    assert len(spy) == 0
    assert all(d.get("bus") != "ide.6" for d in emitted(tab.cfg, "-device"))


def test_controller_removal_includes_retained_inactive_namespaces(make_tab, monkeypatch):
    tab = make_tab(namespaces=[("nvme0", 1)])
    tab.rows[0].active.setChecked(False)
    controller = tab.nvme_controllers()[0]
    questions = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *args: questions.append(args[-1]) or QMessageBox.StandardButton.Yes)
    tab._remove_ctrl(controller)
    assert questions and "inactive" in questions[0]
    assert not tab.rows
    assert tab.cfg.compact() == 3
    assert not tab.cfg.devices and not tab.cfg.blockdevs


def test_wizard_replacement_clears_retained_disks_as_well(make_tab):
    from tabs_wizard import WizardTab

    tab = make_tab(sata=["ide.0"], namespaces=[("nvme0", 1)])
    for row in list(tab.rows):
        model.set_disk_active(tab.cfg, row.bd, row.dev, False)
    WizardTab._clear_all_disks(SimpleNamespace(cfg=tab.cfg, _DISK_DRIVERS=WizardTab._DISK_DRIVERS))
    assert tab.cfg.compact() == 5
    assert not tab.cfg.devices and not tab.cfg.blockdevs


@pytest.mark.parametrize("family", ["ide", "nvme"])
def test_all_disks_can_be_parked_and_reactivated_in_a_new_order(make_tab, family):
    tab = (make_tab(sata=[f"ide.{n}" for n in range(3)]) if family == "ide"
           else make_tab(namespaces=[("nvme0", n) for n in (1, 2, 3)]))
    identities = {r.dev["id"]: (copy.deepcopy(r.dev), copy.deepcopy(r.bd)) for r in tab.rows}
    for _ in range(3):
        tab.rows[0].active.setChecked(False)
    assert len(tab.rows) == 3
    assert not any(r.active.isChecked() for r in tab.rows)
    assert not emitted(tab.cfg, "-blockdev")
    tab.cfg.compact()
    order = [r.dev["id"] for r in reversed(tab.rows)]
    for expected_id in order:
        next(r for r in tab.rows if r.dev["id"] == expected_id).active.setChecked(True)
    assert [r.dev["id"] for r in tab.rows] == order
    for n, row in enumerate(tab.rows):
        original, block = identities[row.dev["id"]]
        assert row.dev == dict(original, **({"bus": f"ide.{n}"} if family == "ide" else {"nsid": n + 1}))
        assert row.bd == block
    assert tab.warn.toPlainText() == "No disk problems found."


@pytest.mark.parametrize("port", range(6))
def test_full_sata_setup_can_toggle_any_port_without_leaving_it_reserved(make_tab, port):
    tab = make_tab(sata=[f"ide.{n}" for n in range(6)])
    row = tab.rows[port]
    original = row.dev
    highest = tab.rows[-1].dev
    row.active.click()
    inactive = tab.rows[-1]
    assert inactive.dev is original
    assert "bus" not in inactive.dev
    assert inactive.busline.text() == "ide"
    assert inactive.dev["_inactive_controller"] == "ide"
    assert [r.busline.text() for r in tab.rows[:-1]] == [f"ide.{n}" for n in range(5)]
    if port < 5:
        assert highest["bus"] == f"ide.{port}"
    # Editing another option on an inactive card must not reserve its old port.
    inactive.serial.setText("KEPT-SERIAL")
    inactive._push()
    assert "bus" not in original
    inactive.active.click()
    assert tab.rows[-1].dev is original
    assert original["bus"] == "ide.5"
    assert original["serial"] == "KEPT-SERIAL"
    assert [r.busline.text() for r in tab.rows] == [f"ide.{n}" for n in range(6)]


@pytest.mark.parametrize("family", ["ide", "sata", "nvme"])
def test_reactivation_repairs_gaps_in_older_inactive_setups(make_tab, family):
    tab = (make_tab(namespaces=[("nvme0", n) for n in range(1, 7)]) if family == "nvme"
           else make_tab(sata=[f"{family}.{n}" for n in range(6)]))
    first, highest = tab.rows[0].dev, tab.rows[-1].dev
    tab.rows[0].dev.update(_disabled=True, _inactive=1)
    tab.rows[0].bd.update(_disabled=True, _inactive=True)
    tab.reload()
    # The previous version retained the old number but left a gap in the
    # active range. There are five occupied slots, so this is not full.
    assert tab.rows[-1].busline.text() == ("nvme0" if family == "nvme" else family)
    tab.rows[-1].active.click()
    if family == "nvme":
        assert highest["nsid"] == 1 and first["nsid"] == 6
        assert [r.nsid.value() for r in tab.rows] == list(range(1, 7))
    else:
        assert highest["bus"] == f"{family}.0" and first["bus"] == f"{family}.5"
        assert [r.busline.text() for r in tab.rows] == [f"{family}.{n}" for n in range(6)]
    assert tab.warn.toPlainText() == "No disk problems found."


@pytest.mark.parametrize("port", [0, 4, 5])
def test_checkbox_mouse_clicks_in_full_window_keep_six_port_setup_consistent(window, app, monkeypatch, port):
    for n in range(1, 6):
        window.cfg.blockdevs.append(dict(driver="file", filename=f"/test/disk{n}.img", **{"node-name": f"disk{n}"}))
        window.cfg.devices.append(dict(driver="ide-hd", id=f"drive{n}", drive=f"disk{n}",
                                        bus=f"ide.{n}", serial=f"SERIAL{n}"))
    tab = window.tab_disks
    tab.reload()
    window._select_tab_by_name("Disks")
    window.resize(1750, 950)
    settle(app)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[-1]))
    original = tab.rows[port].dev
    tab.rows[-1].busline.setFocus()
    tab.ensureWidgetVisible(tab.rows[port].active)
    QTest.mouseClick(tab.rows[port].active, Qt.MouseButton.LeftButton)
    settle(app)
    assert tab.rows[-1].dev is original
    assert "bus" not in original
    assert [r.dev["bus"] for r in tab.rows[:-1]] == [f"ide.{n}" for n in range(5)]
    tab.ensureWidgetVisible(tab.rows[-1].active)
    QTest.mouseClick(tab.rows[-1].active, Qt.MouseButton.LeftButton)
    settle(app)
    assert not warnings
    assert tab.rows[-1].dev is original
    assert [r.dev["bus"] for r in tab.rows] == [f"ide.{n}" for n in range(6)]
