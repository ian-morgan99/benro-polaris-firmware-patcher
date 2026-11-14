#!/usr/bin/env python3
"""#288: index acquisition must verify content, not just file existence.

Offline. Uses a file:// mirror so no network is needed; curl supports file:// and the
checksum manifest is fetched the same way as a real one.

Why this exists: fetch-indexes.sh used plain http and treated "file exists" as
"file is good". A truncated or corrupted index therefore satisfied the check forever,
and the solver then either failed or returned a confident wrong sky position. #288
also notes upstream has always offered HTTPS and publishes md5sums.txt.

These tests drive the real script and assert on its behaviour: verified reuse,
detection and repair of a corrupt cached file, refusal to install a corrupt download,
no .part left behind, non-zero exit, and that a narrow-field request selects the
indexes it should.
"""

import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FETCH = REPO / "container" / "astro" / "fetch-indexes.sh"


def _fixture(path: Path, seed: int) -> None:
    """A stand-in index file.

    These tests assert on acquisition and integrity behaviour -- atomicity, hash
    comparison, refusal to install a bad file -- so the bytes do not need to be a
    real FITS index. Deliberately synthetic and machine-independent: pointing at a
    developer-local cache would make the suite fail on any other host.
    """
    rng = os.urandom(2048)
    path.write_bytes(rng + bytes([seed]) * 16 + rng)


