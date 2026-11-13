#!/usr/bin/env python3
"""#341: a starved extraction on a small frame must retry once at downsample 1.

Offline. Drives the real shipped polaris-align.sh with stubbed polaris-extract /
polaris-solve binaries, so it asserts on the script we actually ship rather than
on a copy of its logic. No device, no network.

Why this exists: DOWNSAMPLE defaults to 4 and the WebUI upload path passes no
DOWNSAMPLE at all, so a phone-downscaled upload is decoded at 1/4 whatever its
real size. Measured on-device with one 1920x1280 JPEG and the shipped indexes:
ds=4 sigma=5 yields 6 stars and the solver returns "search_exhausted", while
ds=1 yields ~300 stars and solves in ~2 s against index-4117. The failure reads
like missing index files but is not, which is exactly how #341 was first
misdiagnosed -- hence a test that pins the retry behaviour itself.
"""

from pathlib import Path
import os
import stat
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ALIGN = ROOT / "container" / "astro" / "ondisk" / "polaris-align.sh"

EXTRACT_STUB = """#!/bin/sh
ds=4; prev=""
for a in "$@"; do
    [ "$prev" = "--downsample" ] && ds=$a
    prev=$a
done
echo "extract-called ds=$ds" >> "$EXTRACT_LOG"
echo "# full resolution $FAKE_W x $FAKE_H"
n=$FAKE_STARS_DS4
[ "$ds" = "1" ] && n=$FAKE_STARS_DS1
i=1
while [ "$i" -le "$n" ]; do echo "$i $i 100"; i=$((i+1)); done
"""

SOLVE_STUB = """#!/bin/sh
echo '{"solved":false,"error":"stub"}'
exit 3
"""


class _Harness:
    """A fake ASTRO dir whose extractor reports whatever the test asks for."""

    def __init__(self, width, stars_ds4, stars_ds1=300):
        self.dir = tempfile.mkdtemp(prefix="polaris-align-")
        astro = Path(self.dir) / "astro"
        astro.mkdir()
        idx = Path(self.dir) / "idx"
        idx.mkdir()
        (idx / "index-4117.fits").write_text("")
        self.log = Path(self.dir) / "extract.log"
        self.log.write_text("")
        img = Path(self.dir) / "img.jpg"
        img.write_text("x")

        for name, body in (("polaris-extract", EXTRACT_STUB),
                           ("polaris-solve", SOLVE_STUB),
                           ("polaris-solve-independent", SOLVE_STUB),
                           ("polaris-solve-independent-search", SOLVE_STUB)):
            p = astro / name
            p.write_text(body)
            p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP)

        env = dict(os.environ)
        env.update({
            "ASTRO": str(astro),
            "INDEXES": str(idx),
            "SOLVE_LOG": str(Path(self.dir) / "solve.log"),
            "EXTRACT_LOG": str(self.log),
            "FAKE_W": str(width),
            "FAKE_H": "1280",
            "FAKE_STARS_DS4": str(stars_ds4),
            "FAKE_STARS_DS1": str(stars_ds1),
            # No mount, no blind all-sky fallback: the retry decision must be
            # observable without a device or an unbounded search.
            "MOUNT_HINT": "0",
            "INDEPENDENT_BLIND_FALLBACK": "0",
        })
        self.env = env
        self.img = img

    def run(self, extra_env=None):
        env = dict(self.env)
        if extra_env:
            env.update(extra_env)
        subprocess.run(
            ["sh", str(ALIGN), str(self.img), "50"],
            env=env, capture_output=True, text=True, timeout=120,
        )
        return [ln.strip() for ln in self.log.read_text().splitlines() if ln.strip()]

    def downsamples_used(self, extra_env=None):
        return [ln.split("ds=")[1]
                for ln in self.run(extra_env) if ln.startswith("extract-called")]

    def cleanup(self):
        subprocess.run(["rm", "-rf", self.dir], check=False)


class StarvedRetryTest(unittest.TestCase):
    def test_script_exists(self):
        self.assertTrue(ALIGN.is_file(), f"missing {ALIGN}")

    def test_starved_small_frame_retries_at_downsample_1(self):
        """The #341 case: 6 stars at ds=4 on a 1920 px frame must re-extract."""
        h = _Harness(width=1920, stars_ds4=6)
        try:
            self.assertEqual(h.downsamples_used(), ["4", "1"])
        finally:
            h.cleanup()

    def test_healthy_full_size_frame_is_not_re_extracted(self):
        """A normal capture must not pay for a second decode pass."""
        h = _Harness(width=6000, stars_ds4=150)
        try:
            self.assertEqual(h.downsamples_used(), ["4"])
        finally:
            h.cleanup()

    def test_enough_stars_does_not_retry(self):
        """Starvation is the trigger, not small size alone."""
        h = _Harness(width=1920, stars_ds4=30)
        try:
            self.assertEqual(h.downsamples_used(), ["4"])
        finally:
            h.cleanup()

    def test_wide_frame_does_not_retry(self):
        """ds=4 is the right choice for a large frame even if stars are few."""
        h = _Harness(width=4000, stars_ds4=6)
        try:
            self.assertEqual(h.downsamples_used(), ["4"])
        finally:
            h.cleanup()

    def test_already_downsample_1_does_not_retry(self):
        """There is nothing below 1; the guard must not loop or re-run."""
        h = _Harness(width=1920, stars_ds4=6)
        try:
            self.assertEqual(h.downsamples_used({"DOWNSAMPLE": "1"}), ["1"])
        finally:
            h.cleanup()

    def test_escape_hatch_disables_the_retry(self):
        """Qualification runs must be able to pin the old behaviour."""
        h = _Harness(width=1920, stars_ds4=6)
        try:
            self.assertEqual(h.downsamples_used({"STARVED_RETRY": "0"}), ["4"])
        finally:
            h.cleanup()


if __name__ == "__main__":
    unittest.main(verbosity=2)
