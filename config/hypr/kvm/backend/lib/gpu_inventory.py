"""Read-only discovery for GPUs which can leave Linux without a desktop handoff."""

import os
from pathlib import Path
import re
import stat

import hostinfo

SYS = Path("/sys")
PROC = Path("/proc")
DEV = Path("/dev")
PCI = SYS / "bus/pci/devices"


def read(path, default=""):
    try:
        return path.read_text().strip()
    except OSError:
        return default


def driver(slot):
    link = PCI / slot / "driver"
    return link.resolve().name if link.is_symlink() else ""


def identity(slot):
    path = PCI / slot
    return {key: read(path / key) for key in
            ("vendor", "device", "subsystem_vendor", "subsystem_device")}


def pci_class(slot):
    try:
        return int((PCI / slot / "class").read_text().strip(), 16)
    except (OSError, ValueError):
        return -1


def group(slot):
    link = PCI / slot / "iommu_group"
    return link.resolve().name if link.is_symlink() else ""


def group_members(slot):
    path = PCI / slot / "iommu_group/devices"
    try:
        return sorted(p.name for p in path.iterdir())
    except OSError:
        return []


def functions(slot, audio=True):
    """Only the GPU and its adjacent HDMI/DP audio, never all APU functions.

    Ryzen APUs can share a PCI slot with host USB, PSP and analog sound devices.
    An IOMMU group containing those endpoints is rejected, not detached.
    """
    result = [slot]
    base, function = slot.rsplit(".", 1)
    companion = f"{base}.{int(function) + 1}"
    if audio and int(function) < 7 and pci_class(companion) >> 8 == 0x0403:
        result.append(companion)
    return result


def _belongs(path, slot):
    try:
        return PCI.joinpath(slot).resolve() in (path.resolve(), *path.resolve().parents)
    except OSError:
        return False


def _nodes(slots):
    """Device numbers and paths for DRM, audio, VFIO and vendor compute users."""
    numbers, names = set(), set()
    for kind, directory in (("drm", DEV / "dri"), ("sound", DEV / "snd")):
        for node in (SYS / "class" / kind).glob("*"):
            if any(_belongs(node / "device", slot) for slot in slots):
                value = read(node / "dev")
                if re.fullmatch(r"\d+:\d+", value):
                    numbers.add(tuple(map(int, value.split(":"))))
                    names.add(str(directory / node.name))
    for slot in slots:
        names.add(str(DEV / "vfio" / group(slot)))
        for node in (PCI / slot / "vfio-dev").glob("vfio*"):
            names.add(str(DEV / "vfio/devices" / node.name))
        if driver(slot) == "nvidia":
            info = read(PROC / "driver/nvidia/gpus" / slot / "information")
            minor = re.search(r"Device Minor:\s*(\d+)", info)
            if minor:
                names.add(str(DEV / ("nvidia" + minor[1])))
            else:
                # Without the per-device mapping, any NVIDIA user is a reason
                # to leave the device alone.
                names.update(str(p) for p in DEV.glob("nvidia[0-9]*"))
        if identity(slot)["vendor"] == "0x1002" and pci_class(slot) >> 16 == 3:
            names.add(str(DEV / "kfd"))  # ROCm's compute node covers all AMD GPUs.
    for name in names:
        try:
            info = os.stat(name)
            if stat.S_ISCHR(info.st_mode):
                numbers.add((os.major(info.st_rdev), os.minor(info.st_rdev)))
        except OSError:
            pass
    return numbers, names


def device_users(slots):
    """Check open handles and surviving mappings. Unknown visibility fails closed.

    The UI may lack permission to inspect other users. The privileged runtime
    repeats this scan immediately before binding and requires complete results.
    """
    numbers, names = _nodes(slots)
    roots = [str((PCI / slot).resolve()) + "/" for slot in slots]
    users, complete = [], True
    try:
        processes = list(PROC.iterdir())
    except OSError:
        return [], False
    for process in processes:
        if not process.name.isdigit():
            continue
        busy = False
        try:
            for fd in (process / "fd").iterdir():
                try:
                    target = os.readlink(fd).removesuffix(" (deleted)")
                    info = fd.stat()
                    number = (os.major(info.st_rdev), os.minor(info.st_rdev))
                    if ((stat.S_ISCHR(info.st_mode) and number in numbers)
                            or target in names or any(target.startswith(root) for root in roots)):
                        busy = True
                        break
                except (FileNotFoundError, ProcessLookupError):
                    continue
            if not busy:
                for line in (process / "maps").read_text().splitlines():
                    parts = line.split(None, 5)
                    if len(parts) == 6:
                        target = parts[5].removesuffix(" (deleted)")
                        if target in names or any(target.startswith(root) for root in roots):
                            busy = True
                            break
        except (FileNotFoundError, ProcessLookupError):
            continue
        except OSError:
            if process.exists():
                complete = False
        if busy:
            users.append(f"{read(process / 'comm', 'process')} (PID {process.name})")
    return users, complete


