"""A spare physical GPU for the guest, with Linux keeping its desktop GPU."""

import copy
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid

import gpu_inventory as inventory
import dual_devices
import input_devices
import launcher
from model import VMConfig
import smbios
import virtual_gpu as vg

VIEWERS = {
    "spice": "SPICE console",
    "vnc": "VNC console",
    "physical": "GPU output (physical monitor)",
    "looking-glass": "Looking Glass window (optional)",
}

AUDIO_MODES = {"spice": "Classic SPICE — HD Audio",
               "lg-usb": "Looking Glass USB audio (recommended)"}


def looking_glass_client():
    from portable import component_path
    bundled=component_path('looking-glass')/'bin/looking-glass-client'
    return str(bundled) if bundled.is_file() else shutil.which('looking-glass-client')


def options(cfg):
    opts = dict(gpu="", gpu_identity={}, gpu_audio=False, romfile="",
                viewer="spice", auto_open=True, floating=True, port=5931,
                width=1920, height=1080, clipboard=False, file_transfer=False,
                audio=False, memory="preset", network="preset", pinning=True,
                input_mode="viewer", evdev_keyboard="", evdev_mouse="",
                evdev_toggle="ctrl-ctrl", lg_capture=True, audio_mode="spice",
                usb_devices=[], pci_devices=[])
    opts.update(cfg.data.get("dual_gpu") or {})
    return opts


