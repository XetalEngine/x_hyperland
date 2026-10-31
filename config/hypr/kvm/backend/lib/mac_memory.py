"""Read-only Mac memory checks, including optional per-run provisioning.

The Windows launcher keeps its existing resource management. Mac tests consume
existing resources by default. Explicit temporary mode is managed separately
by mac_hugepages; checks run again after allocation and before handoff.
"""

import argparse
import json
import os
from pathlib import Path
import re
import sys

# This helper also runs directly under the privileged launch service.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from model import _parse_size

from portable import data_root
TEMP_ROOT = data_root() / "macos/run"


def temporary(data):
    memory = data.get("memory", {})
    return bool(memory.get("hugepages") and memory.get("temporary"))


def temporary_path(path):
    target = Path(path).resolve()
    if not Path(path).is_absolute() or not target.is_relative_to(TEMP_ROOT.resolve()) or target == TEMP_ROOT.resolve():
        raise ValueError(f"Temporary Mac hugepages need a dedicated directory under {TEMP_ROOT}.")
    return target


def spec(cfg):
    return {key: cfg.data.get(key, {}) for key in ("memory", "simple", "machine")} | {
        "objects": [o for o in cfg.objects if not o.get("_disabled")],
    }


def _read(filename):
    return Path(filename).read_text().strip()


def transparent_status():
    try:
        text = _read("/sys/kernel/mm/transparent_hugepage/enabled")
        return re.search(r"\[([^]]+)\]", text).group(1)
    except (OSError, AttributeError):
        return "unknown"


def _unescape(value):
    return re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), value)


def mount_for(path):
    """Find the deepest actual filesystem, including mounts over hugetlbfs."""
    target = os.path.realpath(path)
    best = None
    for line in _read("/proc/self/mounts").splitlines():
        fields = line.split()
        if len(fields) < 4:
            continue
        mount = _unescape(fields[1]).rstrip("/") or "/"
        if target == mount or target.startswith(mount.rstrip("/") + "/"):
            if best is None or len(mount) > len(best["mount"]):
                best = dict(mount=mount, type=fields[2], options=fields[3].split(","))
    if best and best["type"] == "hugetlbfs":
        size = next((s.split("=", 1)[1] for s in best["options"] if s.startswith("pagesize=")), None)
        if size:
            m = re.fullmatch(r"(\d+)([KMG]?)", size, re.I)
            best["pagesize"] = int(m[1]) * {"": 1, "K": 1024, "M": 1024**2,
                                           "G": 1024**3}[m[2].upper()] if m else 0
        else:
            m = re.search(r"^Hugepagesize:\s+(\d+) kB", _read("/proc/meminfo"), re.M)
            best["pagesize"] = int(m[1]) * 1024 if m else 0
    return best


