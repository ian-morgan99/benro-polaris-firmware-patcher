#!/usr/bin/env python3
"""The v-number in a candidate id must equal the display firmware version.

Offline. Imports the shipped validator and calls it directly, so it asserts on
the predicate we actually ship rather than on a copy of it. No device, no
network, no build.

Why this exists: astro-v113 was published as 6.0.0.54.111. The operator reading
the info screen sees ".111" while every folder, receipt and issue thread calls
the same build "v113", so the device cannot tell you which build is on it. That
is the whole point of a version string.

The drift has a specific cause, and pinning only the symptom would let it return.
build-release-candidate.sh derives BUILD_ID from DISPLAY_FWVER
("${DISPLAY_FWVER}-${ID}"), so the two agree automatically for camera releases.
The Astro flow takes both as independent arguments, and kit-only releases
(astro-v111, astro-v112) publish SD archives only -- they consume a v-number but
never claim a display version. The display counter therefore fell two behind the
v-counter, and v113 inherited .111.

So this file pins three things, not one:
  1. an aligned pair is accepted (the fix must not block real releases);
  2. the exact historical drift is refused;
  3. an id with no parseable v-number is refused rather than waved through,
     because "unparseable" and "drifted" look identical to the caller.

It also pins that build-astro-candidate.sh actually passes --build-id. The rule
living in the validator proves nothing if the caller never supplies the id; that
wiring is the part that was missing, so it is asserted here as text.
"""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import verify_display_fwver_monotonic as vdm  # noqa: E402


class TestReleaseNumberAlignment(unittest.TestCase):
    def test_aligned_pairs_accepted(self):
        # Real published ids, all of which were correct at the time.
        for candidate, build_id in [
            ("6.0.0.54.109", "astro-v109-camera-mainline-20261115"),
            ("6.0.0.54.110", "astro-v110-camera-usb-evidence-20261117"),
            ("6.0.0.54.105", "astro-v105-mmss-shutter-descriptors-20261110"),
            ("6.0.0.54.104", "v104"),  # short build_id form, still must parse
            ("6.0.0.54.113", "astro-v113-kit-identity-20261118"),
        ]:
            with self.subTest(candidate=candidate, build_id=build_id):
                vdm.validate_release_number_alignment(candidate, build_id)

    def test_the_actual_v113_drift_is_refused(self):
        # This is the pair that shipped. It must never build again.
        with self.assertRaises(ValueError) as ctx:
            vdm.validate_release_number_alignment(
                "6.0.0.54.111", "astro-v113-kit-identity-20261118"
            )
        message = str(ctx.exception)
        self.assertIn("v113", message)
        self.assertIn(".111", message)

    def test_drift_in_the_other_direction_is_refused(self):
        # A display version ahead of the v-number is the same defect.
        with self.assertRaises(ValueError):
            vdm.validate_release_number_alignment(
                "6.0.0.54.114", "astro-v113-kit-identity-20261118"
            )

    def test_id_without_v_number_is_refused_not_ignored(self):
        # Fail closed: an id we cannot read is indistinguishable from a drifted
        # one, and silently accepting it reopens the original bug.
        for build_id in ["no-v-number-here", "astro-kit-identity", ""]:
            with self.subTest(build_id=build_id):
                with self.assertRaises(ValueError) as ctx:
                    vdm.validate_release_number_alignment(
                        "6.0.0.54.113", build_id
                    )
                self.assertIn("no v-number", str(ctx.exception))

    def test_v_number_is_not_matched_inside_a_date_or_slug(self):
        # astro-v109-camera-mainline-20261115 ends in a date. A looser pattern
        # would pick up digits from the slug or the date and agree by accident.
        self.assertEqual(
            vdm.extract_release_number("astro-v109-camera-mainline-20261115"), 109
        )
        self.assertEqual(vdm.extract_release_number("v104"), 104)


class TestAstroBuilderWiresTheCheck(unittest.TestCase):
    """The rule is inert unless the Astro flow supplies the id it checks."""

    def test_build_astro_candidate_passes_build_id(self):
        script = (ROOT / "scripts" / "build-astro-candidate.sh").read_text()
        # Find the version-validation invocation and require --build-id in it.
        blocks = [
            block
            for block in script.split("\n\n")
            if "verify_display_fwver_monotonic.py" in block
        ]
        self.assertTrue(blocks, "no verify_display_fwver_monotonic call found")
        check = blocks[0]
        self.assertIn("--build-id", check)
        self.assertIn('"$BUILD_ID"', check)


if __name__ == "__main__":
    unittest.main()
