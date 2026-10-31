"""UI regressions using synthetic settings; never launch a VM or save real state."""

import copy
import json
import os
from pathlib import Path
import sys
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox

import vmstart2
import dual_gpu
import dual_devices
import gpu_inventory
import input_devices
from model import VMConfig
from navigation import PAGES


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


def settle(app):
    app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.fixture
def window(app, monkeypatch, tmp_path):
    topo = {
        "model": "Test CPU", "cores": 2, "threads": 4, "smt": True,
        "core_to_cpus": {0: [0, 2], 1: [1, 3]},
        "l3_to_cores": {"0-3": [0, 1]},
        "cpus": [{"cpu": n, "core": n % 2, "socket": 0, "node": 0, "l3": "0-3"}
                 for n in range(4)],
    }
    monkeypatch.setattr(vmstart2.hostinfo, "cpu_topology", lambda: copy.deepcopy(topo))
    monkeypatch.setattr(vmstart2.hostinfo, "cpu_vendor", lambda: "amd")
    monkeypatch.setattr(vmstart2.hostinfo, "_cpu_model", lambda: "Test CPU")
    monkeypatch.setattr(vmstart2.hostinfo, "virt_flag", lambda: "svm")
    monkeypatch.setattr(vmstart2.hostinfo, "iommu_active", lambda: {"active": True, "groups": 2})
    for name in ("gpus", "pci_devices", "usb_devices", "block_devices", "net_bridges",
                 "tpm_devices", "hugetlbfs_mounts"):
        monkeypatch.setattr(vmstart2.hostinfo, name, lambda: [])
    monkeypatch.setattr(vmstart2.hostinfo, "hugepage_pools", lambda: {})
    monkeypatch.setattr(vmstart2.hostinfo, "mount_for", lambda _path: None)
    monkeypatch.setattr(gpu_inventory, "discover", lambda **_: [])
    for name in ("RUN_DIR", *vmstart2.profiles.RUNTIME_FILES):
        monkeypatch.setattr(vmstart2.launcher, name, str(tmp_path / name.lower()))
    monkeypatch.setattr(vmstart2, "LAST_STATE", str(tmp_path / "last-session.json"))
    monkeypatch.setattr(vmstart2, "PRESET_DIR", str(tmp_path))
    monkeypatch.setattr(vmstart2.theme, "THEME_FILE", str(tmp_path / "theme.json"))
    monkeypatch.setattr(vmstart2.settings_defaults, "DEFAULT_STATE", str(tmp_path / "settings_default.json"))
    monkeypatch.setattr(vmstart2.settings_defaults, "DEFAULT_THEME", str(tmp_path / "settings_default.theme.json"))

    data = {
        "_meta": {"binary": "/test/qemu"},
        "machine": {"type": "q35", "opts": {}},
        "cpu": {"model": "host", "features": {"svm": "on", "hypervisor": "off"}},
        "simple": {"name": "test-vm", "m": "size=2G"},
        "smp": {"vcpus": "4", "topology": {"cores": "2", "threads": "2"}},
        "objects": [{"qom-type": "memory-backend-ram", "id": "pc.ram", "size": 2 * 1024**3}],
        "blockdevs": [{"driver": "file", "node-name": "disk0", "filename": "/test/disk.img"}],
        "devices": [{"driver": "ide-hd", "id": "drive0", "drive": "disk0", "bus": "ide.0",
                     "serial": "ORIGINAL", "bootindex": 1}],
        "order": [[key, None] for key in ("machine", "cpu", "smp", "name", "m")],
        "smbios": {"template_blob": "", "output_blob": "", "system_uuid": "", "patches": []},
        "tools": {"tpm_root": str(tmp_path / "tpm"), "swtpm_binary": "", "kvm_build_enabled": False},
        "tpm_chardev": "chrtpm",
        "wizard": {"step": 9, "vendor": "amd", "layout": 2},
    }

    def initial(owner):
        cfg = VMConfig(copy.deepcopy(data))
        owner._baseline = json.dumps(cfg.data, sort_keys=True)
        return cfg

    monkeypatch.setattr(vmstart2.VMStart2, "_load_initial", initial)
    vmstart2.theme.apply_to(app, "#27ae60", "#1d1f24", "")
    widget = vmstart2.VMStart2()
    widget.resize(1440, 960)
    widget.show()
    settle(app)
    yield widget
    widget.hide()
    widget.deleteLater()
    settle(app)
    assert not (tmp_path / "last-session.json").exists()


def open_wizard(window, source):
    if source == "toolbar":
        window.btn_wizard.click()
    else:
        # The sidebar entry is only available after a programmatic opening.
        window.navigation.select("Wizard")
        item = window.navigation.items["Wizard"]
        QTest.mouseClick(window.navigation.list.viewport(), Qt.MouseButton.LeftButton,
                         pos=window.navigation.list.visualItemRect(item).center())


@pytest.mark.parametrize("source", ["toolbar"])
def test_open_wizard_restarts_with_existing_configuration(window, monkeypatch, source):
    before = copy.deepcopy(window.cfg.data)
    command = window.cfg.to_script(True)
    question = Mock(return_value=QMessageBox.StandardButton.No)
    monkeypatch.setattr(QMessageBox, "question", question)

    open_wizard(window, source)

    question.assert_called_once()
    assert window.tabs.currentWidget() is window.tab_wizard
    assert window.tab_wizard.step == 0
    assert window.cfg.data["wizard"] == {"step": 0, "layout": 2}
    assert {k: v for k, v in window.cfg.data.items() if k != "wizard"} == {
        k: v for k, v in before.items() if k != "wizard"}
    assert window.cfg.to_script(True) == command


