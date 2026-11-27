"""The shipped index manifest must list only files that are actually shipped.

Upstream's md5sums.txt covers the whole 4100 series (4107..4119). fetch-indexes.sh
copies it verbatim, and build-astro-candidate.sh zips it alongside only the subset
that overlaps the configured focal range -- ten files, 4110..4119. So the archive
carries a manifest naming three index files that are deliberately absent.

On the device that reads as corruption:

    # cd /app/sd/astrometry && md5sum -c .md5sums.txt
    md5sum: can't open 'index-4107.fits': No such file or directory
    index-4107.fits: FAILED
    ...
    md5sum: WARNING: 4 of 13 computed checksums did NOT match

On 2026-11-26 a genuinely truncated index-4110.fits (981,504 bytes instead of
24,871,680) sat in that same directory. The three phantom failures and the one real
failure were indistinguishable in that output, so the real defect was nearly missed
and time went into chasing the phantoms. A check whose PASS is unreachable cannot
report a real problem.

The pruning happens in build-astro-candidate.sh before astrometry-indexes.zip is
built. These tests run the real block against a fabricated tree -- no network, no
rig, no docker.
"""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRUNE = ROOT / "scripts" / "prune-index-manifest.sh"

UPSTREAM_MANIFEST = "".join(
    f"{i:032d} *index-{n}.fits\n" for i, n in enumerate(range(4107, 4120), start=1)
)


def _run(tmp_path: Path, present: list):
    """Run the real shared script against a fabricated SD_ROOT containing `present`.

    The build calls this same script (scripts/build-astro-candidate.sh invokes it
    before ASTRO-MANIFEST.sha256 is generated), so the build and this test exercise
    one code path. It used to be extracted from the build script by string markers,
    which silently diverged when the block moved: the test kept passing against a
    fragment while the shipped tree no longer matched its own manifest.
    """
    sd = tmp_path / "COPY-TO-SD-CARD-ROOT"
    (sd / "astrometry").mkdir(parents=True)
    (sd / "astrometry" / ".md5sums.txt").write_text(UPSTREAM_MANIFEST, encoding="utf-8")
    for name in present:
        (sd / "astrometry" / name).write_bytes(b"fits-bytes")

    proc = subprocess.run([str(PRUNE), str(sd)], capture_output=True, text=True)
    manifest = sd / "astrometry" / ".md5sums.txt"
    return proc, manifest


def test_manifest_pruned_to_shipped_files(tmp_path):
    shipped = [f"index-{n}.fits" for n in range(4110, 4120)]
    proc, manifest = _run(tmp_path, shipped)
    assert proc.returncode == 0, proc.stderr
    names = {line.split()[1].lstrip("*") for line in manifest.read_text().split("\n") if line}
    assert names == set(shipped), f"manifest lists {sorted(names - set(shipped))} that are not shipped"


def test_pruned_manifest_verifies_clean(tmp_path):
    """The whole point: md5sum -c must be able to pass on a healthy card."""
    shipped = [f"index-{n}.fits" for n in range(4110, 4120)]
    proc, manifest = _run(tmp_path, shipped)
    assert proc.returncode == 0, proc.stderr
    # Digests are placeholders here, so verify structure rather than hashes: every
    # entry must name a file that exists, which is what produced the false FAILEDs.
    names = [line.split()[1].lstrip("*") for line in manifest.read_text().split("\n") if line]
    missing = [n for n in names if not (manifest.parent / n).exists()]
    assert not missing, f"manifest names absent files: {missing}"


def test_corrupt_shipped_index_still_fails_the_check(tmp_path):
    """Pruning must not hide a real problem -- that is what #288 was about."""
    shipped = [f"index-{n}.fits" for n in range(4110, 4120)]
    proc, manifest = _run(tmp_path, shipped)
    assert proc.returncode == 0, proc.stderr
    # A digest that does not match must still be reported.
    (manifest.parent / "index-4110.fits").write_bytes(b"truncated")
    check = subprocess.run(["md5sum", "-c", str(manifest)],
                           capture_output=True, text=True, cwd=manifest.parent)
    assert check.returncode != 0, "a corrupt index must fail the pruned manifest"
    assert "index-4110.fits: FAILED" in check.stdout


def test_absent_manifest_is_tolerated(tmp_path):
    """VERIFY=0 leaves no manifest; the build must not die over a missing one."""
    sd = tmp_path / "COPY-TO-SD-CARD-ROOT"
    (sd / "astrometry").mkdir(parents=True)
    (sd / "astrometry" / "index-4110.fits").write_bytes(b"fits")
    proc = subprocess.run([str(PRUNE), str(sd)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_manifest_matching_nothing_is_an_error(tmp_path):
    """An empty pruned manifest means the tree and manifest disagree -- fail loudly."""
    proc, _ = _run(tmp_path, [])
    assert proc.returncode != 0, "expected failure when no manifest entry matches a shipped file"
    assert "matched no shipped index files" in proc.stderr


def test_build_prunes_before_hashing_the_manifest():
    """The ordering that actually broke v119, asserted directly.

    The pruning tests above exercise the script in isolation. They cannot see the
    build's call site, which is where the defect lived: the prune ran inside the
    archive step, after ASTRO-MANIFEST.sha256 had already been hashed, so the digest
    recorded the unpruned file while the tree shipped the pruned one. install-astro-kit.sh
    verifies the staged tree against that manifest and refused every v119 candidate with
    "./astrometry/.md5sums.txt: FAILED ... 1 of 726 computed checksums did NOT match".

    Asserting position rather than behaviour is the only thing that catches a future
    edit moving the call back below the hash.
    """
    build = (ROOT / "scripts" / "build-astro-candidate.sh").read_text(encoding="utf-8")
    lines = build.splitlines()

    prune_at = [i for i, l in enumerate(lines)
                if "prune-index-manifest.sh" in l and not l.lstrip().startswith("#")]
    assert len(prune_at) == 1, (
        f"expected exactly one call to prune-index-manifest.sh, found {len(prune_at)}")

    hash_at = [i for i, l in enumerate(lines)
               if l.rstrip().endswith("> \"$OUT/astro-bundle/ASTRO-MANIFEST.sha256\"")]
    assert len(hash_at) == 1, (
        f"expected exactly one ASTRO-MANIFEST.sha256 generation, found {len(hash_at)}")

    assert prune_at[0] < hash_at[0], (
        "prune-index-manifest.sh must run BEFORE ASTRO-MANIFEST.sha256 is generated "
        f"(prune at line {prune_at[0] + 1}, manifest at line {hash_at[0] + 1}); "
        "otherwise the manifest records the unpruned digest and kit installs fail")