class _Mirror:
    """A file:// stand-in for data.astrometry.net/4100 with a real md5sums.txt."""

    def __init__(self, names=None):
        # Default to the release's declared envelope (14-400 mm / 36 mm -> 4110..4119)
        # so a run that selects ten files can actually acquire ten files.
        if names is None:
            names = tuple(f"index-{n}.fits" for n in range(4110, 4120))
        self.dir = tempfile.mkdtemp(prefix="idxmirror-")
        self.src = Path(self.dir) / "src"
        self.out = Path(self.dir) / "out"
        self.src.mkdir()
        self.out.mkdir()
        for i, n in enumerate(names):
            _fixture(self.src / n, i + 1)
        self.write_manifest()

    def write_manifest(self):
        lines = []
        for p in sorted(self.src.glob("index-*.fits")):
            h = hashlib.md5(p.read_bytes()).hexdigest()
            lines.append(f"{h} *{p.name}")
        (self.src / "md5sums.txt").write_text("\n".join(lines) + "\n")

    def run(self, focal_min, focal_max, sensor=36, env_extra=None):
        env = dict(os.environ)
        env.update({
            "INDEX_BASE": f"file://{self.src}",
            "INDEX_MD5_URL": f"file://{self.src}/md5sums.txt",
        })
        if env_extra:
            env.update(env_extra)
        return subprocess.run(
            ["bash", str(FETCH), "--focal-min", str(focal_min),
             "--focal-max", str(focal_max), "--sensor-mm", str(sensor),
             "--out", str(self.out)],
            env=env, capture_output=True, text=True, timeout=180)

    def md5(self, name):
        p = self.out / name
        return hashlib.md5(p.read_bytes()).hexdigest() if p.exists() else None

    def cleanup(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class TestVerifiedAcquisition(unittest.TestCase):
    def test_fresh_fetch_verifies_and_records_sha256(self):
        m = _Mirror()
        try:
            r = m.run(14, 400)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue((m.out / "index-4119.fits").is_file(), r.stdout)
            self.assertEqual(m.md5("index-4119.fits"),
                             hashlib.md5((m.src / "index-4119.fits").read_bytes()).hexdigest())
            # #288 asks for hashes recorded as candidate evidence.
            self.assertTrue((m.out / "indexes.sha256").is_file(),
                            "sha256 manifest not written")
        finally:
            m.cleanup()

    def test_rerun_reuses_verified_file_without_refetching(self):
        m = _Mirror()
        try:
            m.run(14, 400)
            r2 = m.run(14, 400)
            self.assertIn("verified", r2.stdout, r2.stdout)
            self.assertNotIn("fetching index-4119", r2.stdout,
                             "upgrade path re-downloaded a verified index")
        finally:
            m.cleanup()


class TestCorruptionIsCaught(unittest.TestCase):
    def test_corrupt_cached_file_is_detected_and_repaired(self):
        """The core #288 bug: '-f' said this file was fine, forever."""
        m = _Mirror()
        try:
            m.run(14, 400)
            with open(m.out / "index-4119.fits", "ab") as fh:
                fh.write(b"GARBAGE")
            r = m.run(14, 400)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("mismatch; refetching", r.stdout, r.stdout)
            self.assertEqual(m.md5("index-4119.fits"),
                             hashlib.md5((m.src / "index-4119.fits").read_bytes()).hexdigest(),
                             "corrupt cached file was not repaired")
        finally:
            m.cleanup()

    def test_empty_cached_file_is_refetched(self):
        m = _Mirror()
        try:
            m.run(14, 400)
            (m.out / "index-4119.fits").write_bytes(b"")
            r = m.run(14, 400)
            self.assertIn("empty; refetching", r.stdout, r.stdout)
            self.assertTrue((m.out / "index-4119.fits").stat().st_size > 0)
        finally:
            m.cleanup()

    def test_corrupt_download_is_refused_and_not_installed(self):
        """A source whose bytes no longer match the published hash must be refused.

        The manifest is deliberately NOT rewritten here: that is the point. The
        published checksum still describes the good file, so a mirror serving
        tampered or damaged bytes is caught by comparison against it.
        """
        m = _Mirror()
        try:
            with open(m.src / "index-4119.fits", "ab") as fh:
                fh.write(b"CORRUPT")
            r = m.run(14, 400)
            self.assertNotEqual(r.returncode, 0, "corrupt download accepted silently")
            self.assertIn("checksum mismatch after download", r.stderr, r.stderr)
            self.assertFalse((m.out / "index-4119.fits").exists(),
                             "corrupt file was installed anyway")
            self.assertEqual(list(m.out.glob("*.part")), [],
                             ".part left behind after failure")
        finally:
            m.cleanup()

    def test_missing_manifest_entry_is_refused(self):
        """VERIFY=1 with no published checksum must not install the file."""
        m = _Mirror()
        try:
            (m.src / "md5sums.txt").write_text("")
            r = m.run(14, 400)
            self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertFalse((m.out / "index-4119.fits").exists())
        finally:
            m.cleanup()

    def test_unreachable_manifest_refuses_to_install_anything(self):
        m = _Mirror()
        try:
            (m.src / "md5sums.txt").unlink()
            r = m.run(14, 400)
            self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("could not fetch the checksum manifest", r.stderr, r.stderr)
            self.assertEqual(list(m.out.glob("index-*.fits")), [],
                             "indexes installed without a manifest")
        finally:
            m.cleanup()

    def test_verify_zero_is_an_explicit_opt_out(self):
        """VERIFY=0 must still work for an air-gapped mirror, and say it is unverified."""
        m = _Mirror()
        try:
            (m.src / "md5sums.txt").unlink()
            r = m.run(14, 400, env_extra={"VERIFY": "0"})
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue((m.out / "index-4119.fits").is_file())
        finally:
            m.cleanup()


class TestFieldOfViewSelection(unittest.TestCase):
    """#343: the narrow-field case must select the indexes that can match it."""

    def test_narrow_field_selects_4107_to_4110(self):
        """11 mm sensor / 450 mm lens -> 1.40 deg FOV, per #343's own figure."""
        m = _Mirror(names=tuple(f"index-{n}.fits" for n in range(4107, 4120)))
        try:
            r = m.run(450, 450, sensor=11)
            self.assertIn("1.40", r.stdout, r.stdout + r.stderr)
            needed = [ln for ln in r.stdout.splitlines() if "needed:" in ln][0]
            for n in ("4107", "4108", "4109"):
                self.assertIn(n, needed, f"{n} not selected for a 1.4 deg field: {needed}")
            # And they must actually be fetchable, not merely named.
            for n in ("4107", "4108", "4109"):
                self.assertTrue((m.out / f"index-{n}.fits").is_file(),
                                f"index-{n} selected but not acquired")
        finally:
            m.cleanup()

    def test_release_envelope_selects_4110_to_4119(self):
        """Matches #288's stated 14-400 mm / 36 mm envelope of ten files."""
        m = _Mirror(names=tuple(f"index-{n}.fits" for n in range(4107, 4120)))
        try:
            r = m.run(14, 400)
            needed = [ln for ln in r.stdout.splitlines() if "needed:" in ln][0]
            self.assertIn("4110", needed, needed)
            self.assertIn("4119", needed, needed)
            self.assertNotIn("4107", needed, needed)
        finally:
            m.cleanup()


class TestTransportHardening(unittest.TestCase):
    def test_default_base_is_https(self):
        body = FETCH.read_text()
        self.assertIn("https://data.astrometry.net/4100", body)
        self.assertNotIn('BASE="http://', body, "plain http default remains")

    def test_downloads_are_atomic(self):
        body = FETCH.read_text()
        self.assertIn(".part", body)
        self.assertIn("mv -f \"$part\" \"$f\"", body)

    def test_zero_length_body_is_a_failure(self):
        body = FETCH.read_text()
        self.assertRegex(body.replace("\n", " "), r"\[ ! -s \"\$part\" \]")


if __name__ == "__main__":
    unittest.main()