def test_cancel_preserves_saved_wizard_progress(window, monkeypatch):
    assert window.tab_wizard.step == 9  # Merely loading the app must not restart setup.
    before = copy.deepcopy(window.cfg.data)
    monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Cancel)
    window.btn_wizard.click()
    assert window.tab_wizard.step == 9
    assert window.cfg.data == before


def test_wizard_stays_out_of_sidebar_even_when_toolbar_opens_it(window, monkeypatch, app):
    item = window.navigation.items["Wizard"]
    assert item.isHidden()
    window.navigation.search.setText("wizard")
    assert item.isHidden()
    window.navigation.search.clear()
    assert item.isHidden()
    window.navigation.search.setText("nvram")
    monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Cancel)
    window.btn_wizard.click()
    settle(app)
    assert item.isHidden()
    assert window.navigation.list.currentItem() is None
    assert window.tabs.currentWidget() is window.tab_wizard
    assert window.tab_wizard.btn_next.hasFocus()
    window.navigation.search.setText("nvram")
    window.btn_wizard.click()
    assert item.isHidden()
    window._select_tab_by_name("Memory")
    assert item.isHidden()


@pytest.fixture
def defaults(window, monkeypatch, tmp_path):
    # Use a separate directory so the ordinary fixture's no-save assertion
    # still protects its session. Reset tests write only these temporary files.
    root = tmp_path / "reset-test"
    root.mkdir()
    paths = {key: root / name for key, name in (
        ("state", "last-session.json"), ("theme", "theme.json"),
        ("master", "settings_default.json"), ("master_theme", "settings_default.theme.json"))}
    monkeypatch.setattr(vmstart2, "LAST_STATE", str(paths["state"]))
    monkeypatch.setattr(vmstart2.theme, "THEME_FILE", str(paths["theme"]))
    monkeypatch.setattr(vmstart2.settings_defaults, "DEFAULT_STATE", str(paths["master"]))
    monkeypatch.setattr(vmstart2.settings_defaults, "DEFAULT_THEME", str(paths["master_theme"]))
    master = copy.deepcopy(window.cfg.data)
    master["globals"] = ["host-x86_64-cpu.model-id=Master CPU"]
    theme = dict(accent="#27ae60", background="#1d1f24", text="", preset=1)
    paths["master"].write_text(json.dumps(master, indent=2))
    paths["master_theme"].write_text(json.dumps(theme, indent=2))
    saved = copy.deepcopy(window.cfg.data)
    saved["simple"]["name"] = "previously-saved"
    paths["state"].write_text(json.dumps(saved))
    paths["theme"].write_text(json.dumps(dict(theme, accent="#e67e22", preset=5)))
    window.tab_machine.globals_edit.setPlainText("host-x86_64-cpu.model-id=Unsaved CPU")
    window.ed_bios_vendor.setText("Unsaved BIOS vendor")
    window._push_type0()
    window.theme_bar.accent = "#3498db"
    window.theme_bar.combo.setCurrentIndex(3)
    return paths, master


def test_reset_defaults_requires_confirmation_even_when_setup_is_saved(window, defaults, monkeypatch):
    paths, _master = defaults
    window._baseline = json.dumps(window.cfg.data, sort_keys=True)
    before = copy.deepcopy(window.cfg.data)
    files = {p: p.read_bytes() for p in paths.values()}
    question = Mock(return_value=QMessageBox.StandardButton.Cancel)
    monkeypatch.setattr(QMessageBox, "question", question)
    window.btn_reset_defaults.click()
    question.assert_called_once()
    assert question.call_args.args[-1] == QMessageBox.StandardButton.Cancel
    assert window.cfg.data == before
    assert all(p.read_bytes() == data for p, data in files.items())
    assert not (paths["state"].parent / "settings_backups").exists()


def test_reset_defaults_restores_every_editor_and_persists_without_changing_master(
        window, defaults, monkeypatch, app):
    paths, master = defaults
    unsaved = copy.deepcopy(window.cfg.data)
    saved = paths["state"].read_bytes()
    master_bytes = paths["master"].read_bytes()
    master_theme = paths["master_theme"].read_bytes()
    window._select_tab_by_name("Machine")
    monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Yes)
    window.btn_reset_defaults.click()
    settle(app)
    assert window.cfg.data == master
    assert window.tabs.currentWidget() is window.tab_machine
    assert window.tab_machine.globals_edit.toPlainText() == master["globals"][0]
    assert window.ed_bios_vendor.text() == ""
    assert not window.is_modified()
    for attr in ("tab_pin", "tab_mem", "tab_disks", "tab_hw", "tab_machine",
                 "tab_paths", "tab_tpm", "tab_proc", "tab_wizard", "tab_virtual", "tab_dual"):
        assert getattr(window, attr).cfg is window.cfg
    assert paths["state"].read_bytes() == master_bytes
    assert paths["theme"].read_bytes() == master_theme
    assert paths["master"].read_bytes() == master_bytes
    assert paths["master_theme"].read_bytes() == master_theme
    assert window.theme_bar.accent == "#27ae60"
    assert window.theme_bar.combo.currentIndex() == 1
    backups = list((paths["state"].parent / "settings_backups").iterdir())
    assert len(backups) == 1
    assert (backups[0] / "last-session.json").read_bytes() == saved
    assert json.loads((backups[0] / "current-session.json").read_text()) == unsaved
    assert json.loads((backups[0] / "current-theme.json").read_text())["accent"] == "#3498db"
    window.btn_reset_defaults.click()
    assert len(list((paths["state"].parent / "settings_backups").iterdir())) == 2
    assert paths["master"].read_bytes() == master_bytes


