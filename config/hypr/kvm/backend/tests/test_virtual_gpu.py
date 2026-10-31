"""Virtual launch isolation and resource ownership, plus optional QEMU smoke tests."""

import copy
import errno
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from model import VMConfig
import launcher
import virtual_gpu as vg
import virtual_runtime as vr


@pytest.fixture
def cfg(monkeypatch):
    monkeypatch.setattr(vg, "pci_class", lambda s: {"0000:01:00.0": 3, "0000:01:00.1": 4,
                                                  "0000:82:00.6": 4}.get(s))
    return VMConfig({
        "_meta": {"binary": "/test/qemu"}, "machine": {"type": "q35", "opts": {"usb": "off", "i8042": "off"}},
        "cpu": {"model": "host", "features": {}}, "smp": {"vcpus": "2", "topology": {"cores": "2"}},
        "simple": {"name": "same-guest", "m": "128M", "uuid": "guest-uuid", "display": "none", "vga": "none",
                   "netdev": '{"type":"tap","fd":"33","vhostfd":"34","id":"net0"}',
                   "qmp": "unix:/tmp/original-qmp,server,nowait", "mon": "chardev=monitor,mode=control",
                   "tpmdev": "emulator,id=tpm0,chardev=tpmchar", "no-shutdown": None, "S": None},
        "order": [[s, None] for s in ("machine", "cpu", "smp", "name", "m", "uuid", "display", "vga", "netdev",
                                       "qmp", "mon", "tpmdev", "no-shutdown", "S")],
        "devices": [
            {"driver": "vfio-pci", "id": "gpu-audio", "host": "0000:01:00.1", "bus": "pci.5"},
            {"driver": "vfio-pci", "id": "gpu", "host": "0000:01:00.0", "bus": "pci.6", "addr": "0x0"},
            {"driver": "vfio-pci", "id": "other-audio", "host": "0000:82:00.6"},
            {"driver": "usb-host", "id": "physical-keyboard", "vendorid": 1234, "productid": 5678},
            {"driver": "e1000e", "id": "nic0", "netdev": "net0", "mac": "52:54:00:12:34:56"},
            {"driver": "ide-hd", "id": "disk0", "drive": "disk0", "serial": "same-disk"},
            {"driver": "tpm-crb", "id": "tpm-device", "tpmdev": "tpm0"}],
        "objects": [{"qom-type": "memory-backend-file", "id": "pc.ram", "size": 128 * 1024**2,
                     "mem-path": "/dev/hugepages/preset", "prealloc": True}],
        "blockdevs": [{"driver": "file", "node-name": "disk0", "filename": "/test/disk.img"}],
        "chardevs": [{"id": "monitor", "_raw": "socket,id=monitor,fd=32,server=on,wait=off"},
                     {"id": "tpmchar", "path": "/tmp/original-tpm", "_raw": "socket,id=tpmchar,path=/tmp/original-tpm"}],
        "network": {"mode": "tap", "ifname": "existing-tap", "bridge": "existing-bridge"},
        "memory": {"hugepages": True, "pagesize": 2 * 1024**2},
        "tools": {"swtpm_binary": "/test/swtpm", "swtpm_state": "/test/tpm-state"},
        "pinning": {"vcpupin": [{"vcpu": 0, "cpuset": "2"}, {"vcpu": 1, "cpuset": "3"}]},
    })


def test_virtual_plan_preserves_shared_preset_and_guest_identity(cfg):
    command = cfg.to_argv(True)
    before = copy.deepcopy(cfg.data)
    plan = vg.prepare(cfg)
    assert cfg.data == before
    assert cfg.to_argv(True) == command
    copy_cfg = plan["config"]
    for key in ("cpu", "smp", "blockdevs", "tools", "pinning"):
        assert copy_cfg[key] == cfg.data[key]
    for key in ("uuid", "name", "m"):
        assert copy_cfg["simple"][key] == cfg.simple[key]
    assert plan["tpm"]["state"] == cfg.data["tools"]["swtpm_state"]
    assert plan["tpm"]["sock"] != "/tmp/original-tpm"
    assert plan["tap"]["name"] != cfg.data["network"]["ifname"]
    assert plan["tap"]["bridge"] == cfg.data["network"]["bridge"]
    assert plan["huge"]["pages"] == 64
    assert plan["huge"]["mount"] != cfg.objects[0]["mem-path"]
    assert not any(d["driver"] in ("vfio-pci", "usb-host") for d in copy_cfg["devices"])
    assert {"usb-kbd", "usb-tablet", "VGA"} <= {d["driver"] for d in copy_cfg["devices"]}
    assert plan["argv"].count("-S") == 1
    assert "-no-shutdown" not in plan["argv"] and "-mon" not in plan["argv"]
    assert not any("original-qmp" in v or "fd=32" in v for v in plan["argv"])


