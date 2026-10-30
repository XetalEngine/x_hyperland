"""Mac resource checks must fail before handoff and never provision the host."""

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import launcher
import mac_memory
from model import VMConfig
import virtual_gpu
import virtual_runtime
from test_ui_navigation import app


@pytest.fixture
def mac(tmp_path):
    return VMConfig({
        "_meta": {"profile": "macos", "binary": "/usr/bin/qemu-system-x86_64"},
        "simple": {"name": "guest=macOS,debug-threads=on", "m": "32G"},
        "machine": {"type": "q35", "opts": {"memory-backend": "pc.ram"}},
        "cpu": {"model": "Skylake-Client", "features": {}},
        "smp": {"vcpus": "2", "topology": {"cores": "1", "threads": "2"}},
        "objects": [{"qom-type": "memory-backend-file", "id": "pc.ram", "size": 32 * 1024**3,
                     "prealloc": True, "mem-path": str(tmp_path)}],
        "memory": {"hugepages": True, "pagesize": 1024**3},
        "network": {"mode": "off"}, "devices": [], "blockdevs": [],
    })


def pool(monkeypatch, free=32, reserved=0, page=1024**3, quota=0):
    def read(filename):
        if filename.endswith("free_hugepages"):
            return str(free)
        if filename.endswith("resv_hugepages"):
            return str(reserved)
        raise AssertionError(filename)
    monkeypatch.setattr(mac_memory, "_read", read)
    monkeypatch.setattr(mac_memory, "mount_for", lambda p: dict(mount=p, type="hugetlbfs", pagesize=page, options=["rw"]))
    monkeypatch.setattr(mac_memory.os, "statvfs", lambda p: SimpleNamespace(f_flag=0, f_blocks=quota,
                                                                         f_bavail=quota, f_frsize=page))


def errors(mac):
    return [message for severity, message in mac_memory.checks(mac_memory.spec(mac)) if severity == "error"]


def test_preallocated_existing_pool_does_not_mutate_spec(mac, monkeypatch):
    pool(monkeypatch)
    before = copy.deepcopy(mac.data)
    assert errors(mac) == []
    assert mac.data == before


def test_reservations_and_mount_quota_are_not_available_pages(mac, monkeypatch):
    pool(monkeypatch, free=32, reserved=1, quota=16)
    failures = errors(mac)
    assert any("only 31" in text for text in failures)
    assert any("quota" in text for text in failures)


@pytest.mark.parametrize("change", [
    lambda c: c.objects[0].update({"size": 32 * 1024**3 + 1}),
    lambda c: c.simple.update(m="16G"),
    lambda c: c.objects[0].update(prealloc=False),
    lambda c: c.objects[0].update(reserve=False),
    lambda c: c.objects[0].update({"qom-type": "memory-backend-ram"}),
    lambda c: c.data["machine"]["opts"].update({"memory-backend": "wrong"}),
    lambda c: c.objects[0].update({"mem-path": "/does-not-exist"}),
])
def test_mismatched_backend_refused(mac, monkeypatch, change):
    pool(monkeypatch)
    change(mac)
    assert errors(mac)


def test_wrong_mount_page_size_refused(mac, monkeypatch):
    pool(monkeypatch, page=2 * 1024**2)
    assert any("1 GiB" in text and "mounted" in text for text in errors(mac))


def test_nested_mount_hides_hugetlbfs(monkeypatch, tmp_path):
    monkeypatch.setattr(mac_memory, "_read", lambda _: f"none {tmp_path} hugetlbfs rw,pagesize=1G 0 0\n"
                        f"none {tmp_path}/nested tmpfs rw 0 0\n")
    assert mac_memory.mount_for(str(tmp_path / "nested"))["type"] == "tmpfs"
    assert mac_memory.mount_for(str(tmp_path / "elsewhere"))["pagesize"] == 1024**3


