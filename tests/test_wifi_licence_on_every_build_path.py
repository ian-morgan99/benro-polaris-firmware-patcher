"""The wifi licence offer must be produced by EVERY path that makes a wifi kit.

Issue #286: scripts/build-astro-bundle.sh generated LICENCE-wifi.txt and copied the
LGPL/ISC/BSD notices into polaris-wifi/, and refused to continue if any was missing.
But scripts/build-astro-candidate.sh -- the script every published release is actually
built by -- calls build-astro.sh directly and tars the result itself, so that gate
never ran. The published 6.0.0.54.99 polaris-wifi.zip shipped wpa_supplicant, wpa_cli,
wpa_passphrase and iw, all statically linked against libnl (LGPL-2.1), with no licence
copy and no source offer. Verified against the published artifact:

    unzip -Z1 polaris-wifi.zip | grep -iE 'licence|license|copying|notice'   -> nothing

A gate on one of two build paths is not a gate. So these tests do not check the wording
of the licence -- they check that the generation is reachable from the low-level script
that both paths share, and that each path inspects the finished archive rather than the
staging directory. The zip is what a user receives; a notice that exists on disk but is
not in the archive is exactly how .99 slipped through.

The behavioural tests run the real block out of build-astro.sh against a fabricated
licenses/ tree: no docker, no network, no rig.
"""

import re
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOW_LEVEL = ROOT / "build-astro.sh"
CANDIDATE = ROOT / "scripts" / "build-astro-candidate.sh"
WRAPPER = ROOT / "scripts" / "build-astro-bundle.sh"

# The names the existing gate in build-astro-bundle.sh checks. Taken from the gate, not
# invented: an earlier abandoned fix wrote SOURCE-OFFER.txt here instead, which satisfies
# LGPL but fails that gate, and someone would then "fix" it by renaming the wrong file.
LICENCE_FILES = (
    "LICENCE-wifi.txt",
    "COPYING-LGPL-2.1.txt",
    "NOTICE-iw.txt",
    "NOTICE-wpa_supplicant.txt",
)

UPSTREAM_TARBALLS = ("libnl-3.7.0.tar.gz", "iw-5.19.tar.gz", "wpa_supplicant-2.10.tar.gz")


def _block(text: str, start_marker: str) -> str:
    """Return the shell block beginning at start_marker, up to its matching `fi`.

    Anchored on a comment rather than a line number: build-astro.sh shifts whenever
    anything else in it changes, and a line-number anchor would silently extract the
    wrong region instead of failing.
    """
    lines = text.splitlines()
    starts = [i for i, l in enumerate(lines) if start_marker in l]
    assert len(starts) == 1, f"expected exactly one '{start_marker}', found {len(starts)}"
    depth = 0
    for i in range(starts[0], len(lines)):
        stripped = lines[i].strip()
        if re.match(r"^if\b", stripped):
            depth += 1
        elif re.match(r"^fi\b", stripped):
            depth -= 1
            if depth == 0:
                return "\n".join(lines[starts[0]:i + 1])
    raise AssertionError(f"no matching `fi` for the block at '{start_marker}'")


def _run_generation(tmp_path: Path, *, break_licence: bool = False) -> subprocess.CompletedProcess:
    """Run build-astro.sh's wifi licence block against a fabricated licenses/ tree."""
    lic = tmp_path / "lic"
    kit = tmp_path / "polaris-wifi"
    lic.mkdir(parents=True)
    kit.mkdir(parents=True)

    # The notices and tarballs that the preceding step in build-astro.sh produces.
    (lic / "COPYING-LGPL-2.1.txt").write_text("GNU LESSER GENERAL PUBLIC LICENSE\nVersion 2.1\n")
    (lic / "NOTICE-iw.txt").write_text("ISC permission notice for iw\n")
    (lic / "NOTICE-wpa_supplicant.txt").write_text("BSD-style notice for wpa_supplicant\n")
    for tgz in UPSTREAM_TARBALLS:
        (lic / tgz).write_bytes(b"\x1f\x8b placeholder")

    block = _block(LOW_LEVEL.read_text(), "The licence and the written offer must travel")
    harness = tmp_path / "harness.sh"
    # WANT_WIFI is always set by build-astro.sh's argument parsing; the extracted block
    # is guarded by it, and running under `set -u` without it aborts on an unbound
    # variable rather than testing anything.
    harness.write_text(
        "set -euo pipefail\n"
        f"WANT_WIFI=1\nLIC='{lic}'\nSD_WIFI='{kit}'\n" + block + "\n"
    )
    if break_licence:
        # Negative control: with no upstream tarballs the offer cannot name a version,
        # so the block must refuse rather than emit a vague offer.
        for tgz in UPSTREAM_TARBALLS:
            (lic / tgz).unlink()

    return subprocess.run(
        ["bash", str(harness)], capture_output=True, text=True, timeout=60
    )