@pytest.mark.parametrize("problem", ["missing", "invalid", "missing_theme"])
def test_unusable_master_keeps_current_setup(window, defaults, monkeypatch, problem):
    paths, _master = defaults
    if problem == "missing":
        paths["master"].unlink()
    elif problem == "invalid":
        paths["master"].write_text("{}")
    else:
        paths["master_theme"].unlink()
    before = copy.deepcopy(window.cfg.data)
    saved = paths["state"].read_bytes()
    appearance = paths["theme"].read_bytes()
    monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Yes)
    error = Mock()
    monkeypatch.setattr(QMessageBox, "critical", error)
    window.btn_reset_defaults.click()
    error.assert_called_once()
    assert window.cfg.data == before
    assert paths["state"].read_bytes() == saved
    assert paths["theme"].read_bytes() == appearance
    assert not (paths["state"].parent / "settings_backups").exists()


def test_failed_reset_write_restores_files_and_editor_state(window, defaults, monkeypatch, app):
    paths, _master = defaults
    old_cfg = window.cfg
    before = copy.deepcopy(old_cfg.data)
    saved = paths["state"].read_bytes()
    appearance = paths["theme"].read_bytes()
    old_baseline = window._baseline
    write = vmstart2.settings_defaults.atomic_write

    def fail_theme(path, data):
        if Path(path) == paths["theme"]:
            raise OSError("simulated write failure")
        write(path, data)

    monkeypatch.setattr(vmstart2.settings_defaults, "atomic_write", fail_theme)
    monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Yes)
    error = Mock()
    monkeypatch.setattr(QMessageBox, "critical", error)
    window.btn_reset_defaults.click()
    settle(app)
    error.assert_called_once()
    assert window.cfg is old_cfg and window.cfg.data == before
    assert window._baseline == old_baseline
    assert paths["state"].read_bytes() == saved
    assert paths["theme"].read_bytes() == appearance
    assert window.theme_bar.accent == "#3498db"
    assert window.tab_machine.globals_edit.toPlainText() == before["globals"][0]


def test_reset_rebinds_all_editors_and_returns_to_step_one(window, monkeypatch, app):
    fresh = copy.deepcopy(window.cfg.data)
    fresh["simple"]["name"] = "fresh-template"
    fresh["wizard"] = {"step": 6, "vendor": "intel"}
    monkeypatch.setattr(VMConfig, "load_template", staticmethod(lambda: copy.deepcopy(fresh)))
    monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Yes)
    window.btn_wizard.click()
    settle(app)
    assert window.cfg.simple["name"] == "fresh-template"
    assert window.cfg.data["wizard"] == {"step": 0, "layout": 2}
    assert window.tab_wizard.step == 0
    assert window.tabs.currentWidget() is window.tab_wizard
    for attr in ("tab_pin", "tab_mem", "tab_disks", "tab_hw", "tab_machine",
                 "tab_paths", "tab_tpm", "tab_proc", "tab_wizard", "tab_virtual", "tab_dual"):
        assert getattr(window, attr).cfg is window.cfg


def test_missing_template_does_not_discard_configuration(window, monkeypatch):
    before = copy.deepcopy(window.cfg.data)
    monkeypatch.setattr(VMConfig, "load_template", Mock(side_effect=FileNotFoundError("missing template")))
    monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Yes)
    error = Mock()
    monkeypatch.setattr(QMessageBox, "critical", error)
    window.btn_wizard.click()
    error.assert_called_once()
    assert window.cfg.data == before
    assert window.tab_wizard.step == 9


def test_navigation_and_search_keep_every_editor_reachable(window, app):
    before = copy.deepcopy(window.cfg.data)
    for key, _group, title, _description, _keywords in PAGES:
        if key == "Wizard" or key in window.navigation.blocked_pages:
            continue
        item = window.navigation.items[key]
        window.navigation.list.setCurrentItem(item)
        QTest.keyClick(window.navigation.list, Qt.Key.Key_Return)
        settle(app)
        assert window.tabs.tabText(window.tabs.currentIndex()) == key
        assert window.navigation.list.currentItem().text() == title
        assert not hasattr(window, "page_title")
    window.navigation.search.setText("nvram")
    QTest.keyClick(window.navigation.search, Qt.Key.Key_Return)
    assert window.tabs.currentWidget() is window.tab_paths
    window._select_tab_by_name("Overview")
    assert not window.navigation.items["Single GPU"].isHidden()
    assert window.navigation.search.text() == ""
    assert window.cfg.data == before


