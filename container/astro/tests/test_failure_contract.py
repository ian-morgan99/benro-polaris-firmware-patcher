from pathlib import Path
import json, subprocess, sys

ROOT = Path(__file__).resolve().parents[1]
def test_no_catalog_coverage_is_fail_closed():
    p = subprocess.run([
        sys.executable, str(ROOT / "polaris-solve-independent.py"),
        "--catalog", str(ROOT / "tests/catalog-fixture.csv"),
        "--stars", str(ROOT / "tests/stars-fixture.txt"),
        "--width", "1000", "--height", "800", "--ra", "30", "--dec", "30",
        "--radius", "0.01", "--focal-mm", "20"],
        capture_output=True, text=True, check=False)
    assert p.returncode != 0
    assert json.loads(p.stdout)["failure_reason"] == "no_index_coverage"
