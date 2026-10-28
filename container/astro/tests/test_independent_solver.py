from pathlib import Path
import csv
import json, subprocess, sys

ROOT = Path(__file__).resolve().parents[1]
def test_independent_solver_fixture():
    # The fixture catalogue is converted to the package format before solve.
    import tempfile
    td = tempfile.mkdtemp(prefix="polaris-cat-test-")
    with open(Path(td) / "fixture.csv", "w", newline="") as f:
        binary = Path(td) / "fixture.pcat"
        source = Path(td) / "fixture.csv"
        w = csv.writer(f); w.writerow(["source_id", "ra_deg", "dec_deg", "phot_g_mean_mag"])
        for n, line in enumerate((ROOT / "tests/catalog-fixture.csv").read_text().splitlines(), 1):
            if line.startswith("#") or not line.strip(): continue
            _ident, ra, dec = line.split(",")
            w.writerow([n, ra, dec, 5])
    subprocess.run([sys.executable, str(ROOT.parents[1] / "tools/build_independent_catalogue.py"),
                    str(source), str(binary), "--manifest", str(Path(td) / "fixture.json")], check=True)
    p = subprocess.run([
        sys.executable, str(ROOT / "polaris-solve-independent.py"),
        "--catalog", str(binary),
        "--stars", str(ROOT / "tests/stars-fixture.txt"),
        "--width", "1000", "--height", "800", "--ra", "0", "--dec", "0",
            "--radius", "1", "--sensor-mm", "36",
        "--min-matches", "3", "--residual-px", "5"],
        capture_output=True, text=True, check=False)
    assert p.returncode == 0, p.stderr + p.stdout
    result = json.loads(p.stdout)
    assert result["solved"] is True
    assert result["matched_count"] >= 3
    assert result["catalog"] == "independent-csv"