def test_loading_preset_keeps_navigation_and_edits_targeting_new_config(window, monkeypatch, tmp_path, app):
    window._select_tab_by_name("Disks")
    old_cfg = window.cfg
    before = copy.deepcopy(old_cfg.data)
    preset = tmp_path / "preset.json"
    preset.write_text(json.dumps(before))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_: (str(preset), "JSON"))
    window.load_preset()
    settle(app)
    assert window.tabs.currentWidget() is window.tab_disks
    assert window.navigation.list.currentItem().text() == "Disks & storage"
    serial = window.tab_disks.rows[0].serial
    serial.selectAll()
    QTest.keyClicks(serial, "NEW-SERIAL")
    assert window.cfg.device_by_id("drive0")["serial"] == "NEW-SERIAL"
    assert "NEW-SERIAL" in window.cfg.to_script(True)
    assert old_cfg.data == before


@pytest.fixture
def manufacturer_model(window, tmp_path):
    original, replacement = "SRD\0MS-3C96F", "DKS\0IC-8A62E"
    patch = dict(enabled=True, label="Manufacturer/Model", find_ascii=original,
                 find_hex=original.encode("latin-1").hex(), replace_ascii=replacement,
                 replace_hex=replacement.encode("latin-1").hex())
    template, output = tmp_path / "template.bin", tmp_path / "output.bin"
    # A minimal Type 1 table with two identity strings, followed by Type 127.
    raw = (bytes([1, 27, 0, 1, 1, 2, 0, 0]) + bytes(19)
           + original.encode("latin-1") + b"\0\0" + bytes([127, 4, 0, 127, 0, 0]))
    template.write_bytes(raw)
    window.cfg.data["smbios"] = dict(template_blob=str(template), output_blob=str(output),
                                     system_uuid="", patches=[patch])
    window._select_tab_by_name("SMBIOS")
    window._fill_smbios()
    return patch, template, output


def test_manufacturer_model_fields_build_the_same_binary_patch(window, manufacturer_model, tmp_path):
    import smbios
    patch, template, output = manufacturer_model
    assert window.ed_manufacturer.text() == "DKS"
    assert window.ed_product_model.text() == "IC-8A62E"
    before = template.read_bytes()
    for editor, value in ((window.ed_manufacturer, "SRD"), (window.ed_product_model, "XT-3C74A")):
        editor.setFocus()
        editor.selectAll()
        QTest.keyClicks(editor, value)
    expected = "SRD\0XT-3C74A"
    assert patch["replace_ascii"] == expected
    assert bytes.fromhex(patch["replace_hex"]) == expected.encode("latin-1")
    assert window.smbios_table.item(0, 3).text() == "SRD\\x00XT-3C74A"
    saved = tmp_path / "edited-identity.json"
    window.cfg.save(str(saved))
    restored = VMConfig.load(str(saved))
    smbios.apply(restored.smbios)
    assert output.read_bytes() == before.replace(b"SRD\0MS-3C96F", expected.encode("latin-1"))
    assert template.read_bytes() == before


def test_invalid_manufacturer_edit_keeps_previous_bytes(window, manufacturer_model, monkeypatch):
    patch, _template, _output = manufacturer_model
    before = copy.deepcopy(patch)
    warning = Mock()
    monkeypatch.setattr(QMessageBox, "warning", warning)
    window.ed_manufacturer.setFocus()
    window.ed_manufacturer.selectAll()
    QTest.keyClicks(window.ed_manufacturer, "XY")
    warning.assert_not_called()
    QTest.keyClick(window.ed_manufacturer, Qt.Key.Key_Return)
    warning.assert_called_once()
    assert patch == before
    assert window.ed_manufacturer.text() == "DKS"


def test_manufacturer_fields_follow_table_edits_and_enabled_state(window, manufacturer_model):
    patch, _template, _output = manufacturer_model
    window.smbios_table.item(0, 3).setText("ABC\\x00XY-12345")
    assert window.ed_manufacturer.text() == "ABC"
    assert window.ed_product_model.text() == "XY-12345"
    window.smbios_table.cellWidget(0, 0).setChecked(False)
    assert not window.chk_manufacturer_model.isChecked()
    assert not window.ed_manufacturer.isEnabled()
    window.chk_manufacturer_model.setChecked(True)
    assert patch["enabled"] and window.ed_manufacturer.isEnabled()
    assert window.smbios_table.cellWidget(0, 0).isChecked()
    window._smbios_regen(0)
    assert [window.ed_manufacturer.text(), window.ed_product_model.text()] == patch["replace_ascii"].split("\0")


def test_resizing_disk_cards_preserves_settings_and_editors(window, app):
    window._select_tab_by_name("Disks")
    before = copy.deepcopy(window.cfg.data)
    row = window.tab_disks.rows[0]
    # Respect the complete toolbar's minimum width with the larger desktop font.
    narrow = max(1100, window.minimumSizeHint().width())
    for width, columns in ((narrow, 1), (1750, 2), (narrow, 1)):
        window.resize(width, 800)
        settle(app)
        assert window.width() == width
        assert window.tab_disks._columns == columns
        assert window.tab_disks.horizontalScrollBar().maximum() == 0
        assert window.tab_disks.rows[0] is row
        assert window.cfg.data == before


