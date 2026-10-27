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
# A gitignored build/ directory is invisible to the dirty check above, but
# container/build_ptp2.sh copies the input with `cp -a`, build directories
# included, so the container reuses objects compiled BEFORE the patcher applied
# its own edits -- most importantly the _Camera padding. The build then dies at
# the fail-closed ABI check with "gp_camera_new does not allocate 4140 B" even
# though the padding message said it applied. Refuse up front instead of
# spending a full build to find out. See docs/LIBGPHOTO2-UPGRADE-PROCESS.md.
for stale in build _build build-asan; do
  if [ -d "$SRC/$stale" ]; then
    echo "ERROR: libgphoto2 input contains a stale '$stale/' directory." >&2
    echo "       It is gitignored, so the dirty check above cannot see it, but" >&2
    echo "       'cp -a' copies it into the container and the stale objects are" >&2
    echo "       reused, which fails the _Camera pad check." >&2
    echo "       Use a clean checkout (a local clone is instant):" >&2
    echo "         git clone --branch main <repo> /tmp/lgp-src" >&2
    exit 2
  fi
done
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
# The patcher tree is not required to be clean (this script edits release state
# as it goes), so record the tree state as well as the commit. A version is
# bound to the exact commits it was built from, and a dirty tree means the
# binding is a commit plus uncommitted work rather than a commit alone.
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

# Capture the gate transcript into the candidate's own evidence directory. The
# gate is the release's proof, and AGENTS.md requires its skips to be recorded
# in the release evidence -- so the transcript is written where the evidence
# lives rather than left to scroll past in the build log. A SKIP is a
# prerequisite gap, not a pass, and must be visible to whoever reads the
# evidence later.
GATE_EVIDENCE="$OUT/gate-transcript.txt"
mkdir -p "$OUT"
# Pass the libgphoto2 source so the gate can run its source contracts against the
# exact tree that produced this candidate. Without it the gate only checks
# provenance and never runs test-pentax-capture-contract.py, which is the check
# that would have caught .75's fail-closed shutter write hanging every capture.
"$ROOT/tests/run_prerelease_gate.sh" --build "$OUT/FwPkt" --libgphoto2-src "$SRC" 2>&1 | tee "$GATE_EVIDENCE"
GATE_RC="${PIPESTATUS[0]}"
if [ "$GATE_RC" -ne 0 ]; then
  echo "ERROR: pre-release gate failed (rc=$GATE_RC); transcript in $GATE_EVIDENCE" >&2
  exit "$GATE_RC"
fi
# Surface the skips explicitly: they are recorded in the transcript, but a
# reader scanning the build log should not have to hunt for them.
GATE_SKIPS="$(grep -c '^SKIP:' "$GATE_EVIDENCE" || true)"
if [ "${GATE_SKIPS:-0}" -gt 0 ]; then
  echo "NOTE: pre-release gate recorded ${GATE_SKIPS} SKIP(s) -- prerequisite gaps, not passes."
  echo "      They are listed in $GATE_EVIDENCE and must be recorded in the release evidence."
  grep '^SKIP:' "$GATE_EVIDENCE" | sed 's/^/      /'
fi

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

# The candidate is real only once it has passed the gate. Claim the version at
# that point so a build that fails its tests does not consume a number, while
# two candidates that both reach this line can never share one.
# Claiming a version also binds it to these exact commits, in both directions:
# the version may never describe a different build, and these commits may never
# be issued under a different version. The tree was proven clean above, and the
# build writes only to out/ (ignored) and mktemp, so this is the same tree.
python3 "$ROOT/scripts/verify_display_fwver_monotonic.py" \
  --candidate "$DISPLAY_FWVER" \
  --state "$VERSION_STATE" --record \
  --libgphoto2-commit "$SRC_SHA" --patcher-commit "$PATCHER_SHA"
git -C "$ROOT" add -- "$VERSION_STATE"

bash "$ROOT/.github/skills/fwpkt-private-upload/scripts/upload-fwpkt-to-pr.sh" \
  --build "$OUT" --id "$ID" --status candidate \
  --note "Main-branch reproducible candidate; gate passed; physical test pending."
echo "Candidate ready: $OUT/FwPkt.zip"
md5sum "$OUT/FwPkt.zip"; sha256sum "$OUT/FwPkt.zip"

# A candidate is not finished until it has been installed and confirmed on the
# device, and the only supported way to do that is this installer: it stages the
# extracted FwPkt/ tree (the on-boot watcher consumes the tree, not the zip —
# issue #58), verifies every firmwareInfo MD5 on-device, reboots, proves the boot
# was real by an uptime reset, and fail-closes on build_id plus every mandatory
# file digest. Printing the exact command here keeps install from becoming tribal
# knowledge; see docs/FIRMWARE-INSTALL-PROCESS.md.
echo
echo "== 6. install this candidate (the only supported path) =="
echo "  ./scripts/release/release-fwpkt.sh $OUT"
echo "  # add --skip-trigger to stage+verify without rebooting,"
echo "  # --allow-busy only after confirming no exposure is in flight"
echo "  # docs/FIRMWARE-INSTALL-PROCESS.md explains why zip-only staging is ignored"
# Install status lives in its own host-owned file. It must NOT be appended to
# build-source-provenance.txt: that file is written inside the patcher container
# and arrives owned by nfsnobody, so a host-side append fails with EACCES and
# `set -e` aborts the whole build *after* it has already published (observed on
# .72, where the candidate was built and pushed but the script exited 1).
{
  echo "build_id=$BUILD_ID"
  echo "install_command=./scripts/release/release-fwpkt.sh $OUT"
  echo "install_status=not-installed"
} > "$OUT/install-status.txt"
