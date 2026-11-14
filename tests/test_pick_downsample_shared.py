#!/usr/bin/env python3
"""#341 fix (1): one size-aware downsample policy, shared by both solve paths.

Offline. Drives the real shipped polaris-align.sh with a stubbed polaris-extract so
the assertions run against the script we ship, not a copy of its logic.

Why this exists: polaris-align.sh pinned DOWNSAMPLE=4, a value chosen for an ~6000 px
camera frame, while the WebUI upload path passed no DOWNSAMPLE at all. A phone-
downscaled 1920x1280 upload was therefore decoded at 1/4 -> 480x320 -> single-digit
stars -> "search_exhausted", which reads like missing index files but is not.
polaris-autosolve.sh already had the size-aware rule; the two had drifted.

The fix lifts the rule into container/astro/ondisk/pick_downsample.sh, sourced by both.
These tests pin three things:
  * a small frame now resolves to ds=1 instead of 4 (the bug is gone);
  * an explicit DOWNSAMPLE is still honoured and pays no probe pass (captures unchanged);
  * the two scripts cannot drift, because neither carries its own copy of the thresholds.
"""

import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ALIGN = REPO / "container" / "astro" / "ondisk" / "polaris-align.sh"
AUTOSOLVE = REPO / "container" / "astro" / "ondisk" / "polaris-autosolve.sh"
HELPER = REPO / "container" / "astro" / "ondisk" / "pick_downsample.sh"

# Reports a chosen frame size, and records every downsample it was asked for.
EXTRACT_STUB = """#!/bin/sh
ds=4; prev=""
for a in "$@"; do
    [ "$prev" = "--downsample" ] && ds=$a
    prev=$a
done
echo "extract-called ds=$ds" >> "$EXTRACT_LOG"
if [ "$ds" = "8" ]; then
    # dimension probe only: report size, no stars needed
    echo "# full resolution $FAKE_W x $FAKE_H"
    exit 0
fi
echo "# full resolution $FAKE_W x $FAKE_H"
i=1
while [ "$i" -le "$FAKE_STARS" ]; do echo "$i $i 100"; i=$((i+1)); done
"""

SOLVE_STUB = """#!/bin/sh
echo '{"solved":false,"error":"stub"}'
exit 3
"""