def test_existing_input_port_assignment_survives_controller_selection(cfg):
    cfg.devices.extend([{"driver": "qemu-xhci", "id": "usb"},
                        {"driver": "usb-kbd", "id": "keyboard", "bus": "usb.0", "port": "3"}])
    plan = vg.prepare(cfg)
    keyboard = next(d for d in plan["config"]["devices"] if d.get("id") == "keyboard")
    assert keyboard["bus"] == "usb.0" and keyboard["port"] == "3"


def test_opt_in_passthrough_keeps_other_devices_but_always_removes_gpu_functions(cfg):
    plan = vg.prepare(cfg, dict(keep_pci=True, keep_usb=True))
    ids = {d["id"] for d in plan["config"]["devices"]}
    assert "other-audio" in ids and "physical-keyboard" in ids
    assert "gpu" not in ids and "gpu-audio" not in ids
    net = json.loads(plan["config"]["simple"]["netdev"])
    assert "fd" not in net and "vhostfd" not in net
    assert net["script"] == net["downscript"] == "no"


def test_gpu_audio_is_removed_even_when_the_preset_does_not_include_the_gpu(cfg):
    cfg.devices[1]["_disabled"] = True
    plan = vg.prepare(cfg, dict(keep_pci=True))
    ids = {d["id"] for d in plan["config"]["devices"]}
    assert "gpu-audio" not in ids
    assert "other-audio" in ids


def test_raw_graphics_and_passthrough_are_filtered_too(cfg):
    cfg.devices[1] = {"_raw": "vfio-pci,id=gpu,host=01:00.0"}
    cfg.devices.append({"_raw": "virtio-gpu-gl-pci,id=old-virtual-gpu"})
    plan = vg.prepare(cfg, dict(keep_pci=True))
    assert not {"gpu", "gpu-audio", "old-virtual-gpu"} & {d["id"] for d in plan["config"]["devices"]}


def test_unknown_pci_cannot_accidentally_pass_the_host_gpu(cfg, monkeypatch):
    monkeypatch.setattr(vg, "pci_class", lambda _: None)
    with pytest.raises(ValueError, match="Cannot classify"):
        vg.prepare(cfg, dict(keep_pci=True))
    assert not any(d["driver"] == "vfio-pci" for d in vg.prepare(cfg)["config"]["devices"])


def test_spice_options_produce_local_server_and_agent_before_devices(cfg):
    plan = vg.prepare(cfg, dict(server="spice", port=5930, model="qxl-vga", clipboard=True, file_transfer=True, audio=True))
    args = plan["argv"]
    spice = args[args.index("-spice") + 1]
    assert "addr=127.0.0.1" in spice and "disable-copy-paste=off" in spice
    assert "disable-agent-file-xfer=off" in spice and "-vnc" not in args
    charindex = next(i for i, v in enumerate(args) if v.startswith("spicevmc,"))
    agentindex = next(i for i, v in enumerate(args) if '"driver":"virtserialport"' in v)
    assert charindex < agentindex
    assert json.loads(plan["config"]["simple"]["audiodev"])["driver"] == "spice"


def test_spice_resizing_has_an_agent_even_with_sharing_disabled(cfg):
    plan = vg.prepare(cfg, dict(server="spice", port=5930, clipboard=False, file_transfer=False))
    spice = plan["config"]["simple"]["spice"]
    assert "disable-copy-paste=on" in spice and "disable-agent-file-xfer=on" in spice
    ports = [d for d in plan["config"]["devices"] if d.get("name") == "com.redhat.spice.0"]
    assert len(ports) == 1
    assert ports[0]["chardev"] == plan["agent_chardev"]
    assert any(c["id"] == ports[0]["chardev"] and "spicevmc" in c["_raw"]
               for c in plan["config"]["chardevs"])


