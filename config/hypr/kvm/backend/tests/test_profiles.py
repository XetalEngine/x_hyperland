"""OS-profile isolation, including UI rebuilds and generated guest hardware."""

import copy
import json
import time
from pathlib import Path
from unittest.mock import Mock

import pytest
from PyQt6.QtWidgets import QFileDialog, QMessageBox

from test_ui_navigation import app, window, settle
import vmstart2
import profiles
import macos_profile
import virtual_gpu
from model import VMConfig

LOAD_INITIAL = vmstart2.VMStart2._load_initial


@pytest.fixture
def os_window(window, monkeypatch, tmp_path):
    root = tmp_path / "profiles"
    root.mkdir()
    monkeypatch.setattr(vmstart2, "LAST_STATE", str(root / "last-session.json"))
    monkeypatch.setattr(vmstart2, "PRESET_DIR", str(root / "presets"))
    monkeypatch.setattr(vmstart2, "TEMPLATE", str(root / "presets/win10-template.json"))
    monkeypatch.setattr(vmstart2.theme, "THEME_FILE", str(root / "theme.json"))
    monkeypatch.setattr(vmstart2.settings_defaults, "DEFAULT_STATE", str(root / "settings_default.json"))
    monkeypatch.setattr(vmstart2.settings_defaults, "DEFAULT_THEME", str(root / "settings_default.theme.json"))
    monkeypatch.setattr(virtual_gpu, "service_active", lambda: False)
    window.cfg.root = root
    windows = copy.deepcopy(window.cfg.data)
    windows["simple"]["name"] = "Windows identity"
    mac = macos_profile.configuration(root, root / "external.iso", "/test/qemu", window.tab_pin.topo)
    for key, data in (("windows", windows), ("macos", mac)):
        paths = profiles.paths(root, key)
        paths.presets.mkdir(parents=True)
        for path in (paths.session, paths.template, paths.defaults):
            path.write_text(json.dumps(data))
        for path in (paths.theme, paths.default_theme):
            path.write_text(json.dumps(dict(accent="#27ae60", background="#1d1f24", text="", preset=1)))
    window._baseline = json.dumps(window.cfg.data, sort_keys=True)
    return window


def test_switch_saves_and_restores_independent_editors_and_firmware(os_window, app):
    w = os_window
    w.tab_mem.gb.setValue(12)
    w.ed_bios_vendor.setText("Windows BIOS")
    w._push_type0()
    w.tab_machine.globals_edit.setPlainText("host-x86_64-cpu.model-id=Windows CPU")
    w.chk_reboot.setChecked(True)
    before = copy.deepcopy(w.cfg.data)
    w.profile_buttons["macos"].click()
    settle(app)
    assert w.profile_id == "macos"
    assert w.profile_buttons["macos"].isChecked()
    assert w.tab_mem.gb.value() == 6
    assert w.tab_pin.smt_mode.currentData() == "single"
    assert w.cpu_model.text() == "Penryn" and w.cpu_vendor.text() == "GenuineIntel"
    assert w.ed_bios_vendor.text() == ""
    assert not w.chk_reboot.isChecked()
    assert "tpmdev" not in w.cfg.simple
    assert w.cfg.smbios["template_blob"] == ""
    assert "windows" not in json.dumps(w.cfg.data).lower()
    assert Path(vmstart2.launcher.START).parent == w._paths().run
    assert w.theme_bar.path == w._paths().theme
    windows_bytes = w._paths("windows").session.read_bytes()
    for attr in ("tab_pin", "tab_mem", "tab_disks", "tab_hw", "tab_machine", "tab_paths", "tab_tpm",
                 "tab_proc", "tab_wizard", "tab_virtual", "tab_dual"):
        assert getattr(w, attr).cfg is w.cfg
    assert all(w.tabs.indexOf(getattr(w, attr)) >= 0 for attr in ("tab_overview", "tab_virtual", "tab_dual"))
    w.ed_bios_vendor.setText("Mac BIOS")
    w._push_type0()
    nvram = w.tab_paths._bd_get("libvirt-pflash1-storage")
    assert str(w._paths().directory) in nvram
    w.tab_paths._bd_set("libvirt-pflash1-storage", nvram + ".private")
    w.tab_virtual.network.setCurrentIndex(w.tab_virtual.network.findData("off"))
    w.switch_profile("windows")
    settle(app)
    assert w._paths().session.read_bytes() == windows_bytes
    assert w.tab_mem.gb.value() == 12
    assert w.ed_bios_vendor.text() == "Windows BIOS"
    assert w.cfg.cpu_features == before["cpu"]["features"]
    assert w.cfg.globals == before["globals"]
    assert w.chk_reboot.isChecked()
    assert w.cfg.blockdevs == before["blockdevs"]
    assert w.theme_bar.path == w._paths().theme
    w.switch_profile("macos")
    settle(app)
    assert w.ed_bios_vendor.text() == "Mac BIOS"
    assert w.tab_paths._bd_get("libvirt-pflash1-storage") == nvram + ".private"
    assert w.tab_virtual.network.currentData() == "off"
    assert profiles.selected(w._paths().root) == "macos"
    w.save_session(quiet=True)
    restored = LOAD_INITIAL(w)
    assert restored.profile == "macos"
    assert restored.smbios["type0"]["vendor"] == "Mac BIOS"
    assert restored.data["virtual_gpu"]["network"] == "off"


