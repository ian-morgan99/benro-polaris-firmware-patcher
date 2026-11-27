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
SCRIPT = ROOT / "scripts" / "build-astro-candidate.sh"

START = '  if [ -d astrometry ]; then'
END = 'zip -qrX astrometry-indexes.zip astrometry'

UPSTREAM_MANIFEST = "".join(
    f"{i:032d} *index-{n}.fits\n" for i, n in enumerate(range(4107, 4120), start=1)
)


def _block() -> str:
    """The astrometry staging block, from its guard through its closing fi.

    Ends on the `fi` rather than the zip line: the zip invocation spans two lines
    (continuation plus its error handler), and cutting it at the marker yields a
    fragment bash refuses to parse.
    """
    lines = SCRIPT.read_text(encoding="utf-8").splitlines()
    starts = [i for i, l in enumerate(lines) if l.rstrip() == START]
    assert len(starts) == 1, f"expected one {START!r}, found {len(starts)}"
    ends = [i for i in range(starts[0], len(lines)) if END in lines[i]]
    assert ends, "no zip invocation after the astrometry guard"
    close = [i for i in range(ends[0], len(lines)) if lines[i] == "  fi"]
    assert close, "astrometry block has no closing fi"
    return "\n".join(lines[starts[0]:close[0] + 1])


def _run(tmp_path: Path, present: list):
    """Run the real block with a fabricated SD_ROOT containing `present` indexes."""
    sd = tmp_path / "COPY-TO-SD-CARD-ROOT"
    (sd / "astrometry").mkdir(parents=True)
    (sd / "astrometry" / ".md5sums.txt").write_text(UPSTREAM_MANIFEST, encoding="utf-8")
    for name in present:
        (sd / "astrometry" / name).write_bytes(b"fits-bytes")

    script = tmp_path / "block.sh"
    script.write_text(
        "set -euo pipefail\n"
        f"cd '{sd}'\n" + _block() + "\n",
        encoding="utf-8",
    )
    proc = subprocess.run(["bash", str(script)], capture_output=True, text=True)
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
    script = tmp_path / "block.sh"
    script.write_text("set -euo pipefail\n" f"cd '{sd}'\n" + _block() + "\n", encoding="utf-8")
    proc = subprocess.run(["bash", str(script)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_manifest_matching_nothing_is_an_error(tmp_path):
    """An empty pruned manifest means the tree and manifest disagree -- fail loudly."""
    proc, _ = _run(tmp_path, [])
    assert proc.returncode != 0, "expected failure when no manifest entry matches a shipped file"
    assert "matched no shipped index files" in proc.stderr
