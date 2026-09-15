import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _rows():
    with (ROOT / "tests/pentax_stability_scenarios.csv").open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_scenario_ids_are_unique():
    rows = _rows()
    ids = [row["id"] for row in rows]
    assert len(ids) == len(set(ids))


def test_initial_campaign_is_non_destructive():
    assert all(row["destructive"] == "false" for row in _rows())


def test_timeout_boundary_straddles_100_seconds():
    seconds = {
        int(row["shutter_s"])
        for row in _rows()
        if row["family"] == "timer_boundary"
    }
    assert {99, 100, 101}.issubset(seconds)


def test_every_scenario_repeats():
    assert all(int(row["repeat"]) >= 2 for row in _rows())