def test_profile_presets_are_separate_and_reject_wrong_os(os_window, monkeypatch):
    w = os_window
    saved = {}
    def destination(_owner, _title, directory, _filter):
        saved[w.profile_id] = Path(directory) / "Same name.json"
        return str(saved[w.profile_id]), ""
    monkeypatch.setattr(QFileDialog, "getSaveFileName", destination)
    w.save_preset()
    windows_bytes = saved["windows"].read_bytes()
    w.switch_profile("macos")
    w.save_preset()
    assert saved["windows"] != saved["macos"]
    assert saved["windows"].read_bytes() == windows_bytes
    assert json.loads(saved["macos"].read_text())["_meta"]["profile"] == "macos"
    before = copy.deepcopy(w.cfg.data)
    failure = Mock()
    monkeypatch.setattr(QMessageBox, "critical", failure)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_: (str(saved["windows"]), ""))
    w.load_preset()
    failure.assert_called_once()
    assert w.cfg.data == before
    assert "Windows" in failure.call_args.args[-1]


def test_opencore_identity_page_does_not_offer_empty_blob_actions(os_window):
    w = os_window
    assert not w.btn_apply_smbios.isHidden()
    w.switch_profile("macos")
    assert "OpenCore supplies" in w.smbios_help.text()
    assert "EFI/OC/config.plist" in w.smbios_help.text()
    assert all(widget.isHidden() and not widget.isEnabled()
               for widget in w.smbios_blob_actions + w.smbios_blob_editors)
    before = copy.deepcopy(w.cfg.data)
    w._smbios_run(False)
    assert w.cfg.data == before
    assert "FAILED" not in w.smbios_log.toPlainText()

    # A deliberately configured blob remains editable, including on a Mac.
    w.cfg.smbios["template_blob"] = "/test/mac-dmi.bin"
    w._fill_smbios()
    assert not w.btn_apply_smbios.isHidden() and w.btn_apply_smbios.isEnabled()
    w.switch_profile("windows")
    assert not w.btn_apply_smbios.isHidden() and w.btn_apply_smbios.isEnabled()
    assert "Apply SMBIOS Identity" in w.smbios_help.text()


def test_mac_reset_and_wizard_use_mac_masters_only(os_window, monkeypatch, app):
    w = os_window
    w.switch_profile("macos")
    windows = w._paths("windows").session.read_bytes()
    master = w._paths().defaults.read_bytes()
    monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Yes)
    w.tab_mem.gb.setValue(8)
    w.tab_machine.globals_edit.setPlainText("Mac override")
    w.reset_defaults()
    settle(app)
    assert w.cfg.profile == "macos" and w.cpu_model.text() == "Penryn"
    assert w.tab_mem.gb.value() == 6 and w.cfg.globals == []
    assert w._paths().session.read_bytes() == master
    assert w._paths("windows").session.read_bytes() == windows
    assert list((w._paths().directory / "settings_backups").glob("before-reset-*"))
    w.tab_wizard._start_over()
    settle(app)
    assert w.cfg.profile == "macos" and w.cfg.data["cpu"]["model"] == "Penryn"
    assert not w.cfg.data["tools"]["kvm_build_enabled"]
    before = copy.deepcopy(w.cfg.data["cpu"])
    w.tab_wizard._apply_vendor_cpu("amd")
    assert w.cfg.data["cpu"] == before
    assert w._paths("windows").session.read_bytes() == windows


@pytest.mark.parametrize("failure", ["running", "submitting", "dual_pending", "save", "invalid"])
def test_failed_switch_keeps_current_profile(os_window, monkeypatch, failure):
    w = os_window
    before = copy.deepcopy(w.cfg.data)
    if failure == "running":
        monkeypatch.setattr(virtual_gpu, "service_active", lambda: True)
    elif failure == "submitting":
        w.tab_virtual._submitting = True
    elif failure == "dual_pending":
        w.tab_dual._submission_deadline = time.monotonic() + 20
    elif failure == "save":
        monkeypatch.setattr(w, "save_session", lambda **_: False)
    else:
        w._paths("macos").session.write_text('{"broken": true}')
        monkeypatch.setattr(QMessageBox, "critical", Mock())
    w.profile_buttons["macos"].click()
    assert w.profile_id == "windows"
    assert w.profile_buttons["windows"].isChecked()
    assert w.cfg.data == before
    assert profiles.selected(w._paths().root) == "windows"