def test_virtual_options_are_separate_and_survive_preset_reload(window, monkeypatch, tmp_path, app):
    before = copy.deepcopy(window.cfg.data)
    command = window.cfg.to_script(True)
    window._select_tab_by_name("Virtual GPU")
    settle(app)
    assert window.tabs.currentWidget() is window.tab_virtual
    assert window.cfg.data == before
    window.tab_virtual.server.setCurrentIndex(window.tab_virtual.server.findData("spice"))
    window.tab_virtual.clipboard.setChecked(True)
    assert window.tab_virtual.remember_console_size.isChecked()
    window.tab_virtual.remember_console_size.setChecked(False)
    assert window.cfg.data["virtual_gpu"]["server"] == "spice"
    assert window.cfg.data["virtual_gpu"]["port"] == 5930
    assert window.cfg.to_script(True) == command
    assert {k: v for k, v in window.cfg.data.items() if k != "virtual_gpu"} == before
    preset = tmp_path / "virtual.json"
    preset.write_text(json.dumps(window.cfg.data))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_: (str(preset), "JSON"))
    window.load_preset()
    settle(app)
    assert window.tabs.currentWidget() is window.tab_virtual
    assert window.tab_virtual.clipboard.isChecked()
    assert window.tab_virtual.server.currentData() == "spice"
    assert not window.tab_virtual.remember_console_size.isChecked()
    assert window.cfg.to_script(True) == command


@pytest.mark.parametrize("page", ["tab_virtual", "tab_dual"])
def test_restart_requires_running_guest_and_confirmation(window, monkeypatch, page):
    tab = getattr(window, page)
    control = Mock()
    monkeypatch.setattr(vmstart2.virtual_gpu, "control", control)
    state = {"state": "stopped"}
    monkeypatch.setattr(vmstart2.virtual_gpu, "status", lambda _: state)
    monkeypatch.setattr(vmstart2.virtual_gpu, "read_log", lambda _: "")
    tab._poll()
    assert not tab.btn_restart.isEnabled()
    state.update(state="running", pid=os.getpid(),
                 process_start=Path(f"/proc/{os.getpid()}/stat").read_text().split()[21])
    tab._poll()
    assert tab.btn_restart.isEnabled()
    prompt = Mock(return_value=QMessageBox.StandardButton.Cancel)
    monkeypatch.setattr(QMessageBox, "warning", prompt)
    tab.btn_restart.click()
    control.assert_not_called()
    assert "immediately resets" in prompt.call_args.args[2]
    assert prompt.call_args.args[-1] == QMessageBox.StandardButton.Cancel
    prompt.return_value = QMessageBox.StandardButton.Yes
    tab.btn_restart.click()
    control.assert_called_once_with(tab.run, "system_reset")
    assert tab.state.text() == "Restart requested…"
    state["state"] = "stopping"
    tab._poll()
    assert not tab.btn_restart.isEnabled()


def test_console_size_preference_applies_to_active_console_without_relaunch(window, monkeypatch):
    tab = window.tab_virtual
    active = {"server": "spice", "port": 6123}
    tab.run = {"options": active}
    viewer = Mock()
    monkeypatch.setattr(vmstart2.virtual_gpu, "open_viewer", viewer)
    tab._open_console()
    viewer.assert_called_with(dict(active, floating=True), remember_size=True)
    tab.remember_console_size.setChecked(False)
    tab._open_console()
    viewer.assert_called_with(dict(active, floating=True), remember_size=False)
    assert active == {"server": "spice", "port": 6123}


@pytest.mark.parametrize('page,section', [('tab_virtual','virtual_gpu'),('tab_dual','dual_gpu')])
def test_console_floating_defaults_and_changes_are_saved_separately(window, monkeypatch, page, section):
    tab=getattr(window,page)
    before=copy.deepcopy(window.cfg.data)
    assert tab.floating.isChecked()
    tab.floating.setChecked(False)
    assert window.cfg.data[section]['floating'] is False
    assert {k:v for k,v in window.cfg.data.items() if k!=section}=={k:v for k,v in before.items() if k!=section}
    tab.run={'options':{'server':'spice','port':6123,'floating':True}}
    original=copy.deepcopy(tab.run)
    viewer=Mock();monkeypatch.setattr(vmstart2.virtual_gpu,'open_viewer',viewer)
    tab._open_console()
    assert viewer.call_args.args[0]['floating'] is False
    assert viewer.call_args.args[0]['port']==6123
    assert tab.run==original
    window._rebuild_tabs()
    assert not getattr(window,page).floating.isChecked()


def test_virtual_launch_never_uses_single_gpu_launch_or_hooks(window, monkeypatch):
    import virtual_gpu
    monkeypatch.setattr(virtual_gpu, "preflight", lambda _: [("ok", "ready")])
    launch = Mock(return_value={"workdir": "/test/run", "options": {}})
    monkeypatch.setattr(virtual_gpu, "launch", launch)
    forbidden = Mock(side_effect=AssertionError("Single-GPU path must never run"))
    for name in ("launch", "write_script", "write_hooks", "build_start", "build_revert"):
        monkeypatch.setattr(vmstart2.launcher, name, forbidden)
    window.tab_virtual.btn_launch.click()
    launch.assert_called_once_with(window.cfg)
    forbidden.assert_not_called()


