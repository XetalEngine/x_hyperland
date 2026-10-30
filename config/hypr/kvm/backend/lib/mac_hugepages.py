"""Temporary Mac 2 MiB hugepages. Journal changes, restore only our additions.

No boot configuration, global cache dropping, forced compaction or firmware edits.
One temporary Mac allocation at a time. Existing pools/mounts remain owned by
their creator; a changed pool or busy mount is preserved rather than forced.
"""
import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

import mac_memory

STATE = mac_memory.TEMP_ROOT / ".temporary-hugepages.json"
POOL = Path("/sys/kernel/mm/hugepages/hugepages-2048kB")
PAGE = 2 * 1024**2


def log(message):
    print(f"[Mac hugepages] {message}", flush=True)


def boot_id():
    return Path("/proc/sys/kernel/random/boot_id").read_text().strip()


def process_start(pid):
    try:
        return Path(f"/proc/{int(pid)}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, ValueError, IndexError):
        return None


@contextmanager
def locked():
    STATE.parent.mkdir(parents=True, exist_ok=True)
    with STATE.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def save(state):
    temp = STATE.with_suffix(".new")
    with temp.open("w") as output:
        os.chmod(temp, 0o600)
        json.dump(state, output, indent=2)
        output.flush()
        os.fsync(output.fileno())
    temp.replace(STATE)


def count(name):
    return int((POOL / name).read_text())


def set_pool(value):
    (POOL / "nr_hugepages").write_text(str(value))


def command(*args):
    subprocess.run(args, check=True, timeout=30, stdin=subprocess.DEVNULL)


def available_memory():
    mem = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines() if ":" in line)
    return int(mem["MemAvailable"].split()[0]) * 1024


def _forget_previous_boot(state):
    """Kernel leases died at reboot; never resize this boot's pool for them."""
    target = mac_memory.temporary_path(state["mount"])
    if state.get("directory_created") and target.is_dir():
        mount = mac_memory.mount_for(str(target))
        if not mount or (mount["mount"] != str(target) and mount["type"] != "hugetlbfs"):
            try:
                target.rmdir()  # Only an empty directory created by the old run.
            except FileNotFoundError:
                pass
            except OSError as exc:
                log(f"Previous run's directory was preserved: {exc}")
    STATE.unlink()
    log("Recovered hugepage state from a previous host boot; the current pool was left untouched.")


def _release(state):
    target = Path(state["mount"])
    if state.get("mounted"):
        mount = mac_memory.mount_for(str(target))
        if mount and mount["mount"] == str(target):
            if mount["type"] != "hugetlbfs" or mount.get("pagesize") != PAGE:
                raise RuntimeError("The temporary mount changed externally; preserved for inspection.")
            command("umount", str(target))  # Never force or lazily detach busy RAM.
        state["mounted"] = False
        save(state)
    before, actual = state["before"], state["actual"]
    if actual > before:
        current = count("nr_hugepages")
        if current != actual:
            log(f"Pool changed externally ({actual} -> {current}); preserving its current size.")
        else:
            available = count("free_hugepages") - count("resv_hugepages")
            if available < actual - before:
                raise RuntimeError("Added pages are still in use/reserved. Cleanup deferred; stop the VM before retrying.")
            set_pool(before)
            if count("nr_hugepages") != before:
                raise RuntimeError("The kernel did not restore the previous hugepage pool size.")
            log(f"Released {actual - before} pages; pool restored to {before} pages.")
    if state.get("directory_created") and target.exists():
        target.rmdir()
    STATE.unlink()


def release(token=None):
    with locked():
        if not STATE.exists():
            return
        state = json.loads(STATE.read_text())
        if state["boot_id"] != boot_id():
            _forget_previous_boot(state)
            return
        if token is not None and token != state["token"]:
            raise RuntimeError("This cleanup request belongs to a different Mac run.")
        if token is None and process_start(state["owner"]) == state["owner_start"]:
            raise RuntimeError("The Mac launcher is still running; refusing manual cleanup.")
        _release(state)


def acquire(data, token=None, owner=None):
    if not mac_memory.temporary(data):
        raise ValueError("Temporary allocation was not enabled in this preset.")
    failures = [message for level, message in mac_memory.checks(data, privileged=True) if level == "error"]
    if failures:
        raise RuntimeError("\n".join(failures))
    ram = next(o for o in data["objects"] if o.get("id") == "pc.ram" and not o.get("_disabled"))
    target = mac_memory.temporary_path(ram["mem-path"])
    need = int(ram["size"]) // PAGE
    token, owner = token or uuid.uuid4().hex, owner or os.getpid()
    with locked():
        if STATE.exists():
            stale = json.loads(STATE.read_text())
            if stale["boot_id"] == boot_id():
                raise RuntimeError(f"A previous Mac hugepage lease exists at {STATE}. Stop its VM and run mac_hugepages.py --release before retrying.")
            _forget_previous_boot(stale)
        before = count("nr_hugepages")
        available = max(0, count("free_hugepages") - count("resv_hugepages"))
        extra = max(0, need - available)
        if extra * PAGE + 4 * 1024**3 > available_memory():
            raise RuntimeError("Not enough available RAM to reserve these pages and leave 4 GiB for the host. Close applications or use the baseline preset.")
        state = dict(token=token, owner=owner, owner_start=process_start(owner), boot_id=boot_id(),
                     before=before, actual=before, mount=str(target), mounted=False, directory_created=False)
        if state["owner_start"] is None:
            raise RuntimeError("The owner process is unavailable; allocation was not started.")
        save(state)
        try:
            if extra:
                log(f"Reserving {extra} additional 2 MiB pages for this run ({need * PAGE // 1024**3} GiB guest RAM).")
                try:
                    set_pool(before + extra)
                finally:
                    state["actual"] = count("nr_hugepages")
                    save(state)
            if count("free_hugepages") - count("resv_hugepages") < need:
                raise RuntimeError("Runtime hugepage allocation came up short (possibly fragmented RAM). Launch aborted before GPU handoff.")
            mount = mac_memory.mount_for(str(target))
            if not target.exists():
                state["directory_created"] = True
                save(state)
                target.mkdir(parents=True, mode=0o700)
            if not mount or mount["type"] != "hugetlbfs":
                if any(target.iterdir()):
                    raise RuntimeError("Refusing to mount over a nonempty directory.")
                state["mounted"] = True
                save(state)
                command("mount", "-t", "hugetlbfs", "-o", "pagesize=2M,mode=0700", "hugetlbfs", str(target))
            mac_memory.require_existing(data)
            log(f"Ready: {need} × 2 MiB pages; preallocation will be verified by QEMU.")
        except BaseException:
            try:
                _release(state)
            except Exception as exc:
                log(f"Cleanup needs a retry: {exc}; journal: {STATE}")
            raise
    return token


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare", action="store_true")
    action.add_argument("--release", action="store_true")
    parser.add_argument("--spec")
    parser.add_argument("--token")
    parser.add_argument("--owner", type=int)
    args = parser.parse_args()
    try:
        if args.prepare:
            if not args.spec or not args.token or not args.owner:
                parser.error("--prepare needs --spec, --token and --owner")
            acquire(json.loads(args.spec), args.token, args.owner)
        else:
            release(args.token)
    except Exception as exc:
        log(str(exc))
        sys.exit(1)