def display_use(slot):
    reasons = []
    if read(PCI / slot / "boot_vga") == "1":
        reasons.append("Linux boot GPU")
    for node in (SYS / "class/drm").glob("card*"):
        if re.fullmatch(r"card\d+", node.name) and _belongs(node / "device", slot):
            for connector in node.glob(node.name + "-*"):
                if read(connector / "enabled") == "enabled":
                    reasons.append(f"active display: {connector.name}")
                elif (read(connector / "enabled") != "disabled"
                      and read(connector / "status") == "connected"):
                    reasons.append(f"cannot confirm that display {connector.name} is inactive")
    for framebuffer in (SYS / "class/graphics").glob("fb[0-9]*"):
        if _belongs(framebuffer / "device", slot):
            reasons.append("Linux framebuffer")
    return reasons


def discover(audio=True, inspect_users=True):
    labels = {d["slot"]: d for d in hostinfo.pci_devices()}
    slots = sorted(p.name for p in PCI.glob("*") if pci_class(p.name) >> 16 == 3)
    results = []
    for slot in slots:
        selected = functions(slot, audio)
        reasons = display_use(slot)
        warnings = []
        if len(slots) < 2:
            reasons.append("no second GPU is visible; enable the iGPU in BIOS and reboot")
        others = [other for other in slots if other != slot and driver(other) not in ("", "vfio-pci")
                  and any(re.fullmatch(r"card\d+", node.name) and _belongs(node / "device", other)
                          for node in (SYS / "class/drm").glob("card*"))]
        if not others:
            reasons.append("no other GPU has a Linux graphics display device")
        if not all(identity(slot).values()):
            reasons.append("cannot read the GPU's hardware identity")
        for member in selected:
            if not group(member):
                reasons.append(f"{member}: no IOMMU group")
                continue
            members = group_members(member)
            if not members:
                reasons.append(f"{member}: cannot inspect its IOMMU group")
            for other in members:
                if other not in selected and pci_class(other) >> 16 != 6:
                    if not audio and other in functions(slot)[1:]:
                        reasons.append(f"HDMI/DP audio {other} shares this GPU's IOMMU group; "
                                       "enable Include the GPU's HDMI / DisplayPort audio")
                    else:
                        reasons.append(f"IOMMU group also contains {other}; it will not be detached")
        # Read activity only for candidates. Boot/display GPUs are already
        # excluded, so scanning every process for them would waste UI time.
        verified, usage = False, {}
        audio_only_busy = False
        if inspect_users and not reasons:
            verified = True
            for member in selected:
                users, complete = device_users([member])
                verified = verified and complete
                usage[member] = users
                if users:
                    kind = "GPU" if member == slot else "HDMI/DP audio"
                    reasons.append(f"{kind} {member}: in use by " + ", ".join(users[:4]))
            # A sound-server control handle does not mean the graphics device
            # is occupied. Omit only independently isolated audio, never an
            # endpoint needed to make the graphics IOMMU group viable.
            audio_only_busy = (len(selected) > 1 and not usage.get(slot)
                               and any(usage.get(s) for s in selected[1:])
                               and all(group(s) != group(slot) for s in selected[1:]))
            if audio_only_busy:
                reasons.append("Uncheck Include the GPU's HDMI / DisplayPort audio to leave its audio with Linux")
            if not verified:
                warnings.append("Full device-usage check will run with administrator access before launch")
        if not (PCI / slot / "reset").exists():
            warnings.append("No individual GPU reset is exposed; repeat-launch support depends on the GPU")
        if identity(slot)["vendor"] == "0x1002":
            warnings.append("AMD iGPU/GPU passthrough may need a matching ROM and can have reset limitations")
        label = labels.get(slot, {})
        name = label.get("device") or f"{identity(slot)['vendor']}:{identity(slot)['device']}"
        results.append(dict(slot=slot, name=name, driver=driver(slot), identity=identity(slot),
                            functions=selected, groups={s: group(s) for s in selected},
                            reasons=list(dict.fromkeys(reasons)), warnings=warnings,
                            available=not reasons, verified=verified,
                            users=usage, audio_only_busy=audio_only_busy))
    return results


def selected_gpu(slot, audio=True, expected=None, strict=False):
    gpu = next((g for g in discover(audio) if g["slot"] == slot), None)
    if gpu is None:
        raise RuntimeError("Selected GPU is not visible. Enable it in BIOS, reboot, then refresh GPUs.")
    if expected and gpu["identity"] != expected:
        raise RuntimeError("The GPU at the saved PCI address has changed. Refresh and select the intended GPU again.")
    if gpu["reasons"]:
        raise RuntimeError(f"{slot}: " + "; ".join(gpu["reasons"]))
    if strict and not gpu["verified"]:
        raise RuntimeError("Cannot inspect all device users. No GPU was detached; check /proc access permissions.")
    return gpu
