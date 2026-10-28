#!/usr/bin/env python3
"""Make a deliberately synthetic catalogue for the dual-solver harness.

This is test scaffolding only.  It converts the observed stars from an
Astrometry.net-rendered frame into a POLCAT input catalogue using the known
scene centre and camera scale.  It lets both solver front ends consume the
same extracted observation without pretending that this is an independent
all-sky catalogue or a blind-solve test.
"""
import argparse
import csv
import math
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stars", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ra", type=float, required=True)
    ap.add_argument("--dec", type=float, required=True)
    ap.add_argument("--width", type=float, required=True)
    ap.add_argument("--height", type=float, required=True)
    ap.add_argument("--focal-mm", type=float, required=True)
    ap.add_argument("--sensor-mm", type=float, default=36.0)
    args = ap.parse_args()

    if args.width <= 0 or args.height <= 0 or args.focal_mm <= 0:
        ap.error("width, height and focal-mm must be positive")

    # Match the geometry used by both native sky simulators and the native
    # solver.  The catalogue's local tangent-plane coordinates are deliberately
    # simple; the independent solver still has to recover the affine transform
    # and reject the wrong triangle candidates.
    scale_arcsec = 206264.806 * math.atan((args.sensor_mm / args.width) / args.focal_mm)
    ra0_rad = math.radians(args.ra)
    dec0_rad = math.radians(args.dec)
    rows = []
    with open(args.stars, encoding="utf-8") as source:
        for number, line in enumerate(source, 1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            fields = line.split()
            if len(fields) < 2:
                continue
            try:
                x = float(fields[0])
                y = float(fields[1])
                flux = float(fields[2]) if len(fields) >= 3 else 1.0
            except ValueError:
                continue
            # Invert the same gnomonic tangent-plane projection used by the
            # native solver.  The earlier degree/cos(dec) approximation made
            # the synthetic catalogue itself expand with distance from the
            # field centre, creating an artificial ~0.1% scale error.
            east = math.radians((x - args.width / 2.0) * scale_arcsec / 3600.0)
            north = math.radians((y - args.height / 2.0) * scale_arcsec / 3600.0)
            denominator = math.cos(dec0_rad) - north * math.sin(dec0_rad)
            ra = math.degrees(ra0_rad + math.atan2(east, denominator)) % 360.0
            dec = math.degrees(math.atan2(
                math.sin(dec0_rad) + north * math.cos(dec0_rad),
                math.sqrt(denominator * denominator + east * east)))
            # A positive flux maps to a bright synthetic magnitude.  Brightness
            # is not used to identify the stars; it only preserves ordering.
            mag = 5.0 - math.log10(max(1.0, flux))
            rows.append((90000000000000000 + number, ra, dec, mag))

    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as target:
        writer = csv.writer(target)
        writer.writerow(["source_id", "ra_deg", "dec_deg", "phot_g_mean_mag"])
        writer.writerows(rows)
    print(f"wrote {len(rows)} synthetic paired-catalogue records to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