# ── path reachability: the actual bug class ────────────────────────────────────────

def test_licence_generation_lives_in_the_shared_builder():
    """build-astro.sh must write the notices itself, not rely on a wrapper.

    This is the assertion that would have failed before the fix and is the whole point
    of the issue: both build paths invoke build-astro.sh, so generation placed here
    reaches every producer of a wifi kit.
    """
    text = LOW_LEVEL.read_text()
    for f in LICENCE_FILES:
        assert f in text, f"build-astro.sh never mentions {f}"
    # The three upstream notices are copied from licenses/ into the kit directory.
    for src, dest in (
        ("COPYING-LGPL-2.1.txt", "$SD_WIFI"),
        ("NOTICE-iw.txt", "$SD_WIFI"),
        ("NOTICE-wpa_supplicant.txt", "$SD_WIFI"),
    ):
        assert re.search(rf'cp\s+"\$LIC/{src}"\s+"{re.escape(dest)}/"', text), (
            f"build-astro.sh does not copy {src} into the wifi kit directory"
        )


def test_generation_is_reachable_without_the_wrapper():
    """Run the block standalone: it must produce all four files with no wrapper present.

    Static presence is not reachability. This executes the real code path that
    build-astro-candidate.sh takes, which is the one that shipped .99 broken.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        res = _run_generation(tmp)
        assert res.returncode == 0, f"generation failed: {res.stderr}"
        for f in LICENCE_FILES:
            produced = tmp / "polaris-wifi" / f
            assert produced.is_file(), f"{f} was not written into the kit"
            assert produced.stat().st_size > 0, f"{f} is empty -- an empty licence is not a licence"


def test_offer_names_the_versions_it_offers_source_for():
    """An offer that names no version is not an offer.

    The abandoned fix interpolated variables that were out of scope on the wrapper path
    and emitted 'libnl-, iw-'. Versions here come from the tarball filenames, so this
    checks the expansion actually happened.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        assert _run_generation(tmp).returncode == 0
        offer = (tmp / "polaris-wifi" / "LICENCE-wifi.txt").read_text()
        for version in ("3.7.0", "5.19", "2.10"):
            assert version in offer, f"LICENCE-wifi.txt does not name version {version}"
        # The libnl release tag uses underscores, as build_wifi.sh builds it; dots would
        # produce libnl370, which is not a real tag and the link would 404.
        assert "libnl3_7_0" in offer, "libnl upstream URL uses the wrong tag form"
        assert not re.search(r"libnl-,|iw-,|wpa_supplicant-,", offer), (
            "offer contains an empty version interpolation"
        )


def test_generation_fails_closed_without_source(tmp_path):
    """No upstream tarballs must abort the build, not emit a vague offer.

    Without this, a cold source cache produces a kit whose 'offer' names nothing --
    which reads as compliant and is not.
    """
    res = _run_generation(tmp_path, break_licence=True)
    assert res.returncode != 0, "generation succeeded with no corresponding source to offer"
    assert "corresponding source" in res.stderr or "not an offer" in res.stderr