def test_inherited_agent_is_replaced_without_duplicate_ports_or_ids(cfg):
    cfg.data["chardevs"].append({"_raw": "socket,id=virtual-agent,path=/old/agent.sock"})
    cfg.devices.append({"_raw": "virtserialport,id=old-agent,chardev=virtual-agent,name=com.redhat.spice.0"})
    before = copy.deepcopy(cfg.data)
    plan = vg.prepare(cfg, dict(server="spice", port=5930))
    assert cfg.data == before
    assert "/old/agent.sock" not in " ".join(plan["argv"])
    ports = [d for d in plan["config"]["devices"] if d.get("name") == "com.redhat.spice.0"]
    assert len(ports) == 1
    assert plan["agent_chardev"] == ports[0]["chardev"] != "virtual-agent"


@pytest.mark.parametrize("model", vg.MODELS)
def test_large_resolution_has_enough_video_memory(cfg, model):
    plan = vg.prepare(cfg, dict(model=model, width=4096, height=4096))
    display = next(d for d in plan["config"]["devices"] if d["driver"] == model)
    assert (display["xres"], display["yres"]) == (4096, 4096)
    if model == "bochs-display":
        assert display["vgamem"] >= 4096 * 4096 * 4
    elif model in ("VGA", "qxl-vga"):
        assert display["vgamem_mb"] * 1024**2 >= 4096 * 4096 * 4
    if model == "qxl-vga":
        assert display["ram_size_mb"] >= display["vgamem_mb"] * 2
    else:
        assert display["edid"] is True


@pytest.mark.parametrize("width,height", [(640, 480), (800, 600), (1600, 900)])
def test_standard_low_resolutions_are_accepted(cfg, width, height):
    plan = vg.prepare(cfg, dict(width=width, height=height))
    assert plan["options"]["height"] == height


def test_firmware_display_plan_follows_pflash_nodes_and_can_be_disabled(cfg):
    cfg.data["machine"]["opts"]["pflash1"] = "vars-raw"
    cfg.blockdevs.extend([{"driver": "raw", "node-name": "vars-raw", "file": "vars-file"},
                         {"driver": "file", "node-name": "vars-file", "filename": "/test/vars.fd"}])
    before = copy.deepcopy(cfg.data)
    plan = vg.prepare(cfg, dict(model="bochs-display", width=1600, height=900))
    assert cfg.data == before
    assert plan["firmware_display"] == dict(path="/test/vars.fd", width=1600, height=900)
    assert vg.prepare(cfg, dict(uefi_resolution=False))["firmware_display"] is None
    assert vg.prepare(cfg, dict(model="qxl-vga"))["firmware_display"] is None
    cfg.blockdevs[-1]["read-only"] = True
    with pytest.raises(ValueError, match="writable raw UEFI"):
        vg.prepare(cfg)


def test_spice_uses_installed_spicy_when_remote_viewer_is_missing(monkeypatch):
    monkeypatch.setattr(vg.shutil, "which", lambda name: "/usr/bin/spicy" if name == "spicy" else None)
    assert vg.viewer_command(dict(server="spice", port=5930)) == [
        "/usr/bin/spicy", "--host=127.0.0.1", "--port=5930"]
    assert vg.viewer_command(dict(server="vnc", port=5901)) is None


def test_spice_prefers_remote_viewer_when_both_clients_are_installed(monkeypatch):
    monkeypatch.setattr(vg.shutil, "which", lambda name: "/usr/bin/" + name)
    assert vg.viewer_command(dict(server="spice", port=5930)) == [
        "/usr/bin/remote-viewer", "spice://127.0.0.1:5930"]


