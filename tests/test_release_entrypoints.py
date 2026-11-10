"""The release entrypoint index must be true, and complete.

Six months of release engineering live in prose across a dozen documents, so each
session re-derived the commands and hand-rolled the gaps. That produced real faults:
staging a kit with scp (impossible against this device -- sshd has no sftp-server
subsystem), copying polaris-astro/ only and leaving polaris-wifi/ stale, and flashing
without re-installing the astro kit so the device returned with the correct version
and port 8090 closed.

docs/RELEASE-ENTRYPOINTS.md is the fix, but a doc that drifts from the tree is worse
than none because it is trusted. These tests make it self-enforcing: every command it
names must exist and be executable, and every release script in the tree must be named
by it.
"""

from pathlib import Path
import re
import stat

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/RELEASE-ENTRYPOINTS.md"


def _commands_in_doc():
    """Repo-relative commands from the table's command column.

    Rows look like: | Operation | `./scripts/foo.sh --flag` | Verifies |
    The first backtick span of column 2 is the command.
    """
    commands = []
    for line in DOC.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2 or not cells[1].startswith("`"):
            continue
        span = re.match(r"`([^`]+)`", cells[1])
        if not span:
            continue
        cmd = span.group(1).strip()
        # Drop env assignments and the trailing prose of multi-command cells.
        cmd = cmd.split("&&")[0].split(";")[0].strip()
        tokens = cmd.split()
        if not tokens:
            continue
        if tokens[0] in ("python3", "bash", "sh"):
            tokens = tokens[1:]
        head = tokens[0]
        if not head.startswith(("./", "scripts/", "docs/")):
            continue  # prose rows, or paths this test does not resolve
        commands.append((cells[0], head))
    return commands


def test_index_exists():
    assert DOC.is_file(), f"{DOC} is missing"


def test_every_command_in_the_index_exists_and_is_executable():
    problems = []
    for operation, head in _commands_in_doc():
        target = ROOT / head.removeprefix("./")
        if not target.exists():
            problems.append(f"{operation}: {head} does not exist")
            continue
        if target.suffix in (".sh", ".py") and not (target.stat().st_mode & stat.S_IXUSR):
            problems.append(f"{operation}: {head} is not executable")
    assert not problems, "RELEASE-ENTRYPOINTS.md names commands that are unusable:\n  " + \
        "\n  ".join(problems)


def test_every_release_script_is_indexed():
    """A release script nobody can find gets hand-rolled instead."""
    indexed = DOC.read_text(encoding="utf-8")
    missing = []
    for script in sorted((ROOT / "scripts/release").iterdir()):
        if not script.is_file() or script.suffix not in (".sh", ".py"):
            continue
        if script.name not in indexed:
            missing.append(script.name)
    assert not missing, (
        "scripts/release/ contains scripts the index does not mention, so they will "
        "be re-derived by hand: " + ", ".join(missing)
    )


def test_index_names_the_installers_that_prevent_known_faults():
    text = DOC.read_text(encoding="utf-8")
    # The flash path must carry the kit step, or a flash silently removes the solver.
    assert "install-astro-kit.sh" in text, "index must name the astro kit installer"
    assert "release-fwpkt.sh" in text, "index must name the supported flash path"
    assert "build-doctor.sh" in text, "index must name the host prerequisite check"
    # scp is not a workaround here; saying so prevents the retry loop.
    assert "sftp-server" in text, "index must explain why scp cannot be used"


def test_index_disambiguates_the_two_build_astro_scripts():
    # Two tracked files share this name and behave differently; picking the wrong
    # one skips the doctor, provisioning and artifact verification entirely.
    assert (ROOT / "build-astro.sh").is_file()
    assert (ROOT / "scripts/build-astro.sh").is_file()
    text = DOC.read_text(encoding="utf-8")
    assert "Two files named `build-astro.sh`" in text, (
        "index must disambiguate the two build-astro.sh scripts"
    )


def test_index_is_linked_from_the_agent_onboarding_section():
    # An index nobody is routed to at session start is an index nobody reads.
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "RELEASE-ENTRYPOINTS.md" in readme, (
        "README.md must link the entrypoint index from agent onboarding"
    )
