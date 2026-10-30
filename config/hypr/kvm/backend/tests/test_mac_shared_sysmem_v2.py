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
KIT = ROOT / "macos/performance/shared-sysmem-experiment-v2"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prepare = load("driver_memory_prepare", KIT / "prepare.py")
with patch.dict(sys.modules, {"prepare": prepare}):
    experiment = load("driver_memory_experiment", KIT / "run-experiment.py")


class SourcesAndPolicy(unittest.TestCase):
    def test_macho_section_type_from_actual_declaration(self):
        body = (KIT / "rm_probe.mm").read_text()
        declaration = body[body.index('__attribute__((used, section('):body.index('static int vm2_rm_selfcheck')]
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for old in (True, False):
                text = declaration.replace(",interposing", "") if old else declaration
                source = tmp / ("old.c" if old else "fixed.c")
                source.write_text("void vm2_IOConnectCallMethod(void);\nvoid IOConnectCallMethod(void);\n" + text)
                binary = source.with_suffix(".o")
                # clang's cross-target assembler emits real Mach-O without an Apple SDK.
                subprocess.run(["clang", "-target", "x86_64-apple-macos15.0", "-c", str(source),
                                "-o", str(binary)], check=True, capture_output=True)
                if old:
                    with self.assertRaisesRegex(ValueError, "S_INTERPOSING"):
                        experiment.macho.inspect_interpose(binary, require_executable=False)
                else:
                    info = experiment.macho.inspect_interpose(binary, require_executable=False)
                    self.assertEqual(info["interpose"]["section_type"], 13)
                    self.assertEqual(info["interpose"]["bytes"], 16)
                    with self.assertRaises(ValueError):
                        experiment.macho.inspect_interpose(binary)  # object is not executable
                    truncated = tmp / "truncated"
                    truncated.write_bytes(binary.read_bytes()[:80])
                    with self.assertRaises(ValueError):
                        experiment.macho.inspect_interpose(truncated, require_executable=False)

    def test_runtime_selfcheck_must_observe_one_forwarded_error(self):
        valid = {"record": "interpose-selfcheck", "passed": True, "device_opened": False,
                 "calls_before": 0, "calls_after": 1, "null_connection_status": 5}
        experiment.verify_selfcheck([valid])
        for changed in ({"calls_after": 0}, {"calls_after": 2}, {"null_connection_status": 0},
                        {"device_opened": True}, {"passed": False}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                experiment.verify_selfcheck([dict(valid, **changed)])
        with self.assertRaises(ValueError):
            experiment.verify_selfcheck([valid, valid])

    def compile_run(self, source, suffix):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            prepare.extract(KIT / "inputs/nvidia-rm-headers-615.78.08.tar.gz", tmp / "headers")
            path, binary = tmp / ("policy" + suffix), tmp / "policy"
            path.write_text(source)
            cxx = suffix == ".cpp"
            subprocess.run(["c++" if cxx else "cc", "-std=c++17" if cxx else "-std=c11",
                "-Wall", "-Wextra", "-Werror", "-fsanitize=undefined", "-pthread",
                "-I", str(KIT), "-I", str(tmp / "headers/src/common/sdk/nvidia/inc"),
                "-I", str(tmp / "headers/src/nvidia/arch/nvalloc/unix/include"),
                str(path), "-o", str(binary)], check=True, capture_output=True)
            subprocess.run([str(binary)], check=True, capture_output=True)

    def test_policy_changes_only_gpu_field_and_refuses_unexpected_requests(self):
        self.compile_run(r'''
#include <assert.h>
#include <string.h>
#include "rm_policy.h"
int main(void) {
    NV_MEMORY_ALLOCATION_PARAMS original;
    memset(&original, 0xa5, sizeof(original));
    original.size = 32ull << 20;
    original.attr = FLD_SET_DRF(OS32, _ATTR, _LOCATION, _PCI, original.attr);
    original.attr = FLD_SET_DRF(OS32, _ATTR, _COHERENCY, _CACHED, original.attr);
    original.attr2 = FLD_SET_DRF(OS32, _ATTR2, _GPU_CACHEABLE, _YES, original.attr2);
    for (unsigned size = 1; size <= 8; size *= 8) {
        NV_MEMORY_ALLOCATION_PARAMS p = original;
        assert(vm2_rm_policy(&p, (uint64_t)size << 20, 0) == 0);
        assert(!memcmp(&p, &original, sizeof(p)));
        assert(vm2_rm_policy(&p, (uint64_t)size << 20, 1) == 1);
        assert(DRF_VAL(OS32, _ATTR2, _GPU_CACHEABLE, p.attr2) == NVOS32_ATTR2_GPU_CACHEABLE_NO);
        assert((p.attr2 ^ original.attr2) == 12);
        p.attr2 = original.attr2;
        assert(!memcmp(&p, &original, sizeof(p)));
    }
    for (int kind = 0; kind < 8; ++kind) {
        NV_MEMORY_ALLOCATION_PARAMS p = original;
        if (kind == 0) p.size = (64ull << 20) + 1;
        if (kind == 1) p.size = (8ull << 20) - 1;
        if (kind == 2) p.attr = FLD_SET_DRF(OS32, _ATTR, _LOCATION, _VIDMEM, p.attr);
        if (kind == 3) p.attr = FLD_SET_DRF(OS32, _ATTR, _COHERENCY, _UNCACHED, p.attr);
        if (kind == 4) p.attr2 = FLD_SET_DRF(OS32, _ATTR2, _GPU_CACHEABLE, _DEFAULT, p.attr2);
        if (kind == 5) p.attr2 = FLD_SET_DRF(OS32, _ATTR2, _GPU_CACHEABLE, _NO, p.attr2);
        NV_MEMORY_ALLOCATION_PARAMS before = p;
        assert(vm2_rm_policy(&p, kind == 6 ? (2ull << 20) : (8ull << 20), kind == 7 ? 2 : 1) == -1);
        assert(!memcmp(&p, &before, sizeof(p)));
    }
    assert(vm2_rm_policy(NULL, 8ull << 20, 1) == -1);
}
''', ".c")

    def test_compiled_interception_scope_forwarding_abi_and_response_recording(self):
        # Compile the actual interception body with an IOKit stand-in. This checks
        # field types/ABI use and forwarding, NOT macOS dyld interposition itself.
        body = (KIT / "rm_probe.mm").read_text().split('__attribute__((used, section(')[0]
        self.compile_run(r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <stdexcept>
using kern_return_t = int;
using mach_port_t = uint32_t;
#define fail(...) throw std::runtime_error("refused")
kern_return_t IOConnectCallMethod(mach_port_t, uint32_t, const uint64_t *, uint32_t,
    const void *, size_t, uint64_t *, uint32_t *, void *, size_t *);
''' + body + r'''
static unsigned calls;
static int kernel_error;
static uint32_t rm_error;
kern_return_t IOConnectCallMethod(mach_port_t, uint32_t, const uint64_t *input, uint32_t,
    const void *, size_t size, uint64_t *, uint32_t *, void *output, size_t *) {
    ++calls;
    if (*input == NV_ESC_RM_ALLOC && size == sizeof(NVOS21_PARAMETERS)) {
        auto *p = (NVOS21_PARAMETERS *)output;
        p->hObjectNew = 42; p->status = rm_error;
    }
    if (*input == NV_ESC_RM_MAP_MEMORY_DMA && size == sizeof(NVOS46_PARAMETERS)) {
        auto *p = (NVOS46_PARAMETERS *)output;
        p->dmaOffset = 0x100000; p->status = rm_error;
    }
    return kernel_error;
}
int main() {
    static_assert(sizeof(NVOS21_PARAMETERS) == 32);
    NV_MEMORY_ALLOCATION_PARAMS mem = {};
    mem.size = 8ull << 20; mem.attr = (1u << 25) | (1u << 29); mem.attr2 = 4;
    NVOS21_PARAMETERS p = {}; p.hRoot = 1; p.hClass = NV01_MEMORY_SYSTEM; p.pAllocParms = (NvP64)&mem;
    uint64_t code = NV_ESC_RM_ALLOC; size_t length = sizeof(p);
    auto alloc = [&](unsigned selector) { return vm2_IOConnectCallMethod(1, selector, &code, 1,
        &p, sizeof(p), nullptr, nullptr, &p, &length); };
    assert(alloc(1) == 0 && calls == 1 && !vm2_rm_alloc_count && mem.attr2 == 4);
    vm2_rm_armed = 1; vm2_rm_treatment = 1;
    assert(alloc(1) == 0 && calls == 2 && !vm2_rm_alloc_count && mem.attr2 == 4);
    vm2_rm_scope_begin(8ull << 20);
    assert(alloc(0) == 0 && calls == 3 && !vm2_rm_alloc_count && mem.attr2 == 4);
    assert(alloc(1) == 0 && calls == 4 && vm2_rm_alloc_count == 1 && mem.attr2 == 8);
    assert(vm2_rm_allocs[0].attr2_before == 4 && vm2_rm_allocs[0].attr2_returned == 8);
    assert(vm2_rm_allocs[0].handle == 42 && vm2_rm_allocs[0].client == 1);
    const unsigned before = calls;
    bool refused = false;
    try { alloc(1); } catch (const std::runtime_error &) { refused = true; }
    assert(refused && calls == before); // unexpected NO request never forwarded
    vm2_rm_scope_end();
    mem.attr2 = 4; vm2_rm_treatment = 0;
    vm2_rm_scope_begin(8ull << 20);
    kernel_error = 3; rm_error = 7;
    assert(alloc(1) == 3 && mem.attr2 == 4);
    assert(vm2_rm_allocs[1].kernel_status == 3 && vm2_rm_allocs[1].rm_status == 7);
    kernel_error = 0; rm_error = 0;
    NVOS46_PARAMETERS m = {}; m.hClient = 1; m.hMemory = 42; m.length = mem.size; m.flags = 16;
    code = NV_ESC_RM_MAP_MEMORY_DMA; length = sizeof(m);
    assert(vm2_IOConnectCallMethod(1, 1, &code, 1, &m, sizeof(m), nullptr, nullptr, &m, &length) == 0);
    assert(vm2_rm_map_count == 1 && vm2_rm_maps[0].flags_before == 16 && vm2_rm_maps[0].flags_after == 16);
    assert(vm2_rm_maps[0].address == 0x100000 && vm2_rm_maps[0].handle == 42);
    vm2_rm_scope_end();
    assert(!vm2_rm_overflow && !vm2_rm_bad_request);
}
''', ".cpp")

    def test_reproducible_patch_keeps_reference_and_workload(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "source"
            prepare.prepare(dest)
            with self.assertRaises(FileExistsError):
                prepare.prepare(dest)
            with tarfile.open(KIT / "foundation/inputs/nullmoth-plugin-v2.5.4.tar.gz") as archive:
                for item in archive.getmembers():
                    if item.isfile():
                        self.assertEqual((dest / "stock" / item.name).read_bytes(), archive.extractfile(item).read())
            original = (KIT / "foundation/core/memory-path.mm").read_text()
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
                prepare.base.patch_vk(changed)

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
        result = subprocess.run(["bash", str(KIT / "Run-Shared-Sysmem-Experiment.command")],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Run inside", result.stdout)


def trace(size, kind, when):
    return {"record": "allocation-trace", "when": when, "shared": {
        "bytes": size, "mapped": True, "memory_type": 2, "memory_flags": 14,
        "bar1_peak_bytes": 0, "treatment": False,
        "route": "system-pool" if size <= 4 << 20 else "ordinary-dedicated"}}


def rm_trace(size, policy, when):
    attr = (1 << 25) | (1 << 29)
    changed = policy == "gpu-cache-no"
    value = (2 if changed else 1) << 2
    return {"record": "rm-request-trace", "when": when, "verified": True, "policy": policy,
        "allocations": [{"scope_bytes": size, "allocation_bytes": max(size, 32 << 20),
            "kernel_status": 0, "rm_status": 0, "changed": int(changed),
            "client": 1, "handle": 2, "attr_before": attr, "attr_sent": attr, "attr_returned": attr,
            "attr2_before": 4, "attr2_sent": value, "attr2_returned": value}],
        "gpu_mappings": [{"client": 1, "handle": 2, "bytes": max(size, 32 << 20),
            "kernel_status": 0, "rm_status": 0, "flags_before": 16, "flags_after": 16}]}


def probe(plugin, kind, policy):
    return {"record": "driver-probe", "protocol": "vmstart2-shared-sysmem-v2",
        "plugin": str(plugin.resolve()), "phase_kind": kind, "rm_policy": policy,
        "instrumented": kind != "reference", "controls_after_load": {
            "NVMTL_SHARED_VRAM": "0", "NVMTL_SHARED_POOL_VRAM": "0", "NVK_BAR_VRAM": "0",
            "NVK_SYSMEM_GPU_UNCACHED": "0"}}


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
            manifest_path = kit / "foundation/inputs/manifest.json"
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
                if argv[-1] == "--check-interpose":
                    stdout.write_text(json.dumps({"record": "interpose-selfcheck", "passed": failure != "selfcheck",
                        "calls_before": 0, "calls_after": 0 if failure == "selfcheck" else 1,
                        "device_opened": False, "null_connection_status": 5}) + "\n")
                    return {"argv": argv, "returncode": 0, "elapsed_seconds": .1}
                calls.append(argv)
                args = dict(arg.split("=", 1) for arg in argv[1:5])
                plugin, kind = Path(args["VM2_PLUGIN"]), args["VM2_PHASE_KIND"]
                policy = args["VM2_RM_POLICY"]
                coherence = "--coherence" in argv
                size, mode = (int(argv[-1]), "coherence") if coherence else (int(argv[-3]), argv[-1])
                if failure == "timeout" and policy == "gpu-cache-no":
                    raise subprocess.TimeoutExpired(argv, timeout)
                rows = [probe(plugin, kind, policy)]
                if kind != "reference":
                    rows += [trace(size, kind, "initial"), rm_trace(size, policy, "initial")]
                if coherence:
                    rows += [trace(size, kind, "final"), rm_trace(size, policy, "final"), {"record": "coherence-complete", "passed": True,
                             "bytes": size, "rounds": 8, "shader_dispatches": 16, "queues": 2, "validated_words": 2 * size}]
                else:
                    rows.append({"record": "case", "protocol": "vmstart2-memory-path-v2",
                                 "bytes": size, "form": "vector", "mode": mode})
                    for rep in range(3):
                        for iteration in range(35):
                            rows.append({"record": "sample", "rep": rep, "iteration": iteration,
                                         "seed": 1 + rep * 35 + iteration, "warmup": iteration < 3,
                                         "passed": True, "validated_elements": size // 16,
                                         "validated_components": 4, "wall_ms": .5 if policy == "gpu-cache-no" else 1.,
                                         "gpu_ms": .4, "cpu_poison_ms": .1, "cpu_validation_ms": .2,
                                         "iteration_total_ms": 2.})
                    if kind != "reference":
                        rows += [trace(size, kind, "final"), rm_trace(size, policy, "final")]
                    rows.append({"record": "complete", "passed": True, "validated_dispatches": 105})
                if failure == "fallback" and policy == "gpu-cache-no":
                    for row in rows:
                        if row["record"] == "rm-request-trace":
                            row["allocations"][0]["attr2_returned"] = 4
                if failure == "driver-changed" and len(calls) == 14:
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
                 patch.object(experiment.macho, "inspect_interpose", return_value={"structural_check_passed": True}), \
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
                self.assertEqual(len(calls), 14 if failure == "driver-changed" else 0 if failure == "selfcheck" else 7)
            else:
                self.assertEqual(rc, 0)
                self.assertEqual(status["state"], "complete")
                self.assertEqual(status["benchmark_cases_completed"], 11)
                self.assertEqual(status["coherence_cases_completed"], 3)
                self.assertTrue(status["installed_driver_unchanged"])
                self.assertTrue(status["persistent_config_unchanged"])
                self.assertEqual(len(calls), 14)
                result = json.loads((output / "comparison.json").read_text())
                self.assertEqual(len(result["results"]), 3)
                self.assertEqual(result["results"][0]["A_before_over_B"], 2.)
                self.assertFalse(result["hardware_PTEs_independently_audited"])

    def test_complete_private_control_treatment_control(self):
        self.exercise()

    def test_fallback_never_accepted_as_treatment(self):
        self.exercise("fallback")

    def test_timeout_preserves_partial_result_and_stops(self):
        self.exercise("timeout")

    def test_inactive_interposer_stops_before_any_gpu_case(self):
        self.exercise("selfcheck")

    def test_driver_changed_during_run_rejects_comparison(self):
        self.exercise("driver-changed")

    def test_missing_interception_wrong_cache_snoop_or_identity_rejected(self):
        p = Path("/private/probe/NVMTLDriver")
        base = [probe(p, "control", "gpu-cache-no"),
                trace(8 << 20, "control", "initial"), trace(8 << 20, "control", "final"),
                rm_trace(8 << 20, "gpu-cache-no", "initial"), rm_trace(8 << 20, "gpu-cache-no", "final")]
        experiment.verify_probe(base, p, "control", 8 << 20, "gpu-cache-no")
        variants = [copy.deepcopy(base) for _ in range(12)]
        variants[0][0]["plugin"] = "/installed/NVMTLDriver"
        variants[1].append(copy.deepcopy(base[-1]))
        variants[2][1]["shared"]["memory_flags"] = 7
        variants[3][3]["allocations"][0]["attr2_sent"] = 0
        variants[4][3]["allocations"][0]["attr2_returned"] = 4
        variants[5][3]["gpu_mappings"][0]["flags_after"] = 0
        variants[6][3]["gpu_mappings"][0]["handle"] = 99
        variants[7][3]["allocations"][0]["attr_returned"] = 1 << 25
        variants[8][3]["allocations"][0]["attr2_sent"] |= 128
        variants[9][3]["gpu_mappings"] = []
        variants[10][3]["allocations"][0]["rm_status"] = 5
        variants[11][0]["controls_after_load"]["NVK_BAR_VRAM"] = "1"
        for i, rows in enumerate(variants):
            with self.subTest(variant=i), self.assertRaises(ValueError):
                experiment.verify_probe(rows, p, "control", 8 << 20, "gpu-cache-no")



if __name__ == "__main__":
    unittest.main()
