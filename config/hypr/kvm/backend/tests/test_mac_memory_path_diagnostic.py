"""Host checks for diagnostic data acceptance and native output validation."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "macos/performance/memory-path-test"
spec = importlib.util.spec_from_file_location("memory_path_runner", SOURCE / "run.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def valid_records():
    rows = [{"record": "case", "protocol": "vmstart2-memory-path-v2",
             "bytes": 1 << 20, "form": "vector", "mode": "shared"}]
    for rep in range(3):
        for iteration in range(35):
            rows.append({"record": "sample", "rep": rep, "iteration": iteration,
                         "seed": 1 + rep * 35 + iteration, "warmup": iteration < 3,
                         "wall_ms": 10000 if iteration < 3 else iteration - 2 + rep,
                         "gpu_ms": 0.5, "validated_elements": (1 << 20) // 16,
                         "validated_components": 4, "passed": True})
    rows.append({"record": "complete", "passed": True, "validated_dispatches": 105})
    return rows


class SummaryAcceptance(unittest.TestCase):
    def run_summary(self, rows):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "case.jsonl"
            path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
            return runner.summarize(path, 1 << 20, "vector", "shared")

    def test_warmups_excluded_and_full_sample_medians(self):
        summary = self.run_summary(valid_records())
        self.assertEqual(summary["validated_dispatches"], 105)
        self.assertEqual(summary["median_of_wall_medians_ms"], 17.5)
        self.assertEqual([r["samples"] for r in summary["repetitions"]], [32, 32, 32])
        self.assertAlmostEqual(summary["repetitions"][0]["wall_p95_ms"], 30.45)

    def test_missing_or_duplicate_dispatch_is_rejected(self):
        rows = valid_records()
        del rows[8]
        with self.assertRaises(ValueError):
            self.run_summary(rows)
        rows = valid_records()
        rows[8] = copy.deepcopy(rows[9])
        with self.assertRaises(ValueError):
            self.run_summary(rows)

    def test_failed_incomplete_stale_or_nonfinite_records_are_rejected(self):
        for key, value in [("passed", False), ("validated_components", 1),
                           ("validated_elements", 4), ("seed", 999),
                           ("warmup", False), ("wall_ms", float("nan")),
                           ("gpu_ms", float("inf"))]:
            with self.subTest(field=key):
                rows = valid_records()
                rows[1][key] = value
                with self.assertRaises(ValueError):
                    self.run_summary(rows)
        rows = valid_records()
        rows[-1]["passed"] = False
        with self.assertRaises(ValueError):
            self.run_summary(rows)

    def test_case_mismatch_or_command_error_is_rejected(self):
        rows = valid_records()
        rows[0]["mode"] = "private"
        with self.assertRaises(ValueError):
            self.run_summary(rows)
        rows = valid_records() + [{"record": "error", "phase": "readback"}]
        with self.assertRaises(ValueError):
            self.run_summary(rows)


class NativeValidation(unittest.TestCase):
    def test_all_components_and_nonfinite_values(self):
        compiler = shutil.which("c++") or shutil.which("g++") or shutil.which("clang++")
        if not compiler:
            self.skipTest("A C++ compiler is required for the portable validation check")
        source = r'''
#include "validation.h"
#include <cassert>
#include <limits>
int main() {
    float data[] = {.1001f, .2f, .3f, .4f, .1002f, .2f, .3f, .4f};
    assert(memory_path::validate(data, 2, 1).passed);
    assert(!memory_path::validate(data, 2, 2).passed); // Stale seed.
    data[7] = .5f;
    auto bad = memory_path::validate(data, 2, 1);
    assert(!bad.passed && bad.element == 1 && bad.component == 3);
    data[7] = .4f;
    for (float invalid : {std::numeric_limits<float>::quiet_NaN(),
                          std::numeric_limits<float>::infinity(),
                         -std::numeric_limits<float>::infinity()}) {
        data[1] = invalid;
        assert(!memory_path::validate(data, 2, 1).passed);
    }
    assert(!memory_path::validate(nullptr, 2, 1).passed);
    assert(!memory_path::validate(data, 0, 1).passed);
    float wrap[] = {.1f, .2f, .3f, .4f};
    assert(memory_path::validate(wrap, 1, 997).passed);
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "validation.cpp"
            binary = Path(tmp) / "validation"
            path.write_text(source)
            subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                            "-I", str(SOURCE), str(path), "-o", str(binary)],
                           check=True, capture_output=True, timeout=30)
            subprocess.run([str(binary)], check=True, capture_output=True, timeout=10)


if __name__ == "__main__":
    unittest.main()
