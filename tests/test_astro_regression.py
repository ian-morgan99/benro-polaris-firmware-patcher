import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tests" / "astro_regression" / "runner.py"


def test_independent_suite_offline_contracts():
    result = subprocess.run([sys.executable, str(RUNNER), "--offline"], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    summary = json.loads(result.stdout.splitlines()[-1])
    assert summary["failed"] is False
    assert summary["blocked"] is False


def test_quarantined_fixture_is_not_classified_as_ready():
    fixture = ROOT / "tests" / "astro_regression" / "fixtures" / "k3iii-link-quarantined.json"
    data = json.loads(fixture.read_text())
    assert data["classification"] == "camera_quarantined"
    assert data["link"]["camera_state"] == -110
    assert data["link"]["model"] == "none"


def test_runner_has_no_mutating_live_paths():
    namespace = {"__file__": str(RUNNER), "__name__": "astro_regression_test"}
    exec(RUNNER.read_text(), namespace)
    assert namespace["SAFE_GETS"] == {"/api/link", "/api/state", "/api/site"}
    assert namespace["SAFE_HISTORIC"] == {"/api/test/upload", "/api/test/solve", "/api/test/state"}
    assert all("capture" not in path and "motor" not in path for path in namespace["SAFE_GETS"] | namespace["SAFE_HISTORIC"])
    assert "motor_control" in (RUNNER.parent / "runner_impl.py").read_text()
