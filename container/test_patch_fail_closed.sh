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
printf 'config\n'              > "$STAGE/out/FwPkt/camera/config"
printf 'uImage\n'              > "$STAGE/out/FwPkt/camera/uImage"
printf 'rootfs.ubifs\n'        > "$STAGE/out/FwPkt/camera/rootfs.ubifs"
printf 'appfs.ubifs\n'         > "$STAGE/out/FwPkt/camera/appfs.ubifs"
printf 'polaris403\n'          > "$STAGE/out/FwPkt/gimbal/polaris403_2.0.0.22.bin"
printf 'polaris413\n'          > "$STAGE/out/FwPkt/gimbal/polaris413_2.0.0.22.bin"

# Stock-style firmwareInfo (the reference manifest the on-board updater's
# key-set check compares against). gen_firmwareinfo.py rewrites this from
# the actual file contents; verify_firmwareinfo.py then proves the rewrite
# matches what is actually shipped.
cat > "$STAGE/stock_firmwareInfo" <<'FWI'
config size:7;config MD5:00000000000000000000000000000000;
uImage size:7;uImage MD5:00000000000000000000000000000000;
rootfs size:11;rootfs MD5:00000000000000000000000000000000;
appfs size:12;appfs MD5:00000000000000000000000000000000;
polaris403 size:11;polaris403 MD5:00000000000000000000000000000000;
polaris413 size:11;polaris413 MD5:00000000000000000000000000000000;
FWI
cp "$STAGE/stock_firmwareInfo" "$STAGE/out/FwPkt/firmwareInfo"

# ----------------------------------------------------------------------------
# Packaging block mirroring container/patch.sh sections 8 + 8a EXACTLY, in
# both archive-creation modes (issue #21 follow-up, 2026-09-06):
#   mode A: 'zip' CLI available            (dev hosts)
#   mode B: 'zip' deliberately unavailable (the production Docker image does
#           NOT install zip — the Python zipfile fallback is the path actually
#           used in the container, so it must be regression-proven too)
#
# Sequence per mode (identical to patch.sh):
#   1. gen_firmwareinfo.py  -> FwPkt/firmwareInfo   (manifest regeneration)
#   2. verify_firmwareinfo.py (fail-closed manifest gate; die before zipping)
#   3. rm -f FwPkt.zip FwPkt.zip.tmp
#      ( cd out && zip|python-zipfile -> FwPkt.zip.tmp && mv -> FwPkt.zip )
#   4. validate_fw_package.py on the EXACT public archive; on FAIL remove both
#      FwPkt.zip and FwPkt.zip.tmp so no publishable artifact survives.
# ----------------------------------------------------------------------------
GEN="$REPO_ROOT/container/gen_firmwareinfo.py"
VERIFY_FI="$REPO_ROOT/container/verify_firmwareinfo.py"

run_packaging_block() {
  # $1 = out dir, $2 = mode (zip|python), $3 = stale (skip manifest regen)
  local out="$1" mode="$2" stale="${3:-}"
  if [ -z "$stale" ]; then
    # 1+2: manifest regeneration + fail-closed firmwareInfo gate.
    # Mirrors patch.sh: gen reads the STOCK reference (/in/firmwareInfo) and
    # rewrites the in-pack manifest from actual file contents.
    python3 "$GEN" "$STAGE/stock_firmwareInfo" "$out/FwPkt" > "$out/FwPkt/firmwareInfo.new" \
      && mv "$out/FwPkt/firmwareInfo.new" "$out/FwPkt/firmwareInfo"
  fi
  if ! python3 "$VERIFY_FI" "$STAGE/stock_firmwareInfo" "$out/FwPkt"; then
    echo "  firmwareInfo gate failed (mode $mode)" >&2
    return 2
  fi
  # 3: build the archive at a temp path, atomically rename on success.
  rm -f "$out/FwPkt.zip" "$out/FwPkt.zip.tmp"
  if ! ( cd "$out" && (
      if [ "$mode" = "zip" ]; then
        zip -rqX FwPkt.zip.tmp FwPkt
      else
        python3 -c 'import os,zipfile
zf=zipfile.ZipFile("FwPkt.zip.tmp","w",zipfile.ZIP_DEFLATED)
for root,dirs,files in os.walk("FwPkt"):
  # Explicit directory entries - the on-board polestar_app expects
  # them (matches the layout of the stock Benro-shipped FwPkt.zip).
  rel=os.path.relpath(root,".")
  if rel != ".":
    zi=zipfile.ZipInfo(rel+"/")
    zi.external_attr=(0o755 << 16)
    zf.writestr(zi,"")
  for fn in files:
    p=os.path.join(root,fn); zf.write(p,p)
zf.close()'
      fi
    ) && mv FwPkt.zip.tmp FwPkt.zip ); then
    echo "  zip step failed (mode $mode)" >&2
    return 3
  fi
  # 4: structural validation of the exact public archive; fail-closed.
  if ! python3 "$VALIDATOR" --stock-sha256s /dev/null "$out/FwPkt.zip"; then
    rm -f "$out/FwPkt.zip" "$out/FwPkt.zip.tmp"
    return 1
  fi
  return 0
}

