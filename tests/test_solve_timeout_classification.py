#!/usr/bin/env python3
"""Issue #321 follow-up: a timeout from polaris-solve-independent-search was
logged as "no match".

solve_finish() classifies one finished solve into the four outcomes #321 exists
to separate -- solved, timed out, found nothing, produced nothing. It matched
only polaris-solve.c's vocabulary:

    {"solved":false,"error":"timeout"}                                  rc=3

polaris-solve-independent-search.c reports a timeout differently (line 601):

    {"solved":false,"failure_reason":"timeout","attempts":5,...}        rc=7

and that string is only emitted once search_deadline has passed, so it is an
unambiguous timeout, never an inference. Because the case statement did not match
it, execution fell through to *"solved":false* -> "no match".

This was observed on hardware, not inferred. The solve.log salvaged from a K-3 III
running polaris-solve-independent-search contains:

    solve no match: 50.37s rc=7 stars=200 bin=polaris-solve-independent-search
      solver said: {"solved":false,"failure_reason":"timeout","attempts":5,...}

A 50-second search that hit its bound was recorded as "the sky has no match for
this frame", which is the opposite diagnosis and sends the reader chasing star
count or focus instead of the timeout.

The sibling value "search_exhausted" means every tile was tried inside the budget,
which genuinely IS "found nothing" -- so it must stay classified as a non-match,
and with its bound named so the two remain distinguishable.

These tests execute the REAL solve_finish() extracted from
container/astro/ondisk/polaris-align.sh. They are not source greps: assertions run
against log lines produced by executing the shipped function.
"""

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ALIGN = REPO / "container" / "astro" / "ondisk" / "polaris-align.sh"


def extract_function(name: str) -> str:
    """Pull one brace-balanced shell function out of polaris-align.sh verbatim."""
    lines = ALIGN.read_text(encoding="utf-8").splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith(f"{name}() {{") or line.startswith(f"{name}(){{"):
            start = i
            break
    if start is None:
        raise AssertionError(f"{name}() not found in {ALIGN}")
    depth = 0
    for j in range(start, len(lines)):
        depth += lines[j].count("{") - lines[j].count("}")
        if depth == 0 and j > start:
            return "\n".join(lines[start:j + 1])
    raise AssertionError(f"unterminated {name}() in {ALIGN}")


