"""Skills must describe tooling that actually exists.

AGENTS.md makes the skills under .github/skills/ the source of truth: "read that
skill first and follow it exactly. Do not invent an alternative approach." That
only works if a referenced command can actually be run. A skill naming a script
that does not exist, or citing a line range that says something else, sends the
next agent down a path that silently no-ops -- the same class of failure as the
Canon-only death-watch guard, where the tool built to catch a problem was the
reason it went unseen.

Scope is deliberately narrow and mechanical:

- every repo-relative scripts/ docs/ tests/ path in a skill must resolve
- every file:line citation must point inside the cited file
- frontmatter must parse and its name must match the directory
- AGENTS.md must mention every skill, or it will not be discovered
- issue references are resolved only when gh is available (SKIP, never green)

Skill-local scripts are invoked by full path. The reference regexes anchor on a
preceding non-path character so skill-local scripts do not look like repo-root
references.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / ".github" / "skills"

# A path must not be preceded by '/', '.', or a word character, so that
# ".github/skills/x/scripts/foo.sh" is not mistaken for "scripts/foo.sh".
_PREFIX = r"(?<![A-Za-z0-9._/-])"


def _skill_files() -> list[Path]:
    if not SKILLS.exists():
        pytest.skip(".github/skills is missing")
    files = sorted(SKILLS.glob("*/SKILL.md"))
    if not files:
        pytest.skip("no SKILL.md files found")
    return files


def _text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def _refs(text: str, kind: str, ext: str) -> set[str]:
    return set(re.findall(rf"{_PREFIX}({kind}/[A-Za-z0-9._/-]+\.{ext})", text))


@pytest.mark.parametrize("skill", _skill_files(), ids=lambda p: p.parent.name)
def test_referenced_scripts_exist(skill: Path):
    """Every repo-root scripts/... path a skill tells an agent to run is real."""
    refs = _refs(_text(skill), "scripts", "sh") | _refs(_text(skill), "scripts", "py")
    missing = sorted(r for r in refs if not (REPO / r).is_file())
    assert not missing, (
        f"{skill.parent.name} references non-existent scripts: {missing}. "
        f"AGENTS.md says follow skills exactly, so a dead path is an instruction "
        f"to run something that cannot run.")


@pytest.mark.parametrize("skill", _skill_files(), ids=lambda p: p.parent.name)
def test_referenced_docs_exist(skill: Path):
    refs = _refs(_text(skill), "docs", "md")
    missing = sorted(r for r in refs if not (REPO / r).is_file())
    assert not missing, f"{skill.parent.name} cites non-existent docs: {missing}"


@pytest.mark.parametrize("skill", _skill_files(), ids=lambda p: p.parent.name)
def test_referenced_tests_exist(skill: Path):
    refs = _refs(_text(skill), "tests", "py")
    missing = sorted(r for r in refs if not (REPO / r).is_file())
    assert not missing, f"{skill.parent.name} references non-existent tests: {missing}"


@pytest.mark.parametrize("skill", _skill_files(), ids=lambda p: p.parent.name)
def test_skill_has_valid_frontmatter(skill: Path):
    """A skill without parseable frontmatter is never loaded by the agent."""
    m = re.match(r"^---\n(.*?)\n---\n", _text(skill), re.S)
    assert m, f"{skill.parent.name}/SKILL.md has no YAML frontmatter block"
    body = m.group(1)
    assert re.search(r"^name:\s*\S+", body, re.M), (
        f"{skill.parent.name}: frontmatter missing 'name:'")
    assert re.search(r"^description:\s*\S+", body, re.M), (
        f"{skill.parent.name}: frontmatter missing 'description:'")
    found = re.search(r"^name:\s*(\S+)", body, re.M).group(1)
    assert found == skill.parent.name, (
        f"frontmatter name '{found}' != directory '{skill.parent.name}'; the two "
        f"must agree or the skill cannot be resolved by name")


def test_file_line_citations_are_accurate():
    """`script.sh:422-430` must point at lines that exist.

    Line citations rot silently on every edit to the cited file, and a stale one
    reads as verified evidence -- worse than having no citation at all.
    """
    bad: list[str] = []
    for skill in _skill_files():
        text = _text(skill)
        for script, start, end in re.findall(
                rf"{_PREFIX}([A-Za-z0-9._/-]+\.(?:sh|py)):(\d+)(?:-(\d+))?", text):
            target = REPO / script
            if not target.is_file():
                target = REPO / "scripts" / script
            if not target.is_file():
                bad.append(f"{skill.parent.name}: cites {script}, which is absent")
                continue
            n_lines = len(target.read_text(
                encoding="utf-8", errors="replace").splitlines())
            lo, hi = int(start), int(end) if end else int(start)
            if hi > n_lines:
                bad.append(
                    f"{skill.parent.name}: cites {script}:{lo}-{hi} but the file "
                    f"has {n_lines} lines")
    assert not bad, "stale or wrong line citations:\n  " + "\n  ".join(bad)


def test_issue_references_resolve():
    """Cited issue numbers must exist. Skips (never greens) without gh auth."""
    if shutil.which("gh") is None:
        pytest.skip("gh not installed; cannot resolve issue references")
    nums: set[str] = set()
    for skill in _skill_files():
        nums.update(re.findall(r"#(\d{2,3})\b", _text(skill)))
    if not nums:
        pytest.skip("no issue references found in skills")

    r = subprocess.run(
        ["gh", "issue", "list", "-R", "ian-morgan99/benro-polaris-firmware-patcher",
         "--state", "all", "--limit", "500", "--json", "number",
         "-q", ".[].number"],
        capture_output=True, text=True)
    if r.returncode != 0:
        pytest.skip(f"gh not authenticated: {r.stderr.strip()[:120]}")
    known = {n.strip() for n in r.stdout.split()}
    missing = sorted(n for n in nums if n not in known)
    assert not missing, f"skills cite issues that do not exist: {missing}"


def test_agents_md_lists_every_skill():
    """AGENTS.md is the index; a skill it omits will not be discovered.

    This is how a new documented process becomes invisible -- the file exists but
    nothing points at it, so agents keep using the older one.
    """
    agents = REPO / "AGENTS.md"
    if not agents.exists():
        pytest.skip("AGENTS.md missing")
    text = _text(agents)
    dirs = {p.parent.name for p in SKILLS.glob("*/SKILL.md")}
    omitted = sorted(d for d in dirs if d not in text)
    assert not omitted, f"AGENTS.md does not mention these skills: {omitted}"


def test_documented_doc_generator_gap_is_stated_not_implied():
    """polaris-release-orchestrator's DOCS_GENERATED phase has no script.

    No script in the repo emits INSTALL.md or CHANGELOG.md -- verified here, not
    assumed. create-release-change-manifest.py writes release-change-manifest.json
    and RELEASE-IDENTITY.md only. If the skill presents that phase as script-driven,
    an agent runs the command, sees it succeed, marks DOCS_GENERATED complete, and
    has produced neither document -- exactly the "looks installed but is not"
    failure #350 exists to prevent.

    This pins the known gap so the caveat cannot be quietly deleted, and stops
    being a requirement once a real generator lands.
    """
    skill = SKILLS / "polaris-release-orchestrator" / "SKILL.md"
    if not skill.exists():
        pytest.skip("polaris-release-orchestrator not present")

    generators = [p for p in (REPO / "scripts").rglob("*")
                  if p.is_file() and p.suffix in {".py", ".sh"}
                  and re.search(r"INSTALL\.md|CHANGELOG\.md", _text(p), re.I)]
    if generators:
        return  # a generator now exists; the caveat is obsolete

    assert "NOT YET IMPLEMENTED" in _text(skill), (
        "DOCS_GENERATED names no real generator, but the skill no longer says so. "
        "Either implement a script that emits INSTALL.md/CHANGELOG.md, or state "
        "the gap -- do not leave a phase that reads as automated but is not.")
