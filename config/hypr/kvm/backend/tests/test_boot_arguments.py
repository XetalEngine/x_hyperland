"""Lossless boot edits and shared Mac UI draft; synthetic boot disks only."""

import copy
from unittest.mock import Mock

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QDialog, QMessageBox

from test_opencore_ui import app, window, os_window, disk, editor
from test_ui_navigation import settle
from boot_arguments import ArgumentsDraft
from navigation import PAGES
from opencore_choices import sip_description
import opencore


def row(editor, key, occurrence=0):
    return [r for r in editor.arguments_page.rows if r.entry.key == key][occurrence]


def load_args(editor, text):
    editor.draft["NVRAM"]["Add"][opencore.APPLE_GUID]["boot-args"] = text
    editor._fill()


def edit_value(editor, key, value):
    field = row(editor, key).value
    field.setText(value)
    field.editingFinished.emit()


def test_opening_editor_retains_all_settings_and_unknown_arguments(editor):
    assert editor.draft == editor.snapshot.config and not editor.dirty
    assert row(editor, "-v").check.isChecked()
    assert not row(editor, "-v").value.isEnabled()
    assert row(editor, "custom").value.text() == "keep"
    assert "not in the built-in descriptions" in row(editor, "custom").description.text()
    assert not row(editor, "nvrmsettle").check.isChecked()
    assert row(editor, "nvrmsettle").value.text() == "10000"


def test_already_configured_delay_explains_no_changes_without_publishing(editor, monkeypatch):
    # Match the fast-boot image: the requested delay is already in the image.
    opencore.set_arguments(editor.draft, "-v nvrmsettle=10000")
    editor.snapshot.config = copy.deepcopy(editor.draft)
    editor._fill()
    publish = Mock()
    monkeypatch.setattr(opencore, "publish", publish)
    assert row(editor, "nvrmsettle").check.isChecked()
    for page in (editor, editor.arguments_page):
        assert not page.apply_button.isEnabled()
        assert page.apply_button.text() == "No changes to apply"
        assert "already match" in page.state.text()
        assert "Edit a setting" in page.apply_button.toolTip()
    assert editor.apply()
    publish.assert_not_called()
    edit_value(editor, "nvrmsettle", "20000")
    for page in (editor, editor.arguments_page):
        assert page.apply_button.isEnabled()
        assert "Unapplied" in page.state.text()
    edit_value(editor, "nvrmsettle", "10000")
    assert not editor.dirty and not editor.arguments_page.apply_button.isEnabled()
    assert "No changes to apply" in editor.arguments_page.state.text()


def test_focusing_an_unchanged_value_does_not_reformat_existing_arguments(editor):
    text = '  -v\tcustom="two words"   '
    load_args(editor, text)
    editor.snapshot.config = copy.deepcopy(editor.draft)
    item = row(editor, "custom")
    item.value.editingFinished.emit()
    assert opencore.arguments(editor.draft) == text
    assert not editor.dirty
    assert row(editor, "custom") is item


def test_check_edit_and_uncheck_preserve_quotes_duplicates_and_order(editor):
    original = '-v  custom="a b"\trevpatch=sbvmm custom=second nvfbheads=4'
    load_args(editor, original)
    edit_value(editor, "nvfbheads", "2")
    assert opencore.arguments(editor.draft) == original[:-1] + "2"
    # Duplicate keys remain independently editable and removable.
    row(editor, "custom", 1).check.setChecked(False)
    assert 'custom="a b"' in opencore.arguments(editor.draft)
    assert "custom=second" not in opencore.arguments(editor.draft)
    row(editor, "custom", 1).check.setChecked(True)
    assert opencore.arguments(editor.draft) == original[:-1] + "2"
    delay = row(editor, "nvrmsettle")
    delay.check.setChecked(True)
    assert "nvrmsettle=10000" in opencore.arguments(editor.draft)
    edit_value(editor, "nvrmsettle", "15000")
    assert "nvrmsettle=15000" in editor.arguments_page.preview.toPlainText()
    delay.check.setChecked(False)
    assert "nvrmsettle=" not in opencore.arguments(editor.draft)
    assert "boot-args" in editor.draft["NVRAM"]["Delete"][opencore.APPLE_GUID]


@pytest.mark.parametrize("key,bad,good", [("nvrmsettle", "-1", "10000"),
                                       ("nvfbheads", "99", "4"),
                                       ("amfi", "xyz", "0x80"),
                                       ("revpatch", "sbvmm other=1", "sbvmm")])