def test_mac_console_helper_keeps_vga_and_usb2(os_window):
    w = os_window
    w.switch_profile("macos")
    w.tab_virtual.model.setCurrentIndex(w.tab_virtual.model.findData("qxl-vga"))
    w.tab_virtual.input_controller.setCurrentIndex(w.tab_virtual.input_controller.findData("xhci"))
    w.tab_virtual.btn_spice.click()
    options = w.tab_virtual.settings()
    assert options["model"] == "VGA" and options["input_controller"] == "ehci"
    assert options["server"] == "spice"
    assert not options["clipboard"] and not options["file_transfer"]
    assert "Windows" not in w.tab_virtual.resolution_note.text()


def test_mac_launch_plan_has_smc_usb2_and_private_firmware(tmp_path):
    data = macos_profile.configuration(tmp_path, tmp_path / "external.iso", "/test/qemu",
                                       {"core_to_cpus": {n: [n, n + 4] for n in range(4)}})
    cfg = VMConfig(data, root=tmp_path)
    before = copy.deepcopy(data)
    plan = virtual_gpu.prepare(cfg)
    assert cfg.data == before
    devices = plan["config"]["devices"]
    assert any(d["driver"] == "isa-applesmc" and d["osk"] == macos_profile.OSK for d in devices)
    assert any(d["driver"] == "usb-ehci" for d in devices)
    assert not any(d["driver"] in ("qemu-xhci", "tpm-crb", "vfio-pci", "usb-host", "ide-hd") for d in devices)
    assert all(d["bus"] == "ehci.0" for d in devices if d["driver"] in ("usb-kbd", "usb-tablet"))
    assert plan["config"]["cpu"] == data["cpu"]
    assert plan["config"]["smp"]["vcpus"] == "4"
    assert plan["config"]["objects"][0]["size"] == 6 * 1024**3
    assert plan["tpm"] is plan["huge"] is plan["tap"] is None
    nvram = next(b["filename"] for b in cfg.blockdevs if b.get("node-name") == "libvirt-pflash1-storage")
    assert Path(nvram).is_relative_to(tmp_path / "macos")
    changed = virtual_gpu.prepare(cfg, {"input_controller": "xhci"})
    xhci = next(d for d in changed["config"]["devices"] if d["driver"] == "qemu-xhci")
    assert all(d["bus"] == xhci["id"] + ".0" for d in changed["config"]["devices"]
               if d["driver"] in ("usb-kbd", "usb-tablet"))


def test_tahoe_baseline_is_separate_and_uses_bridge_in_virtual_mode(tmp_path):
    topology = {"core_to_cpus": {n: [n, n + 8] for n in range(8)}}
    legacy = macos_profile.configuration(tmp_path, tmp_path / "high-sierra.iso", "/test/qemu", topology)
    data = macos_profile.tahoe_configuration(tmp_path, tmp_path / "tahoe.iso", "/test/qemu",
                                           topology, bridge="br0")
    cfg = VMConfig(data, root=tmp_path)
    before = copy.deepcopy(data)
    plan = virtual_gpu.prepare(cfg, workdir=str(tmp_path / "run"), token="tahoe")
    assert cfg.data == before
    assert plan["tap"]["bridge"] == "br0"
    net = json.loads(plan["config"]["simple"]["netdev"])
    assert net["type"] == "tap" and net["ifname"] == plan["tap"]["name"]
    assert "fd" not in net
    assert plan["config"]["cpu"]["model"] == "Skylake-Client"
    assert plan["config"]["cpu"]["features"]["avx2"] == "on"
    assert plan["config"]["cpu"]["features"]["hle"] == "off"
    assert plan["config"]["smp"]["topology"] == {"sockets": "1", "cores": "8", "threads": "1"}
    assert plan["config"]["objects"][0]["size"] == 16 * 1024**3
    assert plan["tpm"] is plan["huge"] is None
    devices = plan["config"]["devices"]
    controller = next(d for d in devices if d["driver"] == "nec-usb-xhci")
    assert all(d["bus"] == controller["id"] + ".0" for d in devices
               if d["driver"] in ("usb-kbd", "usb-tablet"))
    assert not any(d["driver"] in ("vfio-pci", "usb-host", "ide-hd") for d in devices)
    paths = {b["filename"] for b in data["blockdevs"] if b.get("filename")}
    old_paths = {b["filename"] for b in legacy["blockdevs"] if b.get("filename")}
    assert paths.isdisjoint(old_paths)
    assert all("Tahoe-firmware" in b["filename"] for b in data["blockdevs"]
               if b.get("filename") and b["node-name"].startswith("libvirt-pflash"))


def test_tahoe_console_helper_keeps_usb3(os_window):
    w = os_window
    w.cfg = VMConfig(macos_profile.tahoe_configuration(w._paths().root, "/test/tahoe.iso", "/test/qemu",
                                                      w.tab_pin.topo), root=w._paths().root)
    w._rebuild_tabs()
    assert any(row.path.currentText() == "/test/tahoe.iso" for row in w.tab_disks.rows)
    w.tab_virtual.input_controller.setCurrentIndex(w.tab_virtual.input_controller.findData("ehci"))
    w.tab_virtual.btn_spice.click()
    options = w.tab_virtual.settings()
    assert options["model"] == "VGA" and options["input_controller"] == "xhci"
    assert not options["clipboard"] and not options["file_transfer"]