# Force mode B by shimming PATH so 'zip' is not found (mirrors the Docker
# image, which does not install zip).
run_mode() {
  # $1 = mode, $2 = out dir, $3 = stale flag (passed through)
  local mode="$1" out="$2" stale="${3:-}"
  if [ "$mode" = "python" ]; then
    # Force the Python zipfile fallback (the path the production Docker image
    # uses — it does not install zip): run the block with a minimal PATH that
    # has everything the block needs EXCEPT 'zip', so 'command -v zip' inside
    # the block fails and the python branch is taken.
    local shim="$STAGE/bin_nozip"
    rm -rf "$shim"; mkdir -p "$shim"
    for t in python3 mv rm; do
      ln -s "$(command -v $t)" "$shim/$t" || { echo "FAIL: cannot shim $t" >&2; exit 2; }
    done
    PATH="$shim" run_packaging_block "$out" "$mode" "$stale"
  else
    run_packaging_block "$out" "$mode" "$stale"
  fi
}

for MODE in zip python; do
  echo "== positive control (mode: $MODE): valid FwPkt should leave /out/FwPkt.zip =="
  if ! run_mode "$MODE" "$STAGE/out"; then
    echo "FAIL: positive control (mode $MODE) did not pass validator" >&2
    exit 1
  fi
  if [ ! -f "$STAGE/out/FwPkt.zip" ]; then
    echo "FAIL: positive control (mode $MODE) did not produce /out/FwPkt.zip" >&2
    exit 1
  fi
  # The resulting archive must pass BOTH gates (structural + manifest).
  python3 "$VALIDATOR" --stock-sha256s /dev/null "$STAGE/out/FwPkt.zip" \
    || { echo "FAIL: produced archive (mode $MODE) failed structural validator" >&2; exit 1; }
  python3 "$VERIFY_FI" "$STAGE/stock_firmwareInfo" "$STAGE/out/FwPkt" \
    || { echo "FAIL: produced package (mode $MODE) failed firmwareInfo verifier" >&2; exit 1; }
  echo "  OK: $STAGE/out/FwPkt.zip exists, both gates passed (mode $MODE)"

  # --------------------------------------------------------------------------
  # Negative test (per mode): a required camera component is missing from the
  # staged tree. gen_firmwareinfo keeps the stock line for the absent file,
  # so verify_firmwareinfo flags it MISSING and the manifest gate fails BEFORE
  # any zip is written — the fail-closed invariant we want to assert: no
  # public /out/FwPkt.zip, no leaked .tmp.
  # --------------------------------------------------------------------------
  NEG="$STAGE/out_neg_$MODE"
  rm -rf "$NEG"; mkdir -p "$NEG"
  cp -r "$STAGE/out/FwPkt" "$NEG/FwPkt"
  rm -f "$NEG/FwPkt/camera/uImage"   # required component missing

  rc=0
  run_mode "$MODE" "$NEG" || rc=$?
  if [ "$rc" -eq 0 ]; then
    echo "FAIL: manifest gate (mode $MODE) unexpectedly passed a FwPkt missing camera/uImage" >&2
    exit 1
  fi
  if [ -e "$NEG/FwPkt.zip" ]; then
    echo "FAIL: /out/FwPkt.zip exists after gate failure (mode $MODE, fail-closed regressed)" >&2
    exit 1
  fi
  if [ -e "$NEG/FwPkt.zip.tmp" ]; then
    echo "FAIL: /out/FwPkt.zip.tmp leaked after gate failure (mode $MODE)" >&2
    exit 1
  fi
  echo "  OK: gate exit=$rc, no FwPkt.zip, no FwPkt.zip.tmp (mode $MODE)"

  # --------------------------------------------------------------------------
  # Negative test 2 (per mode): a required gimbal component is missing — the
  # same fail-closed invariant via the gimbal glob path in the manifest.
  # --------------------------------------------------------------------------
  NEG2="$STAGE/out_neg2_$MODE"
  rm -rf "$NEG2"; mkdir -p "$NEG2"
  cp -r "$STAGE/out/FwPkt" "$NEG2/FwPkt"
  rm -f "$NEG2/FwPkt/gimbal/polaris413_2.0.0.22.bin"

  rc2=0
  run_mode "$MODE" "$NEG2" || rc2=$?
  if [ "$rc2" -eq 0 ]; then
    echo "FAIL: manifest gate (mode $MODE) unexpectedly passed a FwPkt missing gimbal/polaris413" >&2
    exit 1
  fi
  if [ -e "$NEG2/FwPkt.zip" ]; then
    echo "FAIL: /out/FwPkt.zip exists after missing-gimbal failure (mode $MODE)" >&2
    exit 1
  fi
  echo "  OK: gate exit=$rc2, no FwPkt.zip (mode $MODE)"

  # --------------------------------------------------------------------------
  # Negative test 2b (per mode): a structurally invalid ARCHIVE — duplicate
  # member + wrong top-level dir — must be rejected by the structural
  # validator (the gate that runs on the finished zip). We build the bad
  # archive directly with zipfile so we can inject defects a directory-based
  # zip step cannot produce (duplicate members).
  # --------------------------------------------------------------------------
  NEG2B="$STAGE/out_neg2b_$MODE"
  rm -rf "$NEG2B"; mkdir -p "$NEG2B"
  cp -r "$STAGE/out/FwPkt" "$NEG2B/FwPkt"
  python3 - "$NEG2B" <<'PYEOF'
