"""Mac-only navigation, typed editing and cancellation across profile changes."""

import copy
import json
from unittest.mock import Mock

import pytest
from PyQt6.QtWidgets import QDialog, QLabel, QGroupBox, QMessageBox, QFileDialog, QPushButton
from PyQt6.QtTest import QTest

from test_ui_navigation import app, window, settle
from test_profiles import os_window
from test_opencore import disk
import opencore
import vmstart2
import theme
from tabs_opencore import OpenCoreTab


@pytest.fixture
def editor(app, disk):
    cfg, *_ = disk
    widget = OpenCoreTab(cfg)
    assert widget.reload()
    yield widget
    widget.deleteLater()
    settle(app)


def test_invalid_form_values_cannot_be_ignored_when_applying(editor):
    saved = editor.identity["SystemUUID"].text()
    editor.identity["SystemUUID"].setText("bad uuid")
    editor.identity["SystemUUID"].editingFinished.emit()
    editor.timeout.setValue(5)
    assert editor.identity["SystemUUID"].text() == "bad uuid"
    assert editor.dirty and not editor.apply_button.isEnabled()
    assert not editor.apply()
    editor.identity["SystemUUID"].setText(saved)
    editor.identity["SystemUUID"].editingFinished.emit()
    assert editor.apply_button.isEnabled() and not editor._errors


def test_advanced_editor_preserves_types_and_does_not_edit_keys(editor):
    assert editor.draft["#Comment"] == editor.snapshot.config["#Comment"]
    assert all(not editor.tree.topLevelItem(i).text(0).startswith("#") for i in range(editor.tree.topLevelItemCount()))
    def leaf(path):
        parent = editor.tree.invisibleRootItem()
        for part in path:
            parent = next(parent.child(i) for i in range(parent.childCount()) if parent.child(i).text(0) == str(part))
        return parent
    value = leaf(("UnknownFutureKey", "Bytes"))
    value.setText(1, "aabbcc")
    assert editor.draft["UnknownFutureKey"]["Bytes"] == b"\xaa\xbb\xcc"
    boolean = leaf(("UnknownFutureKey", "Boolean"))
    boolean.setText(1, "not a boolean")
    assert editor.draft["UnknownFutureKey"]["Boolean"] is True
    assert boolean.text(1) == "true"
    number = leaf(("UnknownFutureKey", "Number"))
    number.setText(1, "0x25")
    assert editor.draft["UnknownFutureKey"]["Number"] == 37
    delegate = editor.tree.itemDelegate()
    index = editor.tree.indexFromItem(number, 0)
    assert delegate.createEditor(editor.tree, None, index) is None


def test_cancel_review_leaves_files_and_preset_unchanged(editor, monkeypatch):
    before = copy.deepcopy(editor.cfg.data)
    editor.timeout.setValue(5)
    monkeypatch.setattr(QDialog, "exec", lambda *_: QDialog.DialogCode.Rejected)
    assert not editor.apply()
    assert editor.cfg.data == before and editor.dirty
    assert "Review canceled" in editor.arguments_page.state.text()
    assert editor.arguments_page.apply_button.isEnabled()
    assert opencore.sha(editor.snapshot.image) == editor.snapshot.image_hash


def test_unapplied_draft_survives_close_without_changing_boot_files(editor, tmp_path):
    editor.cfg.root=tmp_path
    image_hash=opencore.sha(editor.snapshot.image)
    vars_hash=opencore.sha(editor.snapshot.variables)
    editor.timeout.setValue(7)
    editor.save_draft()
    restored=OpenCoreTab(editor.cfg)
    try:
        assert restored.reload()
        assert restored.dirty
        assert restored.draft['Misc']['Boot']['Timeout']==7
        assert opencore.sha(restored.snapshot.image)==image_hash
        assert opencore.sha(restored.snapshot.variables)==vars_hash
    finally:
        restored.deleteLater()


@pytest.mark.parametrize("name", ["accent", "accentBig"])
def test_disabled_accent_button_looks_different_from_enabled(app, name):
    button = QPushButton("Review && apply…")
    button.setObjectName(name)
    button.setStyleSheet(theme.build_stylesheet())
    button.resize(240, 44)
    enabled = button.grab().toImage().pixelColor(12, 8)
    button.setEnabled(False)
    disabled = button.grab().toImage().pixelColor(12, 8)
    assert enabled != disabled
    button.deleteLater()


