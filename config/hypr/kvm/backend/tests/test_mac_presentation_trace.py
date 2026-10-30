"""Portable report tests, not native macOS/GPU validation."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "macos/performance/presentation-trace"
spec = importlib.util.spec_from_file_location("presentation_capture", KIT / "collect.py")
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


def sample(t, counters, cpu=None):
    return {"counter_time_s": t, "cpu_time_s": t, "counters": counters,
            "cpu_returncode": 0, "processes": cpu or {}, "counter_read_s": .01, "cpu_read_s": .01}


class ParseAndInterpret(unittest.TestCase):
    def test_unknown_or_denied_counters_are_not_zero(self):
        result = capture.parse_counters("debug.nvaccel_iop_flips: 17\n"
                                        "debug.other: 4\nsysctl: unknown oid 'missing'\n")
        self.assertEqual(result, {"debug.nvaccel_iop_flips": 17})
        with self.assertRaises(ValueError):
            capture.parse_counters("debug.nvaccel_iop_flips: 1\ndebug.nvaccel_iop_flips: 2")
        rows = [sample(10, result), sample(12, {})]
        summary = capture.summarize(rows)
        self.assertEqual(summary["counters"]["debug.nvaccel_iop_flips"]["status"], "unavailable-or-gaps")
        self.assertNotIn("delta", summary["counters"]["debug.nvaccel_iop_flips"])

    def test_resets_and_lifetime_max_are_not_phase_rates(self):
        key = "debug.nvaccel_iop_flips"
        maximum = "debug.nvaccel_surface_gpu_wait_max_us"
        rows = [sample(t, {key: n, maximum: 50000}) for t, n in ((1, 100), (2, 5), (3, 101))]
        result = capture.summarize(rows)
        self.assertEqual(result["counters"][key]["status"], "counter-reset-or-wrap")
        self.assertNotIn("events_per_second", result["counters"][key])
        self.assertNotIn("events_per_second", result["gauges"][maximum])
        self.assertEqual(result["gauges"][maximum]["first"], 50000)
        with self.assertRaises(ValueError):
            capture.summarize([sample(2, {}), sample(1, {})])

    def test_multimonitor_counts_remain_separate_events(self):
        names = ["debug.nvaccel_iop_ok", "debug.nvaccel_iop_ok_h0", "debug.nvaccel_iop_ok_h1",
                 "debug.nvaccel_iop_flips", "debug.nvaccel_iop_async_flips"]
        start = dict.fromkeys(names, 100)
        end = dict(zip(names, (340, 220, 220, 340, 340)))
        result = capture.summarize([sample(1, start), sample(3, end)])
        self.assertEqual(result["counters"][names[0]]["events_per_second"], 120)
        self.assertEqual(result["counters"][names[1]]["events_per_second"], 60)
        self.assertNotIn("fps", result)
        self.assertNotIn("total_frames", result)

    def test_cpu_time_is_interval_based_and_handles_missing_or_restarted_process(self):
        first = capture.parse_processes("10 01:02.50 /System/Library/WindowServer\n"
                                        "11 00:00.10 /Applications/Google Chrome Helper (GPU)\n"
                                        "12 00:10.00 /sensitive/unrelated/path\n")
        self.assertEqual(set(first), {"10", "11"})
        self.assertEqual(capture.cpu_seconds("1-01:02:03.25"), 90123.25)
        with self.assertRaises(ValueError):
            capture.cpu_seconds("00:nan")
        second = {"10": {"name": "WindowServer", "cpu_s": 63.5},
                  "11": {"name": "Google Chrome Helper (GPU)", "cpu_s": .01}}
        result = capture.summarize([sample(10, {}, first), sample(12, {}, second), sample(13, {})])
        self.assertEqual(len(result["process_cpu"]), 1)
        self.assertEqual(result["process_cpu"][0]["one_core_percent"], 50)
        self.assertEqual(result["process_cpu"][0]["observed_s"], 2)

    def test_read_only_snapshot_keeps_partial_multi_key_output(self):
        calls = []

        def run(argv):
            calls.append(argv)
            if argv[0].endswith("sysctl"):
                return {"midpoint_s": 1, "elapsed_s": .01, "returncode": 1,
                        "stderr": "unknown optional key", "stdout": "debug.nvaccel_iop_flips: 12"}
            return {"midpoint_s": 1.1, "elapsed_s": .01, "returncode": 0, "stderr": "",
                    "stdout": "5 00:02.50 /System/WindowServer"}

        with patch.object(capture, "run", side_effect=run):
            result = capture.snapshot()
        self.assertEqual(result["counters"]["debug.nvaccel_iop_flips"], 12)
        self.assertEqual(result["counter_returncode"], 1)
        self.assertTrue(all(repr(arg).find("=") == -1 for arg in calls[0]))
        self.assertNotIn("-w", calls[0])
        self.assertNotIn("debug.nvaccel_crc", calls[0])
        self.assertEqual(result["processes"]["5"]["name"], "WindowServer")


class Preservation(unittest.TestCase):
    def test_errors_are_not_verified_unchanged(self):
        value = {"driver": {"error": "permission denied"}}
        self.assertFalse(capture.unchanged(value, value))
        self.assertFalse(capture.unchanged({}, {}))
        self.assertFalse(capture.unchanged({"a": {"sha256": "1"}}, {"a": {"sha256": "2"}}))

    def test_lifecycle_preserves_completed_and_failed_capture(self):
        for fail in (False, True):
            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "Desktop").mkdir()
                kit = root / "kit"
                kit.mkdir()
                driver = root / "driver"
                driver.write_bytes(b"working driver")
                config = root / "config"
                config.write_text("working config\n")
                (kit / "driver-identity.json").write_text(json.dumps({str(driver): capture.digest(driver)}))
                (kit / "README.txt").write_text("collector provenance\n")
                original = driver.read_bytes(), config.read_bytes()

                def phase(output, label, duration):
                    rows = [sample(1, dict.fromkeys(capture.COUNTERS, 5)),
                            sample(21, dict.fromkeys(capture.COUNTERS, 25))]
                    (output / (label + ".jsonl")).write_text("\n".join(map(json.dumps, rows)))
                    if fail:
                        raise RuntimeError("simulated interruption after raw data")
                    return capture.summarize(rows)

                fake_run = {"returncode": 0, "stdout": "inventory", "stderr": "", "elapsed_s": .01, "midpoint_s": 1}
                with patch.object(capture, "HERE", kit), patch.object(capture, "CONFIG", config), \
                        patch.object(capture.sys, "platform", "darwin"), \
                        patch.object(capture.os, "geteuid", return_value=1000), \
                        patch.object(capture.os, "umask"), \
                        patch.object(capture.Path, "home", return_value=root), \
                        patch.object(capture.sys, "argv", ["collect.py", "--phase", "ufo-6"]), \
                        patch.object(capture.time, "sleep"), patch.object(capture, "run", return_value=fake_run), \
                        patch.object(capture, "record_phase", side_effect=phase), contextlib.redirect_stdout(io.StringIO()):
                    result = capture.main()
                self.assertEqual(result, 2 if fail else 0)
                self.assertEqual((driver.read_bytes(), config.read_bytes()), original)
                archive = next((root / "Desktop").glob("*.zip"))
                with zipfile.ZipFile(archive) as z:
                    self.assertIsNone(z.testzip())
                    prefix = z.namelist()[0].split("/")[0] + "/"
                    status = json.loads(z.read(prefix + "status.json"))
                    self.assertTrue(status["driver_hashes_unchanged"])
                    self.assertTrue(status["config_hash_unchanged"])
                    self.assertEqual(status["state"], "capture-incomplete" if fail else "capture-complete")
                    hashes = json.loads(z.read(prefix + "SHA256SUMS.json"))
                    for name, digest in hashes.items():
                        self.assertEqual(capture.hashlib.sha256(z.read(prefix + name)).hexdigest(), digest)
                    self.assertIn("ufo-6.jsonl", hashes)

    def test_linux_launch_refused_before_guest_collection(self):
        if sys.platform == "darwin":
            self.skipTest("Linux guard")
        result = subprocess.run(["bash", str(KIT / "Capture-Presentation.command")],
                                text=True, capture_output=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Run inside", result.stdout)


if __name__ == "__main__":
    unittest.main()
