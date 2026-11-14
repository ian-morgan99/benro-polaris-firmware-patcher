#!/usr/bin/env python3
"""#342: per-stage timings must be opt-in and must not disturb any consumer.

Offline. Two halves:

1. The shipped polaris-align.sh is driven with a stub polaris-solve whose result
   line carries the new `timings_ms` / `peak_rss_kb` fields, exactly as the
   instrumented binary emits them. align's own parser must still classify the
   line as SOLVED and pass it through on stdout unchanged. This is the forward
   compatibility guard: if a future change makes align choke on trailing JSON
   fields, this fails here rather than on a mount.

2. The C source is asserted to keep timings OFF by default and to time with a
   monotonic clock. Both are contract points, not style:
     - stdout is the solver's only output channel and callers parse it
       (polaris-align.sh documents this at its diagnostics section);
     - the Polaris has no RTC and syncs over NTP, so a wall-clock delta can read
       negative or minutes-long across an NTP step.

Why this exists: #342 needs to know whether solve time is spent reading stars,
loading indexes, or searching quads. polaris-solve previously timed only
solver_run(), with gettimeofday(). Verified on host against the ten shipped
indexes and the real #341 upload (sha256 8b45fc47… is not this image; see
SOLVE_ARGS): blind solve = 97.2 ms search, 3.5 ms index load, 0.1 ms star read,
peak RSS 14.9 MB — so index I/O is not the bottleneck and #343's pruning should
not be assumed to buy wall-clock time.
"""

import json
import os
import re
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ALIGN = REPO / "container" / "astro" / "ondisk" / "polaris-align.sh"
SOLVE_C = REPO / "container" / "astro" / "polaris-solve.c"

# Exactly what the instrumented binary emits, in field order.
SOLVED_WITH_TIMINGS = (
    '{"solved":true,"ra_deg":300.433277,"dec_deg":40.414189,"roll_deg":87.9041,'
    '"pixscale_arcsec":48.931613,"field_w_deg":26.0969,"field_h_deg":17.3979,'
    '"parity":"normal","cd":[-0.00036656999,0.0136066016,0.0135607341,0.00062765244],'
    '"index":"index-4114.fits","logodds":55.905,"nmatch":15,"nfield":100,'
    '"solve_seconds":0.097,"timings_ms":{"star_read":0.1,"index_load":3.5,'
    '"solve":97.2},"peak_rss_kb":14936}'
)

UNSOLVED_WITH_TIMINGS = (
    '{"solved":false,"nfield":100,"solve_seconds":16.625,'
    '"timings_ms":{"star_read":0.0,"index_load":0.4,"solve":16625.0},'
    '"peak_rss_kb":12536}'
)

EXTRACT_STUB = """#!/bin/sh
echo "# full resolution 1920 x 1280"
i=1
while [ "$i" -le 100 ]; do echo "$i $i 100"; i=$((i+1)); done
"""


class _Harness:
    """Fake ASTRO dir whose solver prints a canned result line."""

    def __init__(self, solve_body):
        self.dir = tempfile.mkdtemp(prefix="polaris-timings-")
        astro = Path(self.dir) / "astro"
        astro.mkdir()
        idx = Path(self.dir) / "idx"
        idx.mkdir()
        (idx / "index-4117.fits").write_text("")

        for name, body in (("polaris-extract", EXTRACT_STUB),
                           ("polaris-solve", solve_body),
                           ("polaris-solve-independent", solve_body),
                           ("polaris-solve-independent-search", solve_body)):
            p = astro / name
            p.write_text(body)
            p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP)

        img = Path(self.dir) / "img.jpg"
        img.write_text("x")

        env = dict(os.environ)
        env.update({
            "ASTRO": str(astro),
            "INDEXES": str(idx),
            "SOLVE_LOG": str(Path(self.dir) / "solve.log"),
            "LAT": "", "LON": "", "FOCAL": "", "SENSOR_MM": "36",
            "MOUNT_HINT": "0",
            "INDEPENDENT_BLIND_FALLBACK": "0",
            "STARVED_RETRY": "0",
        })
        self.env = env
        self.img = img

    def run(self):
        return subprocess.run(
            ["sh", str(ALIGN), str(self.img), "50"],
            env=self.env, capture_output=True, text=True, timeout=120,
        )

    def cleanup(self):
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)


