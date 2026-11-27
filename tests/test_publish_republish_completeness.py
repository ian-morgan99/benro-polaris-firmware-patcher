"""Re-publishing a candidate must not silently drop components or provenance.

Two defects, both found against bytes that are already published:

1. astro-bundle.tar.gz was copied inside the `else` branch of the
   existing-publication check, so the guard written to protect published bytes
   also skipped publishing them. 6.0.0.54.117 and .118 shipped without it while
   .115 and .116 carried it. Nothing complained: verify-published-astro-candidate.py
   reports an absent tarball as NOT_APPLICABLE, not FAIL, so the gate could not
   see the gap. Those folders were only made whole by hand.

2. The README heredoc had no appfs MD5 row. README.md is regenerated on every
   publish, so re-publishing .117/.118 to add the SD zips deleted the appfs row
   and the `unzip -p FwPkt/firmwareInfo` check the previous READMEs carried. The
   appfs digest is what release-fwpkt.sh verifies on the device before staging,
   and #288 established that a bad appfs yields a confident wrong sky position
   rather than an error -- so a reader who cannot check it has no way to tell a
   truncated packet from a good one.

Both are tested by executing the real blocks out of the script against fabricated
state: no docker, no network, no rig, and no push.
"""

import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "publish-astro-candidate.sh"

APPFS_MD5 = "003c130b1c69a71c4499e519af335ea4"
DEST = "firmware-packets/6.0.0.54.118--astro-v118"

BUNDLE_BLOCK_START = (
    'if [ "$EXISTING" = 1 ] && [ -f "$PR_CHECKOUT/$DEST/astro-bundle.tar.gz" ]; then'
)
APPFS_BLOCK_START = 'APPFS_MD5="$(unzip -p'
APPFS_BLOCK_END = 'BUNDLE_MD5="$(md5sum'


def _lines() -> list:
    return SCRIPT.read_text(encoding="utf-8").splitlines()


def _region(start_marker: str, end_marker: str) -> str:
    """Script lines from start_marker through the line matching end_marker.

    Anchored on literal text rather than line numbers: the script shifts whenever
    anything else in it changes, and a numeric anchor would quietly extract the
    wrong region instead of failing.
    """
    lines = _lines()
    starts = [i for i, l in enumerate(lines) if start_marker in l]
    assert len(starts) == 1, f"expected one {start_marker!r}, found {len(starts)}"
    ends = [i for i in range(starts[0], len(lines)) if end_marker in lines[i]]
    assert ends, f"no end marker {end_marker!r} after {start_marker!r}"
    return "\n".join(lines[starts[0]:ends[0] + 1])


def _heredoc_body(marker: str) -> str:
    """The README heredoc body, up to its terminating EOF."""
    lines = _lines()
    starts = [i for i, l in enumerate(lines) if marker in l]
    assert len(starts) == 1, f"expected one {marker!r}, found {len(starts)}"
    body = []
    for line in lines[starts[0] + 1:]:
        if line.strip() == "EOF":
            return "\n".join(body)
        body.append(line)
    raise AssertionError("heredoc has no terminating EOF")


def _run(tmp_path: Path, preamble: str, block: str):
    script = tmp_path / "block.sh"
    script.write_text(
        "set -euo pipefail\ndie() { echo \"ERROR: $*\" >&2; exit 1; }\n"
        + preamble + "\n" + block + "\n",
        encoding="utf-8",
    )
    return subprocess.run(["bash", str(script)], capture_output=True, text=True)


def _bundle_block(tmp_path: Path, existing: bool, build_bytes: bytes,
                  published_bytes):
    """Stage a build tree and publication, then run the real bundle-copy block."""
    build = tmp_path / "build"
    checkout = tmp_path / "checkout"
    dest = checkout / DEST
    build.mkdir(parents=True)
    (build / "astro-bundle.tar.gz").write_bytes(build_bytes)
    if published_bytes is not None:
        dest.mkdir(parents=True)
        (dest / "astro-bundle.tar.gz").write_bytes(published_bytes)
    elif existing:
        dest.mkdir(parents=True)

    block = _region(BUNDLE_BLOCK_START, 'cp "$BUILD/astro-bundle.tar.gz"') + "\nfi\n"
    # The real script creates $DEST in the new-candidate branch, before this block.
    # Reproduce that here so EXISTING=0 exercises the copy, not a missing directory.
    preamble = (
        f"BUILD={build}\nPR_CHECKOUT={checkout}\nDEST={DEST}\n"
        f"EXISTING={1 if existing else 0}\n"
        + ("" if existing else 'mkdir -p "$PR_CHECKOUT/$DEST"')
    )
    proc = _run(tmp_path, preamble, block)
    return proc, dest / "astro-bundle.tar.gz"


def _make_packet(path: Path, firmware_info: str) -> None:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("FwPkt/firmwareInfo", firmware_info)


# --- structure ---------------------------------------------------------------

