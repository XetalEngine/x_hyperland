"""Spare GPU selection, isolation and restoration using a synthetic PCI host."""

import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import Mock
import uuid

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import dual_gpu as dg
import dual_runtime as dr
import dual_devices as dd
import gpu_inventory as gi
import launcher
from model import VMConfig
import virtual_gpu as vg

HOST = "0000:01:00.0"
GPU = "0000:82:00.0"
AUDIO = "0000:82:00.1"
SOUND = "0000:82:00.6"


@pytest.fixture
def hardware(tmp_path, monkeypatch):
    sysfs, proc, dev = (tmp_path / n for n in ("sys", "proc", "dev"))
    pci = sysfs / "bus/pci/devices"
    for path in (pci, proc, dev, sysfs / "class/drm"):
        path.mkdir(parents=True)
    for name, path in (("SYS", sysfs), ("PROC", proc), ("DEV", dev), ("PCI", pci)):
        monkeypatch.setattr(gi, name, path)
    monkeypatch.setattr(gi.hostinfo, "pci_devices", lambda: [])
    monkeypatch.setattr(vg, "pci_class", lambda s: gi.pci_class(s) >> 16 if gi.pci_class(s) >= 0 else None)

    def add(slot, cls=0x030000, driver="amdgpu", group="73", boot=False):
        path = pci / slot
        path.mkdir()
        values = dict(vendor="0x1002", device="0x164e", subsystem_vendor="0x1849",
                      subsystem_device="0x1234", boot_vga=str(int(boot)),
                      driver_override="(null)", reset="", **{"class": hex(cls)})
        for name, value in values.items():
            (path / name).write_text(value + "\n")
        if driver:
            target = pci.parent / "drivers" / driver
            target.mkdir(parents=True, exist_ok=True)
            (target / "unbind").touch()
            (path / "driver").symlink_to(target)
        if group:
            target = sysfs / "kernel/iommu_groups" / group
            (target / "devices").mkdir(parents=True, exist_ok=True)
            (path / "iommu_group").symlink_to(target)
            (target / "devices" / slot).symlink_to(path)
        return path

    add(HOST, driver="nvidia", group="9", boot=True)
    add(GPU)
    add(AUDIO, cls=0x040300, driver="snd_hda_intel")
    for n, slot in enumerate((HOST, GPU)):
        node = sysfs / f"class/drm/card{n}"
        node.mkdir()
        (node / "device").symlink_to(pci / slot)
        (node / "dev").write_text(f"226:{n}")
    return add


@pytest.fixture
def cfg(hardware, tmp_path):
    disk = tmp_path / "disk.img"
    disk.touch()
    return VMConfig({
        "_meta": {"binary": "/test/qemu"},
        "machine": {"type": "q35", "opts": {"memory-backend": "pc.ram"}},
        "cpu": {"model": "host", "features": {}}, "smp": {"vcpus": "2", "topology": {"cores": "2"}},
        "simple": {"name": "same-windows", "m": "128M",
                   "uuid": "f4411c62-3280-4595-9a29-868304a51711", "vga": "none"},
        "order": [[s, None] for s in ("machine", "cpu", "smp", "name", "m", "uuid", "vga")],
        "devices": [{"driver": "vfio-pci", "host": HOST, "id": "gaming-gpu", "romfile": "/gaming.rom"},
                    {"driver": "vfio-pci", "host": "0000:10:00.0", "id": "other-PCI"},
                    {"driver": "usb-host", "id": "host-keyboard", "vendorid": 100},
                    {"driver": "ide-hd", "id": "disk", "drive": "disk-node", "serial": "same-disk"}],
        "blockdevs": [{"driver": "file", "node-name": "disk-node", "filename": str(disk)}],
        "objects": [{"qom-type": "memory-backend-ram", "id": "pc.ram", "size": 128 * 1024**2}],
        "virtual_gpu": {"model": "bochs-display", "uefi_resolution": True, "port": 5901},
        "dual_gpu": {"gpu": GPU, "gpu_identity": gi.identity(GPU),
                     "gpu_audio": True, "viewer": "looking-glass"},
        "pinning": {"vcpupin": [{"vcpu": 0, "cpuset": "2"}, {"vcpu": 1, "cpuset": "3"}]},
    })


@pytest.fixture
def extra_hardware(hardware):
    hardware(SOUND, cls=0x040300, driver="snd_hda_intel", group="80")
    controller = hardware("0000:82:00.3", cls=0x0c0330, driver="xhci_hcd", group="81")
    root = controller / "usb1/1-2"
    root.mkdir(parents=True)
    for key, value in dict(idVendor="1234", idProduct="5678", serial="unique-dac",
                           product="USB headset", busnum="1", devnum="5", bDeviceClass="00").items():
        (root / key).write_text(value)
    usb = gi.SYS / "bus/usb/devices"
    usb.mkdir(parents=True)
    (usb / "1-2").symlink_to(root)
    return dict(pci_devices=[dict(slot=SOUND, identity=gi.identity(SOUND))],
                usb_devices=[dict(port="1-2", identity=dd.inspect_usb("1-2")["identity"])])


def test_extra_devices_are_explicit_independent_and_in_supervised_plan(cfg, extra_hardware):
    original_argv = cfg.to_argv(True)
    original = copy.deepcopy(cfg.data)
    plan = dg.prepare(cfg, extra_hardware)
    assert [b["slot"] for b in plan["bindings"]] == [GPU, AUDIO, SOUND]
    usb = [d for d in plan["config"]["devices"] if d["driver"] == "usb-host"]
    assert len(usb) == 1
    assert usb[0]["hostbus"] == 1 and usb[0]["hostport"] == "2"
    assert (usb[0]["vendorid"], usb[0]["productid"]) == (0x1234, 0x5678)
    assert dd.verify_plan(plan, strict=True) == plan["extra_devices"]
    assert plan["argv"] == VMConfig(plan["config"]).to_argv(True) + ["-S"]
    assert cfg.data == original and cfg.to_argv(True) == original_argv


