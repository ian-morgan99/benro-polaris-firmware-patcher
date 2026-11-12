"""Regression tests for R5 in scripts/release/check-release-gates.py.

Why these exist
---------------
R3 proves only that a build commit is an ancestor of origin/main. On 2026-11-12 the
v106 candidate was built from patcher commit 73e3066123b7, which satisfies R3, so
the gate printed "OK" and "(build commit is contained in origin/main)" while main
had moved 20 commits ahead. Two of those commits change files that ship INSIDE the
packet:

    container/astro/ondisk/polaris-autosolve.sh   #321 solve duration + frame dims
    container/astro/ondisk/polaris-align.sh       #321 TIMEOUT classification

The built copies differed by digest and lacked the #321 code entirely (the packet
copy of polaris-autosolve.sh has zero occurrences of FRAME_DIMS_FILE where main has
three), yet every gate was green. Ancestry answers "was this merged", never "is this
current".

Each test below fails against the pre-R5 script and passes with R5 present:

  * stale shipped payload is refused, naming the drifted file
  * a packet built from the current tip is accepted (so the check is not just always
    failing)
  * a packet where the comparison cannot run reports FAIL, never OK -- the vacuous
    pass class behind issue #286
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "release" / "check-release-gates.py"


def run(*args: str, cwd: Path | None = None) -> str:
    return subprocess.check_output(
        list(args), cwd=cwd, text=True, stderr=subprocess.STDOUT
    ).strip()


def make_patcher_repo(path: Path) -> tuple[Path, str]:
    """A patcher-shaped repo with a real origin/main and one shipped ondisk script.

    Returns (repo, first_commit). A local clone is used as 'origin' so that
    refs/remotes/origin/main exists and R3's merge-base actually judges something.
    """
    repo = path / "patcher"
    repo.mkdir()
    run("git", "init", "-b", "main", str(repo))
    run("git", "-C", str(repo), "config", "user.email", "test@example.invalid")
    run("git", "-C", str(repo), "config", "user.name", "Test")

    ondisk = repo / "container" / "astro" / "ondisk"
    ondisk.mkdir(parents=True)
    (ondisk / "polaris-autosolve.sh").write_text("#!/bin/sh\necho v1\n", encoding="utf-8")
    (ondisk / "install_astro.sh").write_text("#!/bin/sh\necho install\n", encoding="utf-8")
    # The bundle builder, which generates README.txt. Shipped text comes from here,
    # not from ondisk, so R5 must watch it too.
    (repo / "build-astro.sh").write_text(
        "#!/bin/sh\ncat > README.txt <<EOF\nDrag COPY-TO-SD-CARD-ROOT onto the card.\nEOF\n",
        encoding="utf-8",
    )
    run("git", "-C", str(repo), "add", "-A")
    run("git", "-C", str(repo), "commit", "-m", "baseline")
    first = run("git", "-C", str(repo), "rev-parse", "HEAD")

    # A second, unrelated commit that does NOT touch shipped paths. This proves R5
    # is scoped: main moving forward on docs must not block a release.
    (repo / "README.md").write_text("docs only\n", encoding="utf-8")
    run("git", "-C", str(repo), "add", "-A")
    run("git", "-C", str(repo), "commit", "-m", "docs: unrelated to shipped payload")

    # Publish as a real remote so origin/main is a genuine ref.
    remote = path / "origin.git"
    run("git", "clone", "--quiet", "--bare", str(repo), str(remote))
    run("git", "-C", str(repo), "remote", "add", "origin", str(remote))
    run("git", "-C", str(repo), "fetch", "--quiet", "origin")
    return repo, first


def make_packet(path: Path, repo: Path, commit: str) -> Path:
    """A candidate directory whose shipped scripts come from <commit>."""
    packet = path / "candidate"
    astro = packet / "astro-bundle" / "COPY-TO-SD-CARD-ROOT" / "polaris-astro"
    astro.mkdir(parents=True)
    for name in ("polaris-autosolve.sh", "install_astro.sh"):
        blob = run("git", "-C", str(repo), "show", "%s:container/astro/ondisk/%s" % (commit, name))
        (astro / name).write_text(blob + "\n", encoding="utf-8")
    # R4 wants both archives present; their contents are irrelevant to R5.
    (packet / "FwPkt.zip").write_bytes(b"zip\n")
    (packet / "polaris-astro.zip").write_bytes(b"zip\n")
    return packet


def make_state(path: Path) -> Path:
    state = path / "state.md"
    state.write_text(
        "consumed_display_fwver=6.0.0.54.106\nlast_display_fwver=6.0.0.54.106\n",
        encoding="utf-8",
    )
    return state


def gate(repo: Path, packet: Path, commit: str, state: Path) -> tuple[int, str]:
    r = subprocess.run(
        [
            "python3", str(GATE),
            "--fwver", "6.0.0.54.107",
            "--patcher-commit", commit,
            "--packet-dir", str(packet),
            "--repo", str(repo),
            "--state", str(state),
        ],
        capture_output=True, text=True,
    )
    return r.returncode, r.stdout + r.stderr


def test_r5_refuses_stale_shipped_payload(tmp_path: Path):
    repo, first = make_patcher_repo(tmp_path)
    state = make_state(tmp_path)

    # Packet built from the FIRST commit, then main changes a shipped script.
    packet = make_packet(tmp_path, repo, first)
    ondisk = repo / "container" / "astro" / "ondisk"
    (ondisk / "polaris-autosolve.sh").write_text(
        "#!/bin/sh\nFRAME_DIMS_FILE=/tmp/polaris-frame-dims\necho v2\n", encoding="utf-8")
    run("git", "-C", str(repo), "commit", "-am", "fix(#321): log solve duration")
    run("git", "-C", str(repo), "push", "--quiet", "origin", "main")

    rc, out = gate(repo, packet, first, state)
    assert rc != 0, "a packet shipping stale ondisk scripts must not pass the gate:\n" + out
    assert "R5" in out, out
    assert "polaris-autosolve.sh" in out, "R5 must name the drifted file:\n" + out
    # R3 still passes -- that is precisely the bug this test pins down.
    assert "R3 code merged to main           : OK" in out, out


def test_r5_accepts_packet_built_from_current_tip(tmp_path: Path):
    """Positive control: the check must not simply always fail."""
    repo, first = make_patcher_repo(tmp_path)
    state = make_state(tmp_path)
    head = run("git", "-C", str(repo), "rev-parse", "origin/main")
    packet = make_packet(tmp_path, repo, head)

    rc, out = gate(repo, packet, head, state)
    assert rc == 0, "a current packet should pass every gate:\n" + out
    assert "R5 shipped payload current       : OK" in out, out


def test_r5_scoped_to_shipped_paths(tmp_path: Path):
    """Main moving forward on non-shipped files must not block a release."""
    repo, first = make_patcher_repo(tmp_path)
    state = make_state(tmp_path)
    # 'first' is already behind origin/main by one docs-only commit.
    packet = make_packet(tmp_path, repo, first)
    rc, out = gate(repo, packet, first, state)
    assert rc == 0, "a docs-only advance on main must not fail R5:\n" + out
    assert "R5 shipped payload current       : OK" in out, out


def test_r5_fails_closed_when_comparison_cannot_run(tmp_path: Path):
    """A packet with no shipped scripts must report FAIL, never a vacuous OK."""
    repo, first = make_patcher_repo(tmp_path)
    state = make_state(tmp_path)
    head = run("git", "-C", str(repo), "rev-parse", "origin/main")

    empty = tmp_path / "empty-packet"
    empty.mkdir()
    (empty / "FwPkt.zip").write_bytes(b"zip\n")
    (empty / "polaris-astro.zip").write_bytes(b"zip\n")

    rc, out = gate(repo, empty, head, state)
    assert rc != 0, "R5 must fail when it cannot locate the shipped scripts:\n" + out
    assert "R5 shipped payload current       : FAIL" in out, out
    assert "Refusing to report OK for a comparison that did not run" in out, out


def test_r5_detects_tampered_copy_matching_neither_commit(tmp_path: Path):
    """Integrity arm: a packet file that matches no commit is caught even when the
    build commit equals origin/main."""
    repo, _ = make_patcher_repo(tmp_path)
    state = make_state(tmp_path)
    head = run("git", "-C", str(repo), "rev-parse", "origin/main")
    packet = make_packet(tmp_path, repo, head)

    tampered = packet / "astro-bundle" / "COPY-TO-SD-CARD-ROOT" / "polaris-astro" / "install_astro.sh"
    tampered.write_text("#!/bin/sh\necho modified after build\n", encoding="utf-8")

    rc, out = gate(repo, packet, head, state)
    assert rc != 0, "a shipped script that differs from its recorded commit must fail:\n" + out
    assert "install_astro.sh" in out, out


def test_r5_catches_a_stale_readme_generator(tmp_path: Path):
    """Currency arm for GENERATED shipped text.

    README.txt is a heredoc inside build-astro.sh, so a stale generator yields a
    stale bundle while every copied ondisk script matches byte-for-byte. An
    ondisk-only scope reports OK on that packet. This is the exact shape of the
    miss found on 2026-11-12: the astro builder requires branch
    feature/astro-native-platesolve, whose tip was 8 commits behind main and still
    emitted the scp instruction removed in edc5f4d.
    """
    repo, first = make_patcher_repo(tmp_path)
    state = make_state(tmp_path)

    # Packet built from 'first'; ondisk is untouched afterwards, so the integrity
    # arm and the ondisk currency check both stay clean.
    packet = make_packet(tmp_path, repo, first)

    # main changes only the generator.
    (repo / "build-astro.sh").write_text(
        "#!/bin/sh\ncat > README.txt <<EOF\nDrag COPY-TO-SD-CARD-ROOT onto the card.\n"
        "Do NOT use scp; this device has no sftp-server subsystem.\nEOF\n",
        encoding="utf-8",
    )
    run("git", "-C", str(repo), "commit", "-am", "fix(docs): stop telling users to run scp")
    run("git", "-C", str(repo), "push", "--quiet", "origin", "main")

    rc, out = gate(repo, packet, first, state)
    assert rc != 0, (
        "a build whose README generator is behind main must not pass:\n" + out
    )
    assert "build-astro.sh" in out, (
        "R5 must name the stale generator:\n" + out
    )