def test_invalid_values_block_both_pages_and_survive_other_edits(editor, key, bad, good):
    item = row(editor, key)
    item.check.setChecked(True)
    edit_value(editor, key, bad)
    before = opencore.arguments(editor.draft)
    editor.timeout.setValue(5)
    assert item.value.text() == bad and editor.dirty
    assert not editor.apply_button.isEnabled() and not editor.arguments_page.apply_button.isEnabled()
    assert not editor.apply() and opencore.arguments(editor.draft) == before
    edit_value(editor, key, good)
    assert not editor._errors and editor.arguments_page.apply_button.isEnabled()


def test_switching_off_invalid_value_keeps_the_last_valid_value(editor):
    item = row(editor, "nvrmsettle")
    item.check.setChecked(True)
    edit_value(editor, "nvrmsettle", "bad")
    item.check.setChecked(False)
    assert not editor._errors and "nvrmsettle" not in opencore.arguments(editor.draft)
    item.check.setChecked(True)
    assert editor._errors  # bad textbox is not silently made part of the command
    edit_value(editor, "nvrmsettle", "20000")
    assert not editor._errors and "nvrmsettle=20000" in opencore.arguments(editor.draft)


def test_argument_validation_does_not_touch_other_tokens_or_accept_extra_args():
    text = r'''-v custom="a b" escaped=a\ b duplicate=1 duplicate=2 strange="unterminated'''
    model = ArgumentsDraft(text)
    assert model.render() == text
    custom = model.entries[1]
    for bad in ['a b', '"unterminated', "bad\nnewline", "a\x00b"]:
        with pytest.raises(ValueError):
            model.edited_token(custom, bad)
    assert model.edited_token(custom, '"changed words"') == 'custom="changed words"'
    assert model.render() == text


def test_named_sip_rom_and_secure_boot_choices_preserve_loaded_values(editor):
    assert editor.sip.currentData() == bytes.fromhex("430a0000")
    assert "0xA43" in editor.sip_note.text()
    assert "unauthenticated system volume" in editor.sip_note.text()
    assert editor.rom_value.isReadOnly() and editor.rom_value.text() == "11:22:33:44:55:66"
    assert not editor.dirty
    editor.sip.setCurrentIndex(next(i for i in range(editor.sip.count()) if editor.sip.itemData(i) == bytes(4)))
    assert editor.draft["NVRAM"]["Add"][opencore.APPLE_GUID]["csr-active-config"] == bytes(4)
    assert "No SIP exceptions" in editor.sip_note.text()
    editor.sip.setCurrentIndex(0)
    assert not editor.dirty
    assert "unrestricted NVRAM access" in sip_description(bytes.fromhex("40000000"))
    assert "unauthenticated system volume" not in sip_description(bytes.fromhex("40000000"))
    # Unknown settings remain visible and are never coerced to the first preset.
    custom = bytes.fromhex("00400000")
    editor.draft["NVRAM"]["Add"][opencore.APPLE_GUID]["csr-active-config"] = custom
    editor.draft["Misc"]["Security"]["SecureBootModel"] = "j185"
    editor._fill()
    assert editor.sip.currentData() == custom and "Custom" in editor.sip.currentText()
    assert editor.secure_boot.currentData() == "j185"
    assert "additional flags" in editor.sip_note.text()


def test_rom_adapter_choice_copies_address_without_changing_adapter(editor):
    nic = {"id": "net0", "driver": "vmxnet3", "netdev": "hostnet0", "mac": "52:54:00:54:41:48"}
    editor.cfg.devices.append(nic)
    before = copy.deepcopy(editor.cfg.data)
    editor._fill()
    editor.rom.setCurrentIndex(1)
    assert editor.draft["PlatformInfo"]["Generic"]["ROM"] == bytes.fromhex("525400544148")
    assert editor.cfg.data == before
    editor.rom.setCurrentIndex(0)
    assert not editor.dirty


