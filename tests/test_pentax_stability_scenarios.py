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


def test_destructive_scenarios_are_last_priority():
    # Design rule (docs/pentax-capture-stability-experiments.md): run clean
    # non-destructive baselines first; destructive embedded fault injection
    # belongs at the end, after baseline behaviour is understood. So every
    # destructive row must carry the highest priority in the catalogue, and
    # no lower-priority row may be destructive.
    rows = _rows()
    priorities = {int(row["priority"]) for row in rows}
    top = max(priorities)
    for row in rows:
        if row["destructive"] == "true":
            assert int(row["priority"]) == top, row["id"]


def test_timeout_boundary_straddles_100_seconds():
    seconds = {
        int(row["shutter_s"])
        for row in _rows()
        if row["family"] == "timer_boundary"
    }
    assert {99, 100, 101}.issubset(seconds)


def test_every_scenario_repeats():
    assert all(int(row["repeat"]) >= 2 for row in _rows())