@pytest.mark.parametrize("page", ["tab_virtual", "tab_dual"])
def test_launch_startup_failures_replace_waiting_and_disable_guest_controls(window, monkeypatch, page):
    tab = getattr(window, page)
    state = dict(state="pending", message="Starting the VM supervisor…")
    monkeypatch.setattr(vmstart2.virtual_gpu, "status", lambda _: state)
    monkeypatch.setattr(vmstart2.virtual_gpu, "read_log", lambda _: "ModuleNotFoundError: fixture failure")
    viewer = Mock()
    monkeypatch.setattr(tab, "_open_console", viewer)
    tab._auto_open = True
    tab._poll()
    assert not tab.btn_launch.isEnabled()
    state.update(state="failed", message="Launch failed before the VM supervisor reported readiness.")
    tab._poll()
    assert "Launch failed" in tab.state.text()
    assert "ModuleNotFoundError" in tab.log.toPlainText()
    assert "Launch failed" in tab.log.toPlainText()
    assert not tab.btn_console.isEnabled()
    assert not tab.btn_restart.isEnabled()
    assert not tab._auto_open
    if page == "tab_virtual":
        assert tab.btn_launch.isEnabled()
    viewer.assert_not_called()


def test_spice_shortcut_sets_only_virtual_options_and_explains_guest_setup(window):
    tab = window.tab_virtual
    before = copy.deepcopy(window.cfg.data)
    command = window.cfg.to_script(True)
    tab.btn_spice.click()
    opts = window.cfg.data["virtual_gpu"]
    assert opts["server"] == "spice" and opts["model"] == "qxl-vga"
    assert opts["port"] == 5930
    assert opts["clipboard"] and opts["file_transfer"] and opts["input"]
    assert tab.spice_box.isEnabled()
    assert "guest display driver" in tab.resolution_note.text()
    assert window.cfg.to_script(True) == command
    assert {k: v for k, v in window.cfg.data.items() if k != "virtual_gpu"} == {
        k: v for k, v in before.items() if k != "virtual_gpu"}


def test_spice_shortcut_preserves_custom_port_and_vnc_explains_disabled_features(window):
    tab = window.tab_virtual
    tab.port.setValue(6200)
    tab.btn_spice.click()
    assert tab.port.value() == 6200
    tab.server.setCurrentIndex(tab.server.findData("vnc"))
    assert not tab.spice_box.isEnabled()
    assert "Choose SPICE" in tab.display_note.text()
    assert "Display settings" in tab.resolution_note.text()


def test_single_gpu_test_cannot_open_an_active_virtual_guests_disks(window, monkeypatch):
    monkeypatch.setattr(vmstart2.virtual_gpu, "service_active", lambda: True)
    launch = Mock(side_effect=AssertionError("Active guest must not be tested again"))
    monkeypatch.setattr(vmstart2.launcher, "test_run", launch)
    window._test_run()
    launch.assert_not_called()
    assert "already running" in window.launch_log.toPlainText()


def test_dual_gpu_is_below_virtual_and_only_candidates_can_be_selected(window, monkeypatch):
    keys = [p[0] for p in PAGES]
    assert keys.index("Dual GPU") == keys.index("Virtual GPU") + 1
    before = copy.deepcopy(window.cfg.data)
    devices = [
        dict(slot="0000:01:00.0", name="Host GPU", identity={"vendor": "host"},
             available=False, verified=True, reasons=["Linux boot GPU"]),
        dict(slot="0000:82:00.0", name="Spare iGPU", identity={"vendor": "guest"},
             available=True, verified=False, reasons=[]),
    ]
    monkeypatch.setattr(gpu_inventory, "discover", lambda **_: copy.deepcopy(devices))
    window.tab_dual.refresh_gpus()
    host_index = window.tab_dual.gpu.findData("0000:01:00.0")
    assert host_index > 0
    assert not window.tab_dual.gpu.model().item(host_index).isEnabled()
    assert "Linux boot GPU" in window.tab_dual.gpu.model().item(host_index).toolTip()
    assert window.tab_dual.gpu.findData("0000:82:00.0") > 0
    assert window.cfg.data == before
    assert "Linux boot GPU" in window.tab_dual.detected.text()
    assert "full usage check" in window.tab_dual.detected.text()


def test_dual_evdev_selection_is_saved_only_for_dual_mode(window, monkeypatch):
    tab = window.tab_dual
    before = {k: copy.deepcopy(v) for k, v in window.cfg.data.items() if k != "dual_gpu"}
    devices = [{"path": "/dev/input/by-id/test-event-kbd", "name": "Test keyboard",
                "roles": ["keyboard"]},
               {"path": "/dev/input/by-id/test-event-mouse", "name": "Test mouse",
                "roles": ["mouse"]}]
    monkeypatch.setattr(input_devices, "discover", lambda: devices)
    tab.refresh_inputs()
    tab.viewer.setCurrentIndex(tab.viewer.findData("looking-glass"))
    assert tab.lg_capture.isEnabled()
    assert not tab.evdev_keyboard.isEnabled()
    tab.input_mode.setCurrentIndex(tab.input_mode.findData("evdev"))
    assert tab.evdev_keyboard.isEnabled() and tab.evdev_mouse.isEnabled()
    assert not tab.lg_capture.isEnabled()
    tab.evdev_keyboard.setCurrentIndex(1)
    tab.evdev_mouse.setCurrentIndex(1)
    saved = window.cfg.data["dual_gpu"]
    assert saved["evdev_keyboard"] == devices[0]["path"]
    assert saved["evdev_mouse"] == devices[1]["path"]
    assert saved["input_mode"] == "evdev"
    assert "both ctrl keys" in tab.input_note.text().lower()
    monkeypatch.setattr(input_devices, "discover", lambda: [])
    tab.refresh_inputs()
    assert tab.evdev_mouse.currentData() == devices[1]["path"]
    assert "unavailable" in tab.evdev_mouse.currentText()
    assert {k: v for k, v in window.cfg.data.items() if k != "dual_gpu"} == before


