import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT.parents[1] / "tools"


def test_native_search_frontend_solves_a_tile_without_python_runtime(tmp_path):
    cc = shutil.which("cc")
    if not cc:
        pytest.skip("host C compiler unavailable")

    source = tmp_path / "catalogue.csv"
    with source.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["source_id", "ra_deg", "dec_deg", "phot_g_mean_mag"])
        for sid, ra, dec in [
            (1, 0.0, 0.0), (2, 0.1, 0.0), (3, 0.0, 0.1),
            (4, 0.1, 0.1), (5, -0.1, 0.0),
        ]:
            writer.writerow([sid, ra, dec, 5.0])

    tiles = tmp_path / "tiles"
    manifest = tmp_path / "tiles.json"
    triangle_index = tmp_path / "tiles.ptri"
    triangle_manifest = tmp_path / "tiles.ptri.json"
    subprocess.run([
        sys.executable, str(TOOLS / "build_catalogue_tiles.py"), str(source),
        str(tiles), "--manifest", str(manifest), "--ra-bin", "10", "--dec-bin", "10",
    ], check=True)
    subprocess.run([
        sys.executable, str(TOOLS / "build_catalogue_triangle_index.py"), str(tiles),
        str(manifest), str(triangle_index), "--index-manifest", str(triangle_manifest),
    ], check=True)

    native = tmp_path / "polaris-solve-independent"
    search = tmp_path / "polaris-solve-independent-search"
    subprocess.run([
        cc, "-O2", "-std=gnu11", "-Werror", "-o", str(native),
        str(ROOT / "polaris-solve-independent.c"), "-lm",
    ], check=True)
    subprocess.run([
        cc, "-O2", "-std=gnu11", "-Werror", "-o", str(search),
        str(ROOT / "polaris-solve-independent-search.c"), "-lm",
    ], check=True)

    stars = ROOT / "tests" / "stars-fixture.txt"
    result = subprocess.run([
        str(search), "--catalog-dir", str(tiles), "--manifest", str(manifest),
        "--triangle-index", str(triangle_index),
        "--stars", str(stars), "--width", "1000", "--height", "800",
        "--focal-mm", "20.626", "--sensor-mm", "36", "--attempts", "1",
        "--max-catalog", "60", "--min-matches", "3", "--solver", str(native),
    ], capture_output=True, text=True, check=False)

    assert result.returncode == 0, result.stdout + result.stderr
    solved = json.loads(result.stdout)
    assert solved["solved"] is True
    assert solved["catalog"] == "independent-POLCAT01"
    assert solved["search_mode"] == "all-sky-triangle-index"