def test_sound_card_binding_and_restore_preserve_other_cards(runtime, cfg, extra_hardware):
    runtime.plan = dg.prepare(cfg, extra_hardware, workdir=str(runtime.directory))
    runtime.bind_gpu()
    assert gi.driver(SOUND) == "vfio-pci"
    assert gi.driver("0000:82:00.3") == "xhci_hcd"
    assert gi.driver(HOST) == "nvidia"
    assert runtime.cleanup() == []
    assert gi.driver(SOUND) == "snd_hda_intel"
    assert (gi.PCI / SOUND / "driver_override").read_text() == ""


def test_extra_card_bind_failure_rolls_back_every_selected_driver(runtime, cfg, extra_hardware, monkeypatch):
    runtime.plan = dg.prepare(cfg, extra_hardware, workdir=str(runtime.directory))
    write = runtime._write
    failed = False

    def fail_once(path, value):
        nonlocal failed
        if path.name == "drivers_probe" and value == SOUND and not failed:
            failed = True
            raise OSError("sound card bind failed")
        write(path, value)

    monkeypatch.setattr(runtime, "_write", fail_once)
    with pytest.raises(OSError, match="sound card bind failed"):
        runtime.bind_gpu()
    assert runtime.cleanup() == []
    assert gi.driver(GPU) == "amdgpu"
    assert gi.driver(AUDIO) == gi.driver(SOUND) == "snd_hda_intel"
    assert gi.driver(HOST) == "nvidia"


def test_explicit_sound_card_can_leave_sound_server_but_not_another_vm(cfg, extra_hardware, monkeypatch):
    monkeypatch.setattr(gi, "device_users", lambda slots:
                        (["wireplumber (PID 42)", "pipewire (PID 43)"] if SOUND in slots else [], True))
    dg.prepare(cfg, extra_hardware)
    monkeypatch.setattr(gi, "device_users", lambda slots:
                        (["qemu (PID 44)"] if SOUND in slots else [], True))
    with pytest.raises(ValueError, match="in use by qemu"):
        dg.prepare(cfg, extra_hardware)


def test_changed_or_shared_extra_pci_is_rejected(cfg, extra_hardware, hardware):
    settings = copy.deepcopy(extra_hardware)
    settings["pci_devices"][0]["identity"]["device"] = "wrong"
    with pytest.raises(ValueError, match="identity changed"):
        dg.prepare(cfg, settings)
    hardware("0000:83:00.0", cls=0x108000, driver="ccp", group="80")
    with pytest.raises(ValueError, match="IOMMU group also needs"):
        dg.prepare(cfg, extra_hardware)


def test_usb_change_and_injected_usb_cannot_bypass_runtime(runtime, cfg, extra_hardware):
    runtime.plan = dg.prepare(cfg, extra_hardware, workdir=str(runtime.directory))
    (gi.SYS / "bus/usb/devices/1-2/devnum").write_text("6")
    with pytest.raises(RuntimeError, match="changed since"):
        runtime.check_passthrough()
    assert not runtime.recorded_writes
    (gi.SYS / "bus/usb/devices/1-2/devnum").write_text("5")
    usb = next(d for d in runtime.plan["config"]["devices"] if d["driver"] == "usb-host")
    usb["hostport"] = "3"
    with pytest.raises(RuntimeError, match="unexpected USB"):
        runtime.check_passthrough()


def test_usb_owned_by_another_process_is_rejected(cfg, extra_hardware):
    node = gi.DEV / "bus/usb/001/005"
    node.parent.mkdir(parents=True)
    node.touch()
    proc = gi.PROC / "500"
    (proc / "fd").mkdir(parents=True)
    (proc / "fd/4").symlink_to(node)
    (proc / "comm").write_text("another-qemu")
    (proc / "maps").write_text("")
    with pytest.raises(ValueError, match="in use by another-qemu"):
        dg.prepare(cfg, extra_hardware)


def test_runtime_requires_complete_usb_ownership_check(runtime, cfg, extra_hardware, monkeypatch):
    runtime.plan = dg.prepare(cfg, dict(usb_devices=extra_hardware["usb_devices"]),
                              workdir=str(runtime.directory))
    monkeypatch.setattr(dd, "_open_users", lambda _: ([], False))
    with pytest.raises(ValueError, match="cannot inspect all device users"):
        runtime.check_passthrough()
    assert not runtime.recorded_writes


def test_active_network_controller_is_not_detached(cfg, hardware):
    nic = hardware("0000:83:00.0", cls=0x020000, driver="r8169", group="84")
    net = gi.SYS / "class/net/testnet"
    net.mkdir(parents=True)
    (net / "device").symlink_to(nic)
    (net / "flags").write_text("0x1003")
    settings = dict(pci_devices=[dict(slot=nic.name, identity=gi.identity(nic.name))])
    with pytest.raises(ValueError, match="network interface testnet is active"):
        dg.prepare(cfg, settings)
    (net / "flags").write_text("0x1002")
    assert dg.prepare(cfg, settings)["extra_devices"]["pci"][0]["slot"] == nic.name


