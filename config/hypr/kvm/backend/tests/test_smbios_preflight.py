"""SMBIOS preflight distinguishes inline QEMU fields from binary blobs."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import launcher
from model import VMConfig
import smbios
import virtual_gpu as vg


@pytest.mark.parametrize("option,expected", [
    (None, None), ("", None), ("type=2", None),
    ("type=1,manufacturer=Acme,, Inc.,product=Workstation", None),
    ("type=1,manufacturer=Acme,,file=not-a-path", None),
    ("file=", ""), ("file=/tmp/dmi.bin", "/tmp/dmi.bin"),
    ("file=/tmp/board,, serial=1.bin", "/tmp/board, serial=1.bin"),
])
def test_blob_path_only_reads_file_options(option, expected):
    assert smbios.blob_path(option) == expected


@pytest.fixture(params=["single", "virtual"])
def checks(request, monkeypatch, tmp_path):
    monkeypatch.setattr(launcher, "START", str(tmp_path / "start.sh"))
    monkeypatch.setattr(launcher, "REVERT", str(tmp_path / "revert.sh"))
    monkeypatch.setattr(launcher, "_can_sudo", lambda: True)
    monkeypatch.setattr(vg, "capabilities", lambda _: {"devices": vg.GRAPHICS, "vnc": True})
    monkeypatch.setattr(vg, "service_active", lambda: False)
    monkeypatch.setattr(vg, "probe_console_port", lambda _: None)
    monkeypatch.setattr(vg, "viewer_command", lambda _: ["test-viewer"])

    def run(option, profile="macos"):
        cfg = VMConfig({
            "_meta": {"binary": sys.executable, "profile": profile},
            "machine": {"type": "q35", "opts": {"usb": "off"}},
            "cpu": {"model": "host", "features": {}},
            "smp": {"vcpus": "2", "topology": {"cores": "2"}},
            "simple": {"name": "smbios-test", "m": "128M", "smbios": option},
            "devices": [], "blockdevs": [], "objects": [],
        })
        if request.param == "single":
            results = launcher.preflight(cfg, {})
        else:
            results = vg.preflight(vg.prepare(cfg, dict(memory="ordinary", network="off",
                                                       input=False, uefi_resolution=False)))
        return [(severity, message) for severity, message in results if "smbios" in message.lower()]
    return run


def test_inline_type_two_does_not_require_a_blob(checks):
    assert checks("type=2") == []


@pytest.mark.parametrize("profile", ["windows", "macos"])
def test_real_blob_paths_are_still_checked(checks, tmp_path, profile):
    blob = tmp_path / "board, serial=1.bin"
    option = "file=" + str(blob).replace(",", ",,")
    errors = checks(option, profile)
    assert len(errors) == 1 and errors[0][0] == "error"
    assert str(blob) in errors[0][1]
    blob.write_bytes(b"test SMBIOS data")
    assert checks(option, profile) == []
    assert checks("file=", profile)[0][0] == "error"