def test_dual_audio_busy_gpu_stays_visible_and_can_be_used_without_audio(window, monkeypatch):
    tab = window.tab_dual
    candidate = dict(slot="0000:82:00.0", name="Raphael", identity={"vendor": "guest"},
                     available=True, verified=True, reasons=[], audio_only_busy=False)

    def inventory(audio=False):
        result = copy.deepcopy(candidate)
        if audio:
            result.update(available=False, audio_only_busy=True,
                          reasons=["HDMI/DP audio is in use by wireplumber; uncheck HDMI audio"])
        return [result]

    monkeypatch.setattr(gpu_inventory, "discover", inventory)
    assert not tab.gpu_audio.isChecked()
    tab.refresh_gpus()
    tab.gpu.setCurrentIndex(tab.gpu.findData(candidate["slot"]))
    assert tab.btn_launch.isEnabled()
    tab.gpu_audio.setChecked(True)
    assert "HDMI audio busy" in tab.gpu.currentText()
    assert not tab.btn_launch.isEnabled()
    assert tab.gpu.currentData() == candidate["slot"]
    tab.gpu_audio.setChecked(False)
    assert tab.btn_launch.isEnabled()
    assert window.cfg.data["dual_gpu"]["gpu"] == candidate["slot"]
    assert not window.cfg.data["dual_gpu"]["gpu_audio"]


def test_dual_offers_console_and_physical_choices_without_lg_settings(window):
    tab = window.tab_dual
    assert tab.viewer.currentData() == "spice"
    assert {tab.viewer.itemData(n) for n in range(tab.viewer.count())} == {
        "spice", "vnc", "physical", "looking-glass"}
    tab.viewer.setCurrentIndex(tab.viewer.findData("vnc"))
    assert tab.port_label.text() == "Local VNC port"
    assert not tab.clipboard.isEnabled() and not tab.audio.isEnabled()
    assert "passed-through GPU's output" in tab.viewer_note.text()
    assert "Looking Glass frame buffer" not in tab.resolution_note.text()
    tab.viewer.setCurrentIndex(tab.viewer.findData("physical"))
    assert not tab.auto_open.isEnabled()
    assert "Looking Glass is not required" in tab.viewer_note.text()
    tab.viewer.setCurrentIndex(tab.viewer.findData("looking-glass"))
    assert "Looking Glass frame buffer" in tab.resolution_note.text()
    assert tab.auto_open.isEnabled()
    assert tab.clipboard.isEnabled()


def test_dual_usb_pci_selection_persists_without_changing_shared_devices(window, monkeypatch, tmp_path):
    tab = window.tab_dual
    original = {k: copy.deepcopy(v) for k, v in window.cfg.data.items() if k != "dual_gpu"}
    usb = dict(port="1-2", identity={"idVendor": "1234", "idProduct": "5678", "serial": "test"},
               name="USB headset", hub=False)
    pci = dict(slot="0000:82:00.6", identity={"device": "0x15e3"}, name="Onboard audio",
               group="30", driver="snd_hda_intel")
    monkeypatch.setattr(dual_devices, "discover_usb", lambda: [usb])
    monkeypatch.setattr(dual_devices, "discover_pci", lambda: [pci])
    tab.refresh_devices()
    tab.usb_devices.item(0).setCheckState(Qt.CheckState.Checked)
    tab.pci_devices.item(0).setCheckState(Qt.CheckState.Checked)
    saved = copy.deepcopy(window.cfg.data["dual_gpu"])
    assert saved["usb_devices"] == [dict(port=usb["port"], identity=usb["identity"])]
    assert saved["pci_devices"] == [dict(slot=pci["slot"], identity=pci["identity"])]
    path = tmp_path / "devices.json"
    window.cfg.save(str(path))
    assert json.loads(path.read_text())["dual_gpu"] == saved
    tab.refresh_devices(saved)
    assert tab.usb_devices.item(0).checkState() == Qt.CheckState.Checked
    assert tab.pci_devices.item(0).checkState() == Qt.CheckState.Checked
    assert {k: v for k, v in window.cfg.data.items() if k != "dual_gpu"} == original


def test_dual_missing_device_remains_selected_until_user_removes_it(window, monkeypatch):
    tab = window.tab_dual
    selected = dict(usb_devices=[dict(port="1-9", identity={"idVendor": "1111"})], pci_devices=[])
    monkeypatch.setattr(dual_devices, "discover_usb", lambda: [])
    monkeypatch.setattr(dual_devices, "discover_pci", lambda: [])
    tab.refresh_devices(selected)
    assert tab.settings()["usb_devices"] == selected["usb_devices"]
    assert "unavailable" in tab.usb_devices.item(0).text()
    tab.usb_devices.item(0).setCheckState(Qt.CheckState.Unchecked)
    assert not window.cfg.data["dual_gpu"]["usb_devices"]