def test_usb_identity_hubs_duplicates_and_controller_overlap_rejected(cfg, extra_hardware):
    root = gi.SYS / "bus/usb/devices/1-2"
    (root / "serial").write_text("replacement")
    with pytest.raises(ValueError, match="identity changed"):
        dg.prepare(cfg, extra_hardware)
    (root / "serial").write_text("unique-dac")
    (root / "bDeviceClass").write_text("09")
    with pytest.raises(ValueError, match="individually"):
        dg.prepare(cfg, extra_hardware)
    (root / "bDeviceClass").write_text("00")
    settings = copy.deepcopy(extra_hardware)
    settings["usb_devices"] *= 2
    with pytest.raises(ValueError, match="more than once"):
        dg.prepare(cfg, settings)
    settings = copy.deepcopy(extra_hardware)
    settings["pci_devices"].append(dict(slot="0000:82:00.3", identity=gi.identity("0000:82:00.3")))
    with pytest.raises(ValueError, match="already included"):
        dg.prepare(cfg, settings)


def test_mounted_usb_storage_is_not_detached(cfg, extra_hardware):
    block = gi.SYS / "bus/usb/devices/1-2/block/sdz/sdz1"
    block.mkdir(parents=True)
    (block / "dev").write_text("8:241")
    classes = gi.SYS / "class/block"
    classes.mkdir()
    (classes / "sdz1").symlink_to(block)
    (gi.PROC / "self").mkdir()
    (gi.PROC / "self/mountinfo").write_text("1 0 8:241 / /media/usb rw - ext4 /dev/sdz1 rw\n")
    with pytest.raises(ValueError, match="mounted Linux storage"):
        dg.prepare(cfg, extra_hardware)


def test_evdev_and_same_physical_usb_cannot_both_own_input(cfg, extra_hardware, monkeypatch):
    inputs = gi.SYS / "class/input/event9"
    inputs.mkdir(parents=True)
    (inputs / "device").symlink_to(gi.SYS / "bus/usb/devices/1-2")
    monkeypatch.setattr(dd.input_devices, "SYS", gi.SYS / "class/input")
    monkeypatch.setattr(dd.input_devices, "selection", lambda _: [dict(name="Test keyboard", node="/dev/input/event9")])
    with pytest.raises(ValueError, match="evdev and physical passthrough"):
        dg.prepare(cfg, extra_hardware)


def test_audio_choice_matches_client_provider_and_qemu_devices(cfg, monkeypatch):
    monkeypatch.setattr(dg.shutil, "which", lambda _: "/usr/bin/looking-glass-client")
    classic = dg.prepare(cfg, {"audio": True})
    assert "spice:usbAudio=no" in dg.viewer_command(classic)
    assert any(d["driver"] == "hda-output" for d in classic["config"]["devices"])
    assert vg._spec(classic["config"]["simple"]["audiodev"], "driver")["driver"] == "spice"
    usb = dg.prepare(cfg, {"audio": True, "audio_mode": "lg-usb"})
    assert "spice:usbAudio=yes" in dg.viewer_command(usb)
    assert "spice:audio=yes" in dg.viewer_command(usb)
    dev = next(d for d in usb["config"]["devices"] if d["driver"] == "usb-redir")
    assert any(c["id"] == dev["chardev"] and "name=usbredir" in c["_raw"]
               for c in usb["config"]["chardevs"])
    assert not any(d["driver"] in ("hda-output", "usb-host") for d in usb["config"]["devices"])
    off = dg.prepare(cfg, {"audio": False, "audio_mode": "lg-usb"})
    assert "spice:audio=no" in dg.viewer_command(off)
    assert not any(d["driver"] == "usb-redir" for d in off["config"]["devices"])


def test_audio_rejects_incompatible_viewers(cfg):
    with pytest.raises(ValueError, match="requires the Looking Glass viewer"):
        dg.prepare(cfg, {"audio": True, "audio_mode": "lg-usb", "viewer": "spice"})
    with pytest.raises(ValueError, match="VNC does not carry audio"):
        dg.prepare(cfg, {"audio": True, "viewer": "vnc"})


def test_discovery_offers_spare_and_protects_host(hardware):
    candidates = {g["slot"]: g for g in gi.discover()}
    assert not candidates[HOST]["available"]
    assert "Linux boot GPU" in candidates[HOST]["reasons"]
    assert candidates[GPU]["available"] and candidates[GPU]["verified"]
    assert candidates[GPU]["functions"] == [GPU, AUDIO]


def separate_audio_group():
    (gi.PCI / AUDIO / "iommu_group/devices" / AUDIO).unlink()
    (gi.PCI / AUDIO / "iommu_group").unlink()
    separate = gi.SYS / "kernel/iommu_groups/74"
    (separate / "devices").mkdir(parents=True)
    (gi.PCI / AUDIO / "iommu_group").symlink_to(separate)
    (separate / "devices" / AUDIO).symlink_to(gi.PCI / AUDIO)


def audio_control_user():
    card = gi.SYS / "class/sound/controlC1"
    card.mkdir(parents=True)
    (card / "device").symlink_to(gi.PCI / AUDIO)
    (card / "dev").write_text("116:9")
    node = gi.DEV / "snd/controlC1"
    node.parent.mkdir(parents=True)
    node.touch()
    process = gi.PROC / "1080"
    (process / "fd").mkdir(parents=True)
    (process / "comm").write_text("wireplumber")
    (process / "maps").write_text("")
    (process / "fd/55").symlink_to(node)


def test_defaults_do_not_require_looking_glass_or_take_hdmi_audio(cfg):
    cfg.data.pop("dual_gpu")
    opts = dg.options(cfg)
    assert opts["viewer"] == "spice"
    assert not opts["gpu_audio"]