def test_ordinary_ram_reports_thp_without_claiming_actual_coverage(mac, monkeypatch):
    mac.data["memory"]["hugepages"] = False
    mac.objects[0].pop("mem-path")
    mac.objects[0]["qom-type"] = "memory-backend-ram"
    monkeypatch.setattr(mac_memory, "transparent_status", lambda: "always")
    results = mac_memory.checks(mac_memory.spec(mac))
    assert results[0][0] == "ok" and "Verify actual coverage" in results[0][1]


def test_no_mac_launch_variant_allocates_mounts_or_frees_pages(mac):
    mac.data["performance"] = {"capture": True}
    scripts = [launcher.build_start(mac, {}), launcher.build_revert(mac, False),
               launcher.build_script(mac, {}), launcher.build_testrun(mac)[0]]
    for text in scripts:
        subprocess.run(["bash", "-n"], input=text, text=True, check=True)
        for forbidden in ("drop_caches", "compact_memory", 'echo "$POOL_WAS"', 'echo 32 >',
                          "mount -t hugetlbfs", 'umount "$MEM_PATH"'):
            assert forbidden not in text
    start = scripts[0]
    assert start.index("mac_memory.py") < start.index("/sys/bus/pci/rescan")
    script = scripts[2]
    assert script.index("mac_memory.py") < script.index('if ! bash "$START"')
    assert "mac_performance_capture.py" in script
    assert 'jobs -pr | grep -Fxq "$PERFORMANCE_PID"' in script


def test_windows_keeps_its_memory_launch_and_no_mac_capture(mac):
    mac.data["_meta"]["profile"] = "windows"
    mac.data["performance"] = {"capture": True}
    start = launcher.build_start(mac, {})
    assert "mac_memory.py" not in start
    assert "compact_memory" in start and "mount -t hugetlbfs" in start
    assert "mac_performance_capture.py" not in launcher.build_script(mac, {})


def test_virtual_and_dual_shared_memory_plan_never_provisions_for_mac(mac, monkeypatch, tmp_path):
    plan = virtual_gpu.prepare(mac, dict(memory="preset", network="off", input=False, uefi_resolution=False), str(tmp_path / "run"))
    assert plan["huge"]["mount"] == mac.objects[0]["mem-path"]
    assert next(o for o in plan["config"]["objects"] if o["id"] == "pc.ram")["mem-path"] == mac.objects[0]["mem-path"]
    pool(monkeypatch, free=0)
    runtime = virtual_runtime.Runtime(plan)
    monkeypatch.setattr(runtime, "command", lambda *args: pytest.fail("must not call mount or other mutating commands"))
    with pytest.raises(RuntimeError, match="host pools unchanged"):
        runtime.memory()
    assert runtime.cleanup_actions == []
    pool(monkeypatch)
    runtime.memory()
    assert runtime.cleanup_actions == []


def test_mac_memory_ui_shows_read_only_pool_controls(mac, monkeypatch, app):
    from PyQt6.QtWidgets import QPushButton
    from tabs import MemoryTab
    pool(monkeypatch)
    tab = MemoryTab(mac)
    assert not any("Allocate" in b.text() or "Free hugepages" in b.text() for b in tab.findChildren(QPushButton))
    assert tab.prealloc.isChecked()
    tab.capture.setChecked(True)
    assert mac.data["performance"]["capture"] is True
    tab.deleteLater()
    app.processEvents()


