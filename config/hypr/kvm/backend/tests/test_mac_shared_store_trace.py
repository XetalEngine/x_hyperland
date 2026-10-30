"""Host checks for a diagnostic collector; these do not execute macOS or a GPU."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "macos/performance/shared-store-trace"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


prepare = load("store_trace_prepare", KIT / "prepare.py")
with patch.dict(sys.modules, {"prepare": prepare}):
    runner = load("store_trace_runner", KIT / "run.py")
fixtures = load("old_trace_fixtures", ROOT / "tests/test_mac_shared_sysmem_v2.py")


def output_rows(plugin, form, mode, capture):
    size = 8 << 20
    rows = [fixtures.probe(plugin, "control", "control")]
    if capture is not None:
        rows[0]["controls_after_load"].update(NAK_DEBUG="print", NVK_DUMP_SHADER_DIR=str(capture / "machine-code"),
            NVMTL_FC_DUMP_ALL=str(capture / "air"), MESA_SHADER_CACHE_DISABLE="true")
    rows += [fixtures.trace(size, "control", "initial"), fixtures.rm_trace(size, "control", "initial")]
    rows += [{"record": "case", "protocol": "vmstart2-memory-path-v2", "bytes": size, "form": form, "mode": mode}]
    for rep in range(3):
        for i in range(35):
            rows.append({"record": "sample", "rep": rep, "iteration": i, "seed": 1 + rep * 35 + i,
                "warmup": i < 3, "passed": True, "validated_elements": size // 16, "validated_components": 4,
                "wall_ms": 91., "gpu_ms": 90., "cpu_poison_ms": .3, "cpu_validation_ms": 2.3,
                "iteration_total_ms": 94.})
    rows += [fixtures.trace(size, "control", "final"), fixtures.rm_trace(size, "control", "final"),
             {"record": "complete", "passed": True, "validated_dispatches": 105}]
    return rows


def write_rows(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def shader_fixture(case, stderr):
    p = case / "machine-code/compute_0.bin"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\x01\x02\x03\x04" * 4)
    stderr.write_text(f"NAK IR after calc_instr_deps:\nEncoded shader:\nnvk: wrote {p} (16 B, hdr_offset 0 code_offset 0)\n")


class SourceTests(unittest.TestCase):
    def test_preparation_preserves_native_workload_plugin_and_bridge(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            prepare.base.prepare(tmp / "native")
            prepare.prepare(tmp / "trace")
            for rel in ["probe/memory-path.mm", "probe/validation.h", "probe/rm_policy.h", "probe/rm_interpose.c",
                        "probe/rm_interpose.h", "benchmark.patch"]:
                self.assertEqual((tmp / "native" / rel).read_bytes(), (tmp / "trace" / rel).read_bytes(), rel)
            for p in (tmp / "native/experiment").iterdir():
                if p.is_file():
                    expected = p.read_bytes().replace(b"vm2-shared-sysmem-probe-v2", b"vm2-shared-store-trace")
                    self.assertEqual(expected, (tmp / "trace/experiment" / p.name).read_bytes())
            support = (tmp / "trace/probe/probe_support.mm").read_text()
            self.assertLess(support.index("dlopen("), support.index('knobs[@"NAK_DEBUG"]'))
            self.assertLess(support.index('knobs[@"NAK_DEBUG"]'), support.index("[[cls alloc] initWithAcceleratorPort:"))
            self.assertIn('knobs[@"NAK_DEBUG"] = @"print";', support)
            rm = (tmp / "trace/probe/rm_probe.mm").read_text()
            self.assertIn('if (vm2_rm_armed || !p || strcmp(p, "control"))', rm)

    def test_macho_accepts_native_regular_dylib_but_not_main_or_invalid_bounds(self):
        # A bounded Mach-O table fixture checks the parser contract, not dyld.
        data = bytearray(32 + 152 + 16)
        struct.pack_into("<8I", data, 0, 0xFEEDFACF, 0x01000007, 3, 6, 1, 152, 0, 0)
        struct.pack_into("<II", data, 32, 0x19, 152)
        struct.pack_into("<I", data, 32 + 64, 1)
        at = 32 + 72
        data[at:at + 16] = b"__interpose".ljust(16, b"\0")
        data[at + 16:at + 32] = b"__DATA_CONST".ljust(16, b"\0")
        struct.pack_into("<QI", data, at + 40, 16, 184)
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "library"
            for marker in (0, 13):
                struct.pack_into("<I", data, at + 64, marker)
                p.write_bytes(data)
                self.assertEqual(runner.accepted.macho.inspect_interpose(p)["filetype"], 6)
            for offset, value in ((12, 2), (at + 48, 0), (at + 64, 1)):
                bad = bytearray(data); struct.pack_into("<I", bad, offset, value); p.write_bytes(bad)
                with self.assertRaises(ValueError):
                    runner.accepted.macho.inspect_interpose(p)

    def test_shader_capture_requires_ir_code_and_upload_acknowledgment(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = Path(tmp); stderr = case / "stderr"
            shader_fixture(case, stderr)
            row = runner.shader_evidence(case, stderr)
            self.assertEqual(len(row["machine_code_files"]), 1)
            self.assertFalse(row["target_kernel_independently_correlated"])
            valid = stderr.read_text()
            for text in ("", valid.replace("nvk: wrote", "not an upload"), valid + "Unknown NAK_DEBUG flag"):
                stderr.write_text(text)
                with self.assertRaises(ValueError): runner.shader_evidence(case, stderr)
            stderr.write_text(valid)
            (case / "machine-code/compute_0.bin").write_bytes(b"")
            with self.assertRaises(ValueError): runner.shader_evidence(case, stderr)

    def test_validation_rejects_wrong_scope_changed_policy_missing_samples_and_controls(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp); path = tmp / "raw"; plugin = tmp / "plugin"
            valid = output_rows(plugin, "scalar", "shared", tmp)
            write_rows(path, valid)
            row = runner.summarize(path, plugin, "scalar", "shared", tmp)
            self.assertEqual(row["validated_dispatches"], 105)
            self.assertFalse(row["performance_comparison_valid"])
            for failure in ("sample", "policy", "diagnostics", "nonfinite"):
                rows = json.loads(json.dumps(valid))
                if failure == "sample": rows.pop(4)
                elif failure == "policy": rows[2]["policy"] = "gpu-cache-no"
                elif failure == "diagnostics": rows[0]["controls_after_load"]["NAK_DEBUG"] = "serial"
                else: rows[4]["cpu_validation_ms"] = float("inf")
                write_rows(path, rows)
                with self.assertRaises(ValueError): runner.summarize(path, plugin, "scalar", "shared", tmp)

    def test_linux_launcher_refuses_before_creating_output(self):
        result = subprocess.run(["bash", str(KIT / "Run-Shared-Store-Trace.command")], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Nothing was changed", result.stderr)


class Lifecycle(unittest.TestCase):
    def exercise(self, failure=None):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp); (home / "Desktop").mkdir()
            kit = home / "kit"
            shutil.copytree(KIT, kit, ignore=shutil.ignore_patterns("__pycache__"))
            stock = home / "NVMTLDriver"; stock.write_bytes(b"stock")
            translator = home / "libnvmtl_translate.dylib"; translator.write_bytes(b"translator")
            config = home / "nvrm610.conf"; config.write_text("unchanged")
            p = kit / "foundation/foundation/inputs/manifest.json"
            manifest = json.loads(p.read_text())
            manifest["installed_driver_sha256"] = {str(f): prepare.sha256(f) for f in (stock, translator)}
            p.write_text(json.dumps(manifest))
            calls = []

            def fake_prepare(dest):
                dest.mkdir()

            def command(argv, stdout, stderr, timeout):
                stdout.write_text(""); stderr.write_text("")
                if "-o" in argv: Path(argv[argv.index("-o") + 1]).write_bytes(b"native fixture")
                result = {"argv": argv, "returncode": 0, "elapsed_seconds": .1}
                if argv[0] != "/usr/bin/env": return result
                if argv[-1] == "--check-interpose":
                    write_rows(stdout, [{"record": "interpose-selfcheck", "passed": failure != "hook", "calls_before": 0,
                        "calls_after": 0 if failure == "hook" else 1, "device_opened": False, "null_connection_status": 5}])
                    return result
                calls.append(argv)
                env = dict(a.split("=", 1) for a in argv[1:6])
                self.assertEqual(env["VM2_RM_POLICY"], "control")
                capture = Path(env["VM2_CAPTURE_ROOT"]) if env["VM2_CAPTURE_ROOT"] else None
                if failure == "timeout" and capture: raise subprocess.TimeoutExpired(argv, timeout)
                write_rows(stdout, output_rows(Path(env["VM2_PLUGIN"]), argv[-2], argv[-1], capture))
                if capture:
                    if failure != "no-code": shader_fixture(capture, stderr)
                    (capture / "cache/air/target.spv").write_bytes(b"kept shader cache")
                if failure == "driver-changed" and len(calls) == 6: stock.write_bytes(b"changed")
                return result

            with patch.object(runner, "HERE", kit), patch.object(runner.prepare, "prepare", side_effect=fake_prepare), \
                 patch.object(runner.accepted, "STOCK", stock), patch.object(runner.accepted, "CONFIG", config), \
                 patch.object(runner.sys, "platform", "darwin"), patch.object(runner.sys, "argv", ["run.py"]), \
                 patch.object(runner.os, "uname", return_value=SimpleNamespace(machine="x86_64")), \
                 patch.object(runner.os, "geteuid", return_value=1000), patch.object(runner.Path, "home", return_value=home), \
                 patch.object(runner.shutil, "which", return_value="xcrun"), \
                 patch.object(runner.subprocess, "run", return_value=SimpleNamespace(returncode=0)), \
                 patch.object(runner.core, "command", side_effect=command), \
                 patch.object(runner.accepted.macho, "inspect_interpose", return_value={"structural_check_passed": True}), \
                 contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                rc = runner.main()
            output = next(p for p in (home / "Desktop").iterdir() if p.is_dir())
            status = json.loads((output / "status.json").read_text())
            self.assertEqual(status["state"], "incomplete" if failure else "complete")
            self.assertEqual(rc, 1 if failure else 0)
            self.assertEqual(len(calls), 0 if failure == "hook" else 3 if failure in ("timeout", "no-code") else 6)
            with zipfile.ZipFile(output.with_suffix(".zip")) as z:
                self.assertIsNone(z.testzip())
                sums = json.loads(z.read(output.name + "/SHA256SUMS.json"))
                for name, digest in sums.items(): self.assertEqual(prepare.sha256(output / name), digest)
                if not failure:
                    self.assertEqual(status["cases_completed"], 6)
                    self.assertTrue(status["installed_driver_unchanged"])
                    self.assertTrue(any(n.endswith("target.spv") for n in sums))
                    self.assertTrue(any(n.endswith("compute_0.bin") for n in sums))
                if failure == "driver-changed": self.assertFalse(status["installed_driver_unchanged"])

    def test_complete_capture_keeps_shader_inputs_and_machine_code(self): self.exercise()
    def test_inactive_hook_prevents_gpu_work(self): self.exercise("hook")
    def test_missing_code_is_incomplete_not_a_success(self): self.exercise("no-code")
    def test_timeout_preserves_partial_report(self): self.exercise("timeout")
    def test_changed_installed_driver_rejects_run(self): self.exercise("driver-changed")


if __name__ == "__main__":
    unittest.main()
