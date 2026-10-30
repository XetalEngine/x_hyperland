"""Formatting guards and UI regressions. Never open or erase a physical drive."""
import copy
import json
import os
from pathlib import Path
import plistlib
import stat
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_ui_navigation import app, window, settle
from PyQt6.QtCore import QProcess
from PyQt6.QtWidgets import QMessageBox

import mac_format as mf
import mac_format_dialog as ui
import macos_profile
import model
from model import VMConfig


@pytest.fixture
def raw(tmp_path):
    image = tmp_path / "development.img"
    with image.open("wb") as stream:
        stream.truncate(64 * 1024**3)
    return image


@pytest.fixture
def target(raw):
    return mf.inspect_target(raw)


@pytest.fixture
def mac(tmp_path):
    return VMConfig(macos_profile.tahoe_configuration(str(tmp_path), str(tmp_path/"recovery.iso"),
                     "/test/qemu", {}), root=tmp_path)


def test_regular_image_identity_and_loop_guard(raw, monkeypatch):
    target = mf.inspect_target(raw)
    assert target["size"] == 64 * 1024**3 and target["kind"] == "file"
    assert target["logical_sector"] == 512
    old = copy.deepcopy(target)
    raw.unlink()
    with raw.open("wb") as stream:
        stream.truncate(65 * 1024**3)
    with pytest.raises(ValueError, match="changed"):
        mf.check_identity(old, mf.inspect_target(raw))
    monkeypatch.setattr(mf, "run", lambda *a, **k: "/dev/loop9")
    with pytest.raises(ValueError, match="loop device"):
        mf.inspect_target(raw)


def test_no_qcow_hardlinks_small_or_optical(raw, tmp_path):
    raw.write_bytes(b"QFI\xfb")
    with pytest.raises(ValueError, match="QCOW2"):
        mf.inspect_target(raw)
    raw.write_bytes(b"tiny")
    with pytest.raises(ValueError, match="32 GiB"):
        mf.inspect_target(raw)
    os.link(raw, tmp_path/"alias.img")
    with pytest.raises(ValueError, match="Hard-linked"):
        mf.inspect_target(raw)
    iso = tmp_path/"installer.iso"
    iso.touch()
    with pytest.raises(ValueError, match="whole physical disk"):
        mf.inspect_target(iso)


@pytest.fixture
def block(monkeypatch, tmp_path):
    real = tmp_path/"fake-sata"
    real.touch()
    disk = dict(name=str(real), type="disk", size=1024**4, model="Test SATA", serial="EXACT-SERIAL",
                ro=False, fstype=None, label=None, mountpoints=[None],
                **{"log-sec": 4096, "phy-sec": 4096}, children=[
                    dict(name=str(real)+"1", type="part", fstype="zfs_member", label="zroot", mountpoints=[None])])
    original_stat, original_is_dir, original_iterdir = Path.stat, Path.is_dir, Path.iterdir
    def fake_stat(self, *args, **kwargs):
        if self == real:
            return SimpleNamespace(st_mode=stat.S_IFBLK, st_rdev=12345)
        return original_stat(self, *args, **kwargs)
    monkeypatch.setattr(Path, "stat", fake_stat)
    monkeypatch.setattr(Path, "is_dir", lambda p: True if str(p).startswith("/sys/class/block/") else original_is_dir(p))
    monkeypatch.setattr(Path, "iterdir", lambda p: iter(()) if str(p).startswith("/sys/class/block/") else original_iterdir(p))
    monkeypatch.setattr(mf.shutil, "which", lambda tool: "/test/"+tool)
    def run(*args, **kwargs):
        return json.dumps(dict(blockdevices=[disk])) if args[0] == "lsblk" else "no pools available"
    monkeypatch.setattr(mf, "run", run)
    return real, disk


def test_whole_disk_preserves_4kn_identity(block):
    real, disk = block
    result = mf.inspect_target(real)
    assert result["labels"] == ["zroot"]
    assert result["logical_sector"] == result["physical_sector"] == 4096
    assert result["identity"] == ["block", 12345, 1024**4, "EXACT-SERIAL"]