def test_wireplumber_audio_handle_does_not_mean_gpu_is_busy(hardware):
    separate_audio_group()
    audio_control_user()
    blocked = next(g for g in gi.discover(audio=True) if g["slot"] == GPU)
    assert not blocked["available"] and blocked["audio_only_busy"]
    assert blocked["users"][GPU] == []
    assert blocked["users"][AUDIO] == ["wireplumber (PID 1080)"]
    assert any("HDMI/DP audio" in r and "wireplumber" in r for r in blocked["reasons"])
    assert any("Uncheck" in r for r in blocked["reasons"])
    gpu = gi.selected_gpu(GPU, audio=False, strict=True)
    assert gpu["available"] and gpu["functions"] == [GPU]


def test_busy_audio_in_same_iommu_group_cannot_be_omitted(hardware):
    audio_control_user()
    blocked = next(g for g in gi.discover(audio=True) if g["slot"] == GPU)
    assert not blocked["audio_only_busy"]
    with pytest.raises(RuntimeError, match="shares this GPU's IOMMU group"):
        gi.selected_gpu(GPU, audio=False, strict=True)


def test_amd_audio_does_not_claim_global_compute_device(hardware):
    assert str(gi.DEV / "kfd") in gi._nodes([GPU])[1]
    assert str(gi.DEV / "kfd") not in gi._nodes([AUDIO])[1]


def test_apu_usb_psp_and_analog_audio_are_never_automatically_taken(hardware):
    hardware("0000:82:00.2", cls=0x108000, driver="ccp", group="74")
    hardware("0000:82:00.3", cls=0x0c0330, driver="xhci_hcd", group="75")
    hardware("0000:82:00.6", cls=0x040300, driver="snd_hda_intel", group="76")
    assert gi.functions(GPU) == [GPU, AUDIO]
    assert gi.selected_gpu(GPU)["available"]


def test_shared_iommu_endpoint_blocks_but_bridge_is_allowed(hardware):
    hardware("0000:00:01.0", cls=0x060400, driver="pcieport")
    assert gi.selected_gpu(GPU)["available"]
    hardware("0000:82:00.3", cls=0x0c0330, driver="xhci_hcd")
    with pytest.raises(RuntimeError, match="IOMMU group also contains 0000:82:00.3"):
        gi.selected_gpu(GPU)


def test_missing_audio_selection_cannot_split_iommu_group(hardware):
    with pytest.raises(RuntimeError, match=AUDIO):
        gi.selected_gpu(GPU, audio=False)


def test_missing_gpu_iommu_and_changed_identity_fail_closed(hardware):
    with pytest.raises(RuntimeError, match="not visible"):
        gi.selected_gpu("0000:99:00.0")
    with pytest.raises(RuntimeError, match="has changed"):
        gi.selected_gpu(GPU, expected={"vendor": "wrong"})
    (gi.PCI / GPU / "iommu_group").unlink()
    with pytest.raises(RuntimeError, match="no IOMMU group"):
        gi.selected_gpu(GPU)


def test_no_host_display_gpu_prevents_headless_handoff(hardware):
    (gi.SYS / "class/drm/card0/device").unlink()
    with pytest.raises(RuntimeError, match="no other GPU"):
        gi.selected_gpu(GPU)


def test_active_output_is_protected_even_without_open_processes(hardware):
    connector = gi.SYS / "class/drm/card1/card1-HDMI-A-1"
    connector.mkdir()
    (connector / "enabled").write_text("enabled")
    (connector / "status").write_text("connected")
    with pytest.raises(RuntimeError, match="active display"):
        gi.selected_gpu(GPU)
    (connector / "enabled").write_text("disabled")
    assert gi.selected_gpu(GPU)["available"]  # An inactive dummy/monitor is OK.


@pytest.mark.parametrize("mapping", [False, True])
def test_device_handles_and_mappings_mark_spare_busy(hardware, monkeypatch, mapping):
    node = gi.DEV / "renderD129"
    node.touch()
    process = gi.PROC / "101"
    (process / "fd").mkdir(parents=True)
    (process / "comm").write_text("gpu-worker")
    if mapping:
        (process / "maps").write_text(f"1-2 rw-s 0 00:01 1 {node}\n")
    else:
        (process / "fd/3").symlink_to(node)
        (process / "maps").write_text("")
    monkeypatch.setattr(gi, "_nodes", lambda _: (set(), {str(node)}))
    with pytest.raises(RuntimeError, match="gpu-worker"):
        gi.selected_gpu(GPU)


def test_unknown_usage_blocks_privileged_handoff(hardware, monkeypatch):
    monkeypatch.setattr(gi, "device_users", lambda _: ([], False))
    assert gi.selected_gpu(GPU)["available"]
    with pytest.raises(RuntimeError, match="Cannot inspect all device users"):
        gi.selected_gpu(GPU, strict=True)


def test_plan_preserves_other_modes_identity_disks_and_preset(cfg):
    command = cfg.to_argv(True)
    before = copy.deepcopy(cfg.data)
    plan = dg.prepare(cfg)
    assert cfg.data == before and cfg.to_argv(True) == command
    assert plan["firmware_display"] is None
    assert plan["config"]["blockdevs"] == cfg.blockdevs
    assert plan["config"]["cpu"] == cfg.data["cpu"]
    assert plan["config"]["simple"]["uuid"] == cfg.simple["uuid"]
    assert plan["config"]["virtual_gpu"] == cfg.data["virtual_gpu"]
    devices = plan["config"]["devices"]
    assert [d["host"] for d in devices if d["driver"] == "vfio-pci"] == [GPU, AUDIO]
    assert not any(d.get("romfile") or d["driver"] == "usb-host" for d in devices)
    args = plan["argv"]
    assert args.count("-S") == 1
    assert args.index(next(a for a in args if '"id":"dual-lg-memory"' in a)) < args.index(
        next(a for a in args if '"driver":"ivshmem-plain"' in a))


