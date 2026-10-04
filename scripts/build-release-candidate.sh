#!/usr/bin/env bash
# Build, gate, fingerprint, and privately publish one reproducible candidate.
# This is the only supported source-to-candidate entry point for normal work.
set -euo pipefail

usage() {
  echo "usage: $0 <id> <stock-FwPkt.zip|dir> <clean-libgphoto2-checkout> <build-id> [display-fwver|auto]" >&2
  exit 2
}
[ $# -ge 4 ] && [ $# -le 5 ] || usage
ID="$1"; BASE="$2"; SRC="$3"; BUILD_ID="$4"; DISPLAY_FWVER="${5:-auto}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/out/$ID"
VERSION_STATE="$ROOT/docs/RELEASE-VERSION-STATE.md"

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
SRC_SHA="$(git -C "$SRC" rev-parse HEAD)"
echo "Building $ID from libgphoto2 main $SRC_SHA and stock base $BASE"

command -v meson >/dev/null || { echo "ERROR: meson is required for libgphoto2 regression tests" >&2; exit 2; }
TEST_BUILD="$(mktemp -d "${TMPDIR:-/tmp}/libgphoto2-regression.XXXXXX")"
PACKAGE_INPUT="$(mktemp -d "${TMPDIR:-/tmp}/fwpkt-package-input.XXXXXX")"
trap 'rm -rf "$TEST_BUILD" "$PACKAGE_INPUT"' EXIT
echo "Running libgphoto2 deterministic regression pack"
meson setup "$TEST_BUILD" "$SRC" --buildtype=debugoptimized -Dcamlibs=ptp2,pentax,directory >/dev/null
meson compile -C "$TEST_BUILD"
echo "SKIP: libgphoto2:test-gp-port (no-ci serial control-line test; host has no supported DTR/CTS fixture)"
meson test -C "$TEST_BUILD" --no-suite no-ci --print-errorlogs

PATCH_ARGS=(--fwpkt "$(realpath "$BASE")" \
  --libgphoto2-source "$(realpath "$SRC")" --out "$OUT" --build-id "$BUILD_ID")
# The formal release path must carry the verified firmware-side Bulb fix as
# well as the matched libgphoto2 stack.  Without this explicit flag, a build
# from an untouched stock FwPkt silently omits the polestar_app pre-shot
# delay fix; a build from an already-patched candidate would hide that mistake
# by inheriting the patch from its base artifact.
PATCH_ARGS+=(--polestar-bulb-patch)
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
"$ROOT/tests/run_prerelease_gate.sh" --build "$OUT/FwPkt"

# The candidate is real only once it has passed the gate. Claim the version at
# that point so a build that fails its tests does not consume a number, while
# two candidates that both reach this line can never share one.
python3 "$ROOT/scripts/verify_display_fwver_monotonic.py" \
  --candidate "$DISPLAY_FWVER" \
  --state "$VERSION_STATE" --record
git -C "$ROOT" add -- "$VERSION_STATE"

bash "$ROOT/.github/skills/fwpkt-private-upload/scripts/upload-fwpkt-to-pr.sh" \
  --build "$OUT" --id "$ID" --status candidate \
  --note "Main-branch reproducible candidate; gate passed; physical test pending."
echo "Candidate ready: $OUT/FwPkt.zip"
md5sum "$OUT/FwPkt.zip"; sha256sum "$OUT/FwPkt.zip"