@pytest.mark.parametrize("change,match", [
    (lambda d: d.update(type="part"), "whole physical disk"),
    (lambda d: d.update(ro=True), "read only"),
    (lambda d: d["children"][0].update(mountpoints=["/mnt/data"]), "mounted"),
    (lambda d: d["children"][0].update(mountpoints=["[SWAP]"]), "swap"),
    (lambda d: d["children"][0].update(type="crypt"), "in use"),
])
def test_unsafe_physical_targets_rejected(block, change, match):
    real, disk = block
    change(disk)
    with pytest.raises(ValueError, match=match):
        mf.inspect_target(real)


def test_imported_zfs_is_rejected(block, monkeypatch):
    real, disk = block
    monkeypatch.setattr(mf, "run", lambda *args, **kwargs:
        json.dumps(dict(blockdevices=[disk])) if args[0] == "lsblk" else "  "+str(real)+"1 ONLINE")
    with pytest.raises(ValueError, match="imported ZFS"):
        mf.inspect_target(real)


def test_holders_are_rejected(block, monkeypatch):
    real, disk = block
    original = Path.iterdir
    monkeypatch.setattr(Path, "iterdir", lambda p: iter([Path("dm-0")])
                        if str(p).startswith("/sys/class/block/") else original(p))
    with pytest.raises(ValueError, match="holders"):
        mf.inspect_target(real)


@pytest.mark.parametrize("name", ["", "  ", "bad/name", "bad:name", "bad\nname", "é"*64])
def test_invalid_volume_names(name):
    with pytest.raises(ValueError):
        mf.validate_name(name)


def test_valid_name_quotes_are_data():
    assert mf.validate_name("  My Mac's $(echo nope)  ") == "My Mac's $(echo nope)"


def test_guest_must_find_exactly_one_matching_whole_disk():
    assert mf.guest_candidate({}, 123) is None
    disk = dict(DeviceIdentifier="disk7", Size=123)
    assert mf.guest_candidate(dict(AllDisksAndPartitions=[disk]), 123) == "disk7"
    for disks in ([disk, disk], [dict(disk, Size=124)], [dict(disk, DeviceIdentifier="disk7s1")]):
        with pytest.raises(ValueError):
            mf.guest_candidate(dict(AllDisksAndPartitions=disks), 123)
    valid = dict(DeviceIdentifier="disk7", WholeDisk=True, TotalSize=123, BusProtocol="USB",
                 Writable=True, WritableMedia=True, Internal=False, DeviceBlockSize=512)
    mf.verify_guest_info(valid, "disk7", 123)
    for key, value in (("WholeDisk", False), ("TotalSize", 124), ("BusProtocol", "SATA"),
                       ("Writable", False), ("Internal", True), ("DeviceBlockSize", 4096)):
        with pytest.raises(ValueError):
            mf.verify_guest_info(dict(valid, **{key:value}), "disk7", 123)


@pytest.fixture
def apfs():
    layout = dict(AllDisksAndPartitions=[dict(DeviceIdentifier="disk7", Content="GUID_partition_scheme", Partitions=[
        dict(Content="EFI", DeviceIdentifier="disk7s1"), dict(Content="Apple_APFS", DeviceIdentifier="disk7s2")])])
    data = dict(Containers=[dict(PhysicalStores=[dict(DeviceIdentifier="disk7s2")], APFSContainerUUID="container-uuid",
                Volumes=[dict(DeviceIdentifier="disk8s1", Name="Macintosh HD", APFSVolumeUUID="volume-uuid")])])
    return layout, data


def test_apfs_verification_tied_to_selected_disk_and_name(apfs):
    layout, data = apfs
    assert mf.verify_apfs(layout, data, "disk7", "Macintosh HD")["volume"] == "disk8s1"
    with pytest.raises(ValueError):
        mf.verify_apfs(layout, data, "disk9", "Macintosh HD")
    with pytest.raises(ValueError):
        mf.verify_apfs(layout, data, "disk7", "Wrong name")
    data["Containers"][0]["PhysicalStores"][0]["DeviceIdentifier"] = "disk10s2"
    with pytest.raises(ValueError):
        mf.verify_apfs(layout, data, "disk7", "Macintosh HD")


