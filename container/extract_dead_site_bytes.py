#!/usr/bin/env python3
"""Extract the REAL stock bytes at each DEAD HDMI site from a firmware image.

Issue #8: hdmi_geometry_patch.py validates --include-dead sites against a
synthesized assumption (DEAD_STOCK_W_H = 1280x720). That assumption is derived
from the disassembly, not from the actual firmware bytes. If a DEAD site in the
real appfs.ubifs carries different stock bytes, the patcher fails loudly (safe),
but it can never claim full coverage honestly.

This tool closes that gap: it reads the 4 bytes actually present at each DEAD
site offset in a real firmware image and emits a JSON map of the form

    {"0x12cea4": "a4f3c3e1", "0x12ceac": "...", ...}

which is exactly what `hdmi_geometry_patch.py --dead-stock-map FILE` consumes.
Run it against the same appfs.ubifs generation that the release candidate uses,
then feed the map into the patcher so --include-dead validates against real
bytes instead of the assumption.

Usage:
    extract_dead_site_bytes.py <appfs.ubifs> [--out dead-site-stock-map.json]

The offsets are imported from hdmi_geometry_patch.DEAD_SITES so the two can
never drift apart. Offsets are file offsets into the appfs image (the patcher
already subtracts the 0x10000 base when building its site list, so the values
here match what the patcher indexes with).
"""
import json
import os
import sys

# Import the single source of truth for the DEAD-site offsets.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from hdmi_geometry_patch import DEAD_SITES
except Exception as e:  # pragma: no cover - import guard
    sys.exit(f"could not import DEAD_SITES from hdmi_geometry_patch.py: {e}")


def main():
    args = sys.argv[1:]
    if len(args) < 1:
        sys.exit(__doc__)
    inp = args[0]
    outp = "dead-site-stock-map.json"
    it = iter(args[1:])
    for a in it:
        if a == '--out':
            outp = next(it)
        else:
            sys.exit(f"unknown arg {a}")

    data = open(inp, 'rb').read()
    # Unique offsets (w/h pairs share an offset base but each entry is distinct).
    seen = set()
    ordered = []
    for off, role, rd in DEAD_SITES:
        if off in seen:
            continue
        seen.add(off)
        ordered.append((off, role))

    if not ordered:
        sys.exit("no DEAD sites defined — nothing to extract")

    result = {}
    missing = []
    for off, role in ordered:
        chunk = data[off:off + 4]
        if len(chunk) < 4:
            missing.append(hex(off))
            continue
        result[hex(off)] = chunk.hex()

    with open(outp, 'w') as f:
        json.dump(result, f, indent=2, sort_keys=True)
        f.write("\n")

    print(f"extracted {len(result)} DEAD-site stock entries from {inp} -> {outp}")
    for off, role in ordered:
        k = hex(off)
        if k in result:
            print(f"  {k} ({role}): {result[k]}")
        else:
            print(f"  {k} ({role}): <image too short>")
    if missing:
        print(f"WARNING: image shorter than some offsets: {', '.join(missing)}", file=sys.stderr)


if __name__ == '__main__':
    main()