def test_usb_replacement_at_same_port_requires_reselection(window, monkeypatch):
    tab = window.tab_dual
    old = dict(port="1-2", identity={"idVendor": "1111"})
    replacement = dict(port="1-2", identity={"idVendor": "2222"}, hub=False, name="Replacement")
    monkeypatch.setattr(dual_devices, "discover_usb", lambda: [replacement])
    monkeypatch.setattr(dual_devices, "discover_pci", lambda: [])
    tab.refresh_devices(dict(usb_devices=[old], pci_devices=[]))
    assert tab.settings()["usb_devices"] == [old]
    item = tab.usb_devices.item(0)
    assert "device changed" in item.text()
    item.setCheckState(Qt.CheckState.Unchecked)
    item.setCheckState(Qt.CheckState.Checked)
    assert tab.settings()["usb_devices"][0]["identity"] == replacement["identity"]


def test_dual_audio_choices_track_viewer_and_persist(window):
    tab = window.tab_dual
    tab.viewer.setCurrentIndex(tab.viewer.findData("looking-glass"))
    tab.audio.setChecked(True)
    tab.audio_mode.setCurrentIndex(tab.audio_mode.findData("lg-usb"))
    assert window.cfg.data["dual_gpu"]["audio_mode"] == "lg-usb"
    assert "Windows Sound settings" in tab.audio_note.text()
    tab.viewer.setCurrentIndex(tab.viewer.findData("spice"))
    assert tab.audio_mode.currentData() == "spice"
    assert window.cfg.data["dual_gpu"]["audio_mode"] == "spice"
    tab.viewer.setCurrentIndex(tab.viewer.findData("vnc"))
    assert not window.cfg.data["dual_gpu"]["audio"]
    assert not tab.audio_mode.isEnabled()


@pytest.mark.parametrize("viewer", ["spice", "vnc", "looking-glass", "physical"])
def test_dual_auto_open_respects_active_viewer_with_no_lg_client(window, monkeypatch, viewer):
    tab = window.tab_dual
    tab.run = {"options": {"viewer": viewer}, "shared_memory": {}}
    monkeypatch.setattr(dual_gpu.shutil, "which", lambda _: None)
    monkeypatch.setattr(vmstart2.virtual_gpu, "status", lambda _: {
        "state": "running", "pid": os.getpid(),
        "process_start": Path(f"/proc/{os.getpid()}/stat").read_text().split()[21]})
    monkeypatch.setattr(vmstart2.virtual_gpu, "read_log", lambda _: "")
    selected, fallback = Mock(), Mock()
    monkeypatch.setattr(tab, "_open_viewer", selected)
    monkeypatch.setattr(tab, "_open_console", fallback)
    tab._auto_open = viewer != "physical"
    tab._poll()
    assert selected.call_count == int(viewer in ("spice", "vnc"))
    assert fallback.call_count == int(viewer == "looking-glass")
    assert tab.btn_viewer.isEnabled() == (viewer != "physical")


def test_dual_options_preserve_single_and_virtual_and_survive_reload(window, monkeypatch, tmp_path, app):
    candidate = dict(slot="0000:82:00.0", name="Spare iGPU", identity={"vendor": "guest"},
                     available=True, verified=True, reasons=[])
    monkeypatch.setattr(gpu_inventory, "discover", lambda **_: [copy.deepcopy(candidate)])
    before = copy.deepcopy(window.cfg.data)
    command = window.cfg.to_script(True)
    tab = window.tab_dual
    tab.refresh_gpus()
    tab.gpu.setCurrentIndex(tab.gpu.findData(candidate["slot"]))
    tab.clipboard.setChecked(True)
    tab.port.setValue(6210)
    assert window.cfg.data["dual_gpu"]["gpu_identity"] == candidate["identity"]
    assert {k: v for k, v in window.cfg.data.items() if k != "dual_gpu"} == before
    assert window.cfg.to_script(True) == command
    preset = tmp_path / "dual.json"
    preset.write_text(json.dumps(window.cfg.data))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_: (str(preset), "JSON"))
    window._select_tab_by_name("Dual GPU")
    window.load_preset()
    settle(app)
    assert window.tabs.currentWidget() is window.tab_dual
    assert window.tab_dual.cfg is window.cfg
    assert window.tab_dual.port.value() == 6210
    assert window.tab_dual.gpu.currentData() == candidate["slot"]
    assert window.cfg.to_script(True) == command
    before = copy.deepcopy(window.cfg.data)
    monkeypatch.setattr(gpu_inventory, "discover", lambda **_: [])
    window.tab_dual.refresh_gpus()
    window.tab_dual._poll()
    assert not window.tab_dual.btn_launch.isEnabled()
    assert "unavailable" in window.tab_dual.gpu.currentText()
    assert window.cfg.data == before


def test_dual_launch_never_calls_single_gpu_or_virtual_launch(window, monkeypatch):
    monkeypatch.setattr(dual_gpu, "prepare", lambda *args: {})
    monkeypatch.setattr(dual_gpu, "preflight", lambda _: [("ok", "ready")])
    launch = Mock(return_value={"workdir": "/test/dual-run", "options": {}})
    monkeypatch.setattr(dual_gpu, "launch", launch)
    forbidden = Mock(side_effect=AssertionError("Wrong launch mode"))
    monkeypatch.setattr(vmstart2.virtual_gpu, "launch", forbidden)
    for name in ("launch", "write_script", "write_hooks", "build_start", "build_revert"):
        monkeypatch.setattr(vmstart2.launcher, name, forbidden)
    window.tab_dual._launch()
    launch.assert_called_once_with(window.cfg)
    forbidden.assert_not_called()
