"""evdev selection checks use synthetic metadata and never read input events."""

from pathlib import Path
import struct
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import input_devices as inputs


def bitmap(codes):
    value = sum(1 << code for code in codes)
    bits = struct.calcsize("L") * 8
    words = []
    while value:
        words.append(f"{value & ((1 << bits) - 1):x}")
        value >>= bits
    return " ".join(reversed(words)) or "0"


@pytest.fixture
def devices(tmp_path, monkeypatch):
    dev, sysfs = tmp_path / "input", tmp_path / "sys"
    (dev / "by-id").mkdir(parents=True)
    (dev / "by-path").mkdir()
    sysfs.mkdir()
    monkeypatch.setattr(inputs, "DEV", dev)
    monkeypatch.setattr(inputs, "SYS", sysfs)
    monkeypatch.setattr(inputs, "_device_number", lambda p: "13:" + p.name.removeprefix("event"))

    def add(number, name, keys, rel, alias):
        node = dev / f"event{number}"
        node.touch()
        entry = sysfs / node.name
        for directory in (entry / "device/capabilities", entry / "device/id"):
            directory.mkdir(parents=True)
        (entry / "dev").write_text(f"13:{number}")
        attrs = {"name": name, "phys": f"usb-port-{number}", "uniq": "serial",
                 "id/bustype": "0003", "id/vendor": "1234", "id/product": "5678",
                 "id/version": "0001", "capabilities/key": bitmap(keys),
                 "capabilities/rel": bitmap(rel)}
        for key, value in attrs.items():
            (entry / "device" / key).write_text(value)
        link = dev / "by-id" / alias
        link.symlink_to(node)
        (dev / "by-path" / f"port-{number}-event").symlink_to(node)
        return str(link)

    keyboard = add(3, "Keyboard", [16, 30, 44, 57, 29, 97, 42, 54], [], "usb-keyboard-event-kbd")
    mouse = add(8, "Mouse", [272, 273], [0, 1, 8], "usb-mouse-event-mouse")
    add(5, "Media keys", [115, 114], [8], "usb-media-event-kbd")
    return dict(input_mode="evdev", evdev_keyboard=keyboard, evdev_mouse=mouse,
                evdev_toggle="ctrl-ctrl")


def test_bitmap_keeps_zero_native_words(tmp_path):
    path = tmp_path / "bits"
    path.write_text("2 0")
    assert inputs._bitmap(path) == 2 << (struct.calcsize("L") * 8)


def test_discovery_prefers_stable_ids_and_excludes_media_only_interfaces(devices):
    found = inputs.discover()
    assert {d["path"] for d in found} == {devices["evdev_keyboard"], devices["evdev_mouse"]}
    assert [d["roles"] for d in found] == [["keyboard"], ["mouse"]]
    assert found[0]["toggles"] == ["ctrl-ctrl", "shift-shift"]


def test_selection_checks_roles_and_release_keys(devices):
    assert len(inputs.selection(devices)) == 2
    with pytest.raises(ValueError, match="not a suitable evdev mouse"):
        inputs.selection(dict(devices, evdev_mouse=devices["evdev_keyboard"]))
    with pytest.raises(ValueError, match="does not expose both alt keys"):
        inputs.selection(dict(devices, evdev_toggle="alt-alt"))
    with pytest.raises(ValueError, match="Select both"):
        inputs.selection(dict(devices, evdev_keyboard=""))
    with pytest.raises(ValueError, match="supported evdev switch"):
        inputs.selection(dict(devices, evdev_toggle="unknown"))


def test_alias_cannot_escape_input_directory(devices, tmp_path):
    outside = tmp_path / "event99"
    outside.touch()
    link = inputs.DEV / "by-id/usb-escape-event-kbd"
    link.symlink_to(outside)
    with pytest.raises(ValueError, match="under /dev/input"):
        inputs.inspect(str(link))


def test_regular_files_are_not_input_devices(tmp_path):
    path = tmp_path / "event0"
    path.touch()
    with pytest.raises(ValueError, match="Linux input event"):
        inputs._device_number(path)


def test_runtime_detects_replaced_device_and_unselected_objects(devices):
    selected = inputs.selection(devices)
    objects = inputs.objects(selected, "ctrl-ctrl", lambda name: name)
    plan = dict(options=devices, input_devices=selected, config={"objects": objects})
    inputs.verify_plan(plan)
    objects.append({"qom-type": "input-linux", "id": "extra", "evdev": "/dev/input/event99"})
    with pytest.raises(RuntimeError, match="unexpected evdev"):
        inputs.verify_plan(plan)
    objects.pop()
    (inputs.SYS / "event8/device/name").write_text("A different mouse")
    with pytest.raises(RuntimeError, match="changed since launch"):
        inputs.verify_plan(plan)


def test_viewer_mode_ignores_disconnected_saved_selections(devices):
    Path(devices["evdev_mouse"]).unlink()
    assert inputs.selection(dict(devices, input_mode="viewer")) == []
    with pytest.raises(ValueError, match="evdev mouse"):
        inputs.selection(devices)
