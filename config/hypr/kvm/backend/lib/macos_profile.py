"""Construct independent macOS presets from prepared local boot files."""

from pathlib import Path
import uuid

OSK = "ourhardworkbythesewordsguardedpleasedontsteal(c)AppleComputerInc"


def configuration(root, iso, binary, topology):
    directory = Path(root) / "macos"
    firmware = directory / "High-Sierra-firmware"
    simple = {
        "name": "guest=High-Sierra,debug-threads=on", "machine": "q35", "accel": "kvm",
        "cpu": "Penryn", "smp": "4", "m": "size=6G", "smbios": "type=2",
        "uuid": str(uuid.uuid4()), "netdev": '{"type":"user","id":"hostnet0"}',
        "display": "none", "vga": "none", "monitor": "none", "overcommit": "mem-lock=off",
    }
    blockdevs = []
    for number, filename, readonly in ((0, "OVMF_CODE.fd", True), (1, "OVMF_VARS.fd", False)):
        node = f"libvirt-pflash{number}"
        blockdevs.extend([
            {"driver": "file", "node-name": node + "-storage", "filename": str(firmware / filename),
             "read-only": readonly},
            {"driver": "raw", "node-name": node + "-format", "file": node + "-storage",
             "read-only": readonly},
        ])
    blockdevs.extend([
        {"driver": "file", "node-name": "macos-recovery-storage", "filename": str(iso), "read-only": True},
    ])
    cores = sorted(topology.get("core_to_cpus", {}))[:4]
    pins = [{"vcpu": i, "core": core, "cpuset": str(topology["core_to_cpus"][core][0])}
            for i, core in enumerate(cores)]
    scheduling = {"scheduler": "other", "priority": 0}
    return {
        "_meta": {"profile": "macos", "binary": binary,
                  "source": "High Sierra 10.13.6 OpenCore recovery; tested Penryn / 6 GiB / USB 2 configuration"},
        "simple": simple,
        "machine": {"type": "q35", "opts": {"usb": "off", "vmport": "off",
                    "memory-backend": "pc.ram", "pflash0": "libvirt-pflash0-format",
                    "pflash1": "libvirt-pflash1-format"}},
        "cpu": {"model": "Penryn", "features": {
            "kvm": "on", "vendor": "GenuineIntel", "invtsc": "on", "vmware-cpuid-freq": "on",
            "ssse3": "on", "sse4.2": "on", "popcnt": "on", "aes": "on", "xsave": "on",
            "xsaveopt": "on", "check": "on"}},
        "smp": {"vcpus": "4", "topology": {"sockets": "1", "cores": "4", "threads": "1"}},
        "objects": [{"qom-type": "memory-backend-ram", "id": "pc.ram", "size": 6 * 1024**3}],
        "blockdevs": blockdevs,
        "devices": [
            {"driver": "isa-applesmc", "id": "apple-smc", "osk": OSK},
            {"driver": "ich9-ahci", "id": "sata"},
            {"driver": "ide-cd", "id": "macos-recovery", "drive": "macos-recovery-storage",
             "bus": "sata.2", "bootindex": 1},
            {"driver": "usb-ehci", "id": "ehci"},
            {"driver": "usb-kbd", "id": "macos-keyboard", "bus": "ehci.0"},
            {"driver": "usb-tablet", "id": "macos-pointer", "bus": "ehci.0"},
            {"driver": "vmxnet3", "id": "net0", "netdev": "hostnet0", "mac": "52:54:00:4d:41:43"},
        ],
        "order": [[key, None] for key in simple],
        "chardevs": [], "globals": [], "acpitables": [],
        "smbios": {"template_blob": "", "output_blob": "", "system_uuid": "", "patches": []},
        "network": {"mode": "user", "ifname": "vm2mac0", "bridge": ""},
        "memory": {"hugepages": False, "pagesize": 2 * 1024**2, "mem_path": "/dev/hugepages/vmstart2-macos"},
        "pinning": {"vcpus": 4, "vcpupin": pins, "smt": False, "l3_topology": False,
                    "rt_runtime_us": None, "vcpusched": dict(scheduling),
                    "emulatorsched": dict(scheduling), "iothreadsched": dict(scheduling)},
        "single_gpu": {"reboot_after": False, "standalone": True},
        "virtual_gpu": {"model": "VGA", "server": "spice", "port": 5930,
                        "width": 1920, "height": 1080, "auto_open": True, "remember_console_size": True,
                        "input": True, "input_controller": "ehci", "clipboard": False,
                        "file_transfer": False, "audio": False, "keep_usb": False, "keep_pci": False,
                        "memory": "ordinary", "network": "user", "pinning": False,
                        "realtime": False, "uefi_resolution": False},
        "dual_gpu": {"memory": "ordinary", "network": "user", "pinning": False, "input_controller": "ehci"},
        "tools": {"kvm_build_enabled": False, "kvm_build": "", "kvm_build_args": ""},
        "wizard": {"step": 8},
    }


def tahoe_configuration(root, iso, binary, topology, bridge=""):
    """Tahoe recovery baseline; the user chooses the installation disk separately."""
    data = configuration(root, iso, binary, topology)
    data["_meta"].update(macos_release="tahoe", macos_version="26.6.2",
                         opencore_memory_gib=16,
                         source="Tahoe 26.6.2 OpenCore recovery; 8 cores / 16 GiB / USB 3")
    data["simple"].update(name="guest=macOS-Tahoe,debug-threads=on", cpu="Skylake-Client",
                          smp="8", m="size=16G")
    data["cpu"]["model"] = "Skylake-Client"
    data["cpu"]["features"].update(hle="off", rtm="off", avx="on", avx2="on")
    data["smp"] = {"vcpus": "8", "topology": {"sockets": "1", "cores": "8", "threads": "1"}}
    data["objects"][0]["size"] = 16 * 1024**3
    for block in data["blockdevs"]:
        if block.get("node-name", "").startswith("libvirt-pflash") and block.get("filename"):
            block["filename"] = str(Path(root) / "macos/Tahoe-firmware" / Path(block["filename"]).name)
    for device in data["devices"]:
        if device["driver"] == "usb-ehci":
            device.update(driver="nec-usb-xhci", id="xhci")
        elif device["driver"] in ("usb-kbd", "usb-tablet"):
            device["bus"] = "xhci.0"
        elif device["driver"] == "vmxnet3":
            device["mac"] = "52:54:00:54:41:48"
    data["pinning"]["vcpus"] = 8
    cores = sorted(topology.get("core_to_cpus", {}))[:8]
    data["pinning"]["vcpupin"] = [
        {"vcpu": i, "core": core, "cpuset": str(topology["core_to_cpus"][core][0])}
        for i, core in enumerate(cores)]
    data["virtual_gpu"].update(input_controller="xhci", width=1280, height=720)
    data["dual_gpu"]["input_controller"] = "xhci"
    if bridge:
        import json
        data["simple"]["netdev"] = json.dumps(dict(type="tap", id="hostnet0", ifname="vm2mac0",
                                                    script="no", downscript="no"))
        data["network"].update(mode="tap", bridge=bridge)
        data["virtual_gpu"]["network"] = "preset"
        data["dual_gpu"]["network"] = "preset"
    return data
