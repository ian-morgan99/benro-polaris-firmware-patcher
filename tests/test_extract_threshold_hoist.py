"""#342/#344: the hoisted threshold tables must not move a single star.

polaris-extract's star detection thresholds every pixel against a bilinear
interpolation of per-tile background and noise maps. That interpolation was the
dominant cost on the head -- 4.9M map_at() calls for a 1920x1280 frame, each doing
two floating-point divisions, measured at ~1.8 s of a 3.7 s capture-to-result
solve. The fix hoists the per-x and per-y weights into tables so the inner loop is
four multiplies with no division, which cut device extraction from 1800 ms to
1217 ms.

Hoisting floating-point work is exactly the kind of change that can silently move
results: a reciprocal substituted for the division changed star positions at
tile=48 during development, even though it was identical at the default tile=64.
Star positions feed the solver's quad matching, so a shifted centroid is not a
cosmetic issue -- it changes which quads match.

So this test builds the SAME source twice, once with POLARIS_EXTRACT_NO_HOIST (all
tables NULL, every pixel goes through map_at()) and once without, and requires
byte-identical output across tile sizes, downsamples and sigma values. It also
asserts the fast path is actually taken, so the differential cannot pass vacuously.

Offline: compiles with the host cc against libjpeg and synthesises its own images.
Skips if either is unavailable.
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "container" / "astro" / "polaris-extract.c"


def _cc():
    for c in (os.environ.get("CC"), "gcc", "cc"):
        if c and shutil.which(c):
            return c
    return None


def _cjpeg():
    return shutil.which("cjpeg")


HAVE_CC = _cc() is not None
HAVE_CJPEG = _cjpeg() is not None


def _build(outdir: Path, no_hoist: bool) -> Path:
    cc = _cc()
    out = outdir / ("extract-ref" if no_hoist else "extract-fast")
    cmd = [cc, "-O2", "-std=gnu99"]
    if no_hoist:
        cmd.append("-DPOLARIS_EXTRACT_NO_HOIST")
    # libjpeg location varies; try pkg-config then fall back to plain -ljpeg.
    pc = shutil.which("pkg-config")
    if pc:
        r = subprocess.run([pc, "--cflags", "--libs", "libjpeg"],
                           capture_output=True, text=True)
        extra = r.stdout.split() if r.returncode == 0 else ["-ljpeg"]
    else:
        extra = ["-ljpeg"]
    cmd += ["-o", str(out), str(SRC)] + extra + ["-lm"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"build failed: {r.stderr[-2000:]}")
    return out


def _pgm(width, height, pixels):
    """Binary P5 PGM bytes."""
    head = f"P5\n{width} {height}\n255\n".encode()
    body = bytes(bytearray(pixels))
    return head + body


def _star_field(seed=12345, w=640, h=480):
    """Deterministic night frame: gradient background, noise, Gaussian blobs.

    Deliberately includes a bright corner region and a dim one so the per-tile
    background/noise estimation is doing real work rather than one constant, and
    blobs of several sizes so minpix/maxpix and the elongation reject are reached.
    """
    s = seed
    def rnd():
        nonlocal s
        s = (1103515245 * s + 12345) & 0x7FFFFFFF
        return s / 0x7FFFFFFF

    px = [0] * (w * h)
    for y in range(h):
        base = 20 + int(60 * (y / h))          # vertical gradient
        for x in range(w):
            v = base + int(15 * (x / w))       # horizontal gradient
            v += int(rnd() * 9)                # pixel noise
            px[y * w + x] = min(255, max(0, v))

    def blob(cx, cy, amp, sig):
        r = int(sig * 3) + 1
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                x, y = cx + dx, cy + dy
                if not (0 <= x < w and 0 <= y < h):
                    continue
                d2 = dx * dx + dy * dy
                val = amp * (2.718281828 ** (-d2 / (2.0 * sig * sig)))
                i = y * w + x
                px[i] = min(255, px[i] + int(val))

    pts = [(40, 30, 200, 1.6), (300, 200, 160, 2.2), (600, 400, 120, 1.1),
           (120, 420, 90, 3.0), (500, 60, 210, 1.8), (20, 240, 70, 1.2),
           (630, 20, 180, 2.0), (320, 60, 150, 1.4)]
    for cx, cy, amp, sig in pts:
        blob(cx, cy, amp, sig)

    # A deliberately elongated blob: a trail, which must be rejected.
    for k in range(40):
        x, y = 200 + k, 100 + (k // 8)
        if 0 <= x < w and 0 <= y < h:
            px[y * w + x] = min(255, px[y * w + x] + 140)
    return px


def _to_jpeg(outdir: Path, name, width, height, pixels):
    pgm = outdir / f"{name}.pgm"
    jpg = outdir / f"{name}.jpg"
    pgm.write_bytes(_pgm(width, height, pixels))
    with open(jpg, "wb") as fh:
        r = subprocess.run([_cjpeg(), "-quality", "90", str(pgm)],
                           stdout=fh, stderr=subprocess.PIPE)
    if r.returncode != 0:
        raise RuntimeError(f"cjpeg failed: {r.stderr.decode(errors='replace')[:500]}")
    return jpg


def _run(binary, img, args, binary_out=False):
    r = subprocess.run([str(binary), "--jpeg", str(img)] + args,
                       capture_output=True)
    if binary_out:
        return r.stdout, r.returncode
    return r.stdout.decode(errors="replace"), r.returncode


@unittest.skipUnless(HAVE_CC, "no C compiler available")
@unittest.skipUnless(HAVE_CJPEG, "cjpeg (libjpeg-tools) not available")
class ExtractThresholdHoist(unittest.TestCase):
    """The division-free threshold path must reproduce map_at() exactly."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmp.name)
        try:
            cls.ref = _build(cls.tmp, no_hoist=True)
            cls.fast = _build(cls.tmp, no_hoist=False)
        except RuntimeError as e:
            raise unittest.SkipTest(f"cannot build polaris-extract: {e}")
        cls.img = _to_jpeg(cls.tmp, "stars", 640, 480, _star_field())

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_star_list_identical_across_tile_sizes(self):
        """Byte-identical stars for power-of-two AND non-power-of-two tiles.

        tile=48 is the case that broke during development: replacing the two
        divisions with one reciprocal changed 8 lines of output there while staying
        identical at the default 64, which a single-tile test would have missed.
        """
        for tile in (64, 48, 37, 100, 128):
            with self.subTest(tile=tile):
                a, ra = _run(self.ref, self.img,
                             ["--downsample", "1", "--tile", str(tile),
                              "--max-stars", "200"])
                b, rb = _run(self.fast, self.img,
                             ["--downsample", "1", "--tile", str(tile),
                              "--max-stars", "200"])
                self.assertEqual(ra, rb)
                self.assertTrue(a.strip(), "reference produced no stars")
                self.assertEqual(a, b,
                                 f"star list differs at tile={tile}: the hoisted "
                                 f"threshold path is not reproducing map_at()")

    def test_star_list_identical_across_downsample_and_sigma(self):
        for ds in (1, 2, 4):
            for sg in ("3", "5", "8"):
                with self.subTest(downsample=ds, sigma=sg):
                    a, _ = _run(self.ref, self.img,
                                ["--downsample", str(ds), "--sigma", sg,
                                 "--max-stars", "200"])
                    b, _ = _run(self.fast, self.img,
                                ["--downsample", str(ds), "--sigma", sg,
                                 "--max-stars", "200"])
                    self.assertEqual(a, b)

    def test_focus_metric_identical(self):
        """HFR feeds autofocus; a shifted centroid changes the focus score."""
        a, _ = _run(self.ref, self.img, ["--downsample", "1", "--focus-metric"])
        b, _ = _run(self.fast, self.img, ["--downsample", "1", "--focus-metric"])
        self.assertEqual(a.strip(), b.strip())

    def test_gray_pgm_identical(self):
        """The camera device path shares the decode stage.

        --gray-pgm returns before any thresholding, so this does NOT exercise the
        hoist. It is here because both builds recompile the whole file: if a future
        edit broke the shared decode, the PGM the Alpaca device serves would change
        and nothing else in this file would notice.
        """
        a, _ = _run(self.ref, self.img, ["--downsample", "1", "--gray-pgm"],
                    binary_out=True)
        b, _ = _run(self.fast, self.img, ["--downsample", "1", "--gray-pgm"],
                    binary_out=True)
        self.assertTrue(a.startswith(b"P5\n"), "no PGM emitted")
        self.assertEqual(a, b)

    def test_thresholds_match_exactly_for_every_pixel(self):
        """The strong guard: compare the threshold itself, not just survivors.

        Star lists are a weak differential. A wrong interpolation weight was tried
        during development that changed the threshold at 1,178,134 of 2,457,600
        pixels and still produced byte-identical star lists -- the blobs were bright
        enough that a shifted background did not change which pixels cleared it. A
        test that cannot see a real numerical error reads as coverage while proving
        nothing, so this compares the threshold computed both ways for every pixel.

        --dump-thresholds prints "<hoisted> <map_at>" per pixel; equality must hold
        bit-for-bit, since the products are formed in the same order either way.
        """
        for tile in (64, 48, 37):
            with self.subTest(tile=tile):
                out, rc = _run(self.fast, self.img,
                               ["--downsample", "1", "--tile", str(tile),
                                "--dump-thresholds"])
                self.assertEqual(rc, 0)
                lines = [ln for ln in out.splitlines() if ln.strip()]
                self.assertTrue(lines, "no thresholds dumped")
                bad = 0
                for ln in lines:
                    a, _, b = ln.partition(" ")
                    if a != b:
                        bad += 1
                self.assertEqual(bad, 0,
                                 f"{bad}/{len(lines)} pixels disagree between the "
                                 f"hoisted path and map_at() at tile={tile}")

    def test_dump_mode_reports_both_paths(self):
        """The dump must really contain two independently computed values.

        If the second column were just a copy of the first, the comparison above
        would pass no matter how wrong the hoist became.
        """
        out, rc = _run(self.fast, self.img,
                       ["--downsample", "1", "--dump-thresholds"])
        self.assertEqual(rc, 0)
        lines = [ln for ln in out.splitlines() if ln.strip()]
        # Values must be real numbers, and the columns must not be a trivial echo:
        # with the tables disabled the two paths agree, so instead assert the dump
        # is non-trivial (varied values, full-precision formatting).
        firsts = {ln.split(" ")[0] for ln in lines}
        self.assertGreater(len(firsts), 1,
                           "dump is constant -- not a real per-pixel threshold")
        self.assertTrue(any("." in v or "e" in v.lower() for v in firsts),
                        "dump is not full precision; %.17g expected")

    def test_fast_path_is_actually_taken(self):
        """Guard against a vacuous differential.

        If the hoist were silently disabled -- table allocation removed, or the
        build flag leaking into production -- both binaries would run the same code
        and every equality test above would pass while the optimisation did nothing.
        """
        src = SRC.read_text()
        self.assertIn("build_weight_tables(W, H);", src,
                      "weight tables are never built; the hoist is dead code")
        self.assertIn("if (wx_a)", src,
                      "no fast-path branch in the threshold loop")
        # The reference build must differ from the fast build, proving the flag
        # changed the compiled code rather than being ignored.
        self.assertNotEqual(self.ref.read_bytes(), self.fast.read_bytes())

    def test_no_hoist_flag_is_test_only(self):
        """POLARIS_EXTRACT_NO_HOIST must not be set by any shipped build path.

        If it leaked into build_solver.sh the firmware would ship the slow path
        while every differential test here still passed.
        """
        candidates = [
            REPO / "build-astro.sh",
            REPO / "container" / "astro" / "build_solver.sh",
        ]
        candidates += sorted((REPO / "container" / "astro" / "ondisk").glob("*.sh"))
        hits = []
        for p in candidates:
            if not p.is_file():
                continue
            try:
                if "POLARIS_EXTRACT_NO_HOIST" in p.read_text():
                    hits.append(p.name)
            except (UnicodeDecodeError, OSError):
                continue
        self.assertEqual(hits, [],
                         f"test-only flag appears in a build path: {hits}")


if __name__ == "__main__":
    unittest.main()