def smbios_blob(cfg, tmp_path, identity):
    # Deliberately differ from -uuid and place Type 1 after another structure.
    # Include a comma in the filename to exercise QEMU's doubled-comma syntax.
    blob = tmp_path / "guest,identity.bin"
    table = bytearray(27)
    table[0:2] = bytes((1, len(table)))
    table[8:24] = identity.bytes_le
    blob.write_bytes(b"\x00\x04\x00\x00\x00\x00" + table + b"\x00\x00")
    vg._flag(cfg, "smbios", "file=" + str(blob).replace(",", ",,"))
    return blob


def test_looking_glass_spice_uuid_matches_existing_smbios_without_editing_it(cfg, tmp_path):
    identity = uuid.UUID("12345678-9abc-4def-8123-456789abcdef")
    blob = smbios_blob(cfg, tmp_path, identity)
    original = blob.read_bytes()
    command = cfg.to_argv(True)
    before = copy.deepcopy(cfg.data)

    plan = dg.prepare(cfg)

    assert plan["config"]["simple"]["uuid"] == str(identity)
    assert plan["argv"][plan["argv"].index("-uuid") + 1] == str(identity)
    assert plan["argv"] == VMConfig(plan["config"]).to_argv(True) + ["-S"]
    assert plan["looking_glass_identity"] == dict(source=str(blob), uuid=str(identity))
    assert cfg.data == before and cfg.to_argv(True) == command
    assert blob.read_bytes() == original
    assert plan["config"]["simple"]["smbios"] == cfg.simple["smbios"]


@pytest.mark.parametrize("viewer", ["spice", "vnc", "physical"])
def test_other_dual_viewers_keep_the_preset_qemu_uuid(cfg, tmp_path, viewer):
    smbios_blob(cfg, tmp_path, uuid.UUID("12345678-9abc-4def-8123-456789abcdef"))
    plan = dg.prepare(cfg, {"viewer": viewer})
    assert plan["config"]["simple"]["uuid"] == cfg.simple["uuid"]
    assert plan["looking_glass_identity"] is None


def test_smbios_without_type1_keeps_qemu_uuid(cfg, tmp_path):
    blob = smbios_blob(cfg, tmp_path, uuid.UUID(int=1))
    blob.write_bytes(b"\x00\x04\x00\x00\x00\x00")
    plan = dg.prepare(cfg)
    assert plan["config"]["simple"]["uuid"] == cfg.simple["uuid"]
    assert plan["looking_glass_identity"] is None


@pytest.mark.parametrize("value", [0, (1 << 128) - 1])
def test_unset_smbios_uuid_cannot_validate_a_looking_glass_guest(cfg, tmp_path, value):
    smbios_blob(cfg, tmp_path, uuid.UUID(int=value))
    with pytest.raises(ValueError, match="UUID is unset"):
        dg.prepare(cfg)


def test_short_smbios_type1_cannot_supply_a_looking_glass_uuid(cfg, tmp_path):
    blob = smbios_blob(cfg, tmp_path, uuid.UUID(int=1))
    blob.write_bytes(b"\x01\x04\x00\x00\x00\x00")
    with pytest.raises(ValueError, match="Type 1 table is too short"):
        dg.prepare(cfg)


def test_rom_is_explicitly_selected_for_the_spare_gpu(cfg, tmp_path):
    rom = tmp_path / "igpu.rom"
    rom.write_bytes(b"test")
    plan = dg.prepare(cfg, {"romfile": str(rom), "viewer": "physical"})
    assert not plan["shared_memory"]
    passed = [d for d in plan["config"]["devices"] if d["driver"] == "vfio-pci"]
    assert passed[0]["romfile"] == str(rom)
    assert "romfile" not in passed[1]


@pytest.mark.parametrize("width,height,mib", [(1920, 1080, 32), (2560, 1440, 64), (3840, 2160, 128)])
def test_lg_buffer_supports_three_aligned_frames(width, height, mib):
    assert dg.shared_memory_size(width, height) == mib * 1024**2


def test_raw_passthrough_flags_cannot_bypass_selection(cfg):
    cfg.simple["device"] = f"vfio-pci,host={HOST}"
    with pytest.raises(ValueError, match="structured"):
        dg.prepare(cfg)


@pytest.fixture
def runtime(cfg, tmp_path, monkeypatch):
    instance = dr.Runtime(dg.prepare(cfg, {"viewer": "physical"}, workdir=str(tmp_path)))
    monkeypatch.setattr(instance, "status", Mock())
    monkeypatch.setattr(dr.signal, "signal", lambda *_: None)
    commands = Mock()
    monkeypatch.setattr(instance, "command", commands)
    writes = []

    def write(path, value):
        writes.append((str(path), value))
        if path.name == "driver_override":
            path.write_text(value)
        elif path.name == "unbind":
            (path.parent.parent / "driver").unlink()
        elif path.name == "drivers_probe":
            target = gi.PCI / value
            selected = (target / "driver_override").read_text()
            driver = gi.PCI.parent / "drivers" / selected
            driver.mkdir(parents=True, exist_ok=True)
            (target / "driver").symlink_to(driver)
        else:
            raise AssertionError(f"Unexpected write: {path}")

    monkeypatch.setattr(instance, "_write", write)
    instance.recorded_writes = writes
    return instance


