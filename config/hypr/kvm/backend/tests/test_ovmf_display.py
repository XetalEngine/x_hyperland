"""Firmware display edits preserve the complete store outside the preference."""

from pathlib import Path
import os
import shutil
import socket
import struct
import subprocess
import sys
import time
import uuid

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import ovmf_display
import virtual_gpu as vg


@pytest.fixture
def firmware(tmp_path):
    edk2 = pytest.importorskip("virt.firmware.varstore.edk2")
    from virt.firmware.efi import efivar

    template = next((p for p in (Path("/usr/share/edk2/x64/OVMF_VARS.4m.fd"),
                                 Path("/usr/share/edk2-ovmf/x64/OVMF_VARS.4m.fd")) if p.is_file()), None)
    if template is None:
        pytest.skip("An OVMF variable-store template is needed")
    store = edk2.Edk2VarStore(str(template))
    variables = store.get_varlist()
    variables["PlatformConfig"] = efivar.EfiVar("PlatformConfig",
        guid=uuid.UUID(bytes_le=ovmf_display.PLATFORM_GUID), attr=7, data=struct.pack("<II", 1024, 768))
    variables["PreservedSetting"] = efivar.EfiVar("PreservedSetting", attr=7, data=b"keep this exact value")
    path = tmp_path / "vars.fd"
    path.write_bytes(store.bytes_varstore(variables))
    return path


def test_only_display_bytes_change_and_exact_backup_is_saved(firmware, tmp_path):
    from virt.firmware.varstore import edk2
    before = firmware.read_bytes()
    offset = ovmf_display._resolution_offset(edk2.Edk2VarStore(str(firmware)))
    backup = tmp_path / "backup.fd"
    assert ovmf_display.apply_resolution(str(firmware), 1600, 900, backup) == (1024, 768)
    after = firmware.read_bytes()
    assert after == before[:offset] + struct.pack("<II", 1600, 900) + before[offset + 8:]
    assert backup.read_bytes() == before
    assert backup.stat().st_mode & 0o777 == 0o600
    variables = edk2.Edk2VarStore(str(firmware)).get_varlist()
    assert variables["PreservedSetting"].data == b"keep this exact value"


def test_matching_resolution_does_not_rewrite_firmware(firmware, tmp_path):
    before = firmware.stat().st_mtime_ns
    backup = tmp_path / "backup.fd"
    assert ovmf_display.apply_resolution(str(firmware), 1024, 768, backup) is None
    assert firmware.stat().st_mtime_ns == before
    assert not backup.exists()


def test_no_override_leaves_firmware_untouched(firmware, tmp_path):
    from virt.firmware.varstore import edk2
    store = edk2.Edk2VarStore(str(firmware))
    variables = store.get_varlist()
    del variables["PlatformConfig"]
    firmware.write_bytes(store.bytes_varstore(variables))
    before = firmware.read_bytes()
    backup = tmp_path / "backup.fd"
    assert ovmf_display.apply_resolution(str(firmware), 1600, 900, backup) is None
    assert firmware.read_bytes() == before and not backup.exists()