def test_helper_inherits_no_data_disks_or_host_handoff(mac, tmp_path):
    job = dict(release="tahoe", profile_root=str(tmp_path), iso="/test/recovery.iso", binary="/test/qemu",
               cpu=mac.data["cpu"], smp=mac.data["smp"], ram=16*1024**3, code="/test/CODE.fd")
    helper = mf.helper_config(job, tmp_path)
    assert {d["driver"] for d in helper.devices}.isdisjoint({"vfio-pci", "nvme", "ide-hd", "usb-host", "tpm-tis"})
    assert not helper.data["tools"]["kvm_build_enabled"]
    assert helper.data["network"]["mode"] == "user"
    paths = {b["filename"] for b in helper.blockdevs if "filename" in b}
    assert paths == {"/test/recovery.iso", "/test/CODE.fd", str(tmp_path/"OVMF_VARS.fd")}


def test_apply_updates_only_reviewed_mac_disk(mac, target):
    block = dict(driver="host_device", filename=target["path"], **{"node-name":"target", "read-only":False})
    device = dict(driver="nvme-ns", id="system", drive="target", bus="nvme0", nsid=1, uuid="old", addr="0x0")
    mac.blockdevs.append(block)
    mac.devices.append(device)
    before = copy.deepcopy(mac.data)
    result = dict(target=target, filesystem="APFS", scheme="GUID Partition Map", label="Macintosh HD", formatted_at="test")
    mf.apply_format_result(mac, block, device, result)
    assert device["driver"] == "ide-hd" and device["bus"] == "sata.0" and device["bootindex"] == 2
    assert not ({"nsid", "uuid", "addr"} & device.keys())
    assert not block["read-only"] and block["driver"] == "file"
    assert mac.devices[:-1] == before["devices"][:-1]
    assert mac.blockdevs[:-1] == before["blockdevs"][:-1]
    assert "_mac_format" not in model._emit(block)
    assert block["_mac_format"]["label"] == "Macintosh HD"
    mac.data["_meta"]["profile"] = "windows"
    after = copy.deepcopy(mac.data)
    with pytest.raises(ValueError, match="Windows"):
        mf.apply_format_result(mac, block, device, result)
    assert mac.data == after


def test_format_button_only_in_mac_disk_rows(window, app, monkeypatch):
    row = window.tab_disks.rows[0]
    assert row.btn_mac_format.isHidden()
    window.cfg.data.setdefault("_meta", {})["profile"] = "macos"
    window.tab_disks.reload()
    row = window.tab_disks.rows[0]
    assert not row.btn_mac_format.isHidden()
    row.ro.setChecked(True)
    assert not row.btn_mac_format.isEnabled()
    row.frontend.setCurrentText("ide-cd")
    row._update_notes()
    assert row.btn_mac_format.isHidden()


def test_running_vm_blocks_format_before_dialog(window, monkeypatch):
    window.cfg.data.setdefault("_meta", {})["profile"] = "macos"
    monkeypatch.setattr(ui.virtual_gpu, "service_active", lambda: True)
    warning = Mock()
    monkeypatch.setattr(QMessageBox, "warning", warning)
    make = Mock(side_effect=AssertionError("No dialog or target access while running"))
    monkeypatch.setattr(ui, "MacFormatDialog", make)
    window.tab_disks.format_mac_disk(window.tab_disks.rows[0])
    warning.assert_called_once()
    make.assert_not_called()


@pytest.fixture
def dialog(app, monkeypatch, mac, target):
    monkeypatch.setattr(mf, "prepare_job", lambda *args: dict(target=target, label="Macintosh HD"))
    d = ui.MacFormatDialog(mac, target["path"])
    yield d
    d.deleteLater()
    settle(app)


def test_review_requires_explicit_confirm_and_valid_name(dialog):
    assert not dialog.start_button.isEnabled()
    dialog.confirm.setChecked(True)
    assert dialog.start_button.isEnabled()
    dialog.volume_name.setText("bad/name")
    assert not dialog.start_button.isEnabled()
    dialog.volume_name.setText("My Mac")
    assert dialog.start_button.isEnabled()


