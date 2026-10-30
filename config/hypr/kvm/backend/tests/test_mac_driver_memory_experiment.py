"""Linux checks for the isolated experiment. These do not validate a macOS GPU."""
import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "macos/performance/driver-memory-experiment"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prepare = load("driver_memory_prepare", KIT / "prepare.py")
with patch.dict(sys.modules, {"prepare": prepare}):
    experiment = load("driver_memory_experiment", KIT / "run-experiment.py")


class SourcesAndPolicy(unittest.TestCase):
    def test_compiled_policy_limits_default_and_overflow(self):
        source = r'''
#include <assert.h>
#include "bar1_policy.h"
int main(void) {
    assert(vm2_bar1_budget(256ull << 20, 0) == 0);
    assert(vm2_bar1_budget(256ull << 20, 1) == (16ull << 20));
    assert(vm2_bar1_budget(256ull << 20, 2) == 0);
    assert(vm2_bar1_budget(255ull << 20, 1) == 0);
    assert(vm2_bar1_budget(257ull << 20, 1) == (1ull << 20));
    assert(vm2_bar1_budget(512ull << 20, 0) == (256ull << 20));
    assert(vm2_bar1_room(8ull << 20, 8ull << 20, VM2_BAR1_CAP));
    assert(!vm2_bar1_room(8ull << 20, (8ull << 20) + 1, VM2_BAR1_CAP));
    assert(!vm2_bar1_room(UINT64_MAX, 1, VM2_BAR1_CAP));
    assert(!vm2_bar1_room(1, UINT64_MAX, VM2_BAR1_CAP));
    assert(!vm2_bar1_room(1, 1, 0));
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.c"
            path.write_text(source)
            binary = Path(tmp) / "policy"
            subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=undefined",
                            "-I", str(KIT), str(path), "-o", str(binary)], check=True, capture_output=True)
            subprocess.run([str(binary)], check=True, capture_output=True)

    def test_reproducible_patch_keeps_reference_and_workload(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "source"
            prepare.prepare(dest)
            with self.assertRaises(FileExistsError):
                prepare.prepare(dest)
            with tarfile.open(KIT / "inputs/nullmoth-plugin-v2.5.4.tar.gz") as archive:
                for item in archive.getmembers():
                    if item.isfile():
                        self.assertEqual((dest / "stock" / item.name).read_bytes(), archive.extractfile(item).read())
            original = (KIT / "core/memory-path.mm").read_text()
            modified = (dest / "probe/memory-path.mm").read_text()
            # Shader and timed GPU command sequence stay byte-identical.
            self.assertEqual(original.split('R"metal(')[1].split(')metal"')[0],
                             modified.split('R"metal(')[1].split(')metal"')[0])
            self.assertEqual(original.split("const double start = now();")[1].split('if (mode == "private")')[0],
                             modified.split("const double start = now();")[1].split('if (mode == "private")')[0])
            subprocess.run(["patch", "--dry-run", "--batch", "-p1", "-i", str(dest / "driver.patch")],
                           cwd=dest / "stock", check=True, capture_output=True)
            changed = (dest / "stock/plugin/nvmtl_vk.c").read_text().replace("256ull << 20", "128ull << 20")
            with self.assertRaises(ValueError):
                prepare.patch_vk(changed)

    def test_extraction_rejects_links_and_traversal(self):
        for name, kind in (("../escape", tarfile.REGTYPE), ("/absolute", tarfile.REGTYPE),
                           ("symlink", tarfile.SYMTYPE), ("hardlink", tarfile.LNKTYPE)):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                archive = base / "bad.tar.gz"
                with tarfile.open(archive, "w:gz") as tar:
                    member = tarfile.TarInfo(name)
                    member.type = kind
                    member.linkname = "/tmp/escape"
                    tar.addfile(member)
                with self.assertRaises(ValueError):
                    prepare.extract(archive, base / "unpack")

    def test_linux_launch_refused(self):
        if sys.platform == "darwin":
            self.skipTest("Checks Linux refusal")
        result = subprocess.run(["bash", str(KIT / "Run-Driver-Memory-Experiment.command")],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Run inside", result.stdout)


def trace(size, kind, when):
    treatment = kind == "treatment"
    shared = {"bytes": size, "mapped": True, "memory_type": 1 if treatment else 2,
              "memory_flags": 7 if treatment else 14, "bar1_peak_bytes": 8 << 20 if treatment else 0,
              "heap_bytes": 256 << 20 if treatment else 24 << 30, "treatment": treatment,
              "route": ("vram-pool" if size <= 4 << 20 else "bar1-dedicated") if treatment
              else ("system-pool" if size <= 4 << 20 else "ordinary-dedicated")}
    return {"record": "allocation-trace", "when": when, "shared": shared, "private": {"route": "sparse-private"}}


class Lifecycle(unittest.TestCase):
    def exercise(self, failure=None):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "Desktop").mkdir()
            kit = home / "kit"
            shutil.copytree(KIT, kit, ignore=shutil.ignore_patterns("__pycache__"))
            installed = home / "installed"
            installed.mkdir()
            stock = installed / "NVMTLDriver"
            stock.write_bytes(b"fake stock plugin")
            translator = installed / "libnvmtl_translate.dylib"
            translator.write_bytes(b"fake translator")
            config = installed / "nvrm610.conf"
            config.write_text("unchanged configuration\n")
            manifest_path = kit / "inputs/manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["installed_driver_sha256"] = {str(p): prepare.sha256(p) for p in (stock, translator)}
            manifest_path.write_text(json.dumps(manifest))
            calls = []

            def command(argv, stdout, stderr, timeout):
                stdout.write_text("")
                stderr.write_text("")
                if "-o" in argv:
                    Path(argv[argv.index("-o") + 1]).write_bytes(b"fake native binary")
                if argv[0] != "/usr/bin/env":
                    return {"argv": argv, "returncode": 0, "elapsed_seconds": .1}
                calls.append(argv)
                args = dict(arg.split("=", 1) for arg in argv[1:4])
                plugin, kind = Path(args["VM2_PLUGIN"]), args["VM2_PHASE_KIND"]
                coherence = "--coherence" in argv
                size, mode = (int(argv[-1]), "coherence") if coherence else (int(argv[-3]), argv[-1])
                if failure == "timeout" and kind == "treatment":
                    raise subprocess.TimeoutExpired(argv, timeout)
                rows = [{"record": "driver-probe", "plugin": str(plugin.resolve()), "phase_kind": kind,
                         "instrumented": kind != "reference", "controls_after_load": {
                             "NVMTL_SHARED_VRAM": "1", "NVMTL_SHARED_VRAM_BUDGET_MB": "16",
                             "NVMTL_SHARED_POOL_VRAM": "1", "NVK_BAR_VRAM": "1"}}]
                if kind != "reference":
                    rows.append(trace(size, kind, "initial"))
                if coherence:
                    rows += [trace(size, kind, "final"), {"record": "coherence-complete", "passed": True,
                             "bytes": size, "round_trips": 4, "validated_words": size}]
                else:
                    rows.append({"record": "case", "protocol": "vmstart2-memory-path-v2",
                                 "bytes": size, "form": "vector", "mode": mode})
                    for rep in range(3):
                        for iteration in range(35):
                            rows.append({"record": "sample", "rep": rep, "iteration": iteration,
                                         "seed": 1 + rep * 35 + iteration, "warmup": iteration < 3,
                                         "passed": True, "validated_elements": size // 16,
                                         "validated_components": 4, "wall_ms": .5 if kind == "treatment" else 1.,
                                         "gpu_ms": .4, "cpu_poison_ms": .1, "cpu_validation_ms": .2,
                                         "iteration_total_ms": 2.})
                    if kind != "reference":
                        rows.append(trace(size, kind, "final"))
                    rows.append({"record": "complete", "passed": True, "validated_dispatches": 105})
                if failure == "fallback" and kind == "treatment":
                    for row in rows:
                        if row["record"] == "allocation-trace":
                            row["shared"]["memory_flags"] = 14
                            row["shared"]["route"] = "system-pool"
                if failure == "driver-changed" and len(calls) == 26:
                    stock.write_bytes(b"changed externally")
                stdout.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
                return {"argv": argv, "returncode": 0, "elapsed_seconds": .1}

            with patch.object(experiment, "HERE", kit), patch.object(prepare, "HERE", kit), \
                 patch.object(experiment, "STOCK", stock), patch.object(experiment, "CONFIG", config), \
                 patch.object(experiment.sys, "platform", "darwin"), \
                 patch.object(experiment.sys, "argv", ["run-experiment.py"]), \
                 patch.object(experiment.os, "uname", return_value=SimpleNamespace(machine="x86_64")), \
                 patch.object(experiment.os, "geteuid", return_value=1000), \
                 patch.object(experiment.Path, "home", return_value=home), \
                 patch.object(experiment.shutil, "which", return_value="/usr/bin/xcrun"), \
                 patch.object(experiment.subprocess, "run", return_value=SimpleNamespace(returncode=0)), \
                 patch.object(experiment.core, "command", side_effect=command), \
                 contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                rc = experiment.main()
            output = next(p for p in (home / "Desktop").iterdir() if p.is_dir())
            status = json.loads((output / "status.json").read_text())
            with zipfile.ZipFile(output.with_suffix(".zip")) as z:
                self.assertIsNone(z.testzip())
                manifest = json.loads(z.read(output.name + "/SHA256SUMS.json"))
                for name, digest in manifest.items():
                    self.assertEqual(prepare.sha256(output / name), digest)
            if failure:
                self.assertEqual(rc, 1)
                self.assertEqual(status["state"], "incomplete")
                self.assertFalse((output / "comparison.json").exists())
                self.assertEqual(len(calls), 26 if failure == "driver-changed" else 11)
            else:
                self.assertEqual(rc, 0)
                self.assertEqual(status["state"], "complete")
                self.assertEqual(status["benchmark_cases_completed"], 20)
                self.assertEqual(status["coherence_cases_completed"], 6)
                self.assertTrue(status["installed_driver_unchanged"])
                self.assertTrue(status["persistent_config_unchanged"])
                self.assertEqual(len(calls), 26)
                result = json.loads((output / "comparison.json").read_text())
                self.assertEqual(len(result["results"]), 6)
                self.assertEqual(result["results"][0]["A_before_over_B"], 2.)
                self.assertFalse(result["physical_placement_independently_audited"])

    def test_complete_private_control_treatment_control(self):
        self.exercise()

    def test_fallback_never_accepted_as_treatment(self):
        self.exercise("fallback")

    def test_timeout_preserves_partial_result_and_stops(self):
        self.exercise("timeout")

    def test_driver_changed_during_run_rejects_comparison(self):
        self.exercise("driver-changed")

    def test_wrong_plugin_duplicate_trace_and_excess_budget_rejected(self):
        p = Path("/private/probe/NVMTLDriver")
        base = [{"record": "driver-probe", "phase_kind": "treatment", "plugin": str(p),
                 "instrumented": True, "controls_after_load": {"NVMTL_SHARED_VRAM": "1",
                 "NVMTL_SHARED_VRAM_BUDGET_MB": "16", "NVMTL_SHARED_POOL_VRAM": "1", "NVK_BAR_VRAM": "1"}},
                trace(8 << 20, "treatment", "initial"), trace(8 << 20, "treatment", "final")]
        experiment.verify_probe(base, p, "treatment", 8 << 20)
        variants = [copy.deepcopy(base) for _ in range(3)]
        variants[0][0]["plugin"] = "/installed/NVMTLDriver"
        variants[1].append(copy.deepcopy(base[-1]))
        variants[2][1]["shared"]["bar1_peak_bytes"] = 17 << 20
        for rows in variants:
            with self.assertRaises(ValueError):
                experiment.verify_probe(rows, p, "treatment", 8 << 20)


if __name__ == "__main__":
    unittest.main()
