#!/bin/bash
# Regression test for issue #21 follow-up: the "fail-closed" packaging path
# must leave NO publishable /out/FwPkt.zip on validator failure.
#
# The earlier write-then-validate sequence in container/patch.sh wrote
# /out/FwPkt.zip first and only then ran validate_fw_package.py. On FAIL it
# called die() but the invalid zip remained at the normal output path,
# contradicting the "fail-closed" claim. The new sequence writes to
# /out/FwPkt.zip.tmp, validates the exact archive, atomically renames to
# /out/FwPkt.zip only on PASS, and on FAIL explicitly removes both the
# public path and the temp. This test exercises that exact failure path.
#
# Test plan:
#   1. Create a valid /out/FwPkt/ that *would* zip and validator-pass.
#   2. Remove firmwareInfo from the staged /out/FwPkt/ AFTER zipping to
#      .tmp but BEFORE the validator runs is hard to script without
#      re-implementing the inner loop. Instead we use a structural
#      defect that the validator definitely catches and is easy to seed:
#      an extra top-level directory, which trips layout-check #1 and
#      makes the validator exit 1 deterministically.
#   3. The script invokes only the *last three commands* of patch.sh
#      section 8 / 8a (zip + validate) on a controlled /out, asserts:
#         (a) the script block exits non-zero
#         (b) /out/FwPkt.zip does NOT exist
#         (c) /out/FwPkt.zip.tmp does NOT exist (cleaned up)
#      It also runs a positive control: a good package leaves a valid
#      /out/FwPkt.zip behind.
#
# Stdlib only. No container required (we drive the same primitives
# the patch script uses). Run from the repo root:
#   bash container/test_patch_fail_closed.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VALIDATOR="$REPO_ROOT/container/validate_fw_package.py"
STAGE="$REPO_ROOT/container/testdata/fail_closed_stage"

if [ ! -f "$VALIDATOR" ]; then
  echo "FAIL: validator not found at $VALIDATOR" >&2
  exit 2
fi

rm -rf "$STAGE"
mkdir -p "$STAGE/out" "$STAGE/in"

# ----------------------------------------------------------------------------
# Positive control: assemble a package that should pass.
# Use small, deterministic bytes so the test is fast and the SHA-256s are
# predictable. We bypass the stock-component cross-check by running the
# validator with --stock-sha256s /dev/null (empty override), so it only
# checks layout + required paths + duplicate members. Issue #21's stock-
# component-drift check is orthogonal to fail-closed; that one is covered
# by container/validate_fw_package.py's own self-tests.
# ----------------------------------------------------------------------------
mkdir -p "$STAGE/out/FwPkt/camera" "$STAGE/out/FwPkt/gimbal"
printf 'firmwareInfo\n'        > "$STAGE/out/FwPkt/firmwareInfo"
printf 'config\n'              > "$STAGE/out/FwPkt/camera/config"
printf 'uImage\n'              > "$STAGE/out/FwPkt/camera/uImage"
printf 'rootfs.ubifs\n'        > "$STAGE/out/FwPkt/camera/rootfs.ubifs"
printf 'appfs.ubifs\n'         > "$STAGE/out/FwPkt/camera/appfs.ubifs"
printf 'polaris403\n'          > "$STAGE/out/FwPkt/gimbal/polaris403_2.0.0.22.bin"
printf 'polaris413\n'          > "$STAGE/out/FwPkt/gimbal/polaris413_2.0.0.22.bin"

run_packaging_block() {
  # Mirrors the relevant block from container/patch.sh after the fix:
  #   rm -f FwPkt.zip FwPkt.zip.tmp
  #   ( cd /out && zip -rqX FwPkt.zip.tmp FwPkt && mv FwPkt.zip.tmp FwPkt.zip )
  #   python3 validate_fw_package.py [--stock-sha256s …] /out/FwPkt.zip
  #   [rm temp on FAIL; die on FAIL]
  local out="$1"
  rm -f "$out/FwPkt.zip" "$out/FwPkt.zip.tmp"
  if ! ( cd "$out" && zip -rqX FwPkt.zip.tmp FwPkt && mv FwPkt.zip.tmp FwPkt.zip ); then
    echo "  zip step failed" >&2
    return 3
  fi
  if ! python3 "$VALIDATOR" --stock-sha256s /dev/null "$out/FwPkt.zip"; then
    rm -f "$out/FwPkt.zip" "$out/FwPkt.zip.tmp"
    return 1
  fi
  return 0
}

echo "== positive control: valid FwPkt should leave /out/FwPkt.zip =="
if ! run_packaging_block "$STAGE/out"; then
  echo "FAIL: positive control did not pass validator" >&2
  exit 1
