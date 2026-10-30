#!/usr/bin/env python3
"""Supervise a spare-GPU guest and restore only the PCI bindings it changed."""

import contextlib
import json
import os
from pathlib import Path
import signal
import sys

import gpu_inventory as inventory
from model import VMConfig
from virtual_runtime import Runtime as DesktopRuntime
import input_devices
import dual_devices

SHM_ROOT = Path("/dev/shm")


def log(message):
    print(f"[dual] {message}", flush=True)


class Runtime(DesktopRuntime):
    def check_passthrough(self):
        opts = self.plan["options"]
        input_devices.verify_plan(self.plan)
        gpu = inventory.selected_gpu(opts["gpu"], opts["gpu_audio"],
                                     self.plan["gpu"]["identity"], strict=True)
        extra = dual_devices.verify_plan(self.plan, strict=True)
        bindings = self.plan["bindings"]
        slots = [item["slot"] for item in bindings]
        if slots != gpu["functions"] + [d["slot"] for d in extra["pci"]]:
            raise RuntimeError("GPU functions changed since the launch plan was created; refresh GPUs")
        for item in bindings:
            if (inventory.identity(item["slot"]) != item["identity"]
                    or inventory.group(item["slot"]) != item["group"]):
                raise RuntimeError(f"PCI identity or IOMMU group changed for {item['slot']}")
        devices = self.plan["config"].get("devices", [])
        passed = [d["host"] for d in devices if d.get("driver") == "vfio-pci" and not d.get("_disabled")]
        if sorted(passed) != sorted(slots):
            raise RuntimeError("The launch plan includes unexpected PCI passthrough devices")
        if self.plan["argv"] != VMConfig(self.plan["config"]).to_argv(True) + ["-S"]:
            raise RuntimeError("The launch command does not match the checked configuration")
        if self.plan.get("firmware_display"):
            raise RuntimeError("Dual GPU must not update shared firmware display preferences")

    def _write(self, path, value):
        path.write_text(str(value) + "\n")

    def _journal(self, bindings, state, errors=None):
        path = self.directory / "gpu-bindings.json"
        temp = path.with_suffix(".new")
        with open(temp, "w") as handle:
            json.dump(dict(state=state, bindings=bindings, errors=errors or []), handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        temp.chmod(0o600)
        if os.geteuid() == 0:
            os.chown(temp, self.plan["uid"], self.plan["gid"])
        temp.replace(path)

    def bind_gpu(self):
        # Recheck after allocating memory/network/TPM, immediately before any
        # host driver write. Another application may have opened the GPU.
        self.check_passthrough()
        originals = []
        for item in self.plan["bindings"]:
            slot = item["slot"]
            override = (inventory.PCI / slot / "driver_override").read_text().strip()
            if override in ("(null)", "(none)"):
                override = ""
            originals.append(dict(item, driver=inventory.driver(slot), override=override))
        self._journal(originals, "preparing")
        # Install rollback before the first write, including partial failures.
        self.defer(self.restore_gpu, originals)
        self.command("modprobe", "vfio-pci")
        for item in originals:
            if item["driver"] != "vfio-pci":
                self._write(inventory.PCI / item["slot"] / "driver_override", "vfio-pci")
        self.check_passthrough()
        for item in originals:
            slot, old = item["slot"], item["driver"]
            if old == "vfio-pci":
                continue
            if inventory.driver(slot) != old:
                raise RuntimeError(f"{slot}: driver changed while preparing passthrough")
            if old:
                self._write(inventory.PCI / slot / "driver/unbind", slot)
            self._write(inventory.PCI.parent / "drivers_probe", slot)
            if inventory.driver(slot) != "vfio-pci":
                raise RuntimeError(f"{slot}: VFIO binding did not succeed")
            log(f"{slot}: {old or 'unbound'} → vfio-pci")
        self._journal(originals, "assigned")

    def restore_gpu(self, originals):
        if self.child is not None and self.child.poll() is None:
            raise RuntimeError("QEMU is still running; GPU restoration was deferred. See gpu-bindings.json.")
        errors, eligible = [], []
        # Release all owned VFIO functions before restoring either original
        # driver. Never detach a device another tool has since rebound.
        for item in reversed(originals):
            slot, old = item["slot"], item["driver"]
            try:
                if inventory.identity(slot) != item["identity"]:
                    raise RuntimeError(f"{slot}: PCI identity changed; restoration skipped")
                current = inventory.driver(slot)
                if current not in ("", "vfio-pci", old):
                    raise RuntimeError(f"{slot}: now using {current}; restoration skipped")
                if current == "vfio-pci" and old != "vfio-pci":
                    self._write(inventory.PCI / slot / "driver/unbind", slot)
                eligible.append(item)
            except Exception as exc:
                errors.append(str(exc))
        for item in reversed(eligible):
            slot, old = item["slot"], item["driver"]
            try:
                if old and inventory.driver(slot) != old:
                    # Use a per-device override only while restoring the exact
                    # driver, then put back the user's original override.
                    self._write(inventory.PCI / slot / "driver_override", old)
                    self._write(inventory.PCI.parent / "drivers_probe", slot)
                    if inventory.driver(slot) != old:
                        raise RuntimeError(f"{slot}: could not restore {old}")
            except Exception as exc:
                errors.append(str(exc))
            finally:
                try:
                    self._write(inventory.PCI / slot / "driver_override", item["override"])
                except Exception as exc:
                    errors.append(str(exc))
        self._journal(originals, "restore-failed" if errors else "restored", errors)
        if errors:
            raise RuntimeError("GPU restoration: " + "; ".join(errors) +
                               f". Original bindings are saved in {self.directory / 'gpu-bindings.json'}")
        log("Original GPU/PCI drivers and overrides restored")

    def shared_memory(self):
        shared = self.plan.get("shared_memory")
        if not shared:
            return
        path = Path(shared["path"])
        if path.parent != SHM_ROOT or not path.name.startswith("vmstart2-lg-"):
            raise RuntimeError("Unexpected Looking Glass shared-memory path")
        size = int(shared["size"])
        if size < 1024**2 or size > 1024**3 or size & (size - 1):
            raise RuntimeError("Invalid Looking Glass shared-memory size")
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        original = os.fstat(fd)

        def remove_owned():
            try:
                current = path.lstat()
                if (current.st_dev, current.st_ino) == (original.st_dev, original.st_ino):
                    path.unlink()
            except FileNotFoundError:
                pass

        self.defer(remove_owned)
        try:
            if os.geteuid() == 0:
                os.fchown(fd, self.plan["uid"], self.plan["gid"])
            # Reserve real tmpfs capacity so QEMU/LG cannot SIGBUS later merely
            # because a sparse file exceeded the free shared-memory space.
            os.posix_fallocate(fd, 0, size)
        finally:
            os.close(fd)
        log(f"Looking Glass memory ready ({size // 1024**2} MiB)")

    def run(self):
        rc, error = 1, ""
        self.status("starting", "Checking spare GPU and preparing the guest")
        try:
            self.check_passthrough()
            self.memory()
            self.network()
            self.tpm()
            self.shared_memory()
            self.bind_gpu()
            rc = self.start_guest()
            if rc:
                error = f"QEMU exited with status {rc}"
        except Exception as exc:
            rc = 1
            error = str(exc)
            log(error)
        finally:
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            with contextlib.suppress(OSError):
                self.status("stopping", "Stopping the guest and restoring its GPU")
            failures = self.cleanup()
            if failures:
                error = "; ".join([error] + failures).strip("; ")
                rc = 1
            self.status("failed" if error else "stopped",
                        error or "Guest stopped; GPU restored and Linux desktop is ready")
            log(error or "Guest stopped; cleanup complete")
        return rc


def main():
    plan = json.loads(Path(sys.argv[1]).read_text())
    os.umask(0o077)

    def interrupted(signum, frame):
        raise InterruptedError("Dual GPU service was stopped")

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    with open(Path(plan["workdir"]) / "output.log", "a", buffering=1) as output:
        os.dup2(output.fileno(), 1)
        os.dup2(output.fileno(), 2)
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            return Runtime(plan).run()


if __name__ == "__main__":
    sys.exit(main())