class _Harness:
    def __init__(self, width, stars=200, height=None):
        self.dir = tempfile.mkdtemp(prefix="polaris-ds-")
        astro = Path(self.dir) / "astro"
        astro.mkdir()
        idx = Path(self.dir) / "idx"
        idx.mkdir()
        (idx / "index-4117.fits").write_text("")

        self.log = Path(self.dir) / "extract.log"
        self.log.write_text("")

        # Ship the real helper into the fake ASTRO dir: this asserts that align
        # finds and sources it by name, which is what install_astro.sh relies on.
        shutil.copy(HELPER, astro / "pick_downsample.sh")

        for name, body in (("polaris-extract", EXTRACT_STUB),
                           ("polaris-solve", SOLVE_STUB),
                           ("polaris-solve-independent", SOLVE_STUB),
                           ("polaris-solve-independent-search", SOLVE_STUB)):
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
            "EXTRACT_LOG": str(self.log),
            "FAKE_W": str(width),
            "FAKE_H": str(height or int(width * 2 // 3)),
            "FAKE_STARS": str(stars),
            "LAT": "", "LON": "", "FOCAL": "50", "SENSOR_MM": "36",
            "MOUNT_HINT": "0",
            "INDEPENDENT_BLIND_FALLBACK": "0",
            "STARVED_RETRY": "0",
        })
        self.env = env
        self.img = img

    def downsamples_used(self, extra_env=None):
        env = dict(self.env)
        if extra_env:
            env.update(extra_env)
        subprocess.run(["sh", str(ALIGN), str(self.img), "50"],
                       env=env, capture_output=True, text=True, timeout=120)
        return [ln.split("ds=")[1] for ln in self.log.read_text().splitlines()
                if ln.startswith("extract-called")]

    def cleanup(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class TestUploadPathIsSizeAware(unittest.TestCase):
    def test_small_frame_resolves_to_ds1(self):
        """The #341 frame: 1920x1280 must not be decoded at 1/4."""
        h = _Harness(width=1920)
        try:
            used = h.downsamples_used()
            self.assertIn("1", used, used)
            self.assertNotIn("4", [d for d in used if d != "8"], used)
        finally:
            h.cleanup()

    def test_medium_frame_resolves_to_ds2(self):
        h = _Harness(width=4000)
        try:
            used = h.downsamples_used()
            self.assertIn("2", [d for d in used if d != "8"], used)
        finally:
            h.cleanup()

    def test_large_frame_still_resolves_to_ds4(self):
        """A real capture must keep the behaviour that already worked."""
        h = _Harness(width=8192)
        try:
            used = h.downsamples_used()
            self.assertIn("4", [d for d in used if d != "8"], used)
        finally:
            h.cleanup()

    def test_explicit_downsample_is_honoured_without_a_probe(self):
        """autosolve passes DOWNSAMPLE on every capture call; that path must not
        pay for the dimension probe."""
        h = _Harness(width=8192)
        try:
            used = h.downsamples_used({"DOWNSAMPLE": "4"})
            self.assertNotIn("8", used, f"probe ran despite explicit DOWNSAMPLE: {used}")
            self.assertEqual(used, ["4"], used)
        finally:
            h.cleanup()


class TestPolicyCannotDrift(unittest.TestCase):
    """Both scripts must read the thresholds from one place."""

    def test_helper_exists_and_is_sourced_by_both(self):
        self.assertTrue(HELPER.is_file(), "pick_downsample.sh missing")
        for script in (ALIGN, AUTOSOLVE):
            self.assertIn('pick_downsample.sh', script.read_text(),
                          f"{script.name} does not source the shared helper")

    def test_neither_script_carries_its_own_thresholds(self):
        """A second copy of 6000/3000 is how the two drifted in the first place."""
        for script in (ALIGN, AUTOSOLVE):
            body = script.read_text()
            self.assertNotIn("-ge 6000", body,
                             f"{script.name} still hard-codes its own downsample rule")

    def test_align_no_longer_pins_four_as_default(self):
        body = ALIGN.read_text()
        self.assertNotIn("DOWNSAMPLE=${DOWNSAMPLE:-4}", body,
                         "align must resolve DOWNSAMPLE from frame size, not pin 4")

    def test_helper_is_safe_under_set_u(self):
        """polaris-autosolve.sh runs `set -u`; an unset var there aborts the loop."""
        body = HELPER.read_text()
        self.assertIn("${1:-}", body)
        self.assertIn("${FRAME_DIMS_FILE:-}", body)


class TestHelperDirectly(unittest.TestCase):
    """The helper's own contract, including the unknown-size fallback."""

    def _run(self, extract_body, dims_file=None):
        d = tempfile.mkdtemp(prefix="pds-")
        try:
            astro = Path(d) / "astro"
            astro.mkdir()
            ext = astro / "polaris-extract"
            ext.write_text(extract_body)
            ext.chmod(ext.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP)
            img = Path(d) / "f.jpg"
            img.write_text("x")
            env = dict(os.environ, ASTRO=str(astro),
                       **({"FRAME_DIMS_FILE": dims_file} if dims_file else {}))
            r = subprocess.run(
                ["sh", "-c", f'. "{HELPER}"; pick_downsample "{img}"'],
                env=env, capture_output=True, text=True, timeout=30)
            return r.stdout.strip(), r.returncode
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_unknown_size_falls_back_to_four(self):
        """Guessing small would decode a big frame at full res and stall capture."""
        out, rc = self._run("#!/bin/sh\nexit 0\n")
        self.assertEqual(out, "4", out)
        self.assertEqual(rc, 0)

    def test_records_dims_when_asked(self):
        d = tempfile.mkdtemp(prefix="pds-dims-")
        try:
            df = str(Path(d) / "dims")
            out, _ = self._run("#!/bin/sh\necho '# full resolution 8192 x 6144'\n", df)
            self.assertEqual(out, "4", out)
            self.assertEqual(Path(df).read_text(), "8192 x 6144")
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