def test_console_observer_is_optional_and_cannot_prevent_opening(monkeypatch, tmp_path):
    monkeypatch.setattr(vg.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(launcher, "RUN_DIR", str(tmp_path))
    viewer = Mock(return_value=Mock(pid=12345))
    observer = Mock(side_effect=OSError("observer unavailable"))
    monkeypatch.setattr(vg.subprocess, "Popen", viewer)
    monkeypatch.setattr(vg.console_window, "observe", observer)
    opts = dict(server="spice", port=5930)
    vg.open_viewer(opts)
    observer.assert_not_called()
    vg.open_viewer(opts, remember_size=True)
    observer.assert_called_once_with(12345, tmp_path / "virtual-console-remote-viewer.json")
    assert viewer.call_count == 2
    assert viewer.call_args.args[0] == ["/usr/bin/remote-viewer", "spice://127.0.0.1:5930"]


def test_virtual_restart_overrides_inherited_exit_on_reboot_without_editing_preset(cfg):
    vg._flag(cfg, "no-reboot", None)
    before = copy.deepcopy(cfg.data)
    plan = vg.prepare(cfg)
    assert "-no-reboot" not in plan["argv"]
    assert cfg.data == before


@pytest.mark.parametrize("host", ["127.0.0.1", "0.0.0.0"])
def test_port_check_still_rejects_a_live_listener(host):
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((host, 0))
        listener.listen(1)
        with pytest.raises(OSError) as error:
            vg.probe_console_port(listener.getsockname()[1])
        assert error.value.errno == errno.EADDRINUSE


def test_port_check_allows_restart_while_closed_connection_is_in_time_wait():
    with socket.socket() as listener, socket.socket() as client:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        listener.listen(1)
        client.settimeout(2)
        client.connect(("127.0.0.1", port))
        connection, _ = listener.accept()
        # The server actively closes first, as QEMU does when shutting down
        # with an attached viewer. Its side then enters TCP TIME_WAIT.
        connection.close()
        assert client.recv(1) == b""
    with socket.socket() as old_probe:
        with pytest.raises(OSError) as error:
            old_probe.bind(("127.0.0.1", port))
        assert error.value.errno == errno.EADDRINUSE
    vg.probe_console_port(port)


def test_preflight_reports_socket_permission_error_without_claiming_port_is_busy(cfg, monkeypatch):
    monkeypatch.setattr(VMConfig, "validate", lambda _: [])
    monkeypatch.setattr(vg, "capabilities", lambda _: {"devices": vg.GRAPHICS, "vnc": True})
    monkeypatch.setattr(vg, "service_active", lambda: False)
    monkeypatch.setattr(vg, "probe_console_port", Mock(side_effect=PermissionError(errno.EACCES, "Permission denied")))
    checks = vg.preflight(vg.prepare(cfg))
    assert any("Cannot check console port" in msg and "Permission denied" in msg for _, msg in checks)
    assert not any("active listener" in msg for _, msg in checks)


@pytest.mark.parametrize("patched", [False, True])
def test_preflight_identifies_spice_driver_hardware_id_mismatches(cfg, monkeypatch, patched):
    monkeypatch.setattr(VMConfig, "validate", lambda _: [])
    monkeypatch.setattr(vg, "capabilities", lambda _: {"devices": vg.GRAPHICS | {"virtio-serial-pci", "virtserialport"}, "spice": True})
    monkeypatch.setattr(vg, "service_active", lambda: False)
    monkeypatch.setattr(vg, "probe_console_port", lambda _: None)
    monkeypatch.setattr(vg, "guest_device_ids", lambda _: {
        "qxl-vga": {"vendor": 0x1022 if patched else 0x1b36},
        "virtio-serial-pci": {"vendor": 0x1022 if patched else 0x1af4}})
    checks = vg.preflight(vg.prepare(cfg, dict(model="qxl-vga", server="spice", port=5930)))
    mismatches = [m for _, m in checks if "standard guest drivers expect" in m]
    assert len(mismatches) == (2 if patched else 0)


@pytest.mark.parametrize("agent_open,viewer_connected", [(False, False), (False, True), (True, True)])
def test_integration_reports_guest_channel_and_viewer_separately(monkeypatch, agent_open, viewer_connected):
    qmp = Mock()
    qmp.execute.side_effect = [{"enabled": True, "channels": [{}] if viewer_connected else []},
                              [{"label": "virtual-agent1", "frontend-open": agent_open}]]
    context = Mock(__enter__=Mock(return_value=qmp), __exit__=Mock(return_value=False))
    monkeypatch.setattr(vg, "QMP", lambda _: context)
    run = dict(qmp="/test/qmp", agent_chardev="virtual-agent1",
               options=dict(server="spice", model="qxl-vga", clipboard=True, file_transfer=False, audio=False))
    checks = vg.integration_checks(run)
    assert checks[0][0] == ("ok" if viewer_connected else "warn")
    assert checks[1][0] == ("ok" if agent_open else "warn")
    assert ("warn", "File transfer: disabled for this run") in checks


def test_explicit_memory_and_network_overrides_do_not_change_preset(cfg):
    before = copy.deepcopy(cfg.data)
    plan = vg.prepare(cfg, dict(memory="ordinary", network="user", pinning=False))
    assert cfg.data == before
    assert plan["huge"] is None and plan["tap"] is None and plan["pinning"] == {}
    assert plan["config"]["objects"][0]["qom-type"] == "memory-backend-ram"
    assert "mem-path" not in plan["config"]["objects"][0]
    assert json.loads(plan["config"]["simple"]["netdev"]) == {"type": "user", "id": "net0"}
    assert next(d for d in plan["config"]["devices"] if d["id"] == "nic0")["mac"] == "52:54:00:12:34:56"
    off = vg.prepare(cfg, dict(network="off"))
    assert "-netdev" not in off["argv"]
    assert not any(d.get("netdev") for d in off["config"]["devices"])


def test_launch_uses_same_unit_and_never_touches_hooks(cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(vg, "service_active", lambda: False)
    monkeypatch.setattr(launcher, "RUN_DIR", str(tmp_path / "run"))
    monkeypatch.setattr(vg.tempfile, "mkdtemp", lambda **_: str(tmp_path))
    run_command = Mock(return_value=subprocess.CompletedProcess([], 0, "started", ""))
    monkeypatch.setattr(vg.subprocess, "run", run_command)
    forbidden = Mock(side_effect=AssertionError("No single-GPU hooks"))
    for name in ("write_script", "write_hooks", "build_script", "build_start", "build_revert", "launch"):
        monkeypatch.setattr(launcher, name, forbidden)
    result = vg.launch(cfg)
    args = run_command.call_args_list[-1].args[0]
    assert args[args.index("--unit") + 1] == "vmstart2-vm"
    assert any(x.endswith("virtual_runtime.py") for x in args)
    assert f"--property=StandardOutput=append:{tmp_path}/output.log" in args
    assert f"--property=StandardError=append:{tmp_path}/output.log" in args
    payload = json.loads((tmp_path / "plan.json").read_text())
    assert not any(d.get("driver") == "vfio-pci" for d in payload["config"]["devices"])
    assert vg.current_run() == result
    forbidden.assert_not_called()


def test_busy_service_prevents_any_snapshot_or_launch(cfg, monkeypatch):
    monkeypatch.setattr(vg, "service_active", lambda: True)
    create = Mock()
    monkeypatch.setattr(vg.tempfile, "mkdtemp", create)
    with pytest.raises(RuntimeError, match="already running"):
        vg.launch(cfg)
    create.assert_not_called()


def test_missing_startup_status_becomes_a_visible_failure(tmp_path, monkeypatch):
    run = dict(workdir=str(tmp_path))
    plan = tmp_path / "plan.json"
    plan.write_text('{}')
    submitted = plan.stat().st_mtime
    monkeypatch.setattr(vg.time, "time", lambda: submitted + 1)
    assert vg.status(run)["state"] == "pending"
    monkeypatch.setattr(vg.time, "time", lambda: submitted + 21)
    monkeypatch.setattr(vg, "service_active", lambda: True)
    assert vg.status(run)["state"] == "pending"
    monkeypatch.setattr(vg, "service_active", lambda: False)
    state = vg.status(run)
    assert state["state"] == "failed"
    assert "before the VM supervisor" in state["message"]
    (tmp_path / "output.log").write_text("ModuleNotFoundError: fixture startup failure\n")
    assert "ModuleNotFoundError" in vg.read_log(run)
    (tmp_path / "status.json").write_text(json.dumps(dict(state="stopped", message="Guest stopped")))
    assert vg.status(run)["state"] == "stopped"
    assert vg.status({}) == {}


@pytest.mark.parametrize("script", ["virtual_runtime.py", "dual_runtime.py"])
def test_runtime_entry_imports_work_without_the_desktop_environment(tmp_path, script):
    # The intentionally absent plan proves imports completed without executing
    # any VM setup, even from an unrelated systemd-style working directory.
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    result = subprocess.run([sys.executable, "-E", "-s", str(Path(vr.__file__).with_name(script)),
                             str(tmp_path / "absent-plan.json")], cwd=tmp_path, env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert "ModuleNotFoundError" not in result.stderr, result.stderr
    assert "FileNotFoundError" in result.stderr and "absent-plan.json" in result.stderr


def test_runtime_records_an_early_launch_failure_without_touching_host_resources(tmp_path):
    plan = dict(workdir=str(tmp_path), uid=os.getuid(), gid=os.getgid(), config={},
                argv=[str(tmp_path / "nonexistent-qemu")])
    payload = tmp_path / "plan.json"
    payload.write_text(json.dumps(plan))
    result = subprocess.run([sys.executable, "-E", "-s", vr.__file__, str(payload)], cwd=tmp_path,
                            capture_output=True, text=True, timeout=10)
    run = dict(workdir=str(tmp_path))
    assert result.returncode == 1, result.stderr
    assert vg.status(run)["state"] == "failed"
    assert "nonexistent-qemu" in vg.read_log(run)


@pytest.mark.parametrize("failure", ["memory", "network", "tpm", "firmware_display", "start_guest", None])
def test_runtime_cleans_owned_resources_in_reverse_order_on_every_exit(cfg, tmp_path, monkeypatch, failure):
    plan = vg.prepare(cfg, workdir=str(tmp_path))
    runtime = vr.Runtime(plan)
    monkeypatch.setattr(vr.signal, "signal", lambda *_: None)
    monkeypatch.setattr(runtime, "status", Mock())
    monkeypatch.setattr(runtime, "check_passthrough", lambda: None)
    acquired, released = [], []
    for name in ("memory", "network", "tpm", "firmware_display", "start_guest"):
        def step(name=name):
            acquired.append(name)
            runtime.defer(released.append, name)
            if name == failure:
                raise RuntimeError("expected failure")
            return 0
        monkeypatch.setattr(runtime, name, step)
    forbidden = Mock(side_effect=AssertionError("No hooks on success or failure"))
    monkeypatch.setattr(launcher, "build_revert", forbidden)
    monkeypatch.setattr(launcher, "build_start", forbidden)
    assert runtime.run() == (1 if failure else 0)
    assert released == acquired[::-1]
    assert runtime.status.call_args.args[0] == ("failed" if failure else "stopped")
    forbidden.assert_not_called()


def test_network_cleanup_only_removes_tap_created_by_this_run(cfg, tmp_path, monkeypatch):
    runtime = vr.Runtime(vg.prepare(cfg, workdir=str(tmp_path)))
    commands = []
    monkeypatch.setattr(runtime, "command", lambda *args: commands.append(args))
    runtime.network()
    runtime.cleanup()
    tap = runtime.plan["tap"]["name"]
    assert commands[0] == ("ip", "tuntap", "add", "dev", tap, "mode", "tap")
    assert commands[-1] == ("ip", "tuntap", "del", "dev", tap, "mode", "tap")
    assert "existing-tap" not in str(commands)


def test_failed_tap_creation_does_not_remove_an_existing_interface(cfg, tmp_path, monkeypatch):
    runtime = vr.Runtime(vg.prepare(cfg, workdir=str(tmp_path)))
    command = Mock(side_effect=RuntimeError("tap already exists"))
    monkeypatch.setattr(runtime, "command", command)
    with pytest.raises(RuntimeError):
        runtime.network()
    runtime.cleanup()
    assert command.call_count == 1


def test_partial_hugepage_allocation_is_released(cfg, tmp_path, monkeypatch):
    plan = vg.prepare(cfg, workdir=str(tmp_path))
    pool = tmp_path / "nr_hugepages"
    pool.write_text("4")
    (tmp_path / "free_hugepages").write_text("2")
    (tmp_path / "resv_hugepages").write_text("1")
    plan["huge"]["pool"] = str(pool)
    runtime = vr.Runtime(plan)
    with pytest.raises(RuntimeError, match="Insufficient hugepages"):
        runtime.memory()
    assert int(pool.read_text()) > 4
    runtime.cleanup()
    assert pool.read_text() == "4"


def test_missing_tpm_state_never_creates_a_new_guest_identity(cfg, tmp_path, monkeypatch):
    plan = vg.prepare(cfg, workdir=str(tmp_path))
    state = tmp_path / "empty-state"
    state.mkdir()
    plan["tpm"]["state"] = str(state)
    child = Mock()
    monkeypatch.setattr(vr.subprocess, "Popen", child)
    with pytest.raises(RuntimeError, match="Existing TPM state"):
        vr.Runtime(plan).tpm()
    assert list(state.iterdir()) == []
    child.assert_not_called()


def tiny_config(binary):
    """An empty paused TCG machine: no VM disks, passthrough, TPM or host setup."""
    return VMConfig({"_meta": {"binary": binary}, "machine": {"type": "q35", "opts": {}},
                     "cpu": {"model": "max", "features": {}}, "smp": {"vcpus": "1", "topology": {}},
                     "simple": {"m": "64M", "nodefaults": None, "accel": "tcg"},
                     "order": [[key, None] for key in ("machine", "cpu", "smp", "m", "nodefaults", "accel")],
                     "devices": [], "objects": [], "blockdevs": [], "chardevs": []})


@pytest.mark.parametrize("model,server", [(m, "vnc") for m in vg.MODELS] + [("qxl-vga", "spice")])
@pytest.mark.parametrize("resolution", [(1600, 900), (4096, 4096)])
def test_generated_display_initializes_in_paused_diskless_qemu(tmp_path, model, server, resolution):
    binary = shutil.which("qemu-system-x86_64")
    if not binary:
        pytest.skip("QEMU not installed")
    caps = vg.capabilities(binary)
    if model not in caps["devices"] or not caps[server]:
        pytest.skip("Optional QEMU display backend not installed")
    with socket.socket() as port_socket:
        port_socket.bind(("127.0.0.1", 0))
        port = port_socket.getsockname()[1]
    plan = vg.prepare(tiny_config(binary), dict(model=model, server=server, port=port,
                       width=resolution[0], height=resolution[1], memory="ordinary",
                       network="off", pinning=False, clipboard=True, file_transfer=True, audio=True),
                       workdir=str(tmp_path))
    # Match the real preset's placement: a dedicated PCIe root port which used
    # to carry the physical GPU, rather than the default machine bus.
    vm = VMConfig(plan["config"])
    vm.devices.insert(0, {"driver": "pcie-root-port", "id": "test-port", "chassis": 1})
    next(d for d in vm.devices if d["driver"] == model)["bus"] = "test-port"
    plan["argv"] = vm.to_argv(True) + ["-S"]
    with open(tmp_path / "qemu.log", "w+") as output:
        child = subprocess.Popen(plan["argv"], stdin=subprocess.DEVNULL, stdout=output, stderr=output)
        try:
            deadline = time.monotonic() + 10
            while not Path(plan["qmp"]).exists() and child.poll() is None and time.monotonic() < deadline:
                time.sleep(0.05)
            output.seek(0)
            assert child.poll() is None, output.read()
            with vg.QMP(plan["qmp"]) as qmp:
                assert qmp.execute("query-status")["status"] == "prelaunch"
                qmp.execute("quit")
            child.wait(timeout=5)
            assert child.returncode == 0
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)


def test_runtime_reports_readiness_restarts_and_shuts_down_an_empty_guest(tmp_path):
    """Exercise the supervisor as a normal user, without systemd or host setup."""
    binary = shutil.which("qemu-system-x86_64")
    if not binary or "VGA" not in vg.capabilities(binary)["devices"]:
        pytest.skip("QEMU with VGA support not installed")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    plan = vg.prepare(tiny_config(binary), dict(server="vnc", port=port, memory="ordinary",
                                              network="off", pinning=False), workdir=str(tmp_path))
    assert not any(plan.get(key) for key in ("huge", "tap", "tpm"))
    assert not plan["config"]["blockdevs"]
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan))
    with open(tmp_path / "supervisor.log", "w+") as output:
        child = subprocess.Popen([sys.executable, "-E", "-s", vr.__file__, str(path)], cwd=tmp_path,
                                 stdin=subprocess.DEVNULL, stdout=output, stderr=output, start_new_session=True)
        try:
            deadline = time.monotonic() + 10
            run = {"workdir": str(tmp_path), "qmp": plan["qmp"]}
            state = {}
            while child.poll() is None and time.monotonic() < deadline:
                state = vg.status(run)
                if state.get("state") == "running":
                    break
                time.sleep(0.05)
            assert state.get("state") == "running", vg.read_log(run)
            assert Path(plan["qmp"]).stat().st_mode & 0o777 == 0o600
            with vg.QMP(plan["qmp"]) as qmp:
                assert qmp.execute("query-status")["running"] is True
            vg.control(run, "system_reset")
            with vg.QMP(plan["qmp"]) as qmp:
                assert qmp.execute("query-status")["running"] is True
            assert child.poll() is None
            assert vg.status(run)["state"] == "running"
            vg.control(run, "quit")
            child.wait(timeout=10)
            assert child.returncode == 0, vg.read_log(run)
            assert vg.status(run)["state"] == "stopped"
            assert "cleanup complete" in vg.read_log(run)
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=5)
