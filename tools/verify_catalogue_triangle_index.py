#!/usr/bin/env python3
import hashlib
import json
import struct
from pathlib import Path

HEADER = struct.Struct("<8sIIII")
RECORD = struct.Struct("<HHI")


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("index")
    ap.add_argument("index_manifest")
    ap.add_argument("catalogue_manifest")
    args = ap.parse_args()
    index_path = Path(args.index)
    metadata = json.loads(Path(args.index_manifest).read_text())
    catalogue_manifest_bytes = Path(args.catalogue_manifest).read_bytes()
    data = index_path.read_bytes()
    if len(data) < HEADER.size:
        raise SystemExit("triangle index too short")
    magic, version, tile_count, record_count, ratio_scale = HEADER.unpack_from(data)
    if magic != b"POLTRI01" or version != 1 or ratio_scale == 0:
        raise SystemExit("invalid triangle index header")
    if len(data) != HEADER.size + record_count * RECORD.size:
        raise SystemExit("triangle index length mismatch")
    if metadata.get("format") != "polaris-independent-triangle-index-1":
        raise SystemExit("invalid triangle index manifest")
    if metadata.get("tile_count") != tile_count or metadata.get("record_count") != record_count:
        raise SystemExit("triangle index totals mismatch")
    if metadata.get("catalogue_manifest_sha256") != hashlib.sha256(catalogue_manifest_bytes).hexdigest():
        raise SystemExit("triangle index/catalogue manifest mismatch")
    if metadata.get("sha256") != hashlib.sha256(data).hexdigest():
        raise SystemExit("triangle index checksum mismatch")
    previous = None
    for position in range(record_count):
        ratio1, ratio2, tile_id = RECORD.unpack_from(data, HEADER.size + position * RECORD.size)
        if tile_id >= tile_count:
            raise SystemExit("triangle index tile id out of range")
        key = (ratio1, ratio2)
        if previous is not None and key < previous:
            raise SystemExit("triangle index is not sorted")
        previous = key
    print(json.dumps({"valid": True, "tile_count": tile_count, "record_count": record_count}))


if __name__ == "__main__":
    main()
