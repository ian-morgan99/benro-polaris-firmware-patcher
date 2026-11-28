#!/usr/bin/env python3
"""A firmware-only builder must not issue an Astro display version (issue #169).

Offline. Runs the real scripts/build-release-candidate.sh with a throwaway id and
asserts it refuses an astro-vNNN candidate id before doing any work, and still
accepts an o-main-* id. No docker, no device, no network, no build.

Why: build-release-candidate.sh produces a firmware-only packet -- FwPkt.zip plus
the install manifest. It never emits polaris-astro.zip, polaris-wifi.zip or
astro-bundle.tar.gz; scripts/build-astro-candidate.sh is the only producer that
satisfies the mandatory complete-release distribution gate in
docs/FWPKT-PROVENANCE-CONTRACT.md.

docs/RELEASE-VERSION-STATE.md makes astro-vNNN and 6.0.0.54.NNN one release
carrying two names, so putting an astro-vNNN id on a firmware-only packet
announces an Astro release to anyone reading the folder name, the registry row or
/app/FwVer -- while shipping none of the kit archives that gate requires.

Observed on this exact path: CANDIDATE_ID=astro-v120-companion-reporting-20261128
claimed 6.0.0.54.120 and published six files where the comparable Astro release
(6.0.0.54.118) publishes seventeen, with polaris-astro.zip, polaris-wifi.zip,
astro-bundle.tar.gz and astrometry-indexes.zip all absent. Nothing complained: the
display version here comes from --next rather than from the id, so the numbering
looked self-consistent, and verify-published-astro-candidate.py reports an absent
tarball as NOT_APPLICABLE rather than FAIL.

The guard must fire before the doctor and before anything is built: the first v120
attempt spent a full ~20-minute ARM build and only died at the last step.
"""

from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build-release-candidate.sh"

# Printed by the --skip-doctor branch, which is the first thing after the guard.
# Reaching it proves the id was accepted and that no build work happened yet.
POST_GUARD_MARKER = "--skip-doctor: build prerequisites were NOT verified"


class AstroIdOnFirmwareOnlyBuilderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="astro-id-"))
        self.summary = self.tmp / "summary.json"
        self.summary.write_text('{"baseline": {}, "changes": []}')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, candidate_id):
        return subprocess.run(
            ["bash", str(SCRIPT), candidate_id, str(self.tmp / "base"),
             str(self.tmp / "src"), "build-id-1", "--skip-doctor",
             "--change-summary", str(self.summary)],
            capture_output=True, text=True, timeout=120,
            cwd=str(self.tmp),  # never operate on the real repo tree
        )

    def test_astro_v_number_is_refused(self):
        """The exact id that burned 6.0.0.54.120 must now be rejected."""
        proc = self._run("astro-v120-companion-reporting-20261128")
        self.assertNotEqual(proc.returncode, 0,
                            "firmware-only builder accepted an astro-vNNN id")
        self.assertIn("astro-vNNN", proc.stderr)
        self.assertIn("build-astro-candidate.sh", proc.stderr)
        # It must refuse before the doctor, i.e. before any build work at all.
        self.assertNotIn(POST_GUARD_MARKER, proc.stderr + proc.stdout)

    def test_short_v_number_is_not_caught(self):
        """A short vNNN id is a different family and must not be refused.

        v86, v9l-74-77 and friends are controlled-test ids, not Astro releases.
        Only the astro-vNNN prefix asserts Astro completeness. Refusing these would
        break legitimate candidates, so this pins the guard's scope from below.
        """
        proc = self._run("v120-something")
        self.assertIn(POST_GUARD_MARKER, proc.stderr + proc.stdout,
                      "guard over-reached: a short vNNN id was refused")

    def test_o_main_id_is_accepted(self):
        """The documented firmware-only family must still pass the guard.

        Without this, the guard could be satisfied by rejecting everything, which
        would break every legitimate firmware-only candidate.
        """
        proc = self._run("o-main-20261128T000000Z")
        self.assertIn(POST_GUARD_MARKER, proc.stderr + proc.stdout,
                      "o-main-* id did not reach the step after the guard")

    def test_non_numeric_astro_prefix_is_accepted(self):
        """'astrology-v9' is not an Astro release id and must not be caught."""
        proc = self._run("astrology-v9-not-a-release")
        self.assertIn(POST_GUARD_MARKER, proc.stderr + proc.stdout)


class GuardPlacementTest(unittest.TestCase):
    def test_guard_precedes_the_doctor_and_the_build(self):
        """Ordering is the point: a rejected id must not cost a 20-minute build."""
        text = SCRIPT.read_text(encoding="utf-8")
        guard = text.index('astro-v[0-9]*')
        doctor = text.index('build-doctor.sh')
        self.assertLess(guard, doctor,
                        "guard runs after the doctor; a bad id still costs a build")

    def test_guard_precedes_the_version_claim(self):
        """The number must never be consumed by a rejected candidate."""
        text = SCRIPT.read_text(encoding="utf-8")
        guard = text.index('astro-v[0-9]*')
        claim = text.index('--state "$VERSION_STATE" --record')
        self.assertLess(guard, claim,
                        "guard runs after --record; a rejected id burns the number")


if __name__ == "__main__":
    unittest.main()
