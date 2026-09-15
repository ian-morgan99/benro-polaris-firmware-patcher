import importlib.util
import json
from pathlib import Path


def _load_module(name: str, relative: str):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(name, root / relative)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_trace_is_jsonl_and_monotonic(tmp_path):
    trace_mod = _load_module("pentax_trace", "tools/pentax_stability_trace.py")
    out = tmp_path / "trace.jsonl"
    trace = trace_mod.Trace(out, "E4", "run-1")
    first = trace.emit("capture_start", phase="requested", command="264")
    second = trace.emit("candidate_discovered", phase="candidate_discovery", candidate_count=2)

    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert len(rows) == 2
    assert rows[0]["run_id"] == "run-1"
    assert rows[0]["experiment"] == "E4"
    assert rows[1]["candidate_count"] == 2
    assert second.monotonic_ns >= first.monotonic_ns


def test_mode_matrix_never_treats_duration_as_completion():
    root = Path(__file__).resolve().parents[1]
    matrix = json.loads((root / "tests/pentax_stability_matrix.json").read_text())
    assert matrix["capture_modes"]
    assert all(not mode["duration_is_completion_signal"] for mode in matrix["capture_modes"])
