#!/usr/bin/env python3
"""Build a compact ratio-triangle index for native all-sky tile selection."""
import argparse
import hashlib
import itertools
import json
import math
import struct
from pathlib import Path

CAT_REC = struct.Struct("<Qddd")
TRI_REC = struct.Struct("<HHI")
MAGIC = b"POLCAT01"
INDEX_MAGIC = b"POLTRI01"
HEADER = struct.Struct("<8sIIII")
RATIO_SCALE = 100


def read_tile(path):
    data = path.read_bytes()
    if len(data) < 16 or data[:8] != MAGIC:
        raise ValueError(f"invalid tile: {path}")
    version, count = struct.unpack_from("<II", data, 8)
    if version != 1 or len(data) != 16 + count * CAT_REC.size:
        raise ValueError(f"invalid tile length: {path}")
    return [CAT_REC.unpack_from(data, 16 + n * CAT_REC.size) for n in range(count)]


def separation_arcsec(a, b):
    _, ra1, dec1, _ = a
    _, ra2, dec2, _ = b
    r1, r2 = math.radians(ra1), math.radians(ra2)
    d1, d2 = math.radians(dec1), math.radians(dec2)
    c = math.sin(d1) * math.sin(d2) + math.cos(d1) * math.cos(d2) * math.cos(r1 - r2)
    return math.degrees(math.acos(max(-1.0, min(1.0, c)))) * 3600.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tile_dir")
    ap.add_argument("manifest")
    ap.add_argument("output")
    ap.add_argument("--max-catalog", type=int, default=15)
    ap.add_argument("--ratio-scale", type=int, default=100)
    ap.add_argument("--index-manifest", required=True)
    args = ap.parse_args()

    source_manifest_path = Path(args.manifest)
    source_manifest_bytes = source_manifest_path.read_bytes()
    source_manifest = json.loads(source_manifest_bytes)
    entries = sorted(source_manifest["tiles"], key=lambda entry: (entry["dec_min"], entry["ra_min"]))
    records = []
    for tile_id, entry in enumerate(entries):
        stars = sorted(read_tile(Path(args.tile_dir) / f"{entry['tile']}.pcat"), key=lambda row: row[3])[:args.max_catalog]
        for triple in itertools.combinations(stars, 3):
            sides = sorted([separation_arcsec(triple[0], triple[1]),
                            separation_arcsec(triple[0], triple[2]),
                            separation_arcsec(triple[1], triple[2])])
            if sides[0] <= 0:
                continue
            ratio1 = min(65535, round(args.ratio_scale * sides[1] / sides[0]))
            ratio2 = min(65535, round(args.ratio_scale * sides[2] / sides[0]))
            records.append((ratio1, ratio2, tile_id))

    records.sort()
    output = Path(args.output)
    with output.open("wb") as fh:
        fh.write(HEADER.pack(INDEX_MAGIC, 1, len(entries), len(records), args.ratio_scale))
        for record in records:
            fh.write(TRI_REC.pack(*record))

    index_manifest = {
        "format": "polaris-independent-triangle-index-1",
        "catalogue_manifest_sha256": hashlib.sha256(source_manifest_bytes).hexdigest(),
        "tile_count": len(entries),
        "record_count": len(records),
        "max_catalog": args.max_catalog,
        "ratio_scale": args.ratio_scale,
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }
    Path(args.index_manifest).write_text(json.dumps(index_manifest, indent=2) + "\n")
    print(json.dumps(index_manifest))


if __name__ == "__main__":
    raise SystemExit(main())
