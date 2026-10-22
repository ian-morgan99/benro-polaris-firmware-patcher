#!/usr/bin/env python3
"""Classify pgphoto capture outcomes from Mlog/Clog without trusting the sign.

Raised by issue #218. `capture_image[3164]` logs an elapsed value that is *always*
negative, including for captures that completed normally:

    capture_image[3164]:----capture end   -23398 ms   <- SUCCESS, produced SP_0365.dng
    capture_image[3164]:----capture end   -71634 ms   <- the real failure

Measured over the archived bundles in docs/evidence: 216 `capture end` lines, of
which **0 are positive** and 47 correspond to an actual failure. Treating a negative
duration as a timeout therefore over-reports failures by roughly 4.6x across the
archive (and 17x over the 20-bundle subset examined in #218). This cost a wrong
conclusion once already: an initial analysis reported "34 capture timeouts" and
inferred several failure modes that did not exist.

Outcome is decided instead by the markers that actually distinguish the cases:

  * `ERROR: Could not capture image`            -> failure
  * a `state:0` completion after `state:4`      -> success
  * a produced file (`SP_*.dng` / `*_*.jpg`)    -> success
  * `state:-N` terminal error                   -> failure, with the code reported

The elapsed value is still reported, labelled as untrustworthy, so a reader cannot
mistake it for a duration.

Usage:
    capture-outcomes.py FILE_OR_DIR...
    capture-outcomes.py --json FILE_OR_DIR...
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

# `capture_image[3164]:----capture end   -23398 ms`
CAPTURE_END = re.compile(
    r"capture_image\[(?P<line>\d+)\]:----capture end\s+(?P<ms>-?\d+)\s*ms")
FAILURE_MARKER = re.compile(r"ERROR: Could not capture image", re.I)
# Mlog state notifications for the capture code: `state:-6`, `state:4`, `state:0`.
STATE = re.compile(r"\bstate:(?P<code>-?\d+)")
FILE_MADE = re.compile(r"(SP_\d+\.dng|[A-Za-z0-9_]+\.(?:dng|jpg))", re.I)
TIMESTAMP = re.compile(r"\[(?P<ts>\d{2}:\d{2}:\d{2}[:.]?\d*)")

# Terminal states observed on this camera that mean the capture did not complete.
TERMINAL_ERROR_STATES = {-6, -10, -110, -1005, -7, -99}

# Measured in docs/evidence/bulb-session-20260930-0201/raw/Clog_000180.log: the
# `ERROR: Could not capture image.` line is emitted *before* its `capture end` line,
# 135-159 lines ahead of it. A forward window therefore finds nothing and every
# failure reads as a pass -- which is exactly how this script first misreported 212
# captures as all-success. The window is generous but bounded so an unrelated earlier
# failure cannot brand a later good capture.
FAILURE_LOOKBACK_LINES = 300


def _looks_like_a_log(name: str) -> bool:
    """Accept only genuine device logs.

    docs/evidence is full of SUMMARY.md files that *quote* log lines as evidence.
    Parsing those would count a quoted example as a real capture and inflate every
    number this script reports, so prose is excluded by name rather than by content.
    """
    base = os.path.basename(name)
    if base.endswith(".md") or ".md" in base:
        return False
    return (base.startswith(("Clog", "Mlog")) or base.endswith(".log")
            or base.startswith(("Clog_", "Mlog_")))


def _iter_lines(paths):
    for path in paths:
        if os.path.isdir(path):
            for root, _dirs, files in os.walk(path):
                for name in sorted(files):
                    if _looks_like_a_log(name):
                        yield os.path.join(root, name), None
        else:
            yield path, None


def classify(paths):
    """Return (records, summary) for the given files/directories."""
    records = []
    for path, _ in _iter_lines(paths):
        try:
            with open(path, "rb") as fh:
                text = fh.read().decode("utf-8", "replace")
        except OSError as exc:
            print(f"skip {path}: {exc}", file=sys.stderr)
            continue
        lines = text.splitlines()
        end_indexes = [i for i, line in enumerate(lines) if CAPTURE_END.search(line)]
        error_indexes = {i for i, line in enumerate(lines)
                         if FAILURE_MARKER.search(line)}
        # Which failure markers were claimed by a capture-end line. Anything left
        # over is reported rather than silently dropped: an ERROR with no adjacent
        # `capture end` is itself a signal (the app gave up before reaching the
        # logging point, or pgphoto died mid-capture).
        claimed_errors: set[int] = set()

        for index in end_indexes:
            line = lines[index]
            match = CAPTURE_END.search(line)
            stamp = TIMESTAMP.search(line)
            back_start = max(0, index - FAILURE_LOOKBACK_LINES)
            preceding = [i for i in error_indexes
                         if back_start <= i < index and i not in claimed_errors]
            if preceding:
                nearest = max(preceding)
                claimed_errors.add(nearest)
                failed = True
            else:
                failed = False
            # Completion evidence may follow the end marker.
            window = "\n".join(lines[index:index + 40])
            file_match = FILE_MADE.search(window)
            states = [int(g) for g in STATE.findall(window)]
            terminal = next((s for s in states if s in TERMINAL_ERROR_STATES), None)

            if failed or terminal is not None:
                outcome = "FAIL"
            elif file_match or 0 in states:
                outcome = "PASS"
            else:
                # No failure marker and no completion evidence: do not guess. This
                # is the honest answer when a log was truncated at boot (#213).
                outcome = "UNKNOWN"

            # A failure marker and a filename in the same neighbourhood contradict
            # each other, and which one describes *this* capture cannot be settled
            # from Clog alone: Clog lines carry no timestamps that can be matched to
            # a specific request (#213), so the filename may belong to the next
            # capture in the sequence. RAW+JPEG is another explanation -- a failed
            # capture can still leave the JPEG behind. The outcome stays FAIL because
            # the app's own error marker is the authoritative statement about the
            # request it handled, but the contradiction is surfaced for review rather
            # than resolved by assumption.
            ambiguous = bool(outcome == "FAIL" and file_match)

            records.append({
                "file": os.path.basename(path),
                "time": stamp.group("ts") if stamp else None,
                "logged_ms": int(match.group("ms")),
                "outcome": outcome,
                "file_produced": file_match.group(1) if file_match else None,
                "states": states[:8],
                "contradictory_evidence": ambiguous,
            })

        unmatched = sorted(error_indexes - claimed_errors)
        for i in unmatched:
            stamp = TIMESTAMP.search(lines[i])
            records.append({
                "file": os.path.basename(path),
                "time": stamp.group("ts") if stamp else None,
                "logged_ms": None,
                "outcome": "FAIL-UNMATCHED",
                "file_produced": None,
                "states": [],
            })

    counts = {"PASS": 0, "FAIL": 0, "UNKNOWN": 0, "FAIL-UNMATCHED": 0}
    negative = 0
    for rec in records:
        counts[rec["outcome"]] += 1
        if rec["logged_ms"] is not None and rec["logged_ms"] < 0:
            negative += 1
    failures = counts["FAIL"] + counts["FAIL-UNMATCHED"]
    summary = {
        "capture_end_lines": sum(1 for r in records if r["logged_ms"] is not None),
        "negative_logged_durations": negative,
        "outcomes": counts,
        "failures_total": failures,
        "contradictory_failures": sum(
            1 for r in records if r.get("contradictory_evidence")),
        # The trap #218 describes: what a naive sign-based reading would report.
        "naive_sign_based_failure_count": negative,
        "over_report_factor": (round(negative / max(failures, 1), 2)
                               if failures else None),
    }
    return records, summary


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--show-passes", action="store_true",
                        help="list passing captures too")
    args = parser.parse_args(argv[1:])

    records, summary = classify(args.paths)
    if args.json:
        print(json.dumps({"summary": summary, "records": records}, indent=2))
        return 0

    print(f"capture end lines      : {summary['capture_end_lines']}")
    print(f"negative durations     : {summary['negative_logged_durations']} "
          f"(pgphoto always logs negative -- NOT a failure indicator, #218)")
    counts = summary["outcomes"]
    print(f"classified PASS        : {counts['PASS']}")
    print(f"classified FAIL        : {counts['FAIL']}")
    print(f"FAIL, no capture end   : {counts['FAIL-UNMATCHED']} "
          f"(failure marker with no adjacent 'capture end' line)")
    print(f"classified UNKNOWN     : {counts['UNKNOWN']} "
          f"(no completion or failure marker in the retained window)")
    print(f"failures total         : {summary['failures_total']}")
    if summary["contradictory_failures"]:
        print(f"  of which contradictory : "
              f"{summary['contradictory_failures']} carry a failure marker AND a "
              f"nearby filename.\n"
              f"                         Reported as FAIL (the app's own error marker "
              f"is authoritative for the\n"
              f"                         request it handled), but the file may belong "
              f"to the next capture or be a\n"
              f"                         RAW+JPEG partial. Needs card-side verification, "
              f"not assumed away.")
    if summary["over_report_factor"]:
        print(f"naive sign-based count : "
              f"{summary['naive_sign_based_failure_count']} -> over-reports by "
              f"{summary['over_report_factor']}x")
    print()
    for rec in records:
        if rec["outcome"] == "PASS" and not args.show_passes:
            continue
        print(f"  {rec['file']} {rec['time'] or '?':>12} "
              f"{rec['outcome']:7} logged={rec['logged_ms']}ms "
              f"file={rec['file_produced'] or '-'} states={rec['states']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