def test_binding_restores_exact_drivers_and_overrides(runtime):
    (gi.PCI / GPU / "driver_override").write_text("amdgpu")
    runtime.bind_gpu()
    assert gi.driver(GPU) == gi.driver(AUDIO) == "vfio-pci"
    assert gi.driver(HOST) == "nvidia"
    assert not runtime.cleanup()
    assert gi.driver(GPU) == "amdgpu" and gi.driver(AUDIO) == "snd_hda_intel"
    assert (gi.PCI / GPU / "driver_override").read_text() == "amdgpu"
    assert (gi.PCI / AUDIO / "driver_override").read_text() == ""
    assert all(HOST not in path for path, _ in runtime.recorded_writes)
    runtime.command.assert_called_once_with("modprobe", "vfio-pci")
    assert json.loads((runtime.directory / "gpu-bindings.json").read_text())["state"] == "restored"


def test_gpu_only_runtime_keeps_wireplumber_audio_binding(runtime, cfg):
    separate_audio_group()
    audio_control_user()
    runtime.plan = dg.prepare(cfg, {"gpu_audio": False, "viewer": "spice"},
                              workdir=str(runtime.directory))
    runtime.bind_gpu()
    assert gi.driver(GPU) == "vfio-pci"
    assert gi.driver(AUDIO) == "snd_hda_intel"
    assert not runtime.cleanup()
    assert gi.driver(GPU) == "amdgpu"
    assert all(AUDIO not in path for path, _ in runtime.recorded_writes)
    assert gi.device_users([AUDIO])[0] == ["wireplumber (PID 1080)"]


@pytest.mark.parametrize("original", ["", "vfio-pci"])
def test_original_unbound_and_vfio_states_are_preserved(runtime, original):
    (gi.PCI / GPU / "driver").unlink()
    if original:
        target = gi.PCI.parent / "drivers" / original
        target.mkdir(parents=True, exist_ok=True)
        (gi.PCI / GPU / "driver").symlink_to(target)
    runtime.bind_gpu()
    assert not runtime.cleanup()
    assert gi.driver(GPU) == original


def test_partial_binding_failure_restores_both_functions(runtime, monkeypatch):
    write = runtime._write
    failed = False

    def failing(path, value):
        nonlocal failed
        if path.name == "drivers_probe" and value == AUDIO and not failed:
            failed = True
            raise OSError("injected bind failure")
        write(path, value)

    monkeypatch.setattr(runtime, "_write", failing)
    with pytest.raises(OSError, match="injected"):
        runtime.bind_gpu()
    assert not runtime.cleanup()
    assert gi.driver(GPU) == "amdgpu" and gi.driver(AUDIO) == "snd_hda_intel"


def test_device_becoming_busy_after_plan_prevents_all_driver_writes(runtime, monkeypatch):
    monkeypatch.setattr(gi, "device_users", lambda _: (["new-renderer (PID 42)"], True))
    assert runtime.run() == 1
    assert not runtime.recorded_writes
    runtime.command.assert_not_called()
    assert runtime.status.call_args.args[0] == "failed"


def test_modified_group_or_unexpected_host_gpu_in_plan_is_rejected(runtime, hardware):
    hardware("0000:82:00.3", cls=0x0c0330, driver="xhci_hcd")
    with pytest.raises(RuntimeError, match="IOMMU"):
        runtime.check_passthrough()
    assert not runtime.recorded_writes


def test_command_must_match_checked_devices(runtime):
    runtime.plan["argv"] += ["-device", f"vfio-pci,host={HOST}"]
    with pytest.raises(RuntimeError, match="command does not match"):
        runtime.check_passthrough()


@pytest.mark.parametrize("exit_kind", ["success", "startup-failure", "qemu-error", "interrupt"])
def test_gpu_returns_to_linux_on_guest_exit_and_startup_failure(runtime, monkeypatch, exit_kind):
    order = []
    for name in ("memory", "network", "tpm", "shared_memory"):
        def acquire(name=name):
            order.append(name)
            runtime.defer(order.append, "release-" + name)
        monkeypatch.setattr(runtime, name, acquire)
    forbidden = Mock(side_effect=AssertionError("No hooks or firmware override"))
    monkeypatch.setattr(runtime, "firmware_display", forbidden)
    monkeypatch.setattr(launcher, "build_start", forbidden)
    monkeypatch.setattr(launcher, "build_revert", forbidden)

    def guest():
        assert gi.driver(GPU) == "vfio-pci"
        runtime.defer(order.append, "stop-qemu")
        if exit_kind == "startup-failure":
            raise RuntimeError("startup failed")
        if exit_kind == "interrupt":
            raise InterruptedError("service stopped")
        return 0 if exit_kind == "success" else 2

    monkeypatch.setattr(runtime, "start_guest", guest)
    assert (runtime.run() == 0) == (exit_kind == "success")
    assert gi.driver(GPU) == "amdgpu" and gi.driver(AUDIO) == "snd_hda_intel"
    assert order[4:] == ["stop-qemu", "release-shared_memory", "release-tpm",
                          "release-network", "release-memory"]
    forbidden.assert_not_called()


def test_restoration_failure_is_reported_and_journal_preserved(runtime, monkeypatch):
    runtime.bind_gpu()
    write = runtime._write

    def fail_restore(path, value):
        if path.name == "drivers_probe" and value == GPU:
            raise OSError("GPU will not reset")
        write(path, value)

    monkeypatch.setattr(runtime, "_write", fail_restore)
    failures = runtime.cleanup()
    assert failures and "GPU will not reset" in failures[0]
    assert gi.driver(AUDIO) == "snd_hda_intel"
    journal = json.loads((runtime.directory / "gpu-bindings.json").read_text())
    assert journal["state"] == "restore-failed"
    assert journal["bindings"][0]["driver"] == "amdgpu"


