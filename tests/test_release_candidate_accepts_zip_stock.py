"""The release builder must accept a stock FwPkt given as a ZIP.

build-release-candidate.sh advertises "<stock-FwPkt.zip|dir>" and its packaging step
reads zip input with zipfile, stripping the FwPkt/ prefix. The acceptance check used

    unzip -l "$BASE" | grep -qE '(^|/)FwPkt/firmwareInfo$'

but `unzip -l` prints "  Length   Date   Time   Name" -- the member name is padded with
leading spaces, so it is never at position 0 and "FwPkt/" is never preceded by "/". The
anchored pattern therefore cannot match any listing line, and every zip packet on disk was
rejected with

    ERROR: stock input must contain FwPkt/firmwareInfo

which reads as a defect in the packet. The packet was fine; the check was broken. `unzip -Z1`
prints bare member names, which is what the pattern needs.

These tests drive the real script rather than re-implementing the pattern, because a test
that duplicates the regex would have passed while the script failed -- which is the whole
shape of this bug.

Ordering matters and cost a first version of these tests their meaning: the script checks
`$SRC/.git` BEFORE the stock packet, so with a non-git source every run died on "libgphoto2
input must have a real git work tree" and never reached the check under test. Asserting the
absence of the rejection message then passed for the wrong reason -- a vacuous green. The
fixture therefore builds a real (tiny, clean) git tree so execution genuinely arrives at
the stock check, and the negative case asserts the message is PRESENT, which cannot pass by
never getting there.
"""
from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BUILDER = REPO / "scripts" / "build-release-candidate.sh"


def _make_zip(path: Path, *, with_firmware_info: bool) -> None:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("FwPkt/", "")
        if with_firmware_info:
            z.writestr("FwPkt/firmwareInfo", "firmwareInfo\n")
        z.writestr("FwPkt/camera/uImage", b"\x00" * 16)


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True,
                   capture_output=True, text=True)


def _clean_git_tree(tmp_path: Path) -> Path:
    """A real, self-contained, clean git work tree.

    The script requires `$SRC/.git` to exist and the tree to be clean before it looks at
    the stock packet at all. Without this the tests would stop at the libgphoto2 check and
    the stock assertion below would be vacuously true.
    """
    src = tmp_path / "libgphoto2-src"
    src.mkdir()
    _git("init", "-q", "-b", "main", cwd=src)
    _git("config", "user.email", "t@example.invalid", cwd=src)
    _git("config", "user.name", "t", cwd=src)
    # configure.ac is what build-doctor.sh looks for; irrelevant here because the doctor
    # is skipped, but a plausible file keeps the fixture honest.
    (src / "configure.ac").write_text("AC_INIT([libgphoto2])\n")
    _git("add", "-A", cwd=src)
    _git("commit", "-q", "-m", "seed", cwd=src)
    return src


def _run(tmp_path: Path, base: Path):
    src = _clean_git_tree(tmp_path)
    summary = tmp_path / "summary.md"
    summary.write_text("# purpose\n\ntest.\n")
    # --skip-doctor: build-doctor.sh runs first and rejects the fake libgphoto2 source
    # (no configure.ac checks, no origin, etc.), which would mask whichever branch of the
    # stock check we are exercising. The doctor has its own suite; the subject here is the
    # builder's acceptance pattern.
    return subprocess.run(
        ["bash", str(BUILDER), "t-id", str(base), str(src), "t-build", "auto",
         "--change-summary", str(summary), "--skip-doctor"],
        capture_output=True, text=True, timeout=120,
    )


STOCK_REJECTED = "stock input must contain FwPkt/firmwareInfo"


def test_zip_with_firmware_info_is_accepted(tmp_path):
    base = tmp_path / "FwPkt.zip"
    _make_zip(base, with_firmware_info=True)
    r = _run(tmp_path, base)
    out = r.stdout + r.stderr
    assert STOCK_REJECTED not in out, (
        "a valid FwPkt.zip was rejected by the acceptance check -- this is the "
        f"`unzip -l` padding bug: {out[:400]}"
    )


def test_zip_without_firmware_info_is_still_refused(tmp_path):
    """The fix must not turn the check into a no-op. A zip with no firmwareInfo is a
    genuinely unusable packet and has to be rejected.

    This asserts PRESENCE, so it cannot pass by the script dying earlier -- which is how
    the first version of these tests was vacuous.
    """
    base = tmp_path / "FwPkt.zip"
    _make_zip(base, with_firmware_info=False)
    r = _run(tmp_path, base)
    out = r.stdout + r.stderr
    assert STOCK_REJECTED in out, (
        f"expected refusal for a zip with no firmwareInfo; got: {out[:400]}"
    )


def test_directory_with_firmware_info_is_accepted(tmp_path):
    """The directory form was always the working path; keep it working."""
    base = tmp_path / "packet"
    (base / "FwPkt").mkdir(parents=True)
    (base / "FwPkt" / "firmwareInfo").write_text("firmwareInfo\n")
    r = _run(tmp_path, base)
    assert STOCK_REJECTED not in (r.stdout + r.stderr)