def test_empty_notice_is_rejected(tmp_path):
    """A zero-byte notice passes `[ -f ]` and still leaves the user with no licence."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        lic = tmp / "lic"
        kit = tmp / "polaris-wifi"
        lic.mkdir(parents=True)
        kit.mkdir(parents=True)
        (lic / "COPYING-LGPL-2.1.txt").write_text("LGPL\n")
        (lic / "NOTICE-iw.txt").write_text("")          # the defect under test
        (lic / "NOTICE-wpa_supplicant.txt").write_text("BSD\n")
        for tgz in UPSTREAM_TARBALLS:
            (lic / tgz).write_bytes(b"\x1f\x8b placeholder")
        block = _block(LOW_LEVEL.read_text(), "The licence and the written offer must travel")
        harness = tmp / "h.sh"
        harness.write_text(
            f"set -euo pipefail\nWANT_WIFI=1\nLIC='{lic}'\nSD_WIFI='{kit}'\n{block}\n"
        )
        res = subprocess.run(["bash", str(harness)], capture_output=True, text=True, timeout=60)
        assert res.returncode != 0, "an empty NOTICE-iw.txt was accepted"
        assert "NOTICE-iw.txt" in res.stderr


# ── the candidate path: it made no archive at all ─────────────────────────────────

def test_candidate_path_produces_the_sd_archives():
    """build-astro-candidate.sh must create polaris-wifi.zip itself.

    It did not. Only build-astro-bundle.sh created the zips, and nothing in production
    calls that script, so the archives published for .99 were made outside any tracked
    build path -- no gate ever saw them. publish-astro-candidate.sh skips a missing zip
    silently (`[ -f ] || continue`), so absence passed unnoticed.
    """
    text = CANDIDATE.read_text()
    assert re.search(r"zip\s+-qrX\s+polaris-wifi\.zip\s+polaris-wifi", text), (
        "build-astro-candidate.sh does not create polaris-wifi.zip"
    )
    assert re.search(r"zip\s+-qrX\s+polaris-astro\.zip\s+polaris-astro", text), (
        "build-astro-candidate.sh does not create polaris-astro.zip"
    )


def test_candidate_path_asserts_on_the_archive_not_the_staging_dir():
    """The check must read the finished zip.

    Checking the staging directory is what let .99 pass: the file can exist on disk and
    still be absent from the archive a user is handed.
    """
    text = CANDIDATE.read_text()
    assert re.search(r'unzip\s+-Z1\s+"\$SD_ROOT/polaris-wifi\.zip"\s*\|\s*grep\s+-qx', text), (
        "candidate path does not test membership by reading entries out of polaris-wifi.zip"
    )
    # The names are iterated, so assert the loop's list covers all four rather than
    # looking for four literal greps that a loop would never contain.
    lists = re.findall(r"for f in ([^;]*); do", text)
    covered = {n for lst in lists for n in lst.split()}
    missing = set(LICENCE_FILES) - covered
    assert not missing, f"candidate path does not assert these are inside the zip: {sorted(missing)}"
    # Presence is not enough -- the bytes must be read out of the archive.
    assert 'unzip -p "$SD_ROOT/polaris-wifi.zip"' in text, (
        "candidate path does not read licence contents out of the zip"
    )


def test_wrapper_check_is_retained_as_second_defence():
    """The wrapper's gate stays. It is no longer the only one, but it must not be removed."""
    text = WRAPPER.read_text()
    for f in LICENCE_FILES:
        assert f in text, f"the wrapper's second line of defence for {f} was removed"


def test_no_path_relies_on_the_other_for_licences():
    """Neither producer may depend on the other to write the notices.

    Guards against a future refactor that moves generation back into one script, which
    is precisely how #286 happened.
    """
    low = LOW_LEVEL.read_text()
    cand = CANDIDATE.read_text()
    wrap = WRAPPER.read_text()
    # build-astro.sh writes them (reached by both paths).
    assert "LICENCE-wifi.txt" in low
    # The candidate path verifies them inside the archive it produces.
    assert "LICENCE-wifi.txt" in cand
    # The wrapper still generates and verifies.
    assert 'cat > "$SD_WIFI/LICENCE-wifi.txt"' in wrap
