"""Exercise the comparison lifecycle with a fake guest, not a GPU or VM."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ab = load("shared_vram_ab", ROOT / "macos/performance/shared-vram-ab-test/run-ab.py")
core = load("memory_path_v2", ROOT / "macos/performance/memory-path-test/run.py")


class ExperimentLifecycle(unittest.TestCase):
    def exercise(self, fail_case=None, available=True):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "Desktop").mkdir()
            calls = []

            def command(argv, stdout, stderr, timeout):
                stdout.write_text("")
                stderr.write_text("")
                rc = 0
                if "--probe-heaps" in argv:
                    stdout.write_text(json.dumps({"record": "memory-heaps",
                        "max_opt_in_budget_bytes": (32 << 20) if available else 0}))
                elif "-o" in argv:
                    Path(argv[argv.index("-o") + 1]).write_bytes(b"fake native binary")
                elif argv[0] == "/usr/bin/env":
                    calls.append(argv)
                    if len(calls) == fail_case:
                        rc = 9
                        stderr.write_text("Injected dispatch failure\n")
                    else:
                        size, form, mode = int(argv[-3]), argv[-2], argv[-1]
                        rows = [{"record": "case", "protocol": "vmstart2-memory-path-v2",
                                 "bytes": size, "form": form, "mode": mode}]
                        for rep in range(3):
                            for iteration in range(35):
                                rows.append({"record": "sample", "rep": rep, "iteration": iteration,
                                             "seed": 1 + rep * 35 + iteration,
                                             "warmup": iteration < 3, "passed": True,
                                             "validated_elements": size // 16,
                                             "validated_components": 4, "wall_ms": 1., "gpu_ms": .5})
                        rows.append({"record": "complete", "passed": True, "validated_dispatches": 105})
                        stdout.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
                return {"argv": argv, "returncode": rc, "elapsed_seconds": .01}

            def digest(path):
                return ab.EXPECTED[str(path)] if str(path) in ab.EXPECTED else core.sha256(path)

            fake = SimpleNamespace(SOURCES=core.SOURCES, save=core.save, sha256=digest,
                                   summarize=core.summarize, command=command)
            spec = SimpleNamespace(loader=SimpleNamespace(exec_module=lambda _: None))
            with patch.object(ab.sys, "platform", "darwin"), patch.object(ab.sys, "argv", ["run-ab.py"]), \
                 patch.object(ab.Path, "home", return_value=home), \
                 patch.object(ab.shutil, "which", return_value="/usr/bin/xcode-select"), \
                 patch.object(ab.subprocess, "run", return_value=SimpleNamespace(returncode=0)), \
                 patch.object(ab.importlib.util, "spec_from_file_location", return_value=spec), \
                 patch.object(ab.importlib.util, "module_from_spec", return_value=fake), \
                 patch.dict(os.environ, {"NVMTL_SHARED_VRAM": "original"}, clear=True), \
                 contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                rc = ab.main()
                self.assertEqual(os.environ["NVMTL_SHARED_VRAM"], "original")
                self.assertNotIn("NVMTL_SHARED_VRAM_BUDGET_MB", os.environ)
            output = next(p for p in (home / "Desktop").iterdir() if p.is_dir())
            status = json.loads((output / "status.json").read_text())
            with zipfile.ZipFile(output.with_suffix(".zip")) as z:
                self.assertIsNone(z.testzip())
                self.assertIn(output.name + "/status.json", z.namelist())
            if not available:
                self.assertEqual(rc, 0)
                self.assertEqual(status["state"], "route-unavailable")
                self.assertEqual(status["cases_completed"], 0)
                self.assertFalse(calls)
                self.assertFalse((output / "comparison.json").exists())
                self.assertFalse((output / "memory-path").exists())
            elif fail_case:
                self.assertEqual(rc, 1)
                self.assertEqual(status["state"], "incomplete")
                self.assertEqual(status["cases_completed"], fail_case - 1)
                self.assertEqual(len(calls), fail_case)
                self.assertFalse((output / "comparison.json").exists())
            else:
                self.assertEqual(rc, 0)
                self.assertEqual(status["state"], "complete")
                self.assertEqual(status["cases_completed"], 18)
                self.assertEqual(len(json.loads((output / "comparison.json").read_text())), 6)
                self.assertEqual([c[1] for c in calls],
                                 ["NVMTL_SHARED_VRAM=0"] * 6 + ["NVMTL_SHARED_VRAM=1"] * 6
                                 + ["NVMTL_SHARED_VRAM=0"] * 6)
                self.assertTrue(all(c[2] == "NVMTL_SHARED_VRAM_BUDGET_MB=32" for c in calls))
                self.assertEqual(len({c[3] for c in calls}), 1)
            return calls

    def test_complete_control_treatment_control_and_environment_isolation(self):
        self.exercise()

    def test_failed_first_treatment_stops_and_preserves_incomplete_evidence(self):
        self.exercise(fail_case=7)

    def test_zero_heap_budget_skips_build_and_dispatch(self):
        self.exercise(available=False)

    def test_missing_or_duplicate_comparison_rejected(self):
        rows = [{"phase": phase, "bytes": size, "mode": mode,
                 "form": "vector", "protocol": "vmstart2-memory-path-v2",
                 "validated_dispatches": 105, "median_of_wall_medians_ms": 1.,
                 "process_elapsed_seconds": 1.}
                for phase, _ in ab.PHASES for size in ab.SIZES for mode in ab.MODES]
        with self.assertRaises(ValueError):
            ab.compare(rows[:-1])
        with self.assertRaises(ValueError):
            ab.compare(rows[:-1] + [rows[0]])

    @unittest.skipIf(os.uname().sysname == "Darwin", "This check verifies Linux refusal")
    def test_host_launch_refused(self):
        script = ROOT / "macos/performance/shared-vram-ab-test/Run-Shared-VRAM-AB.command"
        result = subprocess.run(["bash", str(script)], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 1)
        self.assertIn("inside the working macOS VM", result.stdout)


class HeapProbe(unittest.TestCase):
    def test_heap_budget_and_instance_cleanup_with_fake_icd(self):
        ct = ab.ct
        for mib, expected in ((128, 0), (256, 0), (512, 32 << 20)):
            with self.subTest(heap_mib=mib):
                destroyed = []
                created = []

                @ct.CFUNCTYPE(ct.c_int32, ct.POINTER(ab.InstanceInfo), ct.c_void_p, ct.POINTER(ct.c_void_p))
                def create(info, allocator, out):
                    created.append((info.contents.sType, info.contents.pApplicationInfo.contents.apiVersion))
                    out[0] = 42
                    return 0

                @ct.CFUNCTYPE(None, ct.c_void_p, ct.c_void_p)
                def destroy(instance, allocator):
                    destroyed.append(instance)

                @ct.CFUNCTYPE(ct.c_int32, ct.c_void_p, ct.POINTER(ct.c_uint32), ct.POINTER(ct.c_void_p))
                def enumerate_devices(instance, count, devices):
                    count[0] = 1
                    if devices:
                        devices[0] = 43
                    return 0

                @ct.CFUNCTYPE(None, ct.c_void_p, ct.POINTER(ab.MemoryProperties))
                def properties(device, out):
                    out.contents.memoryTypeCount = 2
                    out.contents.memoryHeapCount = 2
                    out.contents.memoryHeaps[0].size = mib << 20
                    out.contents.memoryHeaps[0].flags = 1
                    out.contents.memoryHeaps[1].size = 16 << 30
                    out.contents.memoryTypes[0].propertyFlags = 7
                    out.contents.memoryTypes[0].heapIndex = 0
                    out.contents.memoryTypes[1].propertyFlags = 14
                    out.contents.memoryTypes[1].heapIndex = 1

                callbacks = {b"vkCreateInstance": create, b"vkDestroyInstance": destroy,
                             b"vkEnumeratePhysicalDevices": enumerate_devices,
                             b"vkGetPhysicalDeviceMemoryProperties": properties}

                def gpa(instance, name):
                    return ct.cast(callbacks[name], ct.c_void_p).value

                result = ab.inspect_heaps(SimpleNamespace(vk_icdGetInstanceProcAddr=gpa))
                self.assertEqual(result["max_opt_in_budget_bytes"], expected)
                self.assertEqual(destroyed, [42])
                self.assertEqual(created, [(1, 1 << 22)])
                self.assertEqual(len(result["eligible_types"]), 1)
        self.assertEqual(ct.sizeof(ab.MemoryProperties), 520)
        self.assertEqual(ab.MemoryProperties.memoryHeaps.offset, 264)


if __name__ == "__main__":
    unittest.main()
