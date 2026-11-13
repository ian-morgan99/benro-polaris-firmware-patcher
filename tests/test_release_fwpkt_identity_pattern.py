#!/usr/bin/env python3
"""#337: the device-identity guard must test family membership, not a patch suffix.

Offline. Extracts the case pattern from the two shipped scripts and runs it under
real bash, so it asserts on the predicate we actually ship rather than on a copy
of it. No device, no network.

Why this exists: both guards used to read *6.0.0.54.* , which demands a literal
dot after "54" and therefore refuses a device reporting exactly "6.0.0.54" -- in
family, but with no patch suffix. The guard's stated purpose is family
membership ("a blank or foreign version means we are not talking to the
Polaris"), so the old pattern was stricter than the thing it claimed to test.
The failure mode is exit 3 mid-deploy with no override flag.

The obvious "fix" -- widening to *6.0.0.54* -- is wrong in the other direction:
as a substring it also matches 6.0.0.541 and 6.0.0.5490, which are different
families. The shipped pattern tests the terminator instead. These tests pin both
halves of that requirement, because a fix that only satisfies one of them is not
a fix.

The two scripts must agree. They are separate files with no shared helper, so
nothing but this test stops one from drifting back.
"""

from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

SOURCES = {
    "release-fwpkt": ROOT / "scripts" / "release" / "release-fwpkt.sh",
    "o-v17a-autonomous-install": ROOT / "scripts" / "o-v17a-autonomous-install.sh",
}

# Real FwVer strings. The first four are in family; the rest must be refused.
IN_FAMILY = [
    "FwVer:6.0.0.54.107;date:2026.11.12;",   # normal, with patch suffix
    "FwVer:6.0.0.54",                        # in family, no suffix -- the #337 case
    "FwVer:6.0.0.54;",                       # in family, terminated by ';'
    "FwVer:6.0.0.54.108;date:2026.11.13;",   # the candidate this guards
]
OUT_OF_FAMILY = [
    "FwVer:6.0.0.541",                # substring trap: matches *6.0.0.54*, not family
    "FwVer:6.0.0.5490;x",             # same trap, longer
    "FwVer:4.0.0.32;date:2025.05.09;",  # stock firmware we must never flash over
    "FwVer:6.0.0.5",                  # truncated
    "",                               # unreadable / blank
]


def identity_pattern(path):
    """Return the device-identity case pattern as written in the shipped script."""
    text = path.read_text(encoding="utf-8", errors="replace")
    hits = [ln.strip() for ln in text.splitlines()
            if "6.0.0.54" in ln and ln.strip().startswith("*")]
    if not hits:
        raise AssertionError(f"{path.name}: no device-identity case pattern found")
    # The pattern list runs from the leading '*' up to the ')' closing it.
    # Neither accepted form contains a paren before that terminator.
    return hits[0].split(")", 1)[0].strip()


def run_pattern(pattern, value):
    """Evaluate a real bash case pattern against one value."""
    script = (
        'case "$1" in\n'
        f"  {pattern}) echo ACCEPT ;;\n"
        "  *) echo REJECT ;;\n"
        "esac\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as fh:
        fh.write(script)
        name = fh.name
    try:
        proc = subprocess.run(["bash", name, value], capture_output=True,
                              text=True, timeout=20)
    finally:
        Path(name).unlink(missing_ok=True)
    if proc.returncode != 0:
        raise AssertionError(
            f"bash rejected the shipped pattern {pattern!r}: {proc.stderr.strip()}")
    return proc.stdout.strip()


class IdentityPattern(unittest.TestCase):
    def test_pattern_is_parseable_and_present(self):
        for label, path in SOURCES.items():
            with self.subTest(source=label):
                pat = identity_pattern(path)
                self.assertTrue(pat.startswith("*"),
                                f"{label}: unexpected pattern {pat!r}")

    def test_the_two_guards_agree(self):
        """No shared helper exists between the scripts, so pin them equal here."""
        pats = {label: identity_pattern(p) for label, p in SOURCES.items()}
        self.assertEqual(len(set(pats.values())), 1,
                         "device-identity patterns have drifted apart: "
                         + "; ".join(f"{k}={v!r}" for k, v in pats.items()))

    def test_in_family_versions_are_accepted(self):
        pat = identity_pattern(SOURCES["release-fwpkt"])
        for value in IN_FAMILY:
            with self.subTest(fwver=value):
                self.assertEqual(run_pattern(pat, value), "ACCEPT",
                                 f"#337: in-family {value!r} must pass the guard")

    def test_foreign_and_substring_versions_are_refused(self):
        pat = identity_pattern(SOURCES["release-fwpkt"])
        for value in OUT_OF_FAMILY:
            with self.subTest(fwver=value):
                self.assertEqual(run_pattern(pat, value), "REJECT",
                                 f"{value!r} must not pass a 6.0.0.54 family guard")

    def test_naive_widening_would_have_been_wrong(self):
        """Documents the trap: *6.0.0.54* matches 6.0.0.541."""
        self.assertEqual(run_pattern("*6.0.0.54*", "FwVer:6.0.0.541"), "ACCEPT")


if __name__ == "__main__":
    unittest.main()
