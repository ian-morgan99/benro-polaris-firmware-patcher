#!/usr/bin/env bash
# Build, gate, publish, deploy, fingerprint, and update one reproducible
# candidate. This is the only supported source-to-test-candidate entry point
# for normal work. Every offline-gated candidate is published before the
# deployment attempt so independent testers can fetch the exact bytes.
set -euo pipefail

usage() {
  echo "usage: $0 <id> <stock-FwPkt.zip|dir> <clean-libgphoto2-checkout> <build-id> [display-fwver|auto] --change-summary FILE [deployment options]" >&2
  echo "change summary is required: it records the purpose and declared fixes; the script adds exact source commits and artifact hashes" >&2
  echo "deployment options: --host IP --ssh-user USER --max-wait SECS --wake-wait SECS --allow-busy" >&2
  echo "offline-gated candidates are published before deployment; deployment updates the published record" >&2
  exit 2
}
[ $# -ge 4 ] || usage
ID="$1"; BASE="$2"; SRC="$3"; BUILD_ID="$4"; DISPLAY_FWVER="auto"
shift 4
if [ $# -gt 0 ] && [[ "$1" != --* ]]; then
  DISPLAY_FWVER="$1"
  shift
fi
CHANGE_SUMMARY=""
DEPLOY_ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --change-summary)
      [ $# -ge 2 ] || usage
      CHANGE_SUMMARY="$2"; shift 2;;
    --host|--ssh-user|--max-wait|--wake-wait)
      [ $# -ge 2 ] || usage
      DEPLOY_ARGS+=("$1" "$2"); shift 2;;
    --allow-busy)
      DEPLOY_ARGS+=("$1"); shift;;
    --skip-trigger|--skip-verify)
      echo "ERROR: normal release candidates must complete deployment and runtime verification; '$1' is not permitted here." >&2
      exit 2;;
    *) echo "ERROR: unknown deployment option: $1" >&2; usage;;
  esac
