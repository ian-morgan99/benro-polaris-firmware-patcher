#!/bin/sh
# test_camlib_target_models.sh — issue #297
#
# Prove, from the SHIPPED bytes, that the two cameras this product is being sold
# to work with are actually present in the camlib that will serve them.
#
# Why an artifact check rather than a source check. container/patch.sh logs
# "local-source target models: K-1 II and K-3 III present" after grepping the
# source tree, and test_polaris_pentax_build_package.sh asserts that log line.
# Both are checks on text in the repository. Neither looks at the .so a device
# receives. A camlib compiled from the right source but with the model table
# filtered, truncated, or built against a different libgphoto2 would pass every
# one of them and still ship a camera that is not recognised -- which is exactly
# the class of failure #297 describes, where the operator's symptom was real and
# the source-side evidence said everything was fine.
#
# The two markers are asserted against ptp2.so specifically, not "any camlib".
# Verified on a real build: pentax.so contains Pentax:K1II, Pentax:K3, Pentax:K3II
# and 14 others, but NOT 'Pentax:K-1 Mark II (PTP mode)' or 'Pentax:K-3 Mark III
# (MTP mode)'. Both of those are in ptp2.so. Asserting against the wrong camlib
# would fail a good build; asserting against "any" would let a build that ships
# only pentax.so pass while serving neither camera.
#
# Usage: test_camlib_target_models.sh <stage2-ondisk-dir>
# Exits 0 if the shipped camlibs carry both target models, 1 otherwise.

set -eu

TARGET_MODELS='Pentax:K-1 Mark II (PTP mode)
Pentax:K-3 Mark III (MTP mode)'

die() { echo "[camlib-target-models] FAIL: $*" >&2; exit 1; }

[ $# -ge 1 ] || die "usage: $0 <stage2-ondisk-dir>"
ROOT_ARG=$1
[ -d "$ROOT_ARG" ] || die "no such directory: $ROOT_ARG"

# Locate the camlib directory by globbing the version dir rather than hardcoding
# 2.5.34: a libgphoto2 bump must not silently skip this gate. A hardcoded path
# that no longer exists would make every [ -f ] test below false and, with the
# usual guards, pass vacuously.
CAMLIB_DIR=$(find "$ROOT_ARG" -type d -path '*/libgphoto2/*' 2>/dev/null | sort | head -1)
[ -n "$CAMLIB_DIR" ] || die "no libgphoto2/<version> camlib directory under $ROOT_ARG"

PTP2="$CAMLIB_DIR/ptp2.so"
[ -f "$PTP2" ] || die "ptp2.so missing from $CAMLIB_DIR -- neither target camera can be served"

command -v strings >/dev/null 2>&1 || die "'strings' is unavailable, cannot inspect the camlib binary (refusing to pass vacuously)"

# It must be an ARM shared object. A host-arch .so would load on the build
# machine and never on the device, and every marker check below would still pass.
# Matched with two independent greps because `file` puts the architecture AFTER
# "shared object" ("ELF 32-bit LSB shared object, ARM, EABI5 ..."): a single
# ordered glob fails on correct bytes, which is how this was caught.
if command -v file >/dev/null 2>&1; then
    FT=$(file "$PTP2" 2>/dev/null || true)
    case "$FT" in *shared\ object*) ;; *) die "ptp2.so is not a shared object: $FT" ;; esac
    case "$FT" in *ARM*) ;; *) die "ptp2.so is not ARM (device is armv7l): $FT" ;; esac
fi

missing=0
# Not `printf | while`: the pipe puts the loop body in a subshell, so anything
# recorded there vanishes when the loop ends and a missing model would be reported
# as success. Read from a redirect instead, and track misses in a temp file.
MISSING_FILE=$(mktemp "${TMPDIR:-/tmp}/camlib-missing.XXXXXX")
trap 'rm -f "$MISSING_FILE"' EXIT HUP INT TERM

while IFS= read -r model; do
    [ -n "$model" ] || continue
    # -a forces a scan of the whole file rather than only printable sections the
    # tool happens to pick; -F treats the marker literally, so the '.' in
    # "(PTP mode)" cannot match anything else.
    if strings -a "$PTP2" | grep -qF -- "$model"; then
        echo "[camlib-target-models] ok: $model present in ptp2.so"
    else
        echo "[camlib-target-models] MISSING: $model" >&2
        printf '%s\n' "$model" >> "$MISSING_FILE"
    fi
done <<EOF
$TARGET_MODELS
EOF

if [ -s "$MISSING_FILE" ]; then
    n=$(wc -l < "$MISSING_FILE" | tr -d ' ')
    die "$n target model(s) absent from $PTP2 -- a device with that camera cannot be recognised"
fi

# The manifest must describe the bytes that are actually there. A stale hash means
# the camlib was replaced after it was recorded, so the identity in
# RELEASE-IDENTITY.md no longer refers to what ships.
if [ -f "$CAMLIB_DIR/camlibs.manifest" ]; then
    while read -r want name; do
        [ -n "${name:-}" ] || continue
        [ -f "$CAMLIB_DIR/$name" ] || die "camlibs.manifest lists $name but it is not in $CAMLIB_DIR"
        have=$(sha256sum "$CAMLIB_DIR/$name" | cut -d' ' -f1)
        [ "$have" = "$want" ] || die "camlibs.manifest hash for $name is stale (manifest $want, actual $have)"
    done < "$CAMLIB_DIR/camlibs.manifest"
    echo "[camlib-target-models] ok: camlibs.manifest matches the shipped camlibs"
else
    echo "[camlib-target-models] note: no camlibs.manifest in $CAMLIB_DIR (not built by this repo?)" >&2
fi

echo "[camlib-target-models] PASS: both target cameras present in the shipped ptp2.so"