def shared_memory_size(width, height):
    # Current IDD: three frames with 256-byte rows plus 4 MiB of metadata.
    # This also accommodates the B7 host application's two SDR frames.
    stride = ((int(width) * 4 + 255) // 256) * 256
    size = stride * int(height) * 3 + 4 * 1024**2
    return 1 << (size - 1).bit_length()


def _align_looking_glass_uuid(vm):
    """Give SPICE the identity the IDD reads from the existing SMBIOS table.

    A raw Type 1 table overrides the guest's UUID independently of QEMU's
    -uuid (which SPICE advertises). Change only this launch's QEMU argument;
    never rewrite the SMBIOS file or the shared preset.
    """
    path = vg._spec(vm.simple.get("smbios", "")).get("file")
    if not path:
        return None
    try:
        data = Path(path).read_bytes()
    except OSError as exc:
        raise ValueError(f"Cannot read the Looking Glass guest's SMBIOS file: {exc}") from exc
    for kind, offset, length in smbios.iter_structures(data):
        if kind != 1:
            continue
        if length < 24 or offset + length > len(data):
            raise ValueError("The SMBIOS Type 1 table is too short to identify the Looking Glass guest")
        identity = uuid.UUID(bytes_le=data[offset + 8:offset + 24])
        if identity.int in (0, (1 << 128) - 1):
            raise ValueError("The SMBIOS Type 1 UUID is unset; configure a valid system UUID "
                             "before using Looking Glass with SPICE")
        vg._flag(vm, "uuid", str(identity))
        return dict(source=path, uuid=str(identity))
    # Without a supplied Type 1 table, QEMU generates it from -uuid itself.
    return None


def prepare(cfg, settings=None, workdir="/tmp/vmstart2-dual-preview", token="preview"):
    opts = options(cfg)
    opts.update(settings or {})
    if not opts["gpu"]:
        raise ValueError("Select an available GPU. If only one is detected, enable the iGPU in BIOS and reboot.")
    opts["gpu"] = vg._slot(opts["gpu"])
    if opts["viewer"] not in VIEWERS:
        raise ValueError("Choose SPICE, VNC, physical GPU output, or Looking Glass")
    inputs = input_devices.selection(opts)
    if opts["audio_mode"] not in AUDIO_MODES:
        raise ValueError("Choose a supported audio method")
    if opts["audio"] and opts["audio_mode"] == "lg-usb" and opts["viewer"] != "looking-glass":
        raise ValueError("Looking Glass USB audio requires the Looking Glass viewer; use classic SPICE instead")
    if opts["audio"] and opts["viewer"] == "vnc":
        raise ValueError("VNC does not carry audio; choose Looking Glass/SPICE or a physical sound device")
    machine = cfg.data.get("machine", {}).get("type", "")
    if machine != "q35" and not machine.startswith("pc-q35"):
        raise ValueError("Dual GPU currently requires the Q35 machine type")
    for key in ("device", "object", "chardev", "readconfig"):
        if key in cfg.simple:
            raise ValueError(f"Use structured settings instead of the raw -{key} flag in Dual GPU mode")
    gpu = inventory.selected_gpu(opts["gpu"], opts["gpu_audio"], opts.get("gpu_identity"))
    opts["gpu_identity"] = gpu["identity"]
    extra = dual_devices.selection(opts, gpu, inputs)
    if opts["romfile"] and not Path(opts["romfile"]).is_file():
        raise ValueError("The selected GPU ROM file does not exist")

    # Reuse the desktop-safe resource plan, never the single-GPU handoff.
    # Every inherited passthrough device and inherited GPU ROM is excluded.
    server = "vnc" if opts["viewer"] == "vnc" else "spice"
    virtual_opts = dict(opts, model="VGA", server=server, input=True,
                        keep_usb=False, keep_pci=False, realtime=False,
                        uefi_resolution=False, audio=opts["audio"] and opts["audio_mode"] == "spice")
    plan = vg.prepare(cfg, virtual_opts, workdir, token)
    vm = VMConfig(plan["config"])
    # LG's SPICE fallback sends relative input to the PS/2 devices. The shared
    # Single GPU preset can disable these when using physical USB passthrough.
    vm.data["machine"].setdefault("opts", {})["i8042"] = "on"
    # Input devices from Single GPU mode must not silently grab the desktop.
    vm.objects[:] = [o for o in vm.objects
                    if (o.get("qom-type") or vg._spec(o.get("_raw", ""), "qom-type").get("qom-type"))
                    != "input-linux"]
    for dev in vm.devices:
        if str(dev.get("driver", "")).startswith("vfio"):
            raise ValueError("Unsupported inherited VFIO device; configure it outside the Dual GPU launch mode")

    used = {d.get("id") for d in vm.devices + vm.objects + vm.data.get("chardevs", [])}

    def fresh(base):
        name, n = base, 1
        while name in used:
            name = f"{base}{n}"
            n += 1
        used.add(name)
        return name

    def root_port(base):
        chassis = {str(d.get("chassis")) for d in vm.devices}
        chassis_id = next(n for n in range(1, 256) if str(n) not in chassis)
        name = fresh(base)
        vm.devices.append(dict(driver="pcie-root-port", id=name, bus="pcie.0", chassis=chassis_id))
        return name

    root = root_port("dual-gpu-root")
    for index, slot in enumerate(gpu["functions"]):
        device = dict(driver="vfio-pci", id=fresh("dual-gpu" if index == 0 else "dual-gpu-audio"),
                      host=slot, bus=root, addr=f"0x0.{index}")
        if index == 0:
            device["multifunction"] = True
            if opts["romfile"]:
                device["romfile"] = opts["romfile"]
        vm.devices.append(device)

    for dev in extra["pci"]:
        root = root_port("dual-pci-root")
        vm.devices.append(dict(driver="vfio-pci", id=fresh("dual-pci"), host=dev["slot"], bus=root))
    usb = next(d for d in vm.devices if d.get("driver") in ("qemu-xhci", "nec-usb-xhci")
               and not d.get("_disabled") and d.get("id"))
    for dev in extra["usb"]:
        vm.devices.append(dict(driver="usb-host", id=fresh("dual-usb-device"), bus=usb["id"] + ".0",
                               **dual_devices.usb_properties(dev)))
    if opts["audio"] and opts["audio_mode"] == "lg-usb":
        channel = fresh("dual-lg-audio")
        vm.data.setdefault("chardevs", []).append(dict(id=channel,
                _raw=f"spicevmc,id={channel},name=usbredir"))
        vm.devices.append(dict(driver="usb-redir", id=fresh("dual-lg-usb-audio"),
                               chardev=channel, bus=usb["id"] + ".0"))

    shared = identity = None
    vm.objects.extend(input_devices.objects(inputs, opts["evdev_toggle"], fresh))
    if opts["viewer"] == "looking-glass":
        identity = _align_looking_glass_uuid(vm)
        token = re.sub(r"[^a-zA-Z0-9_-]", "", token)[:40] or "preview"
        shared = dict(path=f"/dev/shm/vmstart2-lg-{os.getuid()}-{token}",
                      size=shared_memory_size(opts["width"], opts["height"]))
        memory_id = fresh("dual-lg-memory")
        vm.objects.append({"qom-type": "memory-backend-file", "id": memory_id,
                           "mem-path": shared["path"], "size": shared["size"], "share": True})
        vm.devices.append(dict(driver="ivshmem-plain", id=fresh("dual-lg"),
                               memdev=memory_id, bus="pcie.0"))

    vm.compact()
    order = vm.data["order"]
    for bucket, items in (("chardev", vm.data.get("chardevs", [])), ("object", vm.objects)):
        order[:] = [entry for entry in order if entry[0] != bucket]
        order[:0] = [[bucket, n] for n in range(len(items))]
    plan.update(mode="dual", options=dict(virtual_opts, audio=opts["audio"]), argv=vm.to_argv(True) + ["-S"],
                gpu=gpu, bindings=[dict(slot=s, identity=inventory.identity(s),
                                       group=inventory.group(s)) for s in gpu["functions"]] + extra["pci"],
                extra_devices=extra,
                shared_memory=shared, firmware_display=None, input_devices=inputs,
                looking_glass_identity=identity)
    return plan


@lru_cache(maxsize=8)
def _ivshmem_ids(binary, stamp):
    """Probe this build without opening guest disks or any host GPU."""
    with tempfile.TemporaryDirectory(prefix="vmstart2-lg-probe-") as directory:
        argv = [binary, "-machine", "q35,accel=tcg", "-m", "64M", "-nodefaults",
                "-display", "none", "-S", "-qmp", "stdio",
                "-object", json.dumps({"qom-type": "memory-backend-file", "id": "lg-memory",
                                      "size": 1024**2, "share": True,
                                      "mem-path": directory + "/frames"}),
                "-device", "ivshmem-plain,id=lg,memdev=lg-memory"]
        commands = [{"execute": c, "id": c} for c in ("qmp_capabilities", "query-pci", "quit")]
        result = subprocess.run(argv, input="\n".join(json.dumps(c) for c in commands) + "\n",
                                capture_output=True, text=True, timeout=10)
        for line in result.stdout.splitlines():
            try:
                reply = json.loads(line)
            except ValueError:
                continue
            if reply.get("id") == "query-pci":
                for bus in reply.get("return", []):
                    for dev in bus.get("devices", []):
                        if dev.get("qdev_id") == "lg":
                            return dev["id"]
        raise RuntimeError("Could not inspect IVSHMEM PCI IDs: " + result.stderr[-1200:])


def ivshmem_ids(binary):
    return _ivshmem_ids(binary, os.stat(binary).st_mtime_ns)


def preflight(plan):
    # The ordinary virtual plan supplies disk, TPM, memory, network and local
    # console checks. GPU ownership is checked below and by the new runtime.
    console = copy.deepcopy(plan)
    for device in console["config"]["devices"]:
        if device.get("driver") == "vfio-pci":
            device["_disabled"] = True
    VMConfig(console["config"]).compact()
    checks = vg.preflight(console)
    checks = [(s, m.replace("Virtual display on localhost", "Setup console on localhost"))
              for s, m in checks]
    try:
        gpu = inventory.selected_gpu(plan["options"]["gpu"], plan["options"]["gpu_audio"],
                                     plan["gpu"]["identity"])
        checks += [("warn", m) for m in gpu["warnings"]]
        input_devices.verify_plan(plan)
        extra = dual_devices.verify_plan(plan)
        for dev in extra["pci"]:
            checks.append(("ok", f"Additional PCI device: {dev['slot']} (IOMMU group {dev['group']})"))
        for dev in extra["usb"]:
            checks.append(("ok", f"Physical USB: {dev['name']} at port {dev['port']}"))
        if extra["pci"] or extra["usb"]:
            checks.append(("warn", "Selected physical USB/PCI devices belong to Windows while this VM runs. "
                           "A passed-through sound card plays through its physical outputs. "
                           "Linux sound services lose access to a selected sound card until shutdown."))
        if plan.get("input_devices"):
            shortcut = input_devices.TOGGLES[plan["options"]["evdev_toggle"]]
            checks.append(("warn", f"evdev takes the selected keyboard and mouse when the VM starts. "
                           f"Press {shortcut.lower()} together, then release, to switch between Linux "
                           "and Windows. Closing Looking Glass does not release evdev; stopping the VM does."))
        checks.append(("ok", f"Guest GPU: {gpu['name']} ({gpu['slot']}); "
                       f"functions: {', '.join(gpu['functions'])}"))
        if plan["options"]["viewer"] in ("spice", "vnc"):
            checks.append(("warn", "SPICE/VNC show the emulated VGA display. The passed-through GPU is available "
                           "to Windows, but these consoles do not capture its physical display output. "
                           "Use GPU output, Looking Glass, or a remote desktop service inside Windows to view it."))
        if not gpu["verified"]:
            checks.append(("warn", "Launch will stop before detaching anything if the privileged usage check fails"))
        caps = vg.capabilities(plan["argv"][0])
        for needed in ("vfio-pci", "pcie-root-port"):
            if needed not in caps["devices"]:
                checks.append(("error", f"This QEMU build has no {needed} device"))
        if extra["usb"] and "usb-host" not in caps["devices"]:
            checks.append(("error", "This QEMU build has no USB host passthrough support"))
        if plan["options"]["audio"]:
            usb_audio = plan["options"]["audio_mode"] == "lg-usb"
            if usb_audio and "usb-redir" not in caps["devices"]:
                checks.append(("error", "This QEMU build has no USB redirection support for Looking Glass audio"))
            checks.append(("ok", "Audio: " + ("Looking Glass USB audio; open Looking Glass, then select "
                           "Looking Glass USB Audio in Windows Sound settings" if usb_audio else
                           "classic SPICE; select the virtual High Definition Audio output in Windows Sound settings")))
        if plan["shared_memory"]:
            if plan.get("looking_glass_identity"):
                checks.append(("ok", "Looking Glass and SPICE use the existing SMBIOS system UUID "
                               "for this launch; the SMBIOS file and shared preset are preserved"))
            if "ivshmem-plain" not in caps["devices"]:
                checks.append(("error", "This QEMU build has no IVSHMEM support for Looking Glass"))
            else:
                ids = ivshmem_ids(plan["argv"][0])
                if (ids.get("vendor"), ids.get("device")) != (0x1af4, 0x1110):
                    checks.append(("warn", f"Looking Glass: this QEMU exposes IVSHMEM as "
                                   f"{ids.get('vendor', 0):04x}:{ids.get('device', 0):04x}. "
                                   "The standard Windows driver expects 1af4:1110 and will not bind. "
                                   "A matching guest driver or compatible QEMU build is required for Looking Glass; "
                                   "the setup console and physical GPU output remain available."))
            if not looking_glass_client():
                checks.append(("warn", "Looking Glass client is not installed on Linux. Use the setup console "
                               "first and install matching Linux and Windows Looking Glass components."))
            checks.append(("warn", "Install the physical GPU's Windows driver and matching Looking Glass "
                           "components. Select its display in Windows; the setup console is a separate virtual display."))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        checks.append(("error", str(exc)))
    checks.append(("ok", "Only explicitly selected GPU/PCI functions are rebound and restored. Linux keeps its desktop; "
                   "Single GPU hooks and firmware display preferences are not applied."))
    return checks


def current_path():
    return Path(launcher.RUN_DIR) / "dual-current.json"


def current_run():
    try:
        return json.loads(current_path().read_text())
    except (OSError, ValueError):
        return {}


def launch(cfg):
    if vg.service_active():
        raise RuntimeError("A VM is already running or stopping")
    # Validate the selection before leaving a run directory behind.
    prepare(cfg)
    workdir = tempfile.mkdtemp(prefix="vmstart2-dual-")
    plan = prepare(cfg, workdir=workdir, token=uuid.uuid4().hex)
    payload = Path(workdir) / "plan.json"
    payload.write_text(json.dumps(plan, indent=2))
    payload.chmod(0o600)
    (Path(workdir) / "output.log").touch(mode=0o600)
    prefix = [] if os.geteuid() == 0 else ["sudo", "-n"]
    subprocess.run(prefix + ["systemctl", "reset-failed", vg.UNIT], capture_output=True, timeout=10)
    result = subprocess.run(prefix + ["systemd-run", "--unit", vg.UNIT,
                            "--description=vmstart_2 dual GPU guest", "--property=KillMode=mixed",
                            "--property=TimeoutStopSec=120", "--service-type=exec",
                            *vg.runtime_log_properties(workdir), sys.executable,
                            str(Path(__file__).with_name("dual_runtime.py")), str(payload)],
                            capture_output=True, text=True, timeout=20)
    if result.returncode:
        raise RuntimeError((result.stdout + result.stderr).strip() or "systemd-run failed")
    run = dict(workdir=workdir, options=plan["options"], qmp=plan["qmp"],
               agent_chardev=plan["agent_chardev"], shared_memory=plan["shared_memory"],
               gpu=plan["gpu"])
    current_path().parent.mkdir(parents=True, exist_ok=True)
    current_path().write_text(json.dumps(run))
    return run


def viewer_command(run):
    opts = run["options"]
    viewer = opts.get("viewer", "looking-glass")
    if viewer in ("spice", "vnc"):
        return vg.viewer_command(opts)
    if viewer == "physical":
        return None
    shared = run.get("shared_memory")
    binary = looking_glass_client()
    if not shared or not binary:
        return None
    command = [binary, "-f", shared["path"], "spice:enable=yes", "spice:host=127.0.0.1",
            f"spice:port={opts['port']}", f"spice:clipboard={'yes' if opts['clipboard'] else 'no'}",
            f"spice:audio={'yes' if opts['audio'] else 'no'}",
            f"spice:usbAudio={'yes' if opts.get('audio_mode') == 'lg-usb' else 'no'}",
            "audio:micDefault=deny"]
    if opts.get("input_mode") == "evdev":
        # QEMU owns input. Keep the client uncaptured to avoid forwarding the
        # same events via IDD/SPICE when the user switches back to Linux.
        command += ["spice:input=no", "input:captureOnly=yes", "input:captureOnStart=no",
                    "input:captureOnFocus=no", "input:autoCapture=no",
                    "input:grabKeyboard=no", "input:grabKeyboardOnFocus=no"]
    else:
        command += ["spice:input=yes",
                    f"input:captureOnStart={'yes' if opts.get('lg_capture', True) else 'no'}"]
    return command


def open_viewer(run):
    viewer = run["options"].get("viewer", "looking-glass")
    if viewer in ("spice", "vnc"):
        vg.open_viewer(run["options"])
        return
    if viewer == "physical":
        raise RuntimeError("Use a monitor connected to the guest GPU. Open setup console for its virtual display.")
    command = viewer_command(run)
    if not command:
        raise RuntimeError("Choose Looking Glass before launch and install looking-glass-client on Linux. "
                           "The setup console is available while you configure the guest.")
    # Retain client errors for diagnostics; never run a desktop client as root.
    vg.console_window.launch(command, floating=run['options'].get('floating', True),
                             log_path=Path(run['workdir'])/'viewer.log')


def preview(cfg):
    plan = prepare(cfg)
    lines = ["# Dual GPU: Linux keeps its desktop; only these selected PCI functions move to VFIO:",
             "# " + ", ".join(d["slot"] for d in plan["bindings"]),
             "# Original drivers and driver overrides are restored after QEMU exits.",
             "# No Single GPU hooks, host reboot, or firmware-display updates.",
             "# The runtime prepares memory/network/TPM, binds the spare GPU, then resumes QEMU.",
             "", shlex.join(plan["argv"])]
    command = viewer_command(plan)
    if command:
        lines += ["", "# " + VIEWERS[plan["options"]["viewer"]] + ":", shlex.join(command)]
    return "\n".join(lines)
