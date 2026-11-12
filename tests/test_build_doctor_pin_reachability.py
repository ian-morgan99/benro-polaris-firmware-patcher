"""build-doctor.sh must verify the pin against origin, not a local ref.

Why this exists
---------------
Section 3 is titled "libgphoto2 source: self-contained clone at a reachable pin",
and docs/RELEASE-ENTRYPOINTS.md advertises that it checks "libgphoto2 pin reachable
from origin". Until 2026-11-12 the script never contacted origin anywhere. It read
refs/remotes/origin/main off disk and tested ancestry against that, so:

  * a clone whose origin/main ref was months old still printed OK -- the claim was
    never verified, which is the vacuous-pass class behind issue #286;
  * a perfectly good pin could be reported orphaned because the local ref predated
    it (this exact false failure is recorded in the script's own header).

Both come from judging a local ref as if it were the remote. The fix asks origin
what its main actually is, refreshes if we are behind, and reports SKIP -- never
OK -- when origin cannot be reached.

The test below builds a repo whose refs/remotes/origin/main is deliberately stale
relative to its real origin remote, then asserts the doctor notices. Against the
old script this passes section 3 with OK and no mention of staleness.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCTOR = ROOT / "scripts" / "build-doctor.sh"


def run(*args: str, cwd: Path | None = None) -> str:
    return subprocess.check_output(
        list(args), cwd=cwd, text=True, stderr=subprocess.STDOUT
    ).strip()


def make_libgphoto2_repo(path: Path) -> tuple[Path, str, str]:
    """A libgphoto2-shaped clone whose refs/remotes/origin/main is stale.

    Returns (clone, old_tip, new_tip). The bare 'origin' has advanced to new_tip
    while the clone's remote-tracking ref still points at old_tip.
    """
    src = path / "libgphoto2-src"
    src.mkdir()
    run("git", "init", "-b", "main", str(src))
    run("git", "-C", str(src), "config", "user.email", "test@example.invalid")
    run("git", "-C", str(src), "config", "user.name", "Test")
    # configure.ac is what build-doctor.sh uses to recognise a libgphoto2 checkout.
    (src / "configure.ac").write_text("AC_INIT([libgphoto2])\n", encoding="utf-8")
    run("git", "-C", str(src), "add", "-A")
    run("git", "-C", str(src), "commit", "-m", "baseline")
    old_tip = run("git", "-C", str(src), "rev-parse", "HEAD")

    remote = path / "origin.git"
    run("git", "clone", "--quiet", "--bare", str(src), str(remote))
    run("git", "-C", str(src), "remote", "add", "origin", str(remote))
    run("git", "-C", str(src), "fetch", "--quiet", "origin")

    # Advance the remote, then clone --local so the new clone copies the OLD ref.
    (src / "newfile.c").write_text("/* merged upstream */\n", encoding="utf-8")
    run("git", "-C", str(src), "add", "-A")
    run("git", "-C", str(src), "commit", "-m", "upstream change")
    new_tip = run("git", "-C", str(src), "rev-parse", "HEAD")
    run("git", "-C", str(src), "push", "--quiet", "origin", "main")

    clone = path / "clone"
    run("git", "clone", "--quiet", "--local", str(remote), str(clone))
    # Force the clone's remote-tracking ref back to the old tip, simulating a clone
    # that copied a stale ref. HEAD stays on main so ancestry still holds locally.
    run("git", "-C", str(clone), "update-ref", "refs/remotes/origin/main", old_tip)
    return clone, old_tip, new_tip


def section3(output: str) -> str:
    m = re.search(r"== 3\..*?(?=\n== |\Z)", output, re.S)
    assert m, "build-doctor.sh produced no section 3:\n" + output[-3000:]
    return m.group(0)


ANSI = re.compile(r"\x1b\[[0-9;]*m")


def run_doctor(repo: Path, offline: bool = False) -> str:
    cmd = [str(DOCTOR), "--libgphoto2", str(repo)]
    if offline:
        cmd.append("--offline")
    # The doctor runs every section regardless of earlier failures (no set -e), so
    # docker or catalogue problems elsewhere do not prevent section 3 from running.
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    # The doctor colourises OK/FAIL/SKIP with escape sequences. Assertions below
    # match on words and on "SKIP <message>", so strip the codes first -- otherwise
    # a pattern like r"SKIP\s+--offline" never matches and the test fails for a
    # reason that has nothing to do with what it is checking.
    return ANSI.sub("", r.stdout + r.stderr)


def test_doctor_detects_a_stale_origin_ref(tmp_path: Path):
    clone, old_tip, new_tip = make_libgphoto2_repo(tmp_path)
    # No --offline: this test is specifically about contacting origin.
    out = section3(run_doctor(clone))

    assert "origin reachable" in out, (
        "the doctor must contact origin before claiming the pin is reachable:\n" + out
    )
    assert new_tip[:9] in out, (
        "the doctor must report origin/main as the LIVE tip (%s), not the stale local "
        "ref (%s):\n%s" % (new_tip[:9], old_tip[:9], out)
    )


def test_doctor_offline_reports_skip_not_ok(tmp_path: Path):
    """--offline must not silently claim the pin is reachable upstream.

    Deterministic by construction: --offline skips the ls-remote, so the only
    acceptable outcomes are SKIP or an explicit statement that it was not verified.
    Printing "HEAD is reachable from origin/main" here would be the vacuous pass.
    """
    clone, _, _ = make_libgphoto2_repo(tmp_path)
    out = section3(run_doctor(clone, offline=True))
    assert "origin reachable" not in out, (
        "--offline must not contact origin or claim it did:\n" + out
    )
    assert re.search(r"SKIP\s+.*--offline", out), (
        "when origin was not contacted the doctor must SKIP, not OK:\n" + out
    )
    assert "reachable from origin/main" not in out, (
        "the ancestry claim must not be printed when origin was never contacted:\n" + out
    )


def test_doctor_still_passes_a_current_clone(tmp_path: Path):
    """Positive control: a healthy clone is not failed by the new check."""
    src = tmp_path / "good"
    src.mkdir()
    run("git", "init", "-b", "main", str(src))
    run("git", "-C", str(src), "config", "user.email", "t@example.invalid")
    run("git", "-C", str(src), "config", "user.name", "T")
    (src / "configure.ac").write_text("AC_INIT([libgphoto2])\n", encoding="utf-8")
    run("git", "-C", str(src), "add", "-A")
    run("git", "-C", str(src), "commit", "-m", "baseline")
    remote = tmp_path / "origin.git"
    run("git", "clone", "--quiet", "--bare", str(src), str(remote))
    run("git", "-C", str(src), "remote", "add", "origin", str(remote))
    run("git", "-C", str(src), "fetch", "--quiet", "origin")

    out = section3(run_doctor(src))
    assert "HEAD is reachable from origin/main" in out, out
    assert "NOT reachable" not in out, out
