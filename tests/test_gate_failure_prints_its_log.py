"""A gate failure must print the log it names.

Why this exists
---------------
Every check in tests/run_prerelease_gate.sh redirects its output to
/tmp/prerelease-*.log and, on failure, reported only the path:

    FAIL: container deterministic harness (exit 1; log: /tmp/prerelease-deterministic.log)

Locally that is recoverable -- the file is still there. In CI it is not: the runner
is discarded, so the message is a dead end. On 2026-11-12 PR #334, a docs-only change,
failed exactly this check and nothing about *why* was recoverable from the run log. The
only way to learn anything was to re-run, which passed, so it was recorded as a flake
with no evidence either way.

A gate that cannot explain its own red verdict is not usable as a gate -- same class of
problem as reporting OK for a check that never ran (issue #286).

These tests extract bad() from the gate script and execute it in isolation, asserting on
produced output rather than grepping source, so the behaviour is verified rather than
the wording.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "tests" / "run_prerelease_gate.sh"


def bad_function() -> str:
    """Extract the bad() definition from the gate script."""
    text = GATE.read_text(encoding="utf-8")
    m = re.search(r"^bad\(\) \{.*?^\}", text, re.S | re.M)
    assert m, "could not find a multi-line bad() definition in run_prerelease_gate.sh"
    return m.group(0)


def run_bad(message: str, logs: dict[str, str] | None = None) -> str:
    """Call bad() with <message> and return everything it prints."""
    body = "pass=0; fail=0; skip=0; failed=''; skipped=''\n"
    body += "skp() { echo \"SKIP: $1\"; }\n"
    body += bad_function() + "\n"
    body += 'bad "%s"\n' % message.replace('"', '\\"')
    body += 'echo "failcount=$fail"\n'
    r = subprocess.run(
        ["bash", "-c", body], capture_output=True, text=True, timeout=60,
    )
    return r.stdout + r.stderr


def test_failure_prints_the_log_it_names(tmp_path: Path):
    log = tmp_path / "prerelease-deterministic.log"
    log.write_text(
        "--- test_thing.sh ---\nFAIL: test_thing.sh (exit 3)\n=== Summary: 5 passed, 1 failed ===\n",
        encoding="utf-8",
    )
    out = run_bad("container deterministic harness (exit 1; log: %s)" % log)
    assert "FAIL: container deterministic harness" in out, out
    # The point of the change: the reason is now in the output, not just a path.
    assert "FAIL: test_thing.sh (exit 3)" in out, (
        "bad() must dump the named log so a CI failure is diagnosable without a "
        "re-run:\n" + out
    )
    assert "Summary: 5 passed, 1 failed" in out, out


def test_trailing_punctuation_does_not_break_the_path(tmp_path: Path):
    """Real messages end the path with ')', e.g. '(log: /tmp/x.log)'."""
    log = tmp_path / "x.log"
    log.write_text("the reason\n", encoding="utf-8")
    out = run_bad("some check (exit 1; log: %s)" % log)
    assert "the reason" in out, (
        "the trailing ')' must not be captured as part of the filename:\n" + out
    )


def test_message_without_a_log_is_unaffected(tmp_path: Path):
    out = run_bad("a check with no log reference at all")
    assert "FAIL: a check with no log reference at all" in out, out
    assert "begin" not in out, out
    assert "failcount=1" in out, out


def test_missing_log_is_reported_not_silent(tmp_path: Path):
    out = run_bad("check failed (log: %s)" % (tmp_path / "absent.log"))
    assert "does not exist" in out, (
        "a named-but-absent log must say so rather than print nothing:\n" + out
    )


def test_fail_counter_still_increments_once():
    """The rewrite must not change the gate's accounting."""
    out = run_bad("one failure (log: /tmp/does-not-exist.log)")
    assert "failcount=1" in out, out


def test_multiple_logs_all_dumped(tmp_path: Path):
    a, b = tmp_path / "a.log", tmp_path / "b.log"
    a.write_text("reason-a\n", encoding="utf-8")
    b.write_text("reason-b\n", encoding="utf-8")
    out = run_bad("both (log: %s and %s)" % (a, b))
    assert "reason-a" in out and "reason-b" in out, out
