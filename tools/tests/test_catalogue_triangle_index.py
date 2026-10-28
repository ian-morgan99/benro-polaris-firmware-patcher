import csv
import json
import struct
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_triangle_index_matches_device_tile_order(tmp_path):
    source = tmp_path / "gaia.csv"
    with source.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["source_id", "ra_deg", "dec_deg", "phot_g_mean_mag"])
        for sid, ra, dec in [(1, 1, 1), (2, 2, 1), (3, 1, 2), (4, 2, 2)]:
            writer.writerow([sid, ra, dec, 5])
    tiles = tmp_path / "tiles"
    manifest = tmp_path / "tiles.json"
    index = tmp_path / "tiles.ptri"
    index_manifest = tmp_path / "tiles.ptri.json"
    subprocess.run([
        sys.executable, str(ROOT / "build_catalogue_tiles.py"), str(source),
        str(tiles), "--manifest", str(manifest), "--ra-bin", "10", "--dec-bin", "10",
    ], check=True)
    subprocess.run([
        sys.executable, str(ROOT / "build_catalogue_triangle_index.py"), str(tiles),
        str(manifest), str(index), "--index-manifest", str(index_manifest),
    ], check=True)
    metadata = json.loads(index_manifest.read_text())
    assert metadata["format"] == "polaris-independent-triangle-index-1"
    assert metadata["tile_count"] == 1
    assert metadata["record_count"] == 4
    magic, version, tile_count, record_count, ratio_scale = struct.unpack(
        "<8sIIII", index.read_bytes()[:24]
    )
    assert (magic, version, tile_count, record_count, ratio_scale) == (
        b"POLTRI01", 1, 1, 4, 100
    )
    verified = subprocess.run([
        sys.executable, str(ROOT / "verify_catalogue_triangle_index.py"),
        str(index), str(index_manifest), str(manifest),
    ], capture_output=True, text=True, check=True)
    assert json.loads(verified.stdout)["valid"] is True