def run_solve_finish(tmp_path, solver_out: str, rc: int, solver_bin: str,
                     bound: str) -> str:
    """Execute the real solve_finish() and return what it wrote to SOLVE_LOG."""
    solve_log = tmp_path / "solve.log"
    script = tmp_path / "drive.sh"
    # solve_now reads /proc/uptime; pin both ends so the duration is deterministic
    # without changing the function under test.
    script.write_text(
        "#!/bin/sh\n"
        + extract_function("slog")
        + "\n"
        + "solve_now() { echo 1000.00; }\n"
        + extract_function("solve_finish")
        + "\n"
        + f"SOLVE_LOG='{solve_log}'\n"
        + "_star_count=200\n"
        + f"SOLVER_BIN='{solver_bin}'\n"
        + "_t0=950.00\n"
        + f"out={_shquote(solver_out)}\n"
        + f"solve_finish \"$_t0\" {rc} \"$out\" '' {_shquote(bound)}\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    subprocess.run(["/bin/sh", str(script)], check=True, capture_output=True, text=True)
    return solve_log.read_text(encoding="utf-8")


def _shquote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


# Exactly what the device emitted, copied from the salvaged solve.log.
SEARCH_TIMEOUT = ('{"solved":false,"failure_reason":"timeout","attempts":5,'
                  '"search_mode":"all-sky-triangle-index"}')
SEARCH_EXHAUSTED = ('{"solved":false,"failure_reason":"search_exhausted","attempts":40,'
                    '"search_mode":"all-sky-triangle-index"}')
LEGACY_TIMEOUT = '{"solved":false,"error":"timeout"}'
SOLVED = '{"solved":true,"logodds":9.1,"nmatch":42}'
NO_VERIFIED = '{"solved":false,"failure_reason":"no_verified_candidate","matched_count":7}'

SEARCH_BIN = "polaris-solve-independent-search"


def test_independent_search_timeout_is_not_logged_as_no_match(tmp_path):
    """The regression: failure_reason:"timeout" must classify as TIMEOUT.

    Before the fix this produced 'solve no match: ...' because only polaris-solve.c's
    "error":"timeout" was matched, and the case fell through to *"solved":false*.
    """
    log = run_solve_finish(tmp_path, SEARCH_TIMEOUT, 7, SEARCH_BIN, "45")
    assert "solve TIMEOUT" in log, log
    assert "no match" not in log, log


def test_independent_search_timeout_names_the_search_bound(tmp_path):
    """The bound quoted must be the one that actually fired.

    For this solver the value is only emitted once --search-timeout has passed, so
    naming SOLVE_TIMEOUT would attribute the timeout to a limit it was never given.
    """
    log = run_solve_finish(tmp_path, SEARCH_TIMEOUT, 7, SEARCH_BIN, "45")
    assert "45s" in log, log


def test_search_exhausted_stays_a_non_match(tmp_path):
    """search_exhausted means every tile was tried inside the budget.

    That genuinely IS "found nothing", so it must not be relabelled a timeout -- the
    whole point of #321 is that these two look identical from outside and have to be
    told apart, in both directions.
    """
    log = run_solve_finish(tmp_path, SEARCH_EXHAUSTED, 7, SEARCH_BIN, "45")
    assert "TIMEOUT" not in log, log
    assert "no match" in log, log
    assert "search_exhausted" in log or "all tiles searched" in log, log


def test_legacy_polaris_solve_timeout_still_classifies(tmp_path):
    """The original vocabulary must keep working."""
    log = run_solve_finish(tmp_path, LEGACY_TIMEOUT, 3, "polaris-solve", "45")
    assert "solve TIMEOUT" in log, log
    assert "no match" not in log, log


def test_solved_and_other_reasons_unaffected(tmp_path):
    """A success and a genuine non-match must not be swept into the new branches."""
    ok = run_solve_finish(tmp_path, SOLVED, 0, SEARCH_BIN, "45")
    assert "solve SOLVED" in ok, ok
    assert "TIMEOUT" not in ok, ok

    nm = run_solve_finish(tmp_path, NO_VERIFIED, 3, SEARCH_BIN, "45")
    assert "no match" in nm, nm
    assert "TIMEOUT" not in nm, nm


def test_failure_reason_timeout_is_matched_before_generic_false():
    """Ordering guard: the specific pattern must precede *"solved":false*.

    The case statement is first-match-wins. If the generic clause were reordered above
    the new one, every independent-search timeout would silently regress to "no match"
    and no other test here would notice, because they assert on behaviour that the
    generic clause also produces.
    """
    body = extract_function("solve_finish")
    lines = [ln.strip() for ln in body.splitlines() if ln.strip().startswith("*'")]
    idx_timeout = next(i for i, ln in enumerate(lines) if 'failure_reason\\":\\"timeout' in ln
                       or '"failure_reason":"timeout"' in ln)
    idx_generic = next(i for i, ln in enumerate(lines) if ln.startswith("*'\"solved\":false'*"))
    assert idx_timeout < idx_generic, (
        "the specific failure_reason:timeout clause must precede the generic "
        f"\"solved\":false clause; got order {[ln[:40] for ln in lines]}"
    )


def test_call_sites_pass_the_bound_that_can_fire():
    """Each solve_finish call must name the bound its solver was actually given.

    The independent-search branch is limited by --search-timeout and the plain
    independent branch by --cpulimit $SOLVE_TIMEOUT. A diagnostic quoting a bound the
    solver never received is worse than quoting none.
    """
    src = ALIGN.read_text(encoding="utf-8")
    assert "_bound=$INDEPENDENT_SEARCH_TIMEOUT" in src, (
        "the independent-search branch must record its search deadline"
    )
    assert "_bound=$SOLVE_TIMEOUT" in src, (
        "the plain independent branch must record the cpulimit it was given"
    )
    # No call site may hardcode a bound that ignores which branch ran.
    hardcoded = re.findall(r'solve_finish "[^"]*" "[^"]*" "[^"]*" "[^"]*" '
                           r'\$INDEPENDENT_SEARCH_TIMEOUT', src)
    assert not hardcoded, (
        "solve_finish must receive $_bound, not a literal $INDEPENDENT_SEARCH_TIMEOUT, "
        "because the same call site serves both independent branches"
    )