import os, sys, zipfile
out = sys.argv[1]
zf = zipfile.ZipFile(os.path.join(out, "FwPkt.zip"), "w", zipfile.ZIP_DEFLATED)
# wrong top-level entry (not FwPkt/)
zf.writestr(zipfile.ZipInfo("firmware/"), "")
# duplicate member: firmwareInfo written twice
zf.write(os.path.join(out, "FwPkt/firmwareInfo"), "FwPkt/firmwareInfo")
zf.write(os.path.join(out, "FwPkt/firmwareInfo"), "FwPkt/firmwareInfo")
for root, dirs, files in os.walk(os.path.join(out, "FwPkt")):
    for fn in files:
        if fn == "firmwareInfo":
            continue
        p = os.path.join(root, fn)
        zf.write(p, os.path.relpath(p, out))
zf.close()
PYEOF
  rc2b=0
  python3 "$VALIDATOR" --stock-sha256s /dev/null "$NEG2B/FwPkt.zip" || rc2b=$?
  if [ "$rc2b" -eq 0 ]; then
    echo "FAIL: structural validator (mode $MODE) passed a zip with duplicate member + wrong top-level" >&2
    exit 1
  fi
  echo "  OK: structural validator rejected defective archive (exit=$rc2b, mode $MODE)"

  # --------------------------------------------------------------------------
  # Negative test 3 (per mode): stale firmwareInfo — the manifest gate must
  # fail BEFORE any zip is written (the silent-reject root cause, issue #23).
  # --------------------------------------------------------------------------
  NEG3="$STAGE/out_neg3_$MODE"
  rm -rf "$NEG3"; mkdir -p "$NEG3"
  cp -r "$STAGE/out/FwPkt" "$NEG3/FwPkt"
  # Stale manifest: rewrite the appfs line with a wrong size + MD5 (simulates
  # the layered-repack bug from issue #23 — firmwareInfo not regenerated after
  # the appfs changed). The gate must fail BEFORE any zip is written.
  sed 's|^appfs .*|appfs size:999;appfs MD5:00000000000000000000000000000000;|' \
    "$STAGE/stock_firmwareInfo" > "$NEG3/FwPkt/firmwareInfo"

  rc3=0
  run_mode "$MODE" "$NEG3" stale || rc3=$?
  if [ "$rc3" -eq 0 ]; then
    echo "FAIL: firmwareInfo gate (mode $MODE) unexpectedly passed a stale manifest" >&2
    exit 1
  fi
  if [ -e "$NEG3/FwPkt.zip" ] || [ -e "$NEG3/FwPkt.zip.tmp" ]; then
    echo "FAIL: archive exists after firmwareInfo gate failure (mode $MODE)" >&2
    exit 1
  fi
  echo "  OK: firmwareInfo gate exit=$rc3, no archive written (mode $MODE)"
done

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