def test_restore_will_not_detach_a_new_owner_or_a_running_vm(runtime):
    runtime.bind_gpu()
    originals = runtime.cleanup_actions[-1][1][0]
    runtime.child = Mock()
    runtime.child.poll.return_value = None
    with pytest.raises(RuntimeError, match="QEMU is still running"):
        runtime.restore_gpu(originals)
    runtime.child = None
    (gi.PCI / GPU / "driver").unlink()
    other = gi.PCI.parent / "drivers/another-owner"
    other.mkdir()
    (gi.PCI / GPU / "driver").symlink_to(other)
    assert runtime.cleanup()
    assert gi.driver(GPU) == "another-owner"


def test_shared_memory_is_private_owned_and_never_adopted(runtime, tmp_path, monkeypatch):
    monkeypatch.setattr(dr, "SHM_ROOT", tmp_path)
    path = tmp_path / "vmstart2-lg-test"
    runtime.plan["shared_memory"] = dict(path=str(path), size=32 * 1024**2)
    runtime.shared_memory()
    assert path.stat().st_size == 32 * 1024**2
    assert path.stat().st_mode & 0o777 == 0o600
    assert not runtime.cleanup()
    assert not path.exists()
    path.write_bytes(b"existing")
    with pytest.raises(FileExistsError):
        runtime.shared_memory()
    runtime.cleanup()
    assert path.read_bytes() == b"existing"