def test_another_process_lock_prevents_firmware_write(firmware, tmp_path):
    script = ("import fcntl, sys\n"
              "with open(sys.argv[1], 'rb') as f:\n"
              "    fcntl.lockf(f, fcntl.LOCK_SH, 1, 100)\n"
              "    print('locked', flush=True)\n"
              "    sys.stdin.read()\n")
    before = firmware.read_bytes()
    child = subprocess.Popen([sys.executable, "-c", script, str(firmware)],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "locked"
        with pytest.raises((BlockingIOError, PermissionError)):
            ovmf_display.apply_resolution(str(firmware), 1600, 900, tmp_path / "backup.fd")
        assert firmware.read_bytes() == before
        assert not (tmp_path / "backup.fd").exists()
    finally:
        child.communicate(timeout=5)


def test_backup_failure_leaves_original_firmware_untouched(firmware, tmp_path):
    before = firmware.read_bytes()
    backup = tmp_path / "backup.fd"
    backup.write_bytes(b"previous backup")
    with pytest.raises(FileExistsError):
        ovmf_display.apply_resolution(str(firmware), 1600, 900, backup)
    assert firmware.read_bytes() == before
    assert backup.read_bytes() == b"previous backup"


@pytest.mark.parametrize("corruption", ["bounds", "attributes"])
def test_malformed_or_authenticated_display_variable_is_not_edited(firmware, tmp_path, corruption):
    from virt.firmware.varstore import edk2
    store = edk2.Edk2VarStore(str(firmware))
    offset = ovmf_display._resolution_offset(store)
    header = offset - len(ovmf_display.PLATFORM_NAME) - 60
    data = bytearray(firmware.read_bytes())
    struct.pack_into("<I", data, header + (40 if corruption == "bounds" else 4),
                     0xffffffff if corruption == "bounds" else 0x27)
    firmware.write_bytes(data)
    with pytest.raises(ValueError):
        ovmf_display.apply_resolution(str(firmware), 1600, 900, tmp_path / "backup.fd")
    assert firmware.read_bytes() == data
    assert not (tmp_path / "backup.fd").exists()


def test_requested_uefi_resolution_and_immediate_qemu_restart(firmware, tmp_path):
    """Read real VNC framebuffer dimensions; use only a temporary UEFI store."""
    binary = shutil.which("qemu-system-x86_64")
    code = Path(os.environ.get("VMSTART2_TEST_OVMF_CODE", "/usr/share/edk2/x64/OVMF_CODE.4m.fd"))
    if not binary or not code.is_file() or "bochs-display" not in vg.capabilities(binary)["devices"]:
        pytest.skip("QEMU and OVMF are needed")
    if ("VMSTART2_TEST_OVMF_CODE" not in os.environ
            and vg.guest_device_ids(binary).get("bochs-display", {}).get("vendor") != 0x1234):
        pytest.skip("Set VMSTART2_TEST_OVMF_CODE to firmware matching this QEMU's modified display PCI IDs")
    ovmf_display.apply_resolution(str(firmware), 1600, 900, tmp_path / "before.fd")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    qmp_path = str(tmp_path / "qmp.sock")
    argv = [binary, "-machine", "q35,smm=on", "-accel", "tcg", "-m", "128M", "-nodefaults",
            "-drive", f"if=pflash,unit=0,format=raw,readonly=on,file={code}",
            "-drive", f"if=pflash,unit=1,format=raw,file={firmware}",
            "-vga", "none", "-device", "bochs-display,xres=1600,yres=900,edid=on",
            "-display", "none", "-vnc", f"127.0.0.1:{port - 5900}",
            "-qmp", f"unix:{qmp_path},server=on,wait=off"]

    def receive(client, size):
        data = b""
        while len(data) < size:
            chunk = client.recv(size - len(data))
            assert chunk, "VNC connection closed unexpectedly"
            data += chunk
        return data

    for _ in range(2):
        vg.probe_console_port(port)
        with open(tmp_path / "qemu.log", "w+") as output:
            child = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=output, stderr=output)
            client = None
            try:
                deadline = time.monotonic() + 20
                size = None
                while child.poll() is None and time.monotonic() < deadline:
                    try:
                        client = socket.create_connection(("127.0.0.1", port), timeout=2)
                    except ConnectionRefusedError:
                        time.sleep(0.1)
                        continue
                    assert receive(client, 12).startswith(b"RFB ")
                    client.sendall(b"RFB 003.008\n")
                    count = receive(client, 1)[0]
                    assert 1 in receive(client, count)  # No authentication on localhost.
                    client.sendall(b"\x01")
                    assert receive(client, 4) == b"\0" * 4
                    client.sendall(b"\x01")
                    info = receive(client, 24)
                    size = struct.unpack_from(">HH", info)
                    receive(client, struct.unpack_from(">I", info, 20)[0])
                    if size == (1600, 900):
                        break
                    client.close()
                    client = None
                    time.sleep(0.1)
                output.seek(0)
                assert size == (1600, 900), output.read()
                with vg.QMP(qmp_path) as qmp:
                    qmp.execute("quit")
                child.wait(timeout=5)
                assert child.returncode == 0
                assert client.recv(1) == b""  # QEMU actively closed the viewer connection.
                client.close()
                client = None
            finally:
                if client:
                    client.close()
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=5)