def test_progress_and_cancel_boundary(dialog, tmp_path, monkeypatch):
    dialog.work = tmp_path
    monkeypatch.setattr(dialog, "running", lambda: True)
    dialog.reject()
    assert (tmp_path/"cancel").exists()
    (tmp_path/"cancel").unlink()
    dialog.handle_event(dict(stage="formatting", message="Creating APFS", irreversible=True))
    dialog.reject()
    assert not (tmp_path/"cancel").exists() and not dialog.close_button.isEnabled()
    dialog.handle_event(dict(stage="detail", message="Formatting: 42.0%"))
    assert dialog.progress.value() == 42


def test_worker_failure_cannot_report_success(dialog, monkeypatch):
    monkeypatch.setattr(dialog, "_read_output", lambda: None)
    dialog.handle_event(dict(stage="done", message="Ready", result=dict(label="Macintosh HD")))
    dialog.handle_event(dict(stage="error", message="Flush failed"))
    dialog._finished(1, QProcess.ExitStatus.NormalExit)
    assert dialog.result_data is None and dialog.progress.value() == 0
    assert "Flush failed" in dialog.status.text()


def test_submit_reserves_shared_vm_unit_without_launch_hooks(monkeypatch, tmp_path):
    job = tmp_path/"job.json"
    job.write_text('{}')
    monkeypatch.setattr(mf.sys, "argv", ["mac_format.py", "--submit", str(job)])
    monkeypatch.setattr(mf.virtual_gpu, "service_active", lambda: False)
    reset = Mock()
    monkeypatch.setattr(mf.subprocess, "run", reset)
    calls = []
    def execvp(program, argv):
        calls.append((program, argv))
        raise SystemExit(0)
    monkeypatch.setattr(mf.os, "execvp", execvp)
    with pytest.raises(SystemExit):
        mf.main()
    program, argv = calls[0]
    assert program == 'systemd-run'
    assert argv[argv.index('--unit')+1] == mf.virtual_gpu.UNIT
    assert '--wait' in argv and '--pipe' in argv
    assert argv[-2:] == ['--run', str(job)]


def test_submit_refuses_active_vm(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(mf.sys, "argv", ["mac_format.py", "--submit", str(tmp_path/'job.json')])
    monkeypatch.setattr(mf.virtual_gpu, "service_active", lambda: True)
    execute = Mock(side_effect=AssertionError('must not run'))
    monkeypatch.setattr(mf.os, "execvp", execute)
    assert mf.main() == 1
    execute.assert_not_called()
    assert json.loads(capsys.readouterr().out)['stage'] == 'error'


def test_live_file_opener_is_rejected(target, monkeypatch, tmp_path):
    fake_proc = tmp_path/'42'
    (fake_proc/'fd').mkdir(parents=True)
    (fake_proc/'fd/3').symlink_to(target['realpath'])
    original = Path.iterdir
    monkeypatch.setattr(Path, 'iterdir', lambda p: iter([fake_proc]) if p == Path('/proc') else original(p))
    with pytest.raises(ValueError, match='open in process 42'):
        mf.assert_no_openers(target)
    mf.assert_no_openers(target, allowed=(42,))


def test_verified_label_is_kept_for_apfs_and_cleared_for_other_drive(window, target, monkeypatch):
    cfg = window.cfg
    cfg.data.setdefault('_meta', {})['profile'] = 'macos'
    block, device = cfg.blockdevs[0], cfg.devices[0]
    block['filename'] = target['path']
    result = dict(target=target, filesystem='APFS', scheme='GUID Partition Map', label='My Mac', formatted_at='test')
    mf.apply_format_result(cfg, block, device, result)
    window.tab_disks.reload()
    row = window.tab_disks.rows[0]
    assert row.lbl_drive_label.text() == 'My Mac'
    row.path.setEditText('/different/drive.img')
    row._on_path()
    assert '_mac_format' not in block
    assert row.lbl_drive_label.text() == '—'
