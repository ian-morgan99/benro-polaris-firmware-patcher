#!/bin/sh
# Build the independent native-solver Gaia package on the host.
# This is a reproducible data-build helper; it is not copied to Polaris.
set -eu

HERE=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
ROOT=$(CDPATH= cd -- "$HERE/../.." && pwd)
OUT=${1:-$ROOT/out/gaia-dr3-g10}
MAX_MAG=${MAX_MAG:-10}
MAXREC=${MAXREC:-1000000}
RA_BIN_DEG=${RA_BIN_DEG:-10}
DEC_BIN_DEG=${DEC_BIN_DEG:-10}
TRIANGLE_MAX_CATALOG=${TRIANGLE_MAX_CATALOG:-15}
TRIANGLE_RATIO_SCALE=${TRIANGLE_RATIO_SCALE:-1000}
QUERY="SELECT source_id,ra,dec,phot_g_mean_mag FROM gaiadr3.gaia_source WHERE phot_g_mean_mag IS NOT NULL AND phot_g_mean_mag <= ${MAX_MAG}"

mkdir -p "$OUT"
echo "[gaia] downloading Gaia DR3 G<=${MAX_MAG}"
curl -fL --retry 2 --max-time 900 --get \
    'https://gea.esac.esa.int/tap-server/tap/sync' \
    --data-urlencode 'REQUEST=doQuery' \
    --data-urlencode 'LANG=ADQL' \
    --data-urlencode 'FORMAT=csv' \
    --data-urlencode "MAXREC=$MAXREC" \
    --data-urlencode "QUERY=$QUERY" \
    -o "$OUT/gaia.csv"

python3 "$ROOT/tools/build_catalogue_tiles.py" "$OUT/gaia.csv" "$OUT/tiles" \
    --manifest "$OUT/tiles.json" --ra-bin "$RA_BIN_DEG" --dec-bin "$DEC_BIN_DEG" \
    --max-mag "$MAX_MAG"
python3 "$ROOT/tools/verify_catalogue_tiles.py" "$OUT/tiles" "$OUT/tiles.json"
python3 "$ROOT/tools/build_catalogue_triangle_index.py" "$OUT/tiles" "$OUT/tiles.json" \
    "$OUT/tiles.ptri" --index-manifest "$OUT/tiles.ptri.json" \
    --max-catalog "$TRIANGLE_MAX_CATALOG" --ratio-scale "$TRIANGLE_RATIO_SCALE"
python3 "$ROOT/tools/verify_catalogue_triangle_index.py" "$OUT/tiles.ptri" \
    "$OUT/tiles.ptri.json" "$OUT/tiles.json"

echo "[gaia] package -> $OUT"
sha256sum "$OUT/gaia.csv" "$OUT/tiles.json" "$OUT/tiles.ptri" "$OUT/tiles.ptri.json"
