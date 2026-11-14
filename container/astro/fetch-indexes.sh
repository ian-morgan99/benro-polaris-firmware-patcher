#!/usr/bin/env bash
# ============================================================================
#  Pick and download the astrometry.net index files a given lens actually needs.
#
#    fetch-indexes.sh --focal-min MM --focal-max MM [--sensor-mm 36] --out DIR
#    fetch-indexes.sh --list                 # show the whole 4100 series
#
#  Indexes are upstream DATA, not part of this project: we never ship or mirror
#  them (docs/LICENSE-AUDIT.md rule 6). This downloads them to a directory you
#  choose -- on a Polaris, the microSD.
#
#  Scale rule of thumb: astrometry.net wants index quads roughly 10-100% of the
#  field, so we take every 4100-series scale whose quad range overlaps that band
#  fields your focal range produces. A narrower focal range downloads less.
# ============================================================================
set -euo pipefail

# Issue #288: this used to be plain http, and "already downloaded" was decided by
# file existence alone -- so a truncated or corrupted index was accepted forever.
# The server has always offered HTTPS and publishes md5sums.txt; both are now used.
BASE="${INDEX_BASE:-https://data.astrometry.net/4100}"
MD5_URL="${INDEX_MD5_URL:-$BASE/md5sums.txt}"
# Set VERIFY=0 only for an air-gapped mirror already checked elsewhere. It is
# deliberately not the default: an unverified index can produce a confident wrong
# sky position, which is worse than not solving at all.
VERIFY="${VERIFY:-1}"
# index -> quad size range in arcminutes (the published 4100/Tycho-2 series)
SCALES="4107:22:30 4108:30:42 4109:42:60 4110:60:85 4111:85:120 4112:120:170
        4113:170:240 4114:240:340 4115:340:480 4116:480:680 4117:680:1000
        4118:1000:1400 4119:1400:2000"

FMIN=""; FMAX=""; SENSOR=36.0; OUT=""; LIST=0
while [ $# -gt 0 ]; do
  case "$1" in
    --focal-min) FMIN="$2"; shift 2;;
    --focal-max) FMAX="$2"; shift 2;;
    --sensor-mm) SENSOR="$2"; shift 2;;
    --out) OUT="$2"; shift 2;;
    --list) LIST=1; shift;;
    -h|--help) sed -n '2,17p' "$0"; exit 0;;
    *) echo "unknown option: $1" >&2; exit 1;;
  esac
done

if [ "$LIST" = 1 ]; then
  printf '%-8s %-18s %s\n' index "quad size (arcmin)" "suits a field of about"
  for s in $SCALES; do
    IFS=: read -r n lo hi <<<"$s"
    printf '%-8s %-18s %s\n' "$n" "$lo-$hi" "$(awk -v l="$lo" -v h="$hi" 'BEGIN{printf "%.1f-%.0f deg", l/60.0, h/6.0}')"
  done
  exit 0
fi

[ -n "$FMIN" ] && [ -n "$FMAX" ] && [ -n "$OUT" ] || {
  echo "error: --focal-min, --focal-max and --out are required" >&2; exit 1; }

# field width in degrees for each end of the focal range
FOV_WIDE=$(awk -v s="$SENSOR" -v f="$FMIN" 'BEGIN{printf "%.4f", 2*atan2(s/2,f)*57.29577951}')
FOV_NARROW=$(awk -v s="$SENSOR" -v f="$FMAX" 'BEGIN{printf "%.4f", 2*atan2(s/2,f)*57.29577951}')
echo "[indexes] ${FMIN}mm -> ${FOV_WIDE} deg wide, ${FMAX}mm -> ${FOV_NARROW} deg (sensor ${SENSOR}mm)"

mkdir -p "$OUT"
WANT=""
for s in $SCALES; do
  IFS=: read -r n lo hi <<<"$s"
  # keep this scale if its quad range overlaps 10-100% of any field we might see
  keep=$(awk -v lo="$lo" -v hi="$hi" -v fw="$FOV_WIDE" -v fn="$FOV_NARROW" 'BEGIN{
      band_lo = fn*60*0.20; band_hi = fw*60*0.80;
      print (hi >= band_lo && lo <= band_hi) ? 1 : 0 }')
  [ "$keep" = 1 ] && WANT="$WANT $n"
done
echo "[indexes] needed:$WANT"