def test_new_page_is_mac_only_and_shares_draft_across_navigation(os_window, disk, monkeypatch, app):
    w = os_window
    assert w.navigation.items["Boot Arguments"].isHidden()
    previous = w.tabs.currentIndex()
    w._select_tab_by_name("Boot Arguments")
    w.navigation._activate(w.navigation.items["Boot Arguments"])
    assert w.tabs.currentIndex() == previous
    w.switch_profile("macos")
    snapshot = opencore.inspect(disk[0])
    monkeypatch.setattr(opencore, "inspect", lambda *_: snapshot)
    w._select_tab_by_name("Boot Arguments")
    settle(app)
    keys = [p[0] for p in PAGES]
    assert keys.index("Boot Arguments") == keys.index("SMBIOS") + 1
    assert not w.navigation.items["Boot Arguments"].isHidden()
    assert w.tab_boot_arguments.widget() is w.tab_opencore.arguments_page
    assert not w.tab_opencore.dirty
    item = row(w.tab_opencore, "nvrmsettle")
    item.check.setChecked(True)
    item.value.setFocus()
    item.value.selectAll()
    QTest.keyClicks(item.value, "20000")
    w._select_tab_by_name("SMBIOS")
    settle(app)
    assert "nvrmsettle=20000" in opencore.arguments(w.tab_opencore.draft)
    monkeypatch.setattr(QDialog, "exec", lambda *_: QDialog.DialogCode.Rejected)
    assert not w.save_session(quiet=True)
    w.switch_profile("windows")
    assert w.profile_id == "macos" and w.tab_opencore.dirty
    # Discard via reload; changing profile hides the page and keeps Windows separate.
    monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Yes)
    w.tab_opencore.reload()
    w.switch_profile("windows")
    assert w.navigation.items["Boot Arguments"].isHidden() and w.tab_opencore is None


def test_argument_apply_validates_new_copy_and_updates_both_pages(editor, monkeypatch):
    before = editor.snapshot
    row(editor, "nvrmsettle").check.setChecked(True)
    edit_value(editor, "nvrmsettle", "15000")
    monkeypatch.setattr(QDialog, "exec", lambda *_: QDialog.DialogCode.Accepted)
    warning = Mock()
    monkeypatch.setattr(QMessageBox, "warning", warning)
    progress = []
    editor.updated.connect(lambda: progress.append((editor.arguments_page.state.text(), editor.busy,
                                                    editor.apply_button.isEnabled(),
                                                    editor.arguments_page.apply_button.isEnabled())))
    editor.arguments_page.apply_button.click()
    warning.assert_not_called()
    assert editor.snapshot.image != before.image
    assert "nvrmsettle=15000" in opencore.arguments(editor.snapshot.config)
    assert not editor.dirty and not editor.arguments_page.apply_button.isEnabled()
    assert any(text.startswith("Applying (") and busy and not enabled and not other
               for text, busy, enabled, other in progress)
    assert editor.arguments_page.state.text().startswith("Applied and verified:")
    assert editor.arguments_page.state.text() == editor.state.text()
    assert editor.arguments_page.apply_button.text() == "No changes to apply"
    assert opencore.sha(before.image) == before.image_hash
    assert opencore.sha(before.variables) == before.vars_hash


def test_click_apply_commits_focused_value_and_keeps_result_after_rebuild(os_window, disk, monkeypatch, app):
    w = os_window
    w.switch_profile("macos")
    cfg, *_ = disk
    w.cfg.data["blockdevs"] = copy.deepcopy(cfg.blockdevs)
    w.cfg.data["devices"] = copy.deepcopy(cfg.devices)
    w.cfg.objects[0]["size"] = 2 * 1024**3
    w.cfg.data["tools"]["opencore_validators"] = cfg.data["tools"]["opencore_validators"]
    w._rebuild_tabs()
    w._select_tab_by_name("Boot Arguments")
    settle(app)
    before = w.tab_opencore.snapshot
    w.tab_opencore._sync_memory()
    delay = row(w.tab_opencore, "nvrmsettle")
    delay.check.setChecked(True)
    w.tab_boot_arguments.ensureWidgetVisible(delay.value)
    delay.value.setFocus()
    delay.value.selectAll()
    QTest.keyClicks(delay.value, "20000")
    monkeypatch.setattr(QDialog, "exec", lambda *_: QDialog.DialogCode.Accepted)
    warning = Mock()
    monkeypatch.setattr(QMessageBox, "warning", warning)
    button = w.tab_opencore.arguments_page.apply_button
    w.tab_boot_arguments.ensureWidgetVisible(button)
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    settle(app)
    warning.assert_not_called()
    assert "OpenCore setup updated" in w.status.text()
    assert "Save current setup" in w.status.text()
    assert not w.tab_opencore.dirty
    assert w.tab_opencore.snapshot.image != before.image
    assert "nvrmsettle=20000" in opencore.arguments(w.tab_opencore.snapshot.config)
    assert opencore.sha(before.image) == before.image_hash
