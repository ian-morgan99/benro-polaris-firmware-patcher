"""The authoritative-source lookup must actually resolve the case it exists for.

Why this is pinned rather than left to manual use: AGENTS.md tells agents to
follow skills exactly, and polaris-evidence-discipline tells them to run
scripts/find-authoritative-source.py before claiming a defect is not ours. If
that script silently returns nothing -- research tree moved, root default wrong,
grep flags changed -- the guard reads as "confirmed: no vendor source", which is
the precise false conclusion it was written to prevent. A check that cannot tell
"nothing found" from "nothing looked at" is the same bug class as the rig tools
that grepped a non-existent /app/Clog.txt and reported a wedged gate as clean.

The pinned case is real: on 2026-11-27 K-1 II AF (#359) was routed upstream
because updateCameraAutoFocus appeared in no source file in our repos. It does
appear -- in the pgphoto Ghidra decompilation on this workstation.

Skips (never greens) when the research tree is not present, matching how
test_skills_reference_real_tooling.py handles gh auth.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "find-authoritative-source.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True, timeout=300)


def test_script_exists_and_is_registered_in_the_gate():
    assert SCRIPT.is_file(), "authoritative-source lookup is missing"
    gate = (REPO / "tests" / "run_prerelease_gate.sh").read_text(
        encoding="utf-8", errors="replace")
    assert Path(__file__).name in gate, (
        f"{Path(__file__).name} is not registered in tests/run_prerelease_gate.sh; "
        "an unregistered test never runs, which is how a guard stops being a guard.")


def test_skill_requires_the_lookup_before_any_not_ours_claim():
    skill = REPO / ".github" / "skills" / "polaris-evidence-discipline" / "SKILL.md"
    assert skill.is_file(), "polaris-evidence-discipline skill is missing"
    text = skill.read_text(encoding="utf-8", errors="replace")
    assert "find-authoritative-source.py" in text, (
        "the skill no longer names the lookup script, so the rule is unenforceable")
    # AGENTS.md is the discovery index; an unlisted skill is never read.
    agents = (REPO / "AGENTS.md").read_text(encoding="utf-8", errors="replace")
    assert "polaris-evidence-discipline" in agents, (
        "AGENTS.md does not list polaris-evidence-discipline; it will not be discovered")


def test_lookup_resolves_the_symbol_that_was_misattributed():
    """updateCameraAutoFocus must be found in vendor source, not reported absent."""
    root = REPO.parent / "pr-publish" / "pgphoto-re" / "decompiled"
    if not root.is_dir():
        pytest.skip(f"research tree not present here: {root}")

    r = _run("updateCameraAutoFocus")
    assert r.returncode == 0, f"lookup failed: {r.stderr[:200]}"
    out = r.stdout

    assert "[pgphoto      ]" in out, "pgphoto source is not being searched at all"
    assert "VENDOR SOURCE HITS" in out, (
        "updateCameraAutoFocus was not found in vendor source. Either the "
        "decompilation moved or the search broke -- both mean the 'not our code' "
        "guard silently no-ops.")
    assert "NO SOURCE MATCHED" not in out, (
        "the lookup returned nothing for a symbol that is demonstrably present; "
        "an agent following the skill would read that as confirmation the defect "
        "is upstream.")


def test_missing_root_is_reported_not_silently_skipped():
    """A missing source must print MISSING, never vanish from the report."""
    empty = REPO / "tests" / "testdata" / "empty-research-root"
    empty.mkdir(parents=True, exist_ok=True)
    try:
        r = _run("--root", str(empty), "updateCameraAutoFocus")
        assert r.returncode == 0, f"lookup failed on an empty root: {r.stderr[:200]}"
        assert "MISSING (expected present)" in r.stdout, (
            "an absent must-exist source was not reported. Silent skips are how the "
            "pgphoto decompilation stayed invisible while #359 was routed upstream.")
        assert "NO SOURCE MATCHED" in r.stdout, (
            "a zero-hit result must tell the reader what to do next instead of "
            "reading as a clean answer.")
    finally:
        empty.rmdir()


def test_opcode_lookup_is_literal_not_regex():
    """code[262] must not match getPostCode2().

    With regex on, an opcode lookup returned five Benro Connect hits that had
    nothing to do with opcode 262. Confident-but-wrong evidence is worse than
    none, because it gets cited.
    """
    root = REPO.parent / "PrivateResearch"
    if not root.is_dir():
        pytest.skip(f"research tree not present here: {root}")

    r = _run("--opcode", "262")
    assert r.returncode == 0, f"lookup failed: {r.stderr[:200]}"
    assert "getPostCode2" not in r.stdout, (
        "opcode lookup is matching as a regex character class; opcode evidence "
        "from this script cannot be trusted.")