def test_launch_uses_global_vm_lock_and_no_single_gpu_hooks(cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(vg, "service_active", lambda: False)
    monkeypatch.setattr(launcher, "RUN_DIR", str(tmp_path / "run"))
    monkeypatch.setattr(dg.tempfile, "mkdtemp", lambda **_: str(tmp_path))
    command = Mock(return_value=subprocess.CompletedProcess([], 0, "started", ""))
    monkeypatch.setattr(dg.subprocess, "run", command)
    forbidden = Mock(side_effect=AssertionError("No Single GPU hooks"))
    for name in ("launch", "build_start", "build_revert", "write_hooks", "write_script"):
        monkeypatch.setattr(launcher, name, forbidden)
    run = dg.launch(cfg)
    argv = command.call_args.args[0]
    assert argv[argv.index("--unit") + 1] == "vmstart2-vm"
    assert any(s.endswith("dual_runtime.py") for s in argv)
    assert f"--property=StandardOutput=append:{tmp_path}/output.log" in argv
    assert f"--property=StandardError=append:{tmp_path}/output.log" in argv
    assert dg.current_run() == run
    assert not vg.current_path().exists()
    forbidden.assert_not_called()
    monkeypatch.setattr(vg, "service_active", lambda: True)
    with pytest.raises(RuntimeError, match="already running"):
        dg.launch(cfg)


def test_viewer_uses_active_run_and_local_spice_policy(cfg, monkeypatch):
    plan = dg.prepare(cfg, {"port": 6200, "clipboard": False, "audio": True}, token="one")
    monkeypatch.setattr(dg.shutil, "which", lambda _: "/test/looking-glass-client")
    cfg.data["dual_gpu"].update(port=6300, clipboard=True)
    command = dg.viewer_command(plan)
    assert "spice:port=6200" in command and "spice:clipboard=no" in command
    assert "audio:micDefault=deny" in command
    assert plan["shared_memory"]["path"] in command
    assert "spice:input=yes" in command
    assert "input:captureOnStart=yes" in command


def test_dual_restores_ps2_without_changing_single_gpu_preset(cfg):
    cfg.data["machine"]["opts"]["i8042"] = "off"
    cfg.objects.append({"qom-type": "input-linux", "id": "single-keyboard",
                        "evdev": "/dev/input/host-only"})
    before = copy.deepcopy(cfg.data)
    plan = dg.prepare(cfg)
    assert cfg.data == before
    assert plan["config"]["machine"]["opts"]["i8042"] == "on"
    assert not any(o.get("qom-type") == "input-linux" for o in plan["config"]["objects"])
    assert any("i8042=on" in arg for arg in plan["argv"])


def test_evdev_is_explicit_and_viewer_capture_does_not_duplicate_it(cfg, monkeypatch):
    devices = [{"path": "/dev/input/by-id/test-event-kbd", "node": "/dev/input/event3"},
               {"path": "/dev/input/by-id/test-event-mouse", "node": "/dev/input/event8"}]
    monkeypatch.setattr(dg.input_devices, "selection", lambda _: copy.deepcopy(devices))
    before = copy.deepcopy(cfg.data)
    plan = dg.prepare(cfg, {"input_mode": "evdev", "evdev_toggle": "shift-shift"})
    assert cfg.data == before
    objects = [o for o in plan["config"]["objects"] if o.get("qom-type") == "input-linux"]
    assert [o["evdev"] for o in objects] == [d["path"] for d in devices]
    assert objects[0]["grab_all"] and objects[0]["repeat"]
    assert objects[0]["grab-toggle"] == "shift-shift"
    assert plan["input_devices"] == devices
    dg.input_devices.verify_plan(plan)
    monkeypatch.setattr(dg.shutil, "which", lambda _: "/test/looking-glass-client")
    command = dg.viewer_command(plan)
    assert "spice:input=no" in command
    assert "input:captureOnly=yes" in command
    assert "input:captureOnStart=no" in command
    assert "input:grabKeyboard=no" in command


def test_runtime_checks_evdev_before_touching_gpu(runtime, monkeypatch):
    runtime.plan["input_devices"] = [{"path": "/dev/input/changed"}]
    gpu_check = Mock(side_effect=AssertionError("Do not reach GPU setup"))
    monkeypatch.setattr(gi, "selected_gpu", gpu_check)
    with pytest.raises(RuntimeError, match="changed since launch"):
        runtime.check_passthrough()
    gpu_check.assert_not_called()


@pytest.mark.parametrize("viewer", ["spice", "vnc", "physical"])
def test_non_lg_modes_do_not_add_or_probe_ivshmem(cfg, monkeypatch, viewer):
    plan = dg.prepare(cfg, {"viewer": viewer})
    assert plan["shared_memory"] is None
    assert all(d["driver"] != "ivshmem-plain" for d in plan["config"]["devices"])
    assert not any(o.get("id", "").startswith("dual-lg") for o in plan["config"]["objects"])
    assert [d["host"] for d in plan["config"]["devices"] if d["driver"] == "vfio-pci"] == [GPU, AUDIO]
    assert plan["options"]["server"] == ("vnc" if viewer == "vnc" else "spice")
    if viewer == "vnc":
        assert "-vnc" in plan["argv"] and "-spice" not in plan["argv"]
        assert not any(d.get("name") == "com.redhat.spice.0" for d in plan["config"]["devices"])
    monkeypatch.setattr(vg, "preflight", lambda _: [])
    monkeypatch.setattr(vg, "capabilities", lambda _: {"devices": {"vfio-pci", "pcie-root-port"}})
    forbidden = Mock(side_effect=AssertionError("Looking Glass is optional"))
    monkeypatch.setattr(dg, "ivshmem_ids", forbidden)
    assert not any(s == "error" for s, _ in dg.preflight(plan))
    forbidden.assert_not_called()


@pytest.mark.parametrize("viewer", ["spice", "vnc"])
def test_console_viewers_use_the_active_run_without_looking_glass(cfg, monkeypatch, viewer):
    plan = dg.prepare(cfg, {"viewer": viewer, "port": 6211})
    monkeypatch.setattr(dg.shutil, "which", lambda name: None if name == "looking-glass-client" else "/test/" + name)
    command = dg.viewer_command(plan)
    assert command and not any("looking-glass" in part for part in command)
    assert any("6211" in part for part in command)
    cfg.data["dual_gpu"].update(viewer="looking-glass", port=6311)
    launch = Mock()
    monkeypatch.setattr(vg, "open_viewer", launch)
    dg.open_viewer(plan)
    launch.assert_called_once_with(plan["options"])
    assert launch.call_args.args[0]["server"] == viewer


def test_preflight_explains_custom_ivshmem_ids(cfg, monkeypatch):
    plan = dg.prepare(cfg)
    monkeypatch.setattr(vg, "preflight", lambda _: [])
    monkeypatch.setattr(vg, "capabilities", lambda _: {
        "devices": {"vfio-pci", "pcie-root-port", "ivshmem-plain"}})
    monkeypatch.setattr(dg, "ivshmem_ids", lambda _: {"vendor": 0x1022, "device": 0x1110})
    monkeypatch.setattr(dg.shutil, "which", lambda _: None)
    checks = dg.preflight(plan)
    assert any("1022:1110" in message and "will not bind" in message for _, message in checks)
    assert any("not installed" in message for _, message in checks)
    assert not any(severity == "error" for severity, _ in checks)


def test_installed_qemu_can_initialize_lg_transport_without_host_devices(cfg, tmp_path):
    binary = shutil.which("qemu-system-x86_64")
    if not binary:
        pytest.skip("QEMU not installed")
    if not {"VGA", "ivshmem-plain", "pcie-root-port"} <= vg.capabilities(binary)["devices"]:
        pytest.skip("QEMU lacks required display/IVSHMEM devices")
    cfg.data["_meta"]["binary"] = binary
    cfg.data["cpu"]["model"] = "max"
    cfg.data["machine"]["opts"]["accel"] = "tcg"
    plan = dg.prepare(cfg, {"pinning": False}, workdir=str(tmp_path))
    vm = VMConfig(plan["config"])
    for device in vm.devices:
        if device["driver"] in ("vfio-pci", "ide-hd"):
            device["_disabled"] = True
    for block in vm.blockdevs:
        block["_disabled"] = True
    for obj in vm.objects:
        if obj["id"].startswith("dual-lg-memory"):
            obj["mem-path"] = str(tmp_path / "frames")
    vg._drop(vm, "spice", "qmp")
    for char in vm.data["chardevs"]:
        if "spicevmc" in char.get("_raw", ""):
            char["_disabled"] = True
    for device in vm.devices:
        if device.get("name") == "com.redhat.spice.0":
            device["_disabled"] = True
    vg._flag(vm, "qmp", "stdio")
    vm.compact()
    commands = "\n".join(json.dumps({"execute": c, "id": c}) for c in
                         ("qmp_capabilities", "query-pci", "quit")) + "\n"
    result = subprocess.run(vm.to_argv(True) + ["-S"], input=commands,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    replies = [json.loads(line) for line in result.stdout.splitlines()]
    pci = next(reply["return"] for reply in replies if reply.get("id") == "query-pci")
    ids = [device["id"] for bus in pci for device in bus["devices"] if device["qdev_id"] == "dual-lg"]
    assert len(ids) == 1 and ids[0]["device"] == 0x1110