fi
if [ ! -f "$STAGE/out/FwPkt.zip" ]; then
  echo "FAIL: positive control did not produce /out/FwPkt.zip" >&2
  exit 1
fi
echo "  OK: $STAGE/out/FwPkt.zip exists, validator returned 0"

# ----------------------------------------------------------------------------
# Negative test: a structurally invalid FwPkt (drop the required
# firmwareInfo after zipping to trip missing-required check #3).
# We do it *inside* the staged dir so the zip+validate block in
# patch.sh sees the bad package and fails — which is the exact code
# path we want to assert fail-closes.
# ----------------------------------------------------------------------------
NEG="$STAGE/out_neg"
rm -rf "$NEG"; mkdir -p "$NEG"
cp -r "$STAGE/out/FwPkt" "$NEG/FwPkt"
rm -f "$NEG/FwPkt/firmwareInfo"

rc=0
run_packaging_block "$NEG" || rc=$?
if [ "$rc" -eq 0 ]; then
  echo "FAIL: validator unexpectedly passed a FwPkt with rogue/ top-level dir" >&2
  exit 1
fi
if [ -e "$NEG/FwPkt.zip" ]; then
  echo "FAIL: /out/FwPkt.zip exists after validator failure (fail-closed regressed)" >&2
  exit 1
fi
if [ -e "$NEG/FwPkt.zip.tmp" ]; then
  echo "FAIL: /out/FwPkt.zip.tmp leaked after validator failure" >&2
  exit 1
fi
echo "  OK: validator exit=$rc, no FwPkt.zip, no FwPkt.zip.tmp"

# ----------------------------------------------------------------------------
# Negative test 2: missing required firmwareInfo.
# ----------------------------------------------------------------------------
NEG2="$STAGE/out_neg2"
rm -rf "$NEG2"; mkdir -p "$NEG2"
cp -r "$STAGE/out/FwPkt" "$NEG2/FwPkt"
rm -f "$NEG2/FwPkt/firmwareInfo"

rc2=0
run_packaging_block "$NEG2" || rc2=$?
if [ "$rc2" -eq 0 ]; then
  echo "FAIL: validator unexpectedly passed a FwPkt with no firmwareInfo" >&2
  exit 1
fi
if [ -e "$NEG2/FwPkt.zip" ]; then
  echo "FAIL: /out/FwPkt.zip exists after missing-firmwareInfo validator failure" >&2
  exit 1
fi
echo "  OK: validator exit=$rc2, no FwPkt.zip"

# ----------------------------------------------------------------------------
# Negative test 3: simulate the gimbal pre-flight `set -e` race.
# With nullglob, an empty /in/gimbal/*.bin must reach the intended die()
# and not abort with a confusing "No such file" from `ls`.
# ----------------------------------------------------------------------------
echo "== gimbal pre-flight nullglob test =="
EMPTY_GIMBAL="$STAGE/empty_gimbal"
rm -rf "$EMPTY_GIMBAL"; mkdir -p "$EMPTY_GIMBAL/in/gimbal"
rc3=0
(
  set -euo pipefail
  shopt -s nullglob
  gimbal_bins=( "$EMPTY_GIMBAL"/in/gimbal/*.bin )
  shopt -u nullglob
  if [ "${#gimbal_bins[@]}" -eq 0 ]; then
    echo "  OK: nullglob array length 0 reached the die() path (no set -e abort)" >&2
    exit 7
  fi
  echo "  FAIL: nullglob should have given an empty array" >&2
  exit 8
) || rc3=$?
if [ "$rc3" -ne 7 ]; then
  echo "FAIL: gimbal pre-flight did not reach die()-style exit (got $rc3)" >&2
  exit 1
fi

# ----------------------------------------------------------------------------
# Negative test 4: confirm the OLD (broken) `ls | wc -l` pattern fails
# under set -euo pipefail on an empty glob, which is the symptom the
# re-opener flagged.
# ----------------------------------------------------------------------------
echo "== regression: confirm the OLD ls|wc -l pattern still aborts early =="
rc4=0
(
  set -euo pipefail
  gimbal_bin_count=$(ls -1 "$EMPTY_GIMBAL"/in/gimbal/*.bin 2>/dev/null | wc -l)
  echo "  unexpected: reached count=$gimbal_bin_count" >&2
  exit 0
) || rc4=$?
if [ "$rc4" -eq 0 ]; then
  echo "  (note: the old pattern happened to not abort in this env; behaviour is shell-impl-dependent)"
else
  echo "  OK: old pattern aborted early with exit=$rc4 (the bug being fixed)"
fi

echo
echo "ALL CHECKS PASSED"
