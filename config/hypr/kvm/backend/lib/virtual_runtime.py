#!/usr/bin/env python3
"""Supervise a virtual-display guest without invoking any host handoff hooks.

Only resources created by this run are cleaned up: child processes, a fresh
tap, a private hugepage mount, and the extra pages this run reserved. The host
display, PCI drivers, kernel modules and RT throttling are never changed.
"""

import contextlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

# systemd starts this file directly, without the desktop app's import paths.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from virtual_gpu import QMP, pci_class, _slot
import ovmf_display


def log(message):
    print(f"[virtual] {message}", flush=True)


def cpuset(value):
    cpus = set()
    for part in str(value).split(","):
        if "-" in part:
            first, last = (int(n) for n in part.split("-", 1))
            cpus.update(range(first, last + 1))
        elif part.strip():
            cpus.add(int(part))
    if not cpus:
        raise ValueError(f"Empty CPU affinity: {value!r}")
    return cpus


def stop_child(child):
    """Signal only a process we started and still own."""
    if child.poll() is not None:
        return
    try:
        child.terminate()
    except ProcessLookupError:
        return
    try:
        child.wait(timeout=10)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(timeout=5)


class Runtime:
    def __init__(self, plan):
        self.plan = plan
        self.directory = Path(plan["workdir"])
        self.cleanup_actions = []
        self.child = None

    def status(self, state, message=""):
        data = dict(state=state, message=message, pid=os.getpid(),
                    process_start=Path(f"/proc/{os.getpid()}/stat").read_text().split()[21])
        path = self.directory / "status.json"
        temp = path.with_suffix(".new")
        temp.write_text(json.dumps(data))
        os.chmod(temp, 0o600)
        if os.geteuid() == 0:
            os.chown(temp, self.plan["uid"], self.plan["gid"])
        temp.replace(path)

    def command(self, *argv):
        subprocess.run(list(argv), check=True, stdin=subprocess.DEVNULL, timeout=30)

    def defer(self, callback, *args):
        self.cleanup_actions.append((callback, args))

    def cleanup(self):
        failures = []
        for callback, args in reversed(self.cleanup_actions):
            try:
                callback(*args)
            except Exception as exc:
                failures.append(str(exc))
                log(f"Cleanup: {exc}")
        self.cleanup_actions.clear()
        return failures

    def check_passthrough(self):
        for dev in self.plan["config"].get("devices", []):
            if dev.get("driver") != "vfio-pci" or dev.get("_disabled"):
                continue
            slot = _slot(dev.get("host"))
            cls = pci_class(slot)
            if cls is None or cls == 3:
                raise RuntimeError(f"Refusing unclassified or graphics PCI passthrough: {slot}")
            # Include sibling display functions even if the saved plan was
            # generated before a hardware/driver change.
            base = slot.rsplit(".", 1)[0]
            if any(pci_class(f"{base}.{n}") == 3 for n in range(8)):
                raise RuntimeError(f"Refusing a GPU companion function: {slot}")
            driver = Path(f"/sys/bus/pci/devices/{slot}/driver").resolve().name
            if driver != "vfio-pci":
                raise RuntimeError(f"{slot} is not bound to vfio-pci; disable non-GPU PCI passthrough")

    def memory(self):
        huge = self.plan.get("huge")
        if not huge:
            return
        if self.plan["config"].get("_meta", {}).get("profile") == "macos":
            import mac_memory
            if mac_memory.temporary(self.plan["config"]):
                import mac_hugepages
                token = mac_hugepages.acquire(self.plan["config"])
                self.defer(mac_hugepages.release, token)
                return
            mac_memory.require_existing(self.plan["config"])
            log("Using existing Mac hugepages; host pools and mounts are unchanged")
            return
        pool = Path(huge["pool"])
        free_path = pool.with_name("free_hugepages")
        reserve_path = pool.with_name("resv_hugepages")
        before = int(pool.read_text())
        free = int(free_path.read_text()) - int(reserve_path.read_text())
        extra = max(0, int(huge["pages"]) - free)
        actual = before

        def release():
            # Don't undo an intervening administrator's pool change. Existing
            # guest reservations remain protected by the kernel when shrinking.
            if actual > before and int(pool.read_text()) == actual:
                pool.write_text(str(before))
                log(f"Released this run's extra hugepages (pool: {pool.read_text().strip()})")

        self.defer(release)
        if extra:
            log(f"Reserving {extra} additional hugepages; Linux stays running")
            try:
                pool.write_text(str(before + extra))
            finally:
                actual = int(pool.read_text())
        free = int(free_path.read_text()) - int(reserve_path.read_text())
        if free < int(huge["pages"]):
            raise RuntimeError("Insufficient hugepages while the desktop is running. "
                               "Select ordinary RAM in Virtual GPU, or reserve pages before launching.")
        ram = next((o for o in self.plan["config"].get("objects", []) if o.get("id") == "pc.ram"), {})
        if ram.get("qom-type") == "memory-backend-file":
            mount = Path(huge["mount"])
            mount.mkdir(mode=0o700)  # A fresh run must never adopt an existing mount.
            self.defer(mount.rmdir)
            self.command("mount", "-t", "hugetlbfs", "-o", f"pagesize={huge['size']}", "hugetlbfs", str(mount))
            self.defer(self.command, "umount", str(mount))
        log("Preset hugepage backing ready")

    def network(self):
        tap = self.plan.get("tap")
        if not tap:
            return
        name = tap["name"]
        if Path(f"/sys/class/net/{name}").exists():
            raise RuntimeError(f"Tap {name} already exists; refusing to use or remove another connection")
        self.command("ip", "tuntap", "add", "dev", name, "mode", "tap")
        self.defer(self.command, "ip", "tuntap", "del", "dev", name, "mode", "tap")
        if tap.get("bridge"):
            self.command("ip", "link", "set", name, "master", tap["bridge"])
        self.command("ip", "link", "set", name, "up")
        log(f"Private tap {name} ready on {tap.get('bridge') or 'no bridge'}")

    def tpm(self):
        tpm = self.plan.get("tpm")
        if not tpm:
            return
        state = Path(tpm["state"])
        if not state.is_dir() or not any(state.glob("tpm*-*.permall")):
            raise RuntimeError(f"Existing TPM state not found in {state}; configure the original TPM state directory")
        # Older swtpm processes may not have requested storage locking. Check
        # them too, without killing or connecting to any unrelated emulator.
        for entry in Path("/proc").glob("[0-9]*/cmdline"):
            try:
                argv = entry.read_bytes().decode(errors="replace").split("\0")
                if not argv or "swtpm" not in Path(argv[0]).name or "--tpmstate" not in argv:
                    continue
                raw = argv[argv.index("--tpmstate") + 1]
                existing = next((p[4:] for p in raw.split(",") if p.startswith("dir=")), "")
                if existing and Path(existing).resolve() == state.resolve():
                    raise RuntimeError("The preset's TPM state is already in use by swtpm; shut down that guest first")
            except (OSError, IndexError):
                continue
        if "," in str(state):
            raise RuntimeError("swtpm state paths containing commas are unsupported")
        child = subprocess.Popen([tpm["binary"], "socket", "--tpm2", "--tpmstate",
                                  f"dir={state},mode=0600,lock", "--ctrl",
                                  f"type=unixio,path={tpm['sock']},mode=0600", "--terminate"],
                                 stdin=subprocess.DEVNULL)
        self.defer(stop_child, child)
        for _ in range(100):
            if child.poll() is not None:
                raise RuntimeError(f"swtpm exited with status {child.returncode}; see its output above")
            if Path(tpm["sock"]).is_socket():
                log("Existing TPM identity ready on a private socket")
                return
            time.sleep(0.1)
        raise RuntimeError("swtpm did not create its control socket")

    def apply_pinning(self, qmp):
        pinning = self.plan.get("pinning") or {}
        if not pinning:
            return
        cpus = qmp.execute("query-cpus-fast")
        vcpus = {v["cpu-index"]: v["thread-id"] for v in cpus}
        ios = {v["id"]: v["thread-id"] for v in qmp.execute("query-iothreads")}

        def apply(tid, affinity, sched):
            if affinity:
                os.sched_setaffinity(tid, cpuset(affinity))
            if self.plan["options"]["realtime"] and sched:
                policy = {"fifo": os.SCHED_FIFO, "rr": os.SCHED_RR, "batch": os.SCHED_BATCH,
                          "idle": os.SCHED_IDLE, "other": os.SCHED_OTHER}.get(sched.get("scheduler"))
                if policy is not None:
                    priority = int(sched.get("priority", 1)) if policy in (os.SCHED_FIFO, os.SCHED_RR) else 0
                    os.sched_setscheduler(tid, policy, os.sched_param(priority))

        for entry in pinning.get("vcpupin", []):
            index = int(entry["vcpu"])
            if index not in vcpus:
                raise RuntimeError(f"CPU pinning references missing guest CPU {index}")
            apply(vcpus[index], entry["cpuset"], pinning.get("vcpusched"))
        assigned = set(vcpus.values())
        for ident, affinity in zip(self.plan["iothreads"], pinning.get("iothreadpin", [])):
            if ident in ios and str(affinity).strip():
                apply(ios[ident], affinity, pinning.get("iothreadsched"))
                assigned.add(ios[ident])
        for task in Path(f"/proc/{self.child.pid}/task").iterdir():
            if int(task.name) not in assigned:
                try:
                    apply(int(task.name), pinning.get("emulatorpin"), pinning.get("emulatorsched"))
                except ProcessLookupError:
                    pass
        log("Preset CPU affinity applied; host scheduling settings unchanged")

    def firmware_display(self):
        display = self.plan.get("firmware_display")
        if not display:
            return
        backup = self.directory / "firmware-before-display.fd"
        previous = ovmf_display.apply_resolution(display["path"], display["width"], display["height"], backup)
        if previous:
            log(f"UEFI display preference: {previous[0]}×{previous[1]} → "
                f"{display['width']}×{display['height']}; backup: {backup}")

    def start_guest(self):
        log("Starting QEMU paused to finish setup")
        self.child = subprocess.Popen(self.plan["argv"], stdin=subprocess.DEVNULL)
        self.defer(stop_child, self.child)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if self.child.poll() is not None:
                raise RuntimeError(f"QEMU exited during startup with status {self.child.returncode}")
            try:
                qmp = QMP(self.plan["qmp"], timeout=1)
            except (OSError, RuntimeError):
                time.sleep(0.2)
                continue
            with qmp:
                try:
                    self.apply_pinning(qmp)
                except (OSError, ValueError) as exc:
                    raise RuntimeError(f"CPU affinity/scheduling could not be applied: {exc}. "
                                       "Adjust CPU pinning or disable its Virtual GPU overrides.") from exc
                qmp.execute("cont")
            path = self.plan["qmp"]
            os.chmod(path, 0o600)
            if os.geteuid() == 0:
                os.chown(path, self.plan["uid"], self.plan["gid"])
            self.status("running", "Guest running; Linux desktop remains available")
            log("Guest running. Start and revert scripts are skipped for this entire run.")
            return self.child.wait()
        raise RuntimeError("QEMU did not become ready within 120 seconds")

    def run(self):
        rc, error = 1, ""
        self.status("starting", "Preparing virtual display, memory, network and TPM")
        try:
            self.check_passthrough()
            self.memory()
            self.network()
            self.tpm()
            self.firmware_display()
            rc = self.start_guest()
            if rc:
                error = f"QEMU exited with status {rc}"
        except Exception as exc:
            error = str(exc)
            log(error)
        finally:
            # Repeated service-stop signals must not interrupt owned-resource cleanup.
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            with contextlib.suppress(OSError):
                self.status("stopping", "Releasing this run's resources")
            failures = self.cleanup()
            if failures:
                error = "; ".join([error] + failures).strip("; ")
                rc = 1
            self.status("failed" if error else "stopped", error or "Guest stopped; Linux desktop is ready")
            log(error or "Guest stopped; cleanup complete")
        return rc


def main():
    plan = json.loads(Path(sys.argv[1]).read_text())
    os.umask(0o077)

    def interrupted(signum, frame):
        raise InterruptedError("Virtual VM service was stopped")

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    with open(Path(plan["workdir"]) / "output.log", "a", buffering=1) as output:
        # Child processes must share the readable log, including errors before
        # QMP becomes available. Redirect the real descriptors as well as print.
        os.dup2(output.fileno(), 1)
        os.dup2(output.fileno(), 2)
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            return Runtime(plan).run()


if __name__ == "__main__":
    sys.exit(main())