# ---- checksum manifest -----------------------------------------------------
# Upstream publishes md5sums.txt for this directory. It is fetched once and used to
# decide whether a file we already have is actually usable. #288: "-f" is not
# integrity validation -- a truncated download satisfies it, and the solver then
# either fails or returns a confident wrong sky position, forever.
MD5S=""
if [ "$VERIFY" = 1 ]; then
  if ! command -v md5sum >/dev/null 2>&1; then
    echo "error: md5sum is required to verify indexes. Re-run with VERIFY=0 only" >&2
    echo "       against a mirror you have checked by other means." >&2
    exit 1
  fi
  if curl -sfL -o "$OUT/.md5sums.txt" "$MD5_URL" 2>/dev/null; then
    MD5S="$OUT/.md5sums.txt"
  else
    echo "error: could not fetch the checksum manifest from $MD5_URL" >&2
    echo "       Refusing to install unverified index files. Use VERIFY=0 only if" >&2
    echo "       you have verified them another way." >&2
    exit 1
  fi
fi

# Upstream entries look like "<md5> *index-4110.fits"; the star marks binary mode.
want_md5() {
  [ -n "$MD5S" ] || return 1
  awk -v n="$1" '{ f=$2; sub(/^\*/,"",f); if (f==n) { print $1; found=1 } }
                 END { exit !found }' "$MD5S"
}

file_md5() { md5sum "$1" 2>/dev/null | awk '{print $1}'; }

# ---- download --------------------------------------------------------------
total=0
for n in $WANT; do
  f="$OUT/index-$n.fits"
  want=""
  if [ -n "$MD5S" ]; then
    want=$(want_md5 "index-$n.fits" || true)
  fi

  # Reuse only a file that is present AND matches the published hash. A bad cached
  # file is deleted and refetched rather than reported as an error, so re-running
  # the same command recovers on its own.
  if [ -f "$f" ]; then
    if [ -z "$MD5S" ]; then
      echo "  have index-$n.fits (unverified)"
    elif [ ! -s "$f" ]; then
      echo "  index-$n.fits is empty; refetching"; rm -f "$f"
    elif [ -z "$want" ]; then
      echo "error: no published checksum for index-$n.fits; refusing to use it" >&2
      exit 1
    elif [ "$(file_md5 "$f")" = "$want" ]; then
      echo "  have index-$n.fits (verified)"
    else
      echo "  index-$n.fits checksum mismatch; refetching"; rm -f "$f"
    fi
  fi

  if [ ! -f "$f" ]; then
    # Download to a temporary name and rename only after it verifies, so a crash or
    # a truncated transfer can never leave a half-file that looks complete.
    part="$f.part"
    trap 'rm -f "$part"' EXIT INT TERM
    echo "  fetching index-$n.fits …"
    if command -v curl >/dev/null 2>&1; then
      curl -sfL --retry 3 --retry-delay 2 -o "$part" "$BASE/index-$n.fits"
    else
      wget -q -O "$part" "$BASE/index-$n.fits"
    fi
    # A zero-length body is a failure, not an empty index.
    if [ ! -s "$part" ]; then
      echo "error: index-$n.fits downloaded as an empty file" >&2; exit 1
    fi
    if [ -n "$MD5S" ]; then
      if [ -z "$want" ]; then
        echo "error: index-$n.fits has no entry in the checksum manifest" >&2
        exit 1
      fi
      got=$(file_md5 "$part")
      if [ "$got" != "$want" ]; then
        echo "error: index-$n.fits checksum mismatch after download" >&2
        echo "       expected $want" >&2
        echo "       got      $got" >&2
        exit 1
      fi
    fi
    mv -f "$part" "$f"
    trap - EXIT INT TERM
  fi

  sz=$(stat -c %s "$f" 2>/dev/null || stat -f %z "$f")
  total=$((total + sz))
done

# Record what is actually on disk. #288 asks for index family, selection and hashes
# in the candidate evidence so a release can be reproduced exactly.
if command -v sha256sum >/dev/null 2>&1; then
  ( cd "$OUT" && sha256sum index-*.fits > indexes.sha256 2>/dev/null ) || :
fi
echo "[indexes] $OUT holds $(awk -v t="$total" 'BEGIN{printf "%.1f MB", t/1048576}') of index files"
if [ -f "$OUT/indexes.sha256" ]; then
  echo "[indexes] sha256 recorded in $OUT/indexes.sha256"
fi