def test_bundle_copy_is_not_inside_the_new_candidate_branch():
    """The bundle copy must be reachable when the publication already exists."""
    lines = _lines()
    else_idx = [i for i, l in enumerate(lines) if l.strip() == "else"]
    assert else_idx, "no else branch found"
    body = []
    for line in lines[else_idx[0] + 1:]:
        if line.strip() == "fi":
            break
        body.append(line)
    assert "astro-bundle.tar.gz" not in "\n".join(body), (
        "astro-bundle.tar.gz is copied inside the new-candidate else branch again; "
        "a re-publish of an existing candidate will silently omit it"
    )


def test_bundle_copy_guarded_by_refuse_to_replace():
    """Published bytes stay immutable, under the same rule as every other archive."""
    block = _region(BUNDLE_BLOCK_START, "refusing to replace published astro-bundle")
    assert "cmp -s" in block and "die" in block


def test_readme_template_carries_appfs_and_bundle_rows():
    body = _heredoc_body('cat > "$PR_CHECKOUT/$DEST/README.md" <<EOF')
    assert "${APPFS_ROW}" in body, "README template lost the appfs MD5 row"
    assert "astro-bundle.tar.gz MD5" in body, "README template lost the bundle MD5 row"


def test_appfs_derivation_runs_before_readme_is_written():
    """Ordering matters: an unset APPFS_ROW would render as a blank line."""
    lines = _lines()
    derive = [i for i, l in enumerate(lines) if l.startswith("APPFS_MD5=")]
    write = [i for i, l in enumerate(lines)
             if 'cat > "$PR_CHECKOUT/$DEST/README.md" <<EOF' in l]
    assert len(derive) == 1 and len(write) == 1
    assert derive[0] < write[0], "appfs must be derived before the README is generated"


# --- behaviour: bundle copy --------------------------------------------------

def test_new_candidate_still_gets_the_bundle(tmp_path):
    proc, published = _bundle_block(tmp_path, existing=False,
                                    build_bytes=b"GOOD", published_bytes=None)
    assert proc.returncode == 0, proc.stderr
    assert published.read_bytes() == b"GOOD"


def test_republish_adds_an_absent_bundle(tmp_path):
    """The exact case that shipped .117 and .118 incomplete."""
    proc, published = _bundle_block(tmp_path, existing=True,
                                    build_bytes=b"GOOD", published_bytes=None)
    assert proc.returncode == 0, proc.stderr
    assert published.exists(), "re-publish did not add astro-bundle.tar.gz"
    assert published.read_bytes() == b"GOOD"


def test_republish_tolerates_an_identical_bundle(tmp_path):
    proc, published = _bundle_block(tmp_path, existing=True,
                                    build_bytes=b"GOOD", published_bytes=b"GOOD")
    assert proc.returncode == 0, proc.stderr
    assert published.read_bytes() == b"GOOD"


def test_republish_refuses_to_replace_a_different_bundle(tmp_path):
    proc, published = _bundle_block(tmp_path, existing=True,
                                    build_bytes=b"NEW", published_bytes=b"PUBLISHED")
    assert proc.returncode != 0, "must refuse to overwrite published bundle bytes"
    assert "refusing to replace" in proc.stderr
    assert published.read_bytes() == b"PUBLISHED"


# --- behaviour: appfs derivation --------------------------------------------

def _appfs_block(tmp_path: Path, firmware_info: str):
    build = tmp_path / "build"
    build.mkdir()
    _make_packet(build / "FwPkt.zip", firmware_info)
    (build / "astro-bundle.tar.gz").write_bytes(b"BUNDLE")
    block = _region(APPFS_BLOCK_START, APPFS_BLOCK_END)
    return _run(tmp_path, f"BUILD={build}",
                block + '\nprintf "[%s][%s]" "$APPFS_MD5" "$APPFS_ROW"')


def test_appfs_row_derived_from_the_packet_being_published(tmp_path):
    info = f"appfs size:64487424;appfs MD5:{APPFS_MD5};\nrootfs size:1;rootfs MD5:dead;\n"
    proc = _appfs_block(tmp_path, info)
    assert proc.returncode == 0, proc.stderr
    value, row = proc.stdout.strip().strip("[]").split("][", 1)
    assert value == APPFS_MD5, f"derived {value!r}, expected {APPFS_MD5!r}"
    assert row.startswith("| appfs MD5 |") and APPFS_MD5 in row


def test_appfs_row_omitted_when_packet_has_no_appfs_line(tmp_path):
    """No line must mean no row, not a row with an empty digest."""
    proc = _appfs_block(tmp_path, "rootfs size:1;rootfs MD5:dead;\n")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "[][]", f"expected empty values, got {proc.stdout!r}"


def test_appfs_row_omitted_when_packet_is_unreadable(tmp_path):
    build = tmp_path / "build"
    build.mkdir()
    (build / "FwPkt.zip").write_bytes(b"not a zip")
    (build / "astro-bundle.tar.gz").write_bytes(b"BUNDLE")
    block = _region(APPFS_BLOCK_START, APPFS_BLOCK_END)
    proc = _run(tmp_path, f"BUILD={build}", block + '\nprintf "[%s]" "$APPFS_ROW"')
    assert proc.returncode == 0, "a malformed packet must not abort the derivation"
    assert proc.stdout.strip() == "[]"
