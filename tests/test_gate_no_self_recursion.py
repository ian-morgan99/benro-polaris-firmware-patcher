"""The pre-release gate must never re-invoke itself.

Why this exists
---------------
A usage example was pasted into the header comment block of
tests/run_prerelease_gate.sh without its leading '#':

    #   ./tests/run_prerelease_gate.sh --require-arm-emulation \
    #       --arm-harness-src /path/to/.../src
    #
       ./tests/run_prerelease_gate.sh --require-bulb-cancel-return
    #

Bash executes that fourth line. The gate re-invoked itself forever, produced
80,000 processes, and every gate log for the v108 candidate contained nothing
but "bash: warning: shell level (1000) too high, resetting to 1" -- no verdict
at all.

That is the worst failure mode a release gate can have. It does not read as a
failure, it reads as an inconclusive run, so the candidate simply never gets a
green light and nobody is told why. The build reported "step 5/7 produced no
verdict" rather than "the gate recursed", because the recursion consumed the
output before any check could run.

The existing bare-fragment guard (tests/test_shell_no_bare_fragments.sh) only
matches lines that are entirely 1-5 lowercase letters, so a full command with
arguments passes it. A static scanner is not a substitute here: continuation
lines inside arrays such as PY_TESTS are also sandwiched between comment lines,
so any pattern loose enough to catch this catches those too.

So the guard is behavioural. A nested invocation is never legitimate -- no test
in the suite executes the gate, they only assert on its text -- so the script
refuses immediately with exit 3 instead of forking until the machine stops.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "tests" / "run_prerelease_gate.sh"


def run_gate(env_extra: dict[str, str]) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "POLARIS_GATE_RUNNING"}
    env.update(env_extra)
    return subprocess.run(
        ["bash", str(GATE)],
        capture_output=True, text=True, timeout=120, env=env, cwd=str(ROOT),
    )


def test_gate_refuses_a_nested_invocation():
    """With the guard variable set, the gate must exit immediately, not recurse."""
    r = run_gate({"POLARIS_GATE_RUNNING": "1"})
    assert r.returncode == 3, (
        "expected exit 3 from the recursion guard, got %d.\nstdout: %s\nstderr: %s"
        % (r.returncode, r.stdout[:400], r.stderr[:400])
    )
    combined = r.stdout + r.stderr
    assert "already running" in combined, (
        "the guard must say why it refused, so a nested run is diagnosable: "
        + combined[:400]
    )
    assert "run_prerelease_gate.sh" in combined


def test_guard_variable_is_exported_before_any_work():
    """The guard must be set before the script can spawn anything.

    If it were installed after the first subprocess, the first nested child
    would already have been forked and the guard would only stop the second
    generation -- which still means a fork bomb, just a slower one.
    """
    text = GATE.read_text(encoding="utf-8")
    guard_at = text.index("POLARIS_GATE_RUNNING:-")
    export_at = text.index("export POLARIS_GATE_RUNNING")

    # Everything that can spawn: the gate runs pytest, docker, ssh and python.
    first_spawn = min(
        (text.index(tok) for tok in ("subprocess", "python3 -m pytest", "docker ", " ssh ")
         if tok in text),
        default=len(text),
    )
    assert export_at < first_spawn, (
        "the recursion guard must be exported before the gate spawns any child "
        "(guard export at %d, first spawn at %d)" % (export_at, first_spawn)
    )
    assert guard_at < export_at


def test_no_uncommented_command_in_the_header_block():
    """The specific defect: a command line inside the leading comment block.

    Scoped to the header region only, which is every line up to the script's
    first statement. A repo-wide pattern is not viable: continuation lines in
    PY_TESTS and shell-array bodies also begin with a path and are also
    sandwiched between comments, so any rule loose enough to catch this catches
    those too, and a guard that cries wolf gets switched off rather than obeyed.

    Inside the header there is no ambiguity -- every line must be a comment or
    blank, because bash executes anything else the moment the file is sourced.
    """
    lines = GATE.read_text(encoding="utf-8").splitlines()

    # The header ends at the first statement. `set -uo pipefail` is the script's
    # own opening line of code and is asserted by tests elsewhere; if it ever
    # moves, fail loudly rather than silently checking nothing.
    try:
        header_end = next(i for i, l in enumerate(lines) if l.startswith("set -uo pipefail"))
    except StopIteration:
        raise AssertionError(
            "could not find 'set -uo pipefail' in the gate; the header boundary is "
            "undefined, so this test would check nothing"
        )

    offenders = [
        (i + 1, line) for i, line in enumerate(lines[:header_end])
        if line.strip() and not line.startswith("#")
    ]
    assert not offenders, (
        "line(s) inside the gate's header comment block are not comments, so bash "
        "executes them. A usage example missing its '#' re-invokes the gate and it "
        "recurses until the machine runs out of processes: " + str(offenders[:3])
    )


if __name__ == "__main__":
    sys.exit(subprocess.run([sys.executable, "-m", "pytest", __file__, "-q"]).returncode)
