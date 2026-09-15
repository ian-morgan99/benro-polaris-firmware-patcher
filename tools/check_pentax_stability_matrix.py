#!/usr/bin/env python3
"""Cheap deterministic consistency checks for the Pentax stability scenario catalogue."""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "tests/pentax_stability_scenarios.csv"


def main() -> int:
    with SCENARIOS.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    ids = [row["id"] for row in rows]
    assert len(ids) == len(set(ids)), "duplicate scenario id"
    assert any(row["family"] == "back_to_back" for row in rows)
    assert any(row["family"] == "timer_boundary" and row["shutter_s"] == "100" for row in rows)
    assert any(row["mode"] == "long-exposure-nr" for row in rows)
    assert all(int(row["repeat"]) >= 2 for row in rows)

    # The initial executable catalogue must be non-destructive. Destructive
    # fault injection is added only after baseline lifecycle is understood.
    assert all(row["destructive"] == "false" for row in rows)

    print(f"OK: {len(rows)} Pentax stability scenarios")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
