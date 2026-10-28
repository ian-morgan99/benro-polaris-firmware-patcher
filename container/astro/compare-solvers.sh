#!/usr/bin/env bash
# Compare the two solver front ends on one rendered frame and one extracted
# star list.  This is an offline research harness, not a device control path.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
ASTRO_DIR="${ASTRO_DIR:-$ROOT/out/astro-bundle/COPY-TO-SD-CARD-ROOT/polaris-astro}"
INDEX=""
RA=84.5
DEC=-2.7
ROLL=17.0
FOCAL=250
SENSOR=36
WIDTH=4096
HEIGHT=3072
OUTDIR=""
TIMEOUT=45

usage() {
    sed -n '2,31p' "$0"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --astro-dir) ASTRO_DIR="$2"; shift 2 ;;
        --index) INDEX="$2"; shift 2 ;;
        --ra) RA="$2"; shift 2 ;;
        --dec) DEC="$2"; shift 2 ;;
        --roll) ROLL="$2"; shift 2 ;;
        --focal-mm) FOCAL="$2"; shift 2 ;;
        --sensor-mm) SENSOR="$2"; shift 2 ;;
        --width) WIDTH="$2"; shift 2 ;;
        --height) HEIGHT="$2"; shift 2 ;;
        --outdir) OUTDIR="$2"; shift 2 ;;
        --timeout) TIMEOUT="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

[ -n "$INDEX" ] || INDEX="$ROOT/out/.astro-src-cache/astrometry.net-0.98/bench/index-4215.fits"
[ -f "$INDEX" ] || { echo "missing Astrometry.net index: $INDEX" >&2; exit 2; }
for binary in polaris-skysim polaris-extract polaris-solve polaris-solve-independent; do
    [ -x "$ASTRO_DIR/$binary" ] || {
        echo "missing executable: $ASTRO_DIR/$binary" >&2
        exit 2
    }
done

if [ -z "$OUTDIR" ]; then
    WORK="$(mktemp -d /tmp/polaris-dual-solve.XXXXXX)"
    CLEANUP=1
else
    WORK="$OUTDIR"
    mkdir -p "$WORK"
    CLEANUP=0
fi
cleanup() { [ "$CLEANUP" = 1 ] && rm -rf "$WORK"; }
trap cleanup EXIT

FRAME="$WORK/scene.jpg"
STARS="$WORK/scene.stars"
CSV="$WORK/paired.csv"
PCAT="$WORK/paired.pcat"
MANIFEST="$WORK/paired.json"
ASTRO_RESULT="$WORK/astrometry.json"
INDEPENDENT_RESULT="$WORK/independent.json"

"$ASTRO_DIR/polaris-skysim" --index "$INDEX" --ra "$RA" --dec "$DEC" \
    --roll "$ROLL" --focal-mm "$FOCAL" --sensor-mm "$SENSOR" \
    --width "$WIDTH" --height "$HEIGHT" --background 8 --noise 1 \
    --flux 230 --seed 7 --out "$FRAME" --stats >"$WORK/render.json"

"$ASTRO_DIR/polaris-extract" --jpeg "$FRAME" --downsample 1 \
    --max-stars 30 --stats >"$STARS" 2>"$WORK/extract.log"

"$ASTRO_DIR/polaris-solve" --index "$INDEX" --stars "$STARS" \
    --width "$WIDTH" --height "$HEIGHT" --focal-mm "$FOCAL" \
    --sensor-mm "$SENSOR" --ra "$RA" --dec "$DEC" --radius 15 \
    --cpulimit "$TIMEOUT" >"$ASTRO_RESULT" 2>"$WORK/astrometry.log"

python3 "$ROOT/tools/make_paired_catalogue.py" --stars "$STARS" \
    --out "$CSV" --ra "$RA" --dec "$DEC" --width "$WIDTH" \
    --height "$HEIGHT" --focal-mm "$FOCAL" --sensor-mm "$SENSOR"
python3 "$ROOT/tools/build_independent_catalogue.py" "$CSV" "$PCAT" \
    --manifest "$MANIFEST" --source "synthetic paired harness" \
    --release "test" --epoch "J2000" --max-mag 99 >"$WORK/catalogue.log"

"$ASTRO_DIR/polaris-solve-independent" --catalog "$PCAT" --stars "$STARS" \
    --width "$WIDTH" --height "$HEIGHT" --focal-mm "$FOCAL" \
    --sensor-mm "$SENSOR" --ra "$RA" --dec "$DEC" --radius 15 \
    --min-matches 4 --residual-px 5 >"$INDEPENDENT_RESULT"

python3 - "$WORK" "$RA" "$DEC" "$FOCAL" "$SENSOR" "$WIDTH" "$HEIGHT" <<'PY'
import json
import pathlib
import sys

work = pathlib.Path(sys.argv[1])
result = {
    "test": "dual-solver-same-frame",
    "scope": "same Astrometry-rendered JPEG and extracted star list; synthetic regional catalogue for the independent leg",
    "ground_truth": {
        "ra_deg": float(sys.argv[2]), "dec_deg": float(sys.argv[3]),
        "focal_mm": float(sys.argv[4]), "sensor_width_mm": float(sys.argv[5]),
        "width": int(sys.argv[6]), "height": int(sys.argv[7]),
    },
    "astrometry": json.loads((work / "astrometry.json").read_text().strip().splitlines()[-1]),
    "independent": json.loads((work / "independent.json").read_text().strip().splitlines()[-1]),
}
(work / "comparison.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
PY

echo "artifacts: $WORK" >&2
