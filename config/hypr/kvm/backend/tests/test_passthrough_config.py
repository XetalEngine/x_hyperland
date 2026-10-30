"""Device adders must produce valid placements before the desktop is stopped."""

import copy
import json

import pytest

from test_ui_navigation import app, window
from model import VMConfig


def test_add_gpu_without_root_ports_and_repeat_adds(window):
    tab = window.tab_hw
    gpu = "0000:01:00.0"
    audio = "0000:01:00.1"
    tab.host_gpus = [{"slot": gpu, "functions": [{"slot": gpu}, {"slot": audio}]}]
    tab.gpu_combo.addItem("Test GPU", gpu)
    tab.rom.setText("/test/gpu.rom")
    tab._add_gpu()
    devices = [d for d in window.cfg.devices if d.get("driver") == "vfio-pci"]
    assert len(devices) == 2
    assert all("bus" not in d and "addr" not in d for d in devices)
    assert next(d for d in devices if d["host"] == gpu)["romfile"] == "/test/gpu.rom"
    assert "romfile" not in next(d for d in devices if d["host"] == audio)
    tab._add_gpu()
    tab.pci_new.addItem("GPU audio", "01:00.1")
    tab.pci_new.setCurrentIndex(tab.pci_new.count() - 1)
    tab._add_pci()
    assert [d for d in window.cfg.devices if d.get("driver") == "vfio-pci"] == devices


def test_add_pci_uses_free_root_port_and_ignores_disabled_duplicates(window):
    tab = window.tab_hw
    window.cfg.devices.extend([
        {"driver": "pcie-root-port", "id": "pci.1"},
        {"driver": "pcie-root-port", "id": "pci.2"},
        {"driver": "vfio-pci", "id": "old", "host": "0000:01:00.0",
         "bus": "pci.1", "_disabled": True},
        {"driver": "e1000e", "id": "nic", "bus": "pci.1"},
    ])
    tab.pci_new.addItem("Test GPU", "0000:01:00.0")
    tab.pci_new.setCurrentIndex(tab.pci_new.count() - 1)
    tab._add_pci()
    device = window.cfg.devices[-1]
    assert device["bus"] == "pci.2" and device["addr"] == "0x0"


def test_add_usb_uses_existing_xhci_without_reserving_virtual_input_ports(window):
    tab = window.tab_hw
    window.cfg.data["machine"]["opts"]["usb"] = "off"
    window.cfg.devices.extend([
        {"driver": "nec-usb-xhci", "id": "xhci"},
        {"driver": "usb-kbd", "id": "keyboard", "bus": "xhci.0"},
        {"driver": "usb-tablet", "id": "pointer", "bus": "xhci.0"},
    ])
    tab.usb_new.addItem("Test mouse", dict(vendor_id="046d", product_id="c08b", bus="1", device="2"))
    tab.usb_by.setCurrentIndex(tab.usb_by.findData("id"))
    tab._add_usb()
    device = window.cfg.devices[-1]
    assert device["bus"] == "xhci.0" and "port" not in device
    assert device["vendorid"] == 0x046d and device["productid"] == 0xc08b
    argv = window.cfg.to_argv()
    emitted = [json.loads(argv[i + 1]) for i, arg in enumerate(argv) if arg == "-device"]
    assert device in emitted


def test_preflight_validation_rejects_invalid_passthrough_but_ignores_tombstones():
    cfg = VMConfig({
        "machine": {"type": "q35", "opts": {"usb": "off"}},
        "smp": {"vcpus": "1", "topology": {}},
        "devices": [
            {"driver": "vfio-pci", "host": "0000:01:00.1", "id": "audio", "bus": ""},
            {"driver": "vfio-pci", "host": "01:00.1", "id": "duplicate"},
            {"driver": "usb-host", "id": "mouse", "bus": "usb.0"},
        ],
    })
    before = copy.deepcopy(cfg.devices)
    errors = [message for severity, message in cfg.validate() if severity == "error"]
    assert any("empty guest bus" in message for message in errors)
    assert any("assigned more than once" in message for message in errors)
    assert any("uses usb.0" in message for message in errors)
    assert cfg.devices == before
    for device in cfg.devices:
        device["_disabled"] = True
    assert not [message for severity, message in cfg.validate() if severity == "error"]


@pytest.mark.parametrize("controller", ["qemu-xhci", "nec-usb-xhci", "usb-ehci"])
def test_explicit_usb_bus_is_valid_with_built_in_usb_disabled(controller):
    cfg = VMConfig({
        "machine": {"type": "q35", "opts": {"usb": "off"}},
        "smp": {"vcpus": "1", "topology": {}},
        "devices": [{"driver": controller, "id": "usb"},
                    {"driver": "usb-host", "id": "mouse", "bus": "usb.0"}],
    })
    assert not [message for severity, message in cfg.validate() if severity == "error"]