def checks(data, ready=False, privileged=False):
    """Read-only checks; the allocator must not defer private-directory checks.

    A GUI cannot list the root-owned mountpoint left by an interrupted run.
    Only its preview may defer that inspection to the privileged allocator,
    which checks again before reserving pages or handing over the GPU.
    """
    memory = data.get("memory", {})
    objects = data.get("objects", [])
    ram = next((o for o in objects if o.get("id") == "pc.ram" and not o.get("_disabled")), {})
    huge = bool(memory.get("hugepages", bool(ram.get("mem-path"))))
    if not huge:
        if ram.get("mem-path") or ram.get("hugetlb"):
            return [("error", "Mac memory settings disagree with the QEMU backend; select the intended backing in Memory.")]
        return [("ok", f"Ordinary RAM; host anonymous transparent hugepage policy: {transparent_status()}. "
                 "Verify actual coverage in a running QEMU memory report; static pages are not reserved.")]
    out = []
    provision = temporary(data) and not ready
    try:
        size = int(ram.get("size", 0))
        page = int(memory.get("pagesize", 2 * 1024**2))
        if page not in (2 * 1024**2, 1024**3) or size <= 0 or size % page:
            raise ValueError("Guest RAM must be a positive multiple of the selected 2 MiB or 1 GiB page size.")
        if temporary(data):
            if page != 2 * 1024**2:
                raise ValueError("Temporary Mac allocation currently uses 2 MiB pages. Use an existing pool for 1 GiB pages.")
            temporary_path(ram.get("mem-path", ""))
        if ram.get("qom-type") != "memory-backend-file" or ram.get("_raw"):
            raise ValueError("Mac static pages require a structured memory-backend-file object.")
        if data.get("machine", {}).get("opts", {}).get("memory-backend") != "pc.ram":
            raise ValueError("The machine must use memory-backend=pc.ram.")
        if _parse_size(data.get("simple", {}).get("m", "")) != size:
            raise ValueError("QEMU -m and pc.ram size must match.")
        if not ram.get("prealloc") or ram.get("reserve") is False:
            raise ValueError("Mac static-page tests require prealloc=true and memory reservation enabled.")
        if any(ram.get(k) for k in ("offset", "readonly", "pmem")):
            raise ValueError("Use a plain writable hugetlbfs directory without an offset for Mac static-page tests.")
    except (ValueError, TypeError) as exc:
        return [("error", str(exc))]

    need = size // page
    human = "1 GiB" if page == 1024**3 else "2 MiB"
    try:
        pool = f"/sys/kernel/mm/hugepages/hugepages-{page // 1024}kB"
        free = int(_read(pool + "/free_hugepages"))
        reserved = int(_read(pool + "/resv_hugepages"))
        available = max(0, free - reserved)
        if provision:
            out.append(("ok", f"Temporary 2 MiB hugepages: {need} needed; launch will add up to {max(0, need - available)} pages "
                        "before GPU handoff and release this run's additions after QEMU exits."))
        elif available < need:
            out.append(("error", f"Mac needs {need} × {human} pages; only {available} are free and unreserved. "
                        "Mac mode leaves host pools unchanged. Use ordinary RAM or an already provisioned pool."))
        else:
            out.append(("ok", f"Existing {human} pool has {available} unreserved pages; this VM needs {need}."))
    except (OSError, ValueError) as exc:
        out.append(("error", f"Cannot verify the existing {human} pool: {exc}"))

    path = ram.get("mem-path", "")
    try:
        if provision:
            target = temporary_path(path)
            mount = mount_for(path)
            if mount and mount["type"] == "hugetlbfs":
                if mount.get("pagesize") != page or "ro" in mount["options"]:
                    raise ValueError("The selected directory is on an incompatible or read-only hugetlbfs mount.")
            elif target.exists():
                if not target.is_dir():
                    raise ValueError("Temporary hugetlbfs needs an empty dedicated directory.")
                try:
                    nonempty = any(target.iterdir())
                except PermissionError:
                    if privileged:
                        raise
                    out.append(("ok", "The private hugepage directory will be inspected by the privileged launcher "
                                "before allocation and GPU handoff."))
                else:
                    if nonempty:
                        raise ValueError("Temporary hugetlbfs needs an empty dedicated directory.")
            out.append(("ok", "Temporary mount and pool changes last for this VM run; no boot or sysctl configuration is written."))
            return out
        if not path or not os.path.isabs(path) or not Path(path).is_dir():
            raise ValueError("mem-path must be an existing absolute directory on hugetlbfs.")
        mount = mount_for(path)
        if not mount or mount["type"] != "hugetlbfs" or mount.get("pagesize") != page:
            raise ValueError(f"mem-path must already be mounted as hugetlbfs with {human} pages.")
        fs = os.statvfs(path)
        if "ro" in mount["options"] or fs.f_flag & os.ST_RDONLY:
            raise ValueError("The hugetlbfs mount is read-only.")
        # A size-limited mount can be smaller than the global pool. Unlimited
        # hugetlbfs mounts report zero blocks, not zero allocatable memory.
        if fs.f_blocks and fs.f_bavail * fs.f_frsize < size:
            raise ValueError("The hugetlbfs mount's free quota is smaller than guest RAM.")
        out.append(("ok", f"Existing {human} hugetlbfs mount: {mount['mount']}; no mount or pool changes."))
    except (OSError, ValueError) as exc:
        out.append(("error", str(exc)))
    return out


def require_existing(data):
    errors = [message for severity, message in checks(data, ready=True) if severity == "error"]
    if errors:
        raise RuntimeError("\n".join(errors))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, help="JSON memory specification")
    args = parser.parse_args()
    findings = checks(json.loads(args.spec), ready=True)
    for severity, message in findings:
        print(f"[Mac memory: {severity}] {message}")
    raise SystemExit(1 if any(severity == "error" for severity, _ in findings) else 0)
