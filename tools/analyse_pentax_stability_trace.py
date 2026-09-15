#!/usr/bin/env python3
"""Summarise JSONL traces from Pentax stability experiments.

The analyser intentionally groups by first explicitly-marked abnormal event.
Tests should emit `first_abnormal` exactly once when instrumentation detects the
first divergence from the expected lifecycle. Later symptoms remain evidence,
not the root-cause grouping key.
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{line_no}: {exc}") from exc
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("traces", nargs="+", type=Path)
    args = parser.parse_args()

    by_run: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for path in args.traces:
        for row in load(path):
            by_run[row["run_id"]].append(row)

    fingerprints = collections.Counter()
    for run_id, rows in sorted(by_run.items()):
        rows.sort(key=lambda r: r["monotonic_ns"])
        first = next((r for r in rows if r["event"] == "first_abnormal"), None)
        final = rows[-1]
        if first is None:
            print(f"PASS/NO-MARKED-DIVERGENCE {run_id} {final.get('experiment')}")
            continue

        details = first.get("details") or {}
        fingerprint = details.get("fingerprint") or (
            f"{first.get('phase') or '?'}:{first.get('command') or '?'}:"
            f"{first.get('camera_state') or '?'}"
        )
        fingerprints[fingerprint] += 1
        print(
            "FAIL",
            run_id,
            first.get("experiment"),
            fingerprint,
            f"ts={first.get('monotonic_ns')}",
            f"usb={first.get('usb_fingerprint')}",
            f"session={first.get('session_state')}",
            f"candidates={first.get('candidate_count')}",
        )

    if fingerprints:
        print("\nFailure fingerprints:")
        for fingerprint, count in fingerprints.most_common():
            print(f"{count:4d}  {fingerprint}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
