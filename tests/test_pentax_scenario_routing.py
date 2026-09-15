import csv
from pathlib import Path


def _rows():
    root = Path(__file__).resolve().parents[1]
    with (root / "tests/pentax_stability_scenarios.csv").open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_every_scenario_has_explicit_attachment_and_layer():
    rows = _rows()
    assert rows
    for row in rows:
        assert row["camera"] in {"K-3 III", "K-1 II"}
        assert row["attachment"] in {"PC", "POLARIS"}
        assert row["layer"] in {"A", "B", "C"}


def test_layer_host_contract():
    for row in _rows():
        if row["layer"] in {"A", "B"}:
            assert row["attachment"] == "PC", row["id"]
        elif row["layer"] == "C":
            assert row["attachment"] == "POLARIS", row["id"]


def test_k1ii_is_second_pass():
    for row in _rows():
        if row["camera"] == "K-1 II":
            assert row["pass"] == "2", row["id"]
        elif row["camera"] == "K-3 III":
            assert row["pass"] == "1", row["id"]
