"""#389 -- guards for the widget-enumeration benchmark harness.

Offline-safe: no camera, no network. These tests exist because two real
measurement errors were made on the way to the #389 numbers and both were only
caught by hand afterwards. Encoding them here means the next A/B cannot silently
repeat either one.

1. The settings-format trap (R7). libgphoto2's verify_settings() requires a flat
   ``section=key=value`` line (two '=' characters) and *unlinks* the file when the
   format is wrong. INI syntax was written once, the file vanished mid-session,
   and the A/B measured the default twice while reporting a 45% improvement.

2. Misreading a failed session as an efficient one (R5). A refused OpenSession
   (PTP_RC_DeviceBusy 0x02fa is a legitimate post-capture state) yields a tiny op
   count and a huge wall clock. Summarised naively that looks like the fastest
   run of the set.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

import importlib.util

SPEC = importlib.util.spec_from_file_location(
    "bench_widget_enumeration", REPO / "tools" / "bench-widget-enumeration.py"
)
bwe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bwe)


class SettingsFormat(unittest.TestCase):
    """The exact trap that invalidated the first A/B."""

    def test_rendered_line_is_flat_and_has_two_equals(self):
        body = bwe.render_settings(30)
        self.assertEqual(body, "ptp2=cachetime=30\n")
        self.assertEqual(body.count("="), 2, "verify_settings() requires two '=' per line")

    def test_ini_section_is_rejected(self):
        ini = "[ptp2]\ncachetime=30\n"
        problems = bwe.validate_settings_body(ini)
        self.assertTrue(problems, "INI syntax must be reported as invalid")
        self.assertTrue(any("section header" in p for p in problems), problems)

    def test_single_equals_line_is_rejected(self):
        problems = bwe.validate_settings_body("cachetime=30\n")
        self.assertTrue(problems, "one '=' is not the accepted form")

    def test_empty_body_is_rejected(self):
        self.assertTrue(bwe.validate_settings_body(""))

    def test_valid_body_reports_no_problems(self):
        self.assertEqual(bwe.validate_settings_body(bwe.render_settings(2)), [])

    def test_nonpositive_cachetime_is_refused(self):
        for bad in (0, -1, "30"):
            with self.assertRaises(ValueError):
                bwe.render_settings(bad)


class SettingsSurviveOnDisk(unittest.TestCase):
    """verify_settings() unlinks malformed files, so confirm persistence."""

    def test_write_round_trips_and_survives(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = bwe.write_settings(tmp, 30)
            self.assertTrue(os.path.exists(path), "file must survive the write")
            self.assertEqual(Path(path).read_text(), "ptp2=cachetime=30\n")
            self.assertEqual(path, os.path.join(tmp, "gphoto", "settings"))

    def test_write_refuses_invalid_value_without_touching_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                bwe.write_settings(tmp, 0)
            self.assertFalse(os.path.exists(bwe.settings_path(tmp)))


class FailedSessionIsNeverReportedAsFast(unittest.TestCase):
    """R5: low op count + high wall clock means the session never completed."""

    def test_device_busy_marker_is_unreportable(self):
        out = ("Pentax init stage OpenSession attempt 1, session 1, returned 0x02fa.\n"
               "Pentax state is busy or unknown; refusing session close and USB reset.\n")
        ops = {"0x1014": 0, "0x1015": 0, "0x900f": 0, "0x1001": 0, "0x1007": 0}
        ok, reasons = bwe.classify_run(0, out, ops, 10, 400.0)
        self.assertFalse(ok, "a busy body must never be reported as a measurement")
        self.assertTrue(any("0x02fa" in r for r in reasons), reasons)

    def test_timeout_marker_is_unreportable(self):
        ok, reasons = bwe.classify_run(124, "Timeout", {"0x1014": 5}, 10, 180.0)
        self.assertFalse(ok)
        self.assertTrue(any("Timeout" in r for r in reasons), reasons)

    def test_nonzero_exit_is_unreportable(self):
        ok, _ = bwe.classify_run(1, "PTP I/O problem", {"0x1014": 263}, 10, 49.66)
        self.assertFalse(ok)

    def test_suspiciously_low_op_count_is_flagged_not_praised(self):
        # No explicit marker, clean exit, but 2 descriptor fetches for a 10-widget
        # walk in 300 s is not efficiency -- it is an incomplete walk.
        ok, reasons = bwe.classify_run(0, "nothing notable", {"0x1014": 2}, 10, 300.0)
        self.assertFalse(ok, "must be flagged as suspect")
        self.assertTrue(any("incomplete session" in r for r in reasons), reasons)

    def test_healthy_run_is_reportable(self):
        ops = {"0x1014": 263, "0x1015": 180, "0x900f": 50, "0x1001": 2, "0x1007": 3}
        ok, reasons = bwe.classify_run(0, "GetDevicePropDesc ok", ops, 10, 49.66)
        self.assertTrue(ok, reasons)


class OpCounting(unittest.TestCase):
    def test_counts_by_name_and_hex_without_double_counting(self):
        # One line naming the opcode and its hex code must count once, not twice.
        text = "ptp.c:4901 GetDevicePropDesc (0x1014) propcode=d01e\n"
        counts = bwe.count_ops(text)
        self.assertEqual(counts["0x1014"], 1, "name and hex on one line must not sum")

    def test_counts_multiple_occurrences(self):
        text = "\n".join(["GetDevicePropDesc"] * 30)
        self.assertEqual(bwe.count_ops(text)["0x1014"], 30)

    def test_absent_opcode_is_zero(self):
        self.assertEqual(bwe.count_ops("nothing here")["0x900f"], 0)


class CliContract(unittest.TestCase):
    """The tool must be usable on a machine with no camera attached."""

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(REPO / "tools" / "bench-widget-enumeration.py"), *args],
            capture_output=True, text=True,
        )

    def test_dry_run_emits_valid_json_and_no_problems(self):
        proc = self._run("--dry-run", "--cachetime", "2,30")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        records = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(records), 2)
        for record in records:
            self.assertEqual(record["kind"], "dry-run")
            self.assertEqual(record["format_problems"], [])
        self.assertEqual(records[1]["settings_body"], "ptp2=cachetime=30")

    def test_missing_gphoto2_fails_cleanly(self):
        env = dict(os.environ, PATH="/nonexistent")
        proc = subprocess.run(
            [sys.executable, str(REPO / "tools" / "bench-widget-enumeration.py")],
            capture_output=True, text=True, env=env,
        )
        self.assertEqual(proc.returncode, 3)
        self.assertIn("gphoto2", proc.stderr.lower())

    def test_bad_cachetime_is_a_usage_error(self):
        proc = self._run("--cachetime", "abc")
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