def test_apply_failure_is_visible_on_both_pages_and_allows_retry(editor, monkeypatch):
    editor.timeout.setValue(5)
    publish = Mock(side_effect=ValueError("Test validation failure"))
    monkeypatch.setattr(opencore, "publish", publish)
    monkeypatch.setattr(QDialog, "exec", lambda *_: QDialog.DialogCode.Accepted)
    warning = Mock()
    monkeypatch.setattr(QMessageBox, "warning", warning)
    assert not editor.apply()
    warning.assert_called_once()
    assert editor.dirty and not editor.busy
    for page in (editor, editor.arguments_page):
        assert page.state.text() == "Not applied: Test validation failure"
        assert page.apply_button.isEnabled()
    assert opencore.sha(editor.snapshot.image) == editor.snapshot.image_hash


def test_apply_selects_verified_copy_and_resets_draft(editor, monkeypatch):
    monkeypatch.setattr(QDialog, "exec", lambda *_: QDialog.DialogCode.Accepted)
    warning = Mock()
    monkeypatch.setattr(QMessageBox, "warning", warning)
    old_image = editor.snapshot.image
    editor.timeout.setValue(5)
    applied = Mock()
    editor.applied.connect(applied)
    assert editor.apply()
    warning.assert_not_called()
    applied.assert_called_once()
    assert not editor.dirty and not editor.busy
    assert editor.snapshot.image != old_image
    assert editor.snapshot.config["Misc"]["Boot"]["Timeout"] == 5


def test_mac_pages_remove_windows_controls_and_preserve_three_launch_modes(os_window, app):
    w = os_window
    w.switch_profile("macos")
    settle(app)
    assert w.navigation.items["TPM"].isHidden()
    w.navigation.search.setText("TPM")
    assert w.navigation.items["TPM"].isHidden()
    w.navigation.search.clear()
    assert w.navigation.items["SMBIOS"].text() == "Mac & OpenCore"
    for key in ("Single GPU", "Virtual GPU", "Dual GPU"):
        assert not w.navigation.items[key].isHidden()
    assert w.tab_dual.viewer.findData("looking-glass") == -1
    assert w.tab_dual.audio_mode.findData("lg-usb") == -1
    assert w.tab_virtual.model.findData("qxl-vga") == -1
    assert w.tab_virtual.clipboard.isHidden() and w.tab_virtual.file_transfer.isHidden()
    path_text = " ".join(l.text() for l in w.tab_paths.findChildren(QLabel))
    path_text += " ".join(g.title() for g in w.tab_paths.findChildren(QGroupBox))
    assert "TPM" not in path_text and "SMBIOS blob" not in path_text and "vmstealth" not in path_text
    assert "Mac firmware and NVRAM" in path_text and "OpenCore" in path_text
    assert not set(w.cfg.data["tools"]) & {"vmstealth_host", "vmstealth_guest", "tpm_reconstruct", "ovmf_build"}
    assert "tpm:" not in w.lbl_misc.text()
    w.switch_profile("windows")
    settle(app)
    assert not w.navigation.items["TPM"].isHidden()
    assert w.tab_dual.viewer.findData("looking-glass") >= 0
    assert w.tab_virtual.model.findData("qxl-vga") >= 0
    assert w.tab_opencore is None


def test_pending_opencore_changes_block_profile_switch_and_launch_on_cancel(os_window, disk, monkeypatch):
    w = os_window
    w.switch_profile("macos")
    snap = opencore.inspect(disk[0])
    monkeypatch.setattr(opencore, "inspect", lambda *_: snap)
    assert w.tab_opencore.reload()
    w.tab_opencore.timeout.setValue(5)
    monkeypatch.setattr(QDialog, "exec", lambda *_: QDialog.DialogCode.Rejected)
    w.switch_profile("windows")
    assert w.profile_id == "macos" and w.tab_opencore.dirty
    assert not w._before_mac_launch()
    assert not w.save_session(quiet=True)


