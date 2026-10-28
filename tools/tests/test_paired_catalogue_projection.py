import csv
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_paired_catalogue_round_trips_gnomonic_projection(tmp_path):
    stars = tmp_path / "stars.txt"
    paired = tmp_path / "paired.csv"
    stars.write_text("1000 700 100\n3000 2300 80\n", encoding="utf-8")
    subprocess.run([
        sys.executable, str(ROOT / "make_paired_catalogue.py"),
        "--stars", str(stars), "--out", str(paired),
        "--ra", "84.5", "--dec", "-2.7",
        "--width", "4096", "--height", "3072", "--focal-mm", "250",
        "--sensor-mm", "36",
    ], check=True, capture_output=True, text=True)

    scale = 206264.806 * math.atan((36.0 / 4096.0) / 250.0)
    ra0 = math.radians(84.5)
    dec0 = math.radians(-2.7)
    with paired.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    for row, line in zip(rows, stars.read_text(encoding="utf-8").splitlines()):
        x, y, _ = map(float, line.split())
        ra = math.radians(float(row["ra_deg"]))
        dec = math.radians(float(row["dec_deg"]))
        dra = ra - ra0
        denominator = math.sin(dec) * math.sin(dec0) + math.cos(dec) * math.cos(dec0) * math.cos(dra)
        east = math.cos(dec) * math.sin(dra) / denominator * 180.0 / math.pi * 3600.0
        north = (math.sin(dec) * math.cos(dec0) - math.cos(dec) * math.sin(dec0) * math.cos(dra)) / denominator * 180.0 / math.pi * 3600.0
        assert abs((east / scale + 2048.0) - x) < 1e-5
        assert abs((north / scale + 1536.0) - y) < 1e-5