def test_smaps_separates_transparent_and_static_pages():
    filename = Path(__file__).resolve().parents[1] / "scripts/mac_performance_capture.py"
    spec = importlib.util.spec_from_file_location("mac_capture", filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = module.parse_smaps("""1000-2000 rw-p 00000000 00:00 0
Size: 33554432 kB
KernelPageSize: 4 kB
AnonHugePages: 33554432 kB
THPeligible: 1
VmFlags: rd wr hg
2000-3000 rw-s 00000000 00:00 0 /dev/hugepages/qemu
Size: 1048576 kB
KernelPageSize: 1048576 kB
Shared_Hugetlb: 1048576 kB
""")
    assert report["process_totals"]["AnonHugePages_kB"] == 33554432
    assert report["process_totals"]["Shared_Hugetlb_kB"] == 1048576
    assert report["large_or_hugetlb_mappings"][0]["KernelPageSize_kB"] == 4


@pytest.fixture
def temporary_mac(mac, monkeypatch, tmp_path):
    """Model kernel pool/mount transitions without touching real host memory."""
    import mac_hugepages as hp
    root = tmp_path / "macos/run"
    monkeypatch.setattr(mac_memory, "TEMP_ROOT", root)
    monkeypatch.setattr(hp, "STATE", root / ".temporary-hugepages.json")
    monkeypatch.setattr(hp, "available_memory", lambda: 56 * 1024**3)
    mac.data["memory"].update(temporary=True, pagesize=hp.PAGE, mem_path=str(root / "hugepages-2M"))
    mac.objects[0]["mem-path"] = mac.data["memory"]["mem_path"]
    host = dict(nr_hugepages=0, free_hugepages=0, resv_hugepages=0, mounted=False,
                calls=[], limit=None, busy=False, fail_mount=False)
    monkeypatch.setattr(hp, "count", lambda k: host[k])
    def write(value):
        host["calls"].append(("pool", value))
        actual = min(value, host["limit"]) if host["limit"] is not None else value
        host["free_hugepages"] += actual - host["nr_hugepages"]
        host["nr_hugepages"] = actual
    monkeypatch.setattr(hp, "set_pool", write)
    def mount_for(path):
        if host["mounted"]:
            return dict(mount=str(root / "hugepages-2M"), type="hugetlbfs", pagesize=hp.PAGE, options=["rw"])
        return dict(mount="/", type="ext4", options=["rw"])
    monkeypatch.setattr(mac_memory, "mount_for", mount_for)
    real_read = mac_memory._read
    def read(filename):
        name = filename.rsplit("/", 1)[-1]
        return str(host[name]) if name in host else real_read(filename)
    monkeypatch.setattr(mac_memory, "_read", read)
    monkeypatch.setattr(mac_memory.os, "statvfs", lambda _: SimpleNamespace(f_flag=0, f_blocks=0))
    def command(*args):
        host["calls"].append(args)
        if args[0] == "mount":
            if host["fail_mount"]:
                raise RuntimeError("mount failed")
            host["mounted"] = True
        elif args[0] == "umount":
            if host["busy"]:
                raise RuntimeError("mount busy")
            host["mounted"] = False
        else:
            pytest.fail(f"Unexpected host operation: {args}")
    monkeypatch.setattr(hp, "command", command)
    return mac, hp, host


def test_temporary_preflight_allows_empty_pool_but_runtime_guard_requires_ready(temporary_mac):
    mac, hp, host = temporary_mac
    assert errors(mac) == []
    assert host["calls"] == []
    with pytest.raises(RuntimeError, match="only 0"):
        mac_memory.require_existing(mac_memory.spec(mac))
    mac.data["memory"]["pagesize"] = 1024**3
    assert any("2 MiB" in message for message in errors(mac))


def test_private_directory_preview_defers_but_allocator_must_inspect(temporary_mac, monkeypatch):
    mac, hp, host = temporary_mac
    target = Path(mac.objects[0]["mem-path"])
    target.mkdir(parents=True, mode=0o700)
    original_iterdir = Path.iterdir

    def protected_iterdir(path):
        if path == target:
            raise PermissionError(13, "Permission denied", str(path))
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", protected_iterdir)
    before = copy.deepcopy(mac.data)
    findings = mac_memory.checks(mac_memory.spec(mac))
    assert not any(level == "error" for level, _ in findings)
    assert any("privileged launcher" in message for _, message in findings)
    assert mac.data == before and host["calls"] == []
    # The privileged phase must not swallow the same error or reserve any RAM.
    with pytest.raises(RuntimeError, match="Permission denied"):
        hp.acquire(mac_memory.spec(mac))
    assert host["calls"] == [] and not hp.STATE.exists()


@pytest.mark.parametrize("obstruction", ["file", "nonempty-directory"])
def test_allocator_preserves_obstructed_mountpoint_before_reservation(temporary_mac, obstruction):
    mac, hp, host = temporary_mac
    target = Path(mac.objects[0]["mem-path"])
    target.parent.mkdir(parents=True)
    if obstruction == "file":
        payload = target
    else:
        target.mkdir()
        payload = target / "keep.txt"
    payload.write_text("preserve")
    with pytest.raises(RuntimeError, match="empty dedicated directory"):
        hp.acquire(mac_memory.spec(mac))
    assert payload.read_text() == "preserve"
    assert host["calls"] == [] and not hp.STATE.exists()


def test_rebooted_lease_is_recovered_and_next_run_allocates_then_cleans_up(temporary_mac, monkeypatch):
    mac, hp, host = temporary_mac
    target = Path(mac.objects[0]["mem-path"])
    hp.acquire(mac_memory.spec(mac))
    assert target.exists() and hp.STATE.exists()
    # A hard reboot loses mounts/pages but leaves the root-owned directory and
    # journal. A different user has already reserved 200 pages in the new boot.
    monkeypatch.setattr(hp, "boot_id", lambda: "next-host-boot")
    host.update(nr_hugepages=200, free_hugepages=200, resv_hugepages=0, mounted=False, calls=[])
    token = hp.acquire(mac_memory.spec(mac))
    state = json.loads(hp.STATE.read_text())
    assert state["boot_id"] == "next-host-boot" and state["before"] == 200
    assert state["directory_created"] is True
    assert [call for call in host["calls"] if call[0] == "pool"] == [("pool", 16384)]
    mac_memory.require_existing(mac_memory.spec(mac))
    hp.release(token)
    assert host["nr_hugepages"] == 200 and host["free_hugepages"] == 200
    assert not host["mounted"] and not hp.STATE.exists() and not target.exists()


@pytest.mark.parametrize("leftover", ["empty", "nonempty", "mounted"])
def test_previous_boot_cleanup_never_changes_new_pool_or_mount(temporary_mac, monkeypatch, leftover):
    mac, hp, host = temporary_mac
    token = hp.acquire(mac_memory.spec(mac))
    target = Path(mac.objects[0]["mem-path"])
    monkeypatch.setattr(hp, "boot_id", lambda: "next-host-boot")
    host.update(nr_hugepages=400, free_hugepages=400, resv_hugepages=0,
                mounted=leftover == "mounted", calls=[])
    if leftover == "nonempty":
        (target / "keep.txt").write_text("preserve")
    hp.release(token)
    assert host["calls"] == [] and host["nr_hugepages"] == 400
    assert host["mounted"] == (leftover == "mounted") and not hp.STATE.exists()
    assert target.exists() == (leftover != "empty")
    if leftover == "nonempty":
        assert (target / "keep.txt").read_text() == "preserve"


def test_temporary_low_memory_refuses_before_reservation(temporary_mac, monkeypatch):
    mac, hp, host = temporary_mac
    monkeypatch.setattr(hp, "available_memory", lambda: 33 * 1024**3)
    with pytest.raises(RuntimeError, match="leave 4 GiB"):
        hp.acquire(mac_memory.spec(mac))
    assert host["calls"] == [] and not hp.STATE.exists()


def test_temporary_reserves_shortfall_and_restores_existing_pool(temporary_mac):
    mac, hp, host = temporary_mac
    host.update(nr_hugepages=100, free_hugepages=30, resv_hugepages=10)
    token = hp.acquire(mac_memory.spec(mac))
    assert host["nr_hugepages"] == 100 + 16384 - 20
    assert host["mounted"]
    mac_memory.require_existing(mac_memory.spec(mac))
    hp.release(token)
    assert host["nr_hugepages"] == 100
    assert host["free_hugepages"] == 30 and not host["mounted"]
    assert not hp.STATE.exists()
    assert not Path(mac.objects[0]["mem-path"]).exists()
    hp.release(token)  # EXIT and ExecStopPost cleanup can safely repeat.


@pytest.mark.parametrize("failure", ["fragmented", "mount"])
def test_temporary_partial_allocation_and_mount_failure_roll_back(temporary_mac, failure):
    mac, hp, host = temporary_mac
    host["limit"] = 2000 if failure == "fragmented" else None
    host["fail_mount"] = failure == "mount"
    with pytest.raises(RuntimeError):
        hp.acquire(mac_memory.spec(mac))
    assert host["nr_hugepages"] == 0
    assert not hp.STATE.exists()
    assert not host["mounted"]


def test_temporary_preserves_external_pool_resize(temporary_mac):
    mac, hp, host = temporary_mac
    token = hp.acquire(mac_memory.spec(mac))
    host["nr_hugepages"] += 1
    hp.release(token)
    assert host["nr_hugepages"] == 16385
    assert not host["mounted"]


def test_temporary_busy_mount_defers_cleanup_without_shrinking_pool(temporary_mac):
    mac, hp, host = temporary_mac
    token = hp.acquire(mac_memory.spec(mac))
    host["busy"] = True
    with pytest.raises(RuntimeError, match="busy"):
        hp.release(token)
    assert host["nr_hugepages"] == 16384 and hp.STATE.exists()
    host["busy"] = False
    hp.release(token)
    assert host["nr_hugepages"] == 0 and not hp.STATE.exists()


def test_temporary_refuses_other_owner_and_reuses_existing_resources(temporary_mac):
    mac, hp, host = temporary_mac
    target = Path(mac.objects[0]["mem-path"])
    target.mkdir(parents=True)
    host.update(nr_hugepages=20000, free_hugepages=20000, mounted=True)
    token = hp.acquire(mac_memory.spec(mac))
    with pytest.raises(RuntimeError, match="previous Mac"):
        hp.acquire(mac_memory.spec(mac))
    with pytest.raises(RuntimeError, match="different Mac"):
        hp.release("someone-else")
    with pytest.raises(RuntimeError, match="still running"):
        hp.release()
    hp.release(token)
    assert host["mounted"] and target.exists()
    assert host["calls"] == [] and host["nr_hugepages"] == 20000


def test_temporary_unreserved_page_check_protects_other_users(temporary_mac):
    mac, hp, host = temporary_mac
    token = hp.acquire(mac_memory.spec(mac))
    host["resv_hugepages"] = 1
    with pytest.raises(RuntimeError, match="still in use"):
        hp.release(token)
    assert host["nr_hugepages"] == 16384
    host["resv_hugepages"] = 0
    hp.release(token)
    assert host["nr_hugepages"] == 0


def test_temporary_launch_owns_memory_before_handoff_and_cleanup_before_reboot(temporary_mac):
    mac, hp, host = temporary_mac
    script = launcher.build_script(mac, {})
    assert script.index("--prepare") < script.index('if ! bash "$START"')
    assert script.index("    mac_hp_release") < script.index('bash "$REVERT"')
    for text in (script, launcher.build_testrun(mac)[0]):
        subprocess.run(["bash", "-n"], input=text, text=True, check=True)
        assert "--prepare" in text and "--release" in text
        assert "drop_caches" not in text and "compact_memory" not in text
    mac.data["_meta"]["profile"] = "windows"
    assert "mac_hugepages.py" not in launcher.build_script(mac, {})


def test_temporary_virtual_runtime_releases_on_cleanup(temporary_mac):
    mac, hp, host = temporary_mac
    plan = virtual_gpu.prepare(mac, dict(memory="preset", network="off", input=False, uefi_resolution=False))
    runtime = virtual_runtime.Runtime(plan)
    runtime.memory()
    assert host["nr_hugepages"] == 16384
    assert runtime.cleanup() == []
    assert host["nr_hugepages"] == 0


def test_temporary_ui_roundtrip(mac, monkeypatch, app, tmp_path):
    from tabs import MemoryTab
    monkeypatch.setattr(mac_memory, "TEMP_ROOT", tmp_path / "macos/run")
    tab = MemoryTab(mac)
    tab.temporary_hp.setChecked(True)
    assert mac.data["memory"]["temporary"] is True
    assert mac.data["memory"]["pagesize"] == 2 * 1024**2
    assert mac.objects[0]["mem-path"] == str(mac_memory.TEMP_ROOT / "hugepages-2M")
    tab.deleteLater()
    app.processEvents()
