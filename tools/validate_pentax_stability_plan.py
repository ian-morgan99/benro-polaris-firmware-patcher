#!/usr/bin/env python3
"""Validate the non-hardware invariants of the Pentax stability plan."""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def csv_rows(name: str):
    with (ROOT / "tests" / name).open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    matrix = json.loads((ROOT / "tests/pentax_stability_matrix.json").read_text())
    phases = json.loads((ROOT / "tests/pentax_stability_phase_model.json").read_text())
    scenarios = csv_rows("pentax_stability_scenarios.csv")
    hypotheses = csv_rows("pentax_stability_hypotheses.csv")

    assert all(not m["duration_is_completion_signal"] for m in matrix["capture_modes"])
    assert len({r["id"] for r in scenarios}) == len(scenarios)
    assert all(int(r["repeat"]) >= 2 for r in scenarios)
    assert all(r["destructive"] == "false" for r in scenarios), "initial catalogue must be non-destructive"
    assert {99, 100, 101}.issubset({int(r["shutter_s"]) for r in scenarios if r["family"] == "timer_boundary"})
    assert any(p["name"] == "RECONCILE" and p["camera_owned"] for p in phases["phases"])
    assert any(p["name"] == "FAILED" and p["camera_owned"] for p in phases["phases"])
    assert all(r["status"] == "OPEN" for r in hypotheses), "hypotheses must not be pre-claimed as proven"

    print(f"OK: plan v1; {len(scenarios)} scenarios; {len(hypotheses)} hypotheses")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