def _stub(body):
    return "#!/bin/sh\ncat <<'JSONEOF'\n%s\nJSONEOF\nexit %s\n" % (
        body, 0 if '"solved":true' in body else 3)


class TestAlignToleratesTimings(unittest.TestCase):
    """The real shipped consumer must accept the new trailing fields."""

    def test_solved_line_with_timings_is_still_recognised(self):
        h = _Harness(_stub(SOLVED_WITH_TIMINGS))
        try:
            r = h.run()
            self.assertIn('"solved":true', r.stdout, r.stderr)
        finally:
            h.cleanup()

    def test_solved_line_with_timings_passes_through_verbatim(self):
        """align must not drop or reorder the timing fields it does not use."""
        h = _Harness(_stub(SOLVED_WITH_TIMINGS))
        try:
            r = h.run()
            line = [ln for ln in r.stdout.splitlines() if '"solved":true' in ln]
            self.assertTrue(line, r.stdout + r.stderr)
            d = json.loads(line[0])
            self.assertEqual(d["ra_deg"], 300.433277)
            self.assertEqual(d["dec_deg"], 40.414189)
            self.assertIn("timings_ms", d, "timings were stripped by align")
            self.assertEqual(d["timings_ms"]["solve"], 97.2)
            self.assertEqual(d["peak_rss_kb"], 14936)
        finally:
            h.cleanup()

    def test_unsolved_line_with_timings_is_not_misclassified(self):
        """A slow no-match must not be read as a timeout by the #321 classifier."""
        h = _Harness(_stub(UNSOLVED_WITH_TIMINGS))
        try:
            r = h.run()
            log = Path(h.env["SOLVE_LOG"])
            text = log.read_text() if log.exists() else ""
            self.assertNotIn("solve TIMEOUT", text, text)
        finally:
            h.cleanup()


class TestSolverSourceContract(unittest.TestCase):
    """Timings stay opt-in and monotonic."""

    @classmethod
    def setUpClass(cls):
        cls.src = SOLVE_C.read_text()

    def test_timings_flag_is_opt_in(self):
        self.assertIn('"--timings"', self.src)
        self.assertRegex(self.src, r"static\s+int\s+g_timings\s*=\s*0",
                         "timings must default OFF: stdout is a parsed contract")

    def test_default_output_carries_no_timing_fields(self):
        """The tail helper must emit nothing when the flag is off."""
        m = re.search(r"static void timings_tail\(.*?\n\}", self.src, re.S)
        self.assertTrue(m, "timings_tail() not found")
        body = m.group(0)
        # Match the guard literally rather than by regex: the NUL byte makes
        # backslash-escaping here more confusing than it is worth.
        normalised = " ".join(body.split())
        self.assertIn("if (!g_timings) { buf[0] = '\\0'; return; }", normalised,
                      "timings_tail must emit an empty string when disabled")

    def test_uses_monotonic_clock_not_wall_clock(self):
        """The Polaris has no RTC; an NTP step would corrupt a gettimeofday delta."""
        m = re.search(r"static double now_seconds\(void\)\s*\{(.*?)\}", self.src, re.S)
        self.assertTrue(m, "now_seconds() not found")
        body = m.group(1)
        self.assertIn("CLOCK_MONOTONIC", body)
        self.assertNotIn("gettimeofday", body)

    def test_peak_rss_reported(self):
        """#342 asks for RAM characteristics; index loading is the memory question."""
        self.assertIn("getrusage", self.src)
        self.assertIn("ru_maxrss", self.src)

    def test_both_result_paths_emit_the_tail(self):
        """Solved and unsolved lines must not drift apart."""
        tail_uses = self.src.count("dt, tail") + self.src.count("tail)")
        self.assertGreaterEqual(tail_uses, 2,
                                "both printf result lines must include the tail")


if __name__ == "__main__":
    unittest.main()
