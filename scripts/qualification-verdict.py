#!/usr/bin/env python3
"""Turn per-case qualification results into one enforced gate verdict (#203).

The previous runner printed `DONE — artefacts in ...` unconditionally: probe exit
codes were discarded, a case could silently SKIP, and grepping PASS/FAIL was
observational rather than enforced. That is how a round with failures inside it
came to be cited as qualification evidence.

This module owns the decision so it can be tested offline. The runner feeds it
one JSON object per case; the exit code is the gate.

Input: JSON Lines, one object per case, on stdin or via --results-file.
Recognised keys (all optional except `case`):

  case            str   identifier for the case, e.g. "timed6s"
  status          str   pass | fail | skip | error
  rc              int   canary-probe exit code, if it ran
  verdict         str   probe verdict token when known (no-file, partial-files...)
  reason          str   human-readable cause; required for skip
  expected_files  int   output obligation the case asked for
  files           list  device files created by THIS case only
  unattributed_files list  card files that appeared during the case but which
                        the probe did not report as its own outputs
  expected_exposure_s float  shutter duration the case claims
  actual_exposure_s   float  EXIF ExposureTime read back from the produced file
  mode_before     str   exposure-mode-raw observed before the capture
  mode_after      str   exposure-mode-raw observed after

Exit codes:
  0  every planned case passed, and the round is qualified
  1  at least one case failed/errored, a claim is unsupported, or nothing ran
  2  no failures, but one or more cases were skipped (qualified with gaps)
"""

from __future__ import annotations

import argparse
import json
import sys

PASS, FAIL, SKIP, ERROR = "pass", "fail", "skip", "error"


def _as_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def evaluate(cases: list[dict]) -> tuple[int, list[str], list[str]]:
    """Return (exit_code, problems, notes) for a round."""
    problems: list[str] = []
    notes: list[str] = []

    if not cases:
        return 1, ["no cases were recorded — hardware qualification BLOCKED"], notes

    seen: set[str] = set()
    passed = 0
    skipped = 0

    for entry in cases:
        name = str(entry.get("case") or "<unnamed>")
        if name in seen:
            problems.append(f"{name}: recorded twice — a case must be evaluated once")
        seen.add(name)
        status = str(entry.get("status") or "").lower()

        if status == PASS:
            passed += 1
        elif status == SKIP:
            skipped += 1
            reason = entry.get("reason")
            if not reason:
                problems.append(
                    f"{name}: SKIP without a machine-evaluated reason — an "
                    "unexplained skip is indistinguishable from a dropped case"
                )
            notes.append(f"SKIP {name}: {reason or '<no reason given>'}")
            continue
        elif status == ERROR:
            problems.append(f"{name}: ERROR — {entry.get('reason') or 'no reason given'}")
            continue
        elif status == FAIL:
            verdict = entry.get("verdict")
            problems.append(
                f"{name}: FAIL — {verdict or entry.get('reason') or 'no verdict recorded'}"
            )
            continue
        else:
            problems.append(f"{name}: unrecognised status {status!r}")
            continue

        # A pass must be backed by the probe's own exit code, not a string match.
        rc = entry.get("rc")
        if rc is None:
            problems.append(f"{name}: PASS without a probe exit code")
        elif int(rc) != 0:
            problems.append(f"{name}: PASS recorded but probe exited {rc}")

        obligation = entry.get("expected_files")
        files = entry.get("files") or []
        if obligation is None:
            problems.append(
                f"{name}: PASS without an output obligation — photoFormat is not authoritative"
            )
        elif len(files) != int(obligation):
            problems.append(
                f"{name}: PASS with {len(files)} correlated file(s) but "
                f"{obligation} required"
            )

        # Anything the card gained during this case that the probe did not report
        # is an unattributed capture (#203). It may be a stray from an earlier
        # case or a second output the obligation did not account for; either way
        # the round cannot claim to know what produced it.
        extra = entry.get("unattributed_files") or []
        if extra:
            problems.append(
                f"{name}: {len(extra)} card file(s) appeared during this case but "
                f"are not attributed to it: {', '.join(map(str, extra))}"
            )

        # The claim a case makes must be supported by the file it produced.
        want = _as_float(entry.get("expected_exposure_s"))
        got = _as_float(entry.get("actual_exposure_s"))
        if want is not None:
            if got is None:
                problems.append(
                    f"{name}: claims a {want:g}s exposure but no EXIF ExposureTime "
                    "was read back — the claim is unsupported"
                )
            elif abs(got - want) > max(0.05, 0.02 * want):
                problems.append(
                    f"{name}: claims a {want:g}s exposure but EXIF says {got:g}s"
                )

        mode_before = entry.get("mode_before")
        if mode_before in (None, "", "unknown"):
            problems.append(
                f"{name}: PASS without a verified pre-capture exposure mode — "
                "a timed capture taken in B mode is not a timed capture"
            )
        elif entry.get("mode_after") not in (None, mode_before):
            notes.append(
                f"NOTE {name}: exposure mode drifted {mode_before} -> "
                f"{entry.get('mode_after')}"
            )

    if passed == 0:
        return 1, problems + ["no case passed — hardware qualification BLOCKED"], notes
    if problems:
        return 1, problems, notes
    if skipped:
        return 2, [], notes
    return 0, [], notes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--results-file", default=None,
                    help="JSON Lines of per-case results (default: stdin)")
    args = ap.parse_args(argv)

    source = open(args.results_file) if args.results_file else sys.stdin
    cases: list[dict] = []
    try:
        for lineno, line in enumerate(source, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                cases.append(json.loads(line))
            except json.JSONDecodeError as exc:
                print(f"QUALIFICATION_BAD line {lineno}: unparseable result: {exc}")
                return 1
    finally:
        if args.results_file:
            source.close()

    code, problems, notes = evaluate(cases)
    for note in notes:
        print(note)
    for problem in problems:
        print(f"PROBLEM {problem}")

    passed = sum(1 for c in cases if str(c.get("status")).lower() == PASS)
    skipped = sum(1 for c in cases if str(c.get("status")).lower() == SKIP)
    failed = len(cases) - passed - skipped
    if code == 0:
        print(f"QUALIFIED — {passed} case(s) passed, no gaps")
    elif code == 2:
        print(f"QUALIFIED WITH GAPS — {passed} passed, {skipped} skipped; "
              "the skipped cases are NOT qualified")
    else:
        print(f"NOT QUALIFIED — {passed} passed, {failed} failed/errored, "
              f"{skipped} skipped, {len(problems)} problem(s)")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