def test_mac_usb_routing_edits_stay_in_mac_profile(os_window):
    w = os_window
    before = copy.deepcopy(w.cfg.devices)
    w.switch_profile("macos")
    controller = next(d for d in w.cfg.devices if d.get("driver") == "usb-ehci")
    controller.update(driver="nec-usb-xhci", p2=8)
    w._rebuild_tabs()
    assert w.tab_hw.mac_usb_ports[(controller["id"], "p2")].value() == 8
    w.tab_hw.mac_usb_ports[(controller["id"], "p2")].setValue(9)
    assert controller["p2"] == 9
    w.switch_profile("windows")
    assert w.cfg.devices == before


def test_preflight_leaves_pending_opencore_draft_unapplied(os_window, disk, monkeypatch):
    w = os_window
    w.switch_profile("macos")
    snap = opencore.inspect(disk[0])
    monkeypatch.setattr(opencore, "inspect", lambda *_: snap)
    assert w.tab_opencore.reload()
    w.tab_opencore.timeout.setValue(5)
    apply = Mock()
    monkeypatch.setattr(w.tab_opencore, "apply", apply)
    monkeypatch.setattr(vmstart2.launcher, "preflight", lambda *_: [])
    w._launch(True)
    apply.assert_not_called()
    assert w.tab_opencore.dirty


def test_load_preset_can_cancel_or_discard_draft_without_applying(os_window, disk, monkeypatch):
    w = os_window
    w.switch_profile("macos")
    snap = opencore.inspect(disk[0])
    monkeypatch.setattr(opencore, "inspect", lambda *_: snap)
    assert w.tab_opencore.reload()
    w.tab_opencore.timeout.setValue(5)
    old_cfg = w.cfg
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_: (str(w._paths().template), ""))
    monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Cancel)
    w.load_preset()
    assert w.cfg is old_cfg and w.tab_opencore.dirty
    monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Yes)
    w.load_preset()
    assert w.cfg is not old_cfg and not w.tab_opencore.dirty
    assert opencore.sha(snap.image) == snap.image_hash


def test_save_with_pending_draft_persists_new_paths_and_rebuilds_editors(os_window, disk, monkeypatch, app):
    w = os_window
    windows_devices = copy.deepcopy(w.cfg.devices)
    w.switch_profile("macos")
    cfg, *_ = disk
    w.cfg.data["blockdevs"] = copy.deepcopy(cfg.blockdevs)
    w.cfg.data["devices"] = [d for d in w.cfg.devices if not d.get("drive")] + copy.deepcopy(cfg.devices)
    w.cfg.objects[0]["size"] = 2 * 1024**3
    w.cfg.data["tools"]["opencore_validators"] = cfg.data["tools"]["opencore_validators"]
    w._rebuild_tabs()
    assert w.tab_opencore.reload()
    original = w.tab_opencore.snapshot
    w.tab_opencore._sync_memory()
    w.tab_opencore.timeout.setValue(5)
    w._select_tab_by_name("Boot Arguments")
    delay = next(row for row in w.tab_opencore.arguments_page.rows if row.entry.key == "nvrmsettle")
    delay.check.setChecked(True)
    delay.value.setFocus()
    delay.value.selectAll()
    QTest.keyClicks(delay.value, "20000")
    monkeypatch.setattr(QDialog, "exec", lambda *_: QDialog.DialogCode.Accepted)
    warning, critical = Mock(), Mock()
    monkeypatch.setattr(QMessageBox, "warning", warning)
    monkeypatch.setattr(QMessageBox, "critical", critical)
    assert w.save_session(quiet=True), (warning.call_args, critical.call_args)
    settle(app)
    saved = json.loads(w._paths().session.read_text())
    assert saved["blockdevs"][0]["filename"] != str(original.image)
    assert "opencore-versions" in saved["blockdevs"][0]["filename"]
    assert not w.tab_opencore.dirty
    assert w.tab_boot_arguments.widget() is w.tab_opencore.arguments_page
    assert "nvrmsettle=20000" in opencore.arguments(w.tab_opencore.snapshot.config)
    assert w.tab_paths._bd_get("oc") == saved["blockdevs"][0]["filename"]
    assert w.tab_opencore.cfg is w.tab_disks.cfg is w.cfg
    assert opencore.sha(original.image) == original.image_hash
    w.switch_profile("windows")
    settle(app)
    assert w.cfg.devices == windows_devices