done
[ -n "$CHANGE_SUMMARY" ] || {
  echo "ERROR: --change-summary FILE is required; every candidate must state exactly what changed." >&2
  usage
}
[ -f "$CHANGE_SUMMARY" ] || { echo "ERROR: change summary not found: $CHANGE_SUMMARY" >&2; exit 2; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/out/$ID"
VERSION_STATE="$ROOT/docs/RELEASE-VERSION-STATE.md"

# Never reuse an output directory. Reusing it can leave a valid-looking ZIP,
# manifest, or provenance file from an earlier attempt beside newly-built
# payloads, which makes the displayed version and the actual bytes diverge.
if [ -e "$OUT" ]; then
  echo "ERROR: output directory already exists: $OUT" >&2
  echo "       Choose a new candidate id; do not merge or overwrite candidate outputs." >&2
  exit 3
fi
mkdir -p "$OUT"
BUILD_LOG="$OUT/build-release-candidate.log"
exec > >(tee -a "$BUILD_LOG") 2>&1

# Benro Connect displays this value, so two builds must never report the same
# one. It used to be typed by hand and the baseline advanced by hand as well,
# which is how several candidates ended up carrying an identical version.
# Unless a value is supplied explicitly, derive it from the recorded baseline.
if [ -z "$DISPLAY_FWVER" ] || [ "$DISPLAY_FWVER" = "auto" ]; then
  DISPLAY_FWVER="$(python3 "$ROOT/scripts/verify_display_fwver_monotonic.py" \
    --next --state "$VERSION_STATE")"
  echo "Derived display firmware version: $DISPLAY_FWVER"
fi
python3 "$ROOT/scripts/verify_display_fwver_monotonic.py" \
  --candidate "$DISPLAY_FWVER" \
  --state "$VERSION_STATE"

# Keep the immutable build id and the app-visible version in step. When the
# caller does not supply one, derive it so the two can never disagree.
if [ -z "$BUILD_ID" ] || [ "$BUILD_ID" = "auto" ]; then
  BUILD_ID="${DISPLAY_FWVER}-${ID}"
  echo "Derived build id: $BUILD_ID"
fi

case "$ID" in (*[!a-zA-Z0-9._-]*) echo "ERROR: invalid candidate id" >&2; exit 2;; esac
[ -e "$BASE" ] || { echo "ERROR: stock FwPkt not found: $BASE" >&2; exit 2; }
[ -d "$SRC/.git" ] || { echo "ERROR: libgphoto2 input must have a real .git directory" >&2; exit 2; }
[ "$(git -C "$SRC" status --porcelain)" = "" ] || { echo "ERROR: libgphoto2 checkout is dirty" >&2; exit 2; }
BRANCH="$(git -C "$SRC" branch --show-current)"
[ "$BRANCH" = main ] || { echo "ERROR: libgphoto2 must be on main (got ${BRANCH:-detached})" >&2; exit 2; }
# A version is bound to the exact commits it was built from, so the patcher tree
# must be clean too: uncommitted work would make the binding a claim about a
# commit that does not describe the build. Checked here rather than at claim
# time so a doomed release does not spend a full build finding out.
[ "$(git -C "$ROOT" status --porcelain)" = "" ] || {
  echo "ERROR: patcher checkout is dirty; commit or stash before releasing." >&2
  echo "       The display version is bound to one exact set of commits, so it" >&2
  echo "       cannot be claimed from a tree that is not committed." >&2
  exit 3
}
SRC_SHA="$(git -C "$SRC" rev-parse HEAD)"
PATCHER_BRANCH="$(git -C "$ROOT" branch --show-current)"
[ "$PATCHER_BRANCH" = main ] || { echo "ERROR: patcher checkout must be on main (got ${PATCHER_BRANCH:-detached})" >&2; exit 2; }
PATCHER_SHA="$(git -C "$ROOT" rev-parse HEAD)"
echo "Building $ID from libgphoto2 main $SRC_SHA, patcher $PATCHER_SHA, stock base $BASE"

command -v meson >/dev/null || { echo "ERROR: meson is required for libgphoto2 regression tests" >&2; exit 2; }
TEST_BUILD="$(mktemp -d "${TMPDIR:-/tmp}/libgphoto2-regression.XXXXXX")"
PACKAGE_INPUT="$(mktemp -d "${TMPDIR:-/tmp}/fwpkt-package-input.XXXXXX")"
trap 'rm -rf "$TEST_BUILD" "$PACKAGE_INPUT"' EXIT
echo "Running libgphoto2 deterministic regression pack"
# `directory` is deliberately in the gate camlib set and NOT in the shipped set
# (#214 D4). Upstream's own regression suite needs it: several tests enumerate
# cameras through the directory backend, so omitting it drops coverage rather than
# matching the ship configuration. The shipped libraries come from autotools with
# --with-camlibs="$POLARIS_CAMLIBS" (ptp2,pentax only), so this build is a test
# harness, not a rehearsal of what ships -- see #214 D1 for why that gap matters and
# what would close it (assert the shipped .so set directly rather than trusting a
# differently-configured build to stand in for it).
meson setup "$TEST_BUILD" "$SRC" --buildtype=debugoptimized -Dcamlibs=ptp2,pentax,directory >/dev/null
meson compile -C "$TEST_BUILD"
echo "SKIP: libgphoto2:test-gp-port (no-ci serial control-line test; host has no supported DTR/CTS fixture)"
meson test -C "$TEST_BUILD" --no-suite no-ci --print-errorlogs

PATCH_ARGS=(--fwpkt "$(realpath "$BASE")" \
  --libgphoto2-source "$(realpath "$SRC")" --out "$OUT" --build-id "$BUILD_ID")
# Do not apply the retired polestar_app Bulb patch. It zeroed bulb_ms and
# forced the plain-capture branch, bypassing the non-zero Bulb request path.
if [ -n "$DISPLAY_FWVER" ]; then
  PATCH_ARGS+=(--display-fwver "$DISPLAY_FWVER")
fi
"$ROOT/patch-polaris.sh" "${PATCH_ARGS[@]}"
# Exercise the package builder's DISPLAY_FWVER path from the original stock
# tree. The package test itself performs the rebuild; passing the already
# patched candidate here would make its stock polestar_app analyzer read a
# repacked filesystem instead of an ELF input. The normal deterministic runner
# cannot invoke this parameterised test without a Docker image, stock tree, and
# clean source checkout, so the formal release flow supplies all three.
python3 - "$BASE" "$PACKAGE_INPUT" <<'PY'
from pathlib import Path
import shutil
import sys
import zipfile

source = Path(sys.argv[1])
target = Path(sys.argv[2]).resolve()
target.mkdir(parents=True, exist_ok=True)

def copy_tree(root: Path) -> None:
    for item in root.iterdir():
        destination = target / item.name
        if item.is_dir():
            shutil.copytree(item, destination)
        else:
            shutil.copy2(item, destination)

if source.is_dir():
    root = source / "FwPkt" if (source / "FwPkt" / "firmwareInfo").is_file() else source
    copy_tree(root)
else:
    with zipfile.ZipFile(source) as archive:
        for member in archive.infolist():
            name = member.filename
            if not name.startswith("FwPkt/"):
                continue
            relative = Path(name[len("FwPkt/"):])
            if not relative.parts:
                continue
            destination = (target / relative).resolve()
            if target not in destination.parents:
                raise SystemExit(f"unsafe stock archive member: {name}")
            if name.endswith("/"):
                destination.mkdir(parents=True, exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as stream, destination.open("wb") as output:
                    shutil.copyfileobj(stream, output)

if not (target / "firmwareInfo").is_file():
    raise SystemExit(f"stock package has no firmwareInfo: {source}")
PY
PACKAGE_IMAGE="${POLARIS_PATCHER_IMAGE:-polaris-patcher}"
echo "Running parameterised package/display-version regression"
bash "$ROOT/container/test_polaris_pentax_build_package.sh" \
  "$PACKAGE_IMAGE" "$PACKAGE_INPUT" "$SRC"

# The gate requires install-manifest.json and refuses the candidate without it, so
# generate it here rather than relying on someone remembering to. It must be
# written after patch-polaris.sh has produced the zip: the gate re-reads the zip's
# SHA-256 and fails if the manifest disagrees with the bytes on disk, so a
# manifest generated before the final zip exists is stale by construction.
echo "Generating install manifest"
python3 "$ROOT/scripts/generate-fwpkt-manifest.py" "$OUT"

echo "Generating immutable release change manifest"
python3 "$ROOT/scripts/create-release-change-manifest.py" \
  --summary "$CHANGE_SUMMARY" \
  --candidate-id "$ID" \
  --display-fwver "$DISPLAY_FWVER" \
  --build-id "$BUILD_ID" \
  --libgphoto2 "$SRC" \
  --patcher "$ROOT" \
  --stock "$BASE" \
  --candidate-dir "$OUT"
CHANGE_MANIFEST_SHA256="$(sha256sum "$OUT/release-change-manifest.json" | awk '{print $1}')"
{
  echo "candidate_id=$ID"
  echo "release_change_manifest=release-change-manifest.json"
  echo "release_change_manifest_sha256=$CHANGE_MANIFEST_SHA256"
} >> "$OUT/build-source-provenance.txt"

echo "Checking candidate identity"
python3 "$ROOT/scripts/verify-candidate-identity.py" "$OUT" --require-deployable

{
  echo "build_log=build-release-candidate.log"
  echo "install_log=install.log"
} >> "$OUT/build-source-provenance.txt"

"$ROOT/tests/run_prerelease_gate.sh" --build "$OUT/FwPkt"

# Compare the shipped bytes against the previous candidate BEFORE claiming a version.
# A display version is a claim about behaviour, and two claims that describe identical
# files are both false. The commit binding cannot catch this: the patcher sha moves when
# a README is edited, so an unchanged firmware tree still passes it. Runs before --record
# so a rejected candidate never consumes a number.
if [ "${SKIP_DIFFERENTIAL:-0}" != "1" ]; then
  echo "Shipped-artifact differential against the previous candidate"
  python3 "$ROOT/scripts/verify-candidate-differential.py" \
    --current "$OUT" --auto-detect || {
      echo "ERROR: shipped-artifact differential failed; not claiming $DISPLAY_FWVER." >&2
      echo "       Set SKIP_DIFFERENTIAL=1 only if you have a reason and record it." >&2
      exit 1
    }
fi

# The candidate is publishable once it has passed the offline gate. Publication
# must happen before any hardware deployment attempt so testers on another rig
# can fetch the exact bytes even when this rig is unavailable. Deployment and
# runtime verification then advance the published record; they do not decide
# whether the artifact is published at all.
# Claiming a version also binds it to these exact commits, in both directions:
# the version may never describe a different build, and these commits may never
# be issued under a different version. The tree was proven clean above, and the
# build writes only to out/ (ignored) and mktemp, so this is the same tree.
python3 "$ROOT/scripts/verify_display_fwver_monotonic.py" \
  --candidate "$DISPLAY_FWVER" \
  --state "$VERSION_STATE" --record \
  --libgphoto2-commit "$SRC_SHA" --patcher-commit "$PATCHER_SHA"
git -C "$ROOT" add -- "$VERSION_STATE"

echo
echo "== 6. publish the gated candidate =="
{
  echo "install_command=./scripts/release/release-fwpkt.sh $OUT"
  echo "install_status=pending-deployment"
} >> "$OUT/build-source-provenance.txt"

bash "$ROOT/.github/skills/fwpkt-private-upload/scripts/upload-fwpkt-to-pr.sh" \
  --build "$OUT" --id "$ID" --status gated \
  --note "Main-branch reproducible candidate; offline gate passed and artifact published for independent testing; deployment pending."
echo "Published gated candidate: $OUT/FwPkt.zip"
md5sum "$OUT/FwPkt.zip"; sha256sum "$OUT/FwPkt.zip"

# Deployment is still attempted automatically when hardware is available. The
# installer stages the extracted FwPkt/ tree, verifies every firmwareInfo MD5
# on-device, reboots, proves the boot was real by an uptime reset, and checks
# the exact build/source identity. It writes install_status=installed-verified
# and an install receipt into OUT. A failure does not retract publication.
echo
echo "== 7. deploy and runtime-verify the published candidate =="
if ! "$ROOT/scripts/release/release-fwpkt.sh" "$OUT" "${DEPLOY_ARGS[@]}"; then
  echo "ERROR: deployment/runtime verification failed." >&2
  echo "       The gated artifact remains published for independent testers." >&2
  echo "       Exact local output retained for diagnosis: $OUT" >&2
  bash "$ROOT/.github/skills/fwpkt-private-upload/scripts/upload-fwpkt-to-pr.sh" \
    --build "$OUT" --id "$ID" --status gated \
    --note "Offline gate passed and artifact published; local deployment attempt failed; see the uploaded build and install logs."
  exit 1
fi

grep -qx 'install_status=installed-verified' "$OUT/build-source-provenance.txt" || {
  echo "ERROR: installer returned without installed-verified provenance." >&2
  echo "       Refusing to publish an identity-incomplete candidate." >&2
  exit 1
}

echo "== 8. update the published record with deployment evidence =="
bash "$ROOT/.github/skills/fwpkt-private-upload/scripts/upload-fwpkt-to-pr.sh" \
  --build "$OUT" --id "$ID" --status installed-verified \
  --note "Main-branch reproducible candidate; deployed and runtime-verified by the canonical installer; physical camera qualification recorded separately."
echo "User-test candidate published: $OUT/FwPkt.zip"
md5sum "$OUT/FwPkt.zip"; sha256sum "$OUT/FwPkt.zip"
