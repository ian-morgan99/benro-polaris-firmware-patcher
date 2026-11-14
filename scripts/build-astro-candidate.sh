#!/usr/bin/env bash
# Build a separately identified Astro candidate without deploying it.
# The FwPkt uses the same patch-polaris.sh camera path as standard firmware.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ID="" STOCK="" LIBSRC="" OUT="" DISPLAY_FWVER="" BUILD_ID=""
CHANGE_SUMMARY=""
CAMERA_BASELINE="397320411a1355f06d21233435e144d24efc4207"
# Driver selection is mandatory for every candidate: no silently stale fallback.
# Supply --libgphoto2-commit FULL_SHA and record it in the release summary.
LIB_BASELINE=""
# Previous released driver pin is retained only for regression/superset checking.
PREVIOUS_LIB_BASELINE="3fb26e536ac169e4970d69516a9d45daf62563f5"
CATALOG_PACKAGE="" FMIN="14" FMAX="400" SENSOR="36"
ASTRO_SRC_CACHE="${ASTRO_SRC_CACHE:-$ROOT/out/.astro-src-cache}"
FORCE=0 NO_INDEXES=0 IMAGE="${POLARIS_PATCHER_IMAGE:-polaris-patcher}"

usage() {
  cat >&2 <<'EOF'
usage: scripts/build-astro-candidate.sh --id ID --stock-fwpkt PATH \
  --libgphoto2-source PATH --display-fwver X.Y.Z.N.M --build-id ID \
  --catalog-package DIR --change-summary FILE [options]

Build-only Astro candidate. Output contains FwPkt/ and additive
astro-bundle/. This never stages, reboots, flashes, or uploads.
options: --camera-baseline SHA --libgphoto2-commit SHA
  --focal-min MM --focal-max MM --sensor-mm MM
  --astro-src-cache DIR --image NAME --no-indexes --out DIR --force
EOF
  exit 2
}
die() { echo "ERROR: $*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --id) ID="$2"; shift 2;; --stock-fwpkt) STOCK="$2"; shift 2;;
    --libgphoto2-source) LIBSRC="$2"; shift 2;;
    --display-fwver) DISPLAY_FWVER="$2"; shift 2;; --build-id) BUILD_ID="$2"; shift 2;;
    --change-summary) CHANGE_SUMMARY="$2"; shift 2;;
    --camera-baseline) CAMERA_BASELINE="$2"; shift 2;;
    --libgphoto2-commit) LIB_BASELINE="$2"; shift 2;;
    --catalog-package) CATALOG_PACKAGE="$2"; shift 2;;
    --focal-min) FMIN="$2"; shift 2;; --focal-max) FMAX="$2"; shift 2;;
    --sensor-mm) SENSOR="$2"; shift 2;; --astro-src-cache) ASTRO_SRC_CACHE="$2"; shift 2;;
    --image) IMAGE="$2"; shift 2;; --no-indexes) NO_INDEXES=1; shift;;
    --out) OUT="$2"; shift 2;; --force) FORCE=1; shift;; -h|--help) usage;;
    *) die "unknown option: $1";;
  esac
done
[ -n "$LIB_BASELINE" ] || die "explicit --libgphoto2-commit FULL_SHA is required; no default driver pin is permitted"
[ -n "$ID" ] && [ -n "$STOCK" ] && [ -n "$LIBSRC" ] &&
[ -n "$DISPLAY_FWVER" ] && [ -n "$BUILD_ID" ] && [ -n "$CATALOG_PACKAGE" ] &&
[ -n "$CHANGE_SUMMARY" ] || usage
[ -f "$CHANGE_SUMMARY" ] || die "change summary does not exist: $CHANGE_SUMMARY"
# Parse it NOW. The file is only read at step 6/7 by create-astro-candidate-manifest.py,
# so a trailing comma or an unescaped quote is reported after a full multi-minute firmware
# build has already been spent -- and the build output is left half-written. I hit exactly
# that writing the v99 summary. Fail in milliseconds with the parser's line and column.
python3 -c "import json,sys;json.load(open(sys.argv[1],encoding='utf-8'))" \
  "$CHANGE_SUMMARY" 2>/dev/null || die "change summary is not valid JSON: $CHANGE_SUMMARY
       $(python3 -c "import json,sys;json.load(open(sys.argv[1],encoding='utf-8'))" \
          "$CHANGE_SUMMARY" 2>&1 | tail -1)"
case "$ID" in (*[!a-zA-Z0-9._-]*) die "invalid candidate id: $ID";; esac
case "$DISPLAY_FWVER" in (*[!0-9.]*|.*|*..*|*.) die "invalid display version";; esac
case "$DISPLAY_FWVER" in (*.*.*.*.*) ;; (*) die "need five-component display version";; esac
case "$CAMERA_BASELINE$LIB_BASELINE" in (*[!0-9a-f]*) die "baseline commits must be lower-case SHAs";; esac
[ "$(printf %s "$CAMERA_BASELINE" | wc -c)" -eq 40 ] || die "camera baseline must be full SHA"
[ "$(printf %s "$LIB_BASELINE" | wc -c)" -eq 40 ] || die "libgphoto2 baseline must be full SHA"

BRANCH="$(git -C "$ROOT" branch --show-current)"
[ "$BRANCH" = "feature/astro-native-platesolve" ] || die "wrong Astro branch: $BRANCH"
TREE_STATUS="$(git -C "$ROOT" status --porcelain=v1 --untracked-files=all)"
[ -z "$TREE_STATUS" ] || die "Astro source tree is dirty; use a clean clone"
git -C "$ROOT" diff --check || die "Astro source whitespace errors"
git -C "$ROOT" cat-file -e "$CAMERA_BASELINE^{commit}" || die "camera baseline is not present"
git -C "$ROOT" merge-base --is-ancestor "$CAMERA_BASELINE" HEAD || die "camera baseline is not in Astro HEAD"

[ -d "$LIBSRC" ] || die "libgphoto2 source must be a checkout"
# The pinned commit must be reachable from a real branch on origin, so provenance always
# points at something a third party can fetch. A detached checkout at that SHA is fine; an
# orphan is not. Driver main carries the v94 pin (43dccb81b). feature/polaris-capture-events
# carries #233 (pentax_model_answers_undeclared_generic_props) and, once PR #144 is merged,
# the #235 shutter gate -- so a v95 pin lives there, not on main.
LIB_REACHABLE=0
for LIB_REF in origin/main origin/feature/polaris-capture-events; do
  git -C "$LIBSRC" rev-parse -q --verify "$LIB_REF^{commit}" >/dev/null || continue
  if git -C "$LIBSRC" merge-base --is-ancestor "$LIB_BASELINE" "$LIB_REF" 2>/dev/null; then
    LIB_REACHABLE=1
    break
  fi
done
[ "$LIB_REACHABLE" = 1 ] || {
  # "orphan or unmerged commit?" was misleading on 2026-11-06: the pin WAS on
  # origin/main, but this clone had been created from a local repo whose
  # refs/remotes/origin/main was stale, so the ancestor test ran against the wrong
  # tip and a perfectly good commit looked orphaned. Distinguish the two cases here
  # rather than making the operator guess and go chase the wrong thing.
  echo "ERROR: libgphoto2 baseline $LIB_BASELINE is not reachable from origin/main"
  echo "       or origin/feature/polaris-capture-events in $LIBSRC."
  if git -C "$LIBSRC" cat-file -e "${LIB_BASELINE}^{commit}" 2>/dev/null; then
    echo "       The commit IS present locally, so this is one of two things:"
    echo "         (a) a stale remote-tracking ref -- very common when the clone was"
    echo "             made from another local repo rather than fetched from GitHub."
    echo "             Check what this clone thinks main is:" $(git -C "$LIBSRC" rev-parse --short origin/main 2>/dev/null || echo '(absent)')
    echo "             Refresh it and retry:"
    echo "               git -C $LIBSRC fetch origin 'refs/remotes/origin/*:refs/remotes/origin/*'"
    echo "         (b) genuinely unmerged -- the commit exists only on a local branch."
    echo "             Verify against the real remote before believing this."
  else
    echo "       The commit is not even present in $LIBSRC. Fetch it:"
    echo "         git -C $LIBSRC fetch origin $LIB_BASELINE"
  fi
  exit 1
}
# Reachability proves nothing about *completeness*. When the pin changes, require that it still
# carries everything the previous pin carried. Fail closed: if the previous pin cannot be inspected
# in this checkout, that is itself a reason not to build.
if [ "$LIB_BASELINE" != "$PREVIOUS_LIB_BASELINE" ]; then
  if ! git -C "$LIBSRC" cat-file -e "${PREVIOUS_LIB_BASELINE}^{commit}" 2>/dev/null; then
    die "cannot verify superset: previous pin $PREVIOUS_LIB_BASELINE is not present in $LIBSRC (fetch it)"
  fi
  bash "$ROOT/scripts/pin-divergence-check.sh" "$LIBSRC" "$LIB_BASELINE" "$PREVIOUS_LIB_BASELINE" \
    || die "libgphoto2 pin is not a superset of the previous pin; refusing to build a regressed candidate"
fi
[ "$(git -C "$LIBSRC" rev-parse HEAD)" = "$LIB_BASELINE" ] || die "wrong libgphoto2 commit"
[ -z "$(git -C "$LIBSRC" status --porcelain --untracked-files=all)" ] || die "libgphoto2 source is dirty"
for stale in build _build build-asan; do [ ! -d "$LIBSRC/$stale" ] || die "libgphoto2 has stale $stale/"; done
[ -e "$STOCK" ] || die "stock FwPkt does not exist: $STOCK"
[ -d "$CATALOG_PACKAGE/tiles" ] || die "catalogue package has no tiles/"
for required in tiles.json tiles.ptri tiles.ptri.json; do
  [ -f "$CATALOG_PACKAGE/$required" ] || die "catalogue package missing $required"
done

if [ -z "$OUT" ]; then OUT="$ROOT/out/$ID"; elif [[ "$OUT" != /* ]]; then OUT="$ROOT/$OUT"; fi
OUT="$(realpath -m "$OUT")"; ROOT_REAL="$(realpath -m "$ROOT")"
case "$OUT" in "$ROOT_REAL/out/"*) ;; (*) die "output must be below out/";; esac
[ "$OUT" != "$ROOT_REAL/out" ] || die "refusing whole out/"
[ ! -L "$OUT" ] || die "refusing symlink output"
if [ -e "$OUT" ]; then [ "$FORCE" = 1 ] || die "output exists; use --force"; rm -rf -- "$OUT"; fi
mkdir -p "$OUT"

# ---------------------------------------------------------------------------
# Prerequisites, checked BEFORE the first build step (#306 follow-up).
#
# The doctor used to run only inside scripts/build-astro.sh, which this script
# calls at step [2/7]. Step [1/7] is patch-polaris.sh -- the long camera build --
# so on 2026-11-09 a broken host was discovered *after* the expensive part had
# already been attempted, and the failure surfaced as "no usable docker" from a
# script that had nothing to do with the cause. Checking here moves that to seconds.
#
# Provision first so the doctor sees the environment the build will actually use,
# otherwise it reports blockers this wrapper would have handled anyway: TMPDIR must
# be host-visible (patch-polaris.sh extracts the stock packet with mktemp -d and
# bind-mounts it, and /tmp is private to the sandbox), and a broken native ubireader
# has a working bridge in-repo.
ENVBIN="$ROOT/out/.build-env/bin"
TMPROOT="$ROOT/out/.build-env/tmp"
mkdir -p "$ENVBIN" "$TMPROOT" || die "could not create $ROOT/out/.build-env"
export TMPDIR="$TMPROOT"
case ":$PATH:" in (*":$ENVBIN:"*) ;; (*) PATH="$ENVBIN:$PATH";; esac
export PATH
if ! (command -v ubireader_extract_files >/dev/null 2>&1 \
      && ubireader_extract_files --help >/dev/null 2>&1); then
  [ -x "$ROOT/tools/ubireader-docker" ] || die "tools/ubireader-docker missing"
  export UBIREADER_EXTRACT_FILES="$ROOT/tools/ubireader-docker"
fi

# Put a working `docker` on the child's PATH. This is the systemic fix rather than
# another per-script patch: every script this wrapper invokes calls plain `docker`,
# and each one that checks independently has failed with its own wording --
# patch-polaris.sh says "Install Docker Desktop", build-astro.sh says "docker not
# found", and the host shim returns rc=127 reading like "not installed" (#308).
# Patching them one at a time is how five sites became six. $ENVBIN is already first
# on PATH and inherited by every child, so one entry here covers all of them,
# including scripts that have not been audited.
#
# The generated shim execs an ABSOLUTE host path. It must never be
# `exec flatpak-spawn --host docker "$@"`: that asks the host to resolve `docker` on
# the host's PATH, where ~/.local/bin and ~/bin sit by default, so a shim of that
# same shape on the host re-enters itself and dies.
if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  # shellcheck disable=SC1091
  . "$ROOT/tools/host-docker.sh"
  DOCKER_PREFIX="$(polaris_docker_prefix 2>/dev/null || true)"
  if [ -z "$DOCKER_PREFIX" ]; then
    echo "ERROR: no usable docker for this build." >&2
    if polaris_docker_shadowed; then
      echo "       a 'docker' IS on PATH but cannot reach a daemon." >&2
      echo "       the host resolves it to: $(polaris_host_docker_resolved)" >&2
    fi
    echo "       run scripts/build-doctor.sh, which names the exact cause." >&2
    exit 1
  fi
  printf '#!/bin/sh\n# generated by scripts/build-astro-candidate.sh -- do not edit\nexec %s "$@"\n' \
    "$DOCKER_PREFIX" > "$ENVBIN/docker"
  chmod +x "$ENVBIN/docker"
fi

echo "=== preflight: scripts/build-doctor.sh ==="
if [ "${SKIP_DOCTOR:-0}" = 1 ]; then
  echo "WARNING: --skip-doctor: build prerequisites were NOT verified." >&2
  DOCTOR_STATUS="skipped-by-flag"
elif bash "$ROOT/scripts/build-doctor.sh" --libgphoto2 "$LIBSRC" --stock "$STOCK" \
        --catalog "$CATALOG_PACKAGE" --image "$IMAGE" > "$OUT/doctor.log" 2>&1; then
  DOCTOR_STATUS="green"
  echo "build-doctor: GREEN (log: $OUT/doctor.log)"
else
  DOCTOR_STATUS="red"
  echo "ERROR: build-doctor.sh reported RED -- refusing to start a build that will" >&2
  echo "       fail later and report itself as an unrelated problem." >&2
  echo "       Full output: $OUT/doctor.log" >&2
  grep -E '^  (FAIL|WARN)' "$OUT/doctor.log" | sed 's/^/       /' >&2 || true
  echo "       Fix each FAIL line, or set SKIP_DOCTOR=1 for a documented exception." >&2
  exit 1
fi

echo "[1/7] building shared camera firmware packet"
bash "$ROOT/patch-polaris.sh" --fwpkt "$STOCK" --libgphoto2-source "$LIBSRC" \
  --enable-usb-scsi --out "$OUT" --build-id "$BUILD_ID" \
  --display-fwver "$DISPLAY_FWVER" --image "$IMAGE"

echo "[2/7] building additive native-C Astro bundle"
ASTRO_ARGS=(--out "$OUT/astro-bundle" --image "$IMAGE" --focal-min "$FMIN" \
  --focal-max "$FMAX" --sensor-mm "$SENSOR" --catalog-package "$CATALOG_PACKAGE" \
  --src-cache "$ASTRO_SRC_CACHE")
[ "$NO_INDEXES" = 1 ] && ASTRO_ARGS+=(--no-indexes)
bash "$ROOT/build-astro.sh" "${ASTRO_ARGS[@]}"
[ -d "$OUT/astro-bundle/COPY-TO-SD-CARD-ROOT/polaris-astro" ] || die "Astro tree missing"

# The on-device manifest, generated HERE because this is the script production
# actually runs. scripts/build-astro-bundle.sh has always created it and fails
# closed if empty, but nothing in production calls that script -- so every astro
# candidate published so far shipped polaris-astro.zip WITHOUT it. install_astro.sh
# then prints "installed files are unverified" and skips its byte comparison, and
# polaris-astro-sync.sh at boot falls back to copy-if-missing: a new release can
# install nothing at all while reporting success. That is the #292 silent no-op,
# reintroduced by packaging rather than by code.
#
# Paths are relative to the astro directory because that is the directory both
# install_astro.sh and polaris-astro-sync.sh hash against.
SD_ASTRO="$OUT/astro-bundle/COPY-TO-SD-CARD-ROOT/polaris-astro"

# Issue #331, on the path production actually runs.
#
# The same fix was first written into scripts/build-astro-bundle.sh, which the
# comment further down this file already records as never being called by
# anything. It therefore had no effect: the v108 build failed its artifact gate
# with "no licence texts under polaris-astro/licenses/", which is the gate doing
# its job rather than a spurious failure -- it reads the finished archive, so a
# copy that never happened cannot pass.
#
# licenses/ sits OUTSIDE COPY-TO-SD-CARD-ROOT, so a user who follows this
# bundle's own README and copies only the SD tree receives polaris-solve and
# polaris-skysim -- GPL v2-or-later, because qfits-an is linked in -- with no
# licence text and no source offer. The tarball beside the tree is a build
# artefact, not a distribution medium. This mirrors what the wifi kit already
# does: the texts travel inside the tree the user copies, next to the binaries
# they cover. Only the texts go on the card (~46 KB); the corresponding source
# is reached by the written offer below, which is the alternative GPL v2 section
# 3 explicitly allows.
#
# Note the source path differs from build-astro-bundle.sh: OUT here is the
# candidate root, so the licence texts are under astro-bundle/, not licenses/.
ASTRO_LIC_SRC="$OUT/astro-bundle/licenses"
SD_ASTRO_LIC="$SD_ASTRO/licenses"
mkdir -p "$SD_ASTRO_LIC" || die "cannot create $SD_ASTRO_LIC"
for lf in COPYING-GPL-2.txt COPYING-LGPL-2.1.txt README-GPL.txt; do
  [ -f "$ASTRO_LIC_SRC/$lf" ] \
    || die "issue #331: $ASTRO_LIC_SRC/$lf is missing, cannot ship a licence inside the SD tree"
  cp "$ASTRO_LIC_SRC/$lf" "$SD_ASTRO_LIC/$lf" || die "cannot copy $lf into the SD tree"
done
[ -s "$SD_ASTRO_LIC/README-GPL.txt" ] \
  || die "issue #331: README-GPL.txt did not land in $SD_ASTRO_LIC -- GPL binaries would ship with no offer"

cat > "$SD_ASTRO/LICENCE-astro.txt" << 'OFFER'
Copyleft licences applying to polaris-solve and polaris-skysim
==============================================================

These two binaries are GPL v2-or-later. They link astrometry.net's qfits-an
FITS reader, whose files carry the ESO "GNU General Public License ... either
version 2 of the License, or (at your option) any later version" notice.

The full licence texts are beside this file, in polaris-astro/licenses/:

  COPYING-GPL-2.txt      the GNU GPL v2
  COPYING-LGPL-2.1.txt   the GNU LGPL v2.1 (applies to libnl, used by the
                         separate polaris-wifi kit -- see its own LICENCE-wifi.txt)
  README-GPL.txt         which components are copyleft, why, the per-file
                         licence census, sha256 of every source archive, and
                         the upstream URLs

Written offer for corresponding source (GPL v2 section 3)
---------------------------------------------------------
The exact source used to build these binaries is:

  astrometry.net-0.98.tar.gz     upstream source that was compiled
  jpeg-9f.tar.gz                 IJG libjpeg, statically linked into polaris-extract
  polaris-build-recipe.tar.gz    our build recipe, the BSD-3 GSL shim, and our C sources

Those archives are published alongside this release in the bundle's top-level
licenses/ directory, and in the patcher repository under .astro-src-cache. If
you received these binaries without that directory, request a copy from whoever
supplied them; under GPL v2 section 3 they must provide the source with the
binary or a written offer to do so.

Everything else in polaris-astro/ (polaris-extract's star finder, polaris-mount,
polaris-httpd, polaris-link/jog/prog/astro, polaris-logwatch, polaris-match and
all *.sh) is MIT or BSD-3 and talks to the GPL binaries as separate processes
over files and sockets -- nothing GPL is linked into them.
OFFER
[ -s "$SD_ASTRO/LICENCE-astro.txt" ] \
  || die "issue #331: could not write $SD_ASTRO/LICENCE-astro.txt"

ASTRO_MANIFEST="$SD_ASTRO/polaris-astro.manifest"
(
  cd "$SD_ASTRO"
  {
    for b in polaris-httpd polaris-solve polaris-solve-independent \
             polaris-solve-independent-search polaris-exif-solve \
             polaris-skysim-independent polaris-extract polaris-logwatch \
             polaris-match polaris-skysim polaris-mount; do
      [ -f "$b" ] && printf '%s\n' "$b"
    done
    for s in *.sh; do [ -f "$s" ] && printf '%s\n' "$s"; done
  } | sort -u |
    while IFS= read -r f; do sha256sum "$f"; done
) > "$ASTRO_MANIFEST"
[ -s "$ASTRO_MANIFEST" ] || die "generated $ASTRO_MANIFEST is empty"
grep -q 'polaris-httpd$' "$ASTRO_MANIFEST" \
  || die "$ASTRO_MANIFEST does not cover polaris-httpd (the web UI lives inside it)"

(
  cd "$OUT/astro-bundle/COPY-TO-SD-CARD-ROOT"
  find . -type f -print0 | sort -z |
    while IFS= read -r -d '' file; do sha256sum "$file"; done
) > "$OUT/astro-bundle/ASTRO-MANIFEST.sha256"
[ -f "$OUT/astro-bundle/ASTRO-MANIFEST.sha256" ] || die "Astro manifest missing"

# Build the SD-rooted kit archives here, and verify them as archives.
#
# Until now this path produced no polaris-astro.zip or polaris-wifi.zip at all:
# only scripts/build-astro-bundle.sh creates them, and nothing in production calls
# that script. The zips published for 6.0.0.54.99 were therefore made outside any
# tracked build path, so the wrapper's licence gate never ran on the bytes anyone
# was handed -- polaris-wifi.zip shipped four statically-linked LGPL binaries with
# no licence and no source offer (issue #286). publish-astro-candidate.sh skips a
# missing zip silently ([ -f ] || continue), so absence passed unnoticed.
#
# Assert against the finished archive, not the staging directory: the zip is what a
# user receives, and a file that exists on disk but is excluded from the archive is
# exactly how .99 slipped through.
SD_ROOT="$OUT/astro-bundle/COPY-TO-SD-CARD-ROOT"
# Fail loudly rather than skip. Every assertion below is guarded by [ -d ]/[ -f ]
# tests, so a wrong SD_ROOT would silently skip all of them and exit 0 -- a vacuous
# pass, which is exactly the bug class in issue #286. The polaris-astro check above
# guarantees this directory exists on the real path, so reaching the die means the
# tree really is missing.
[ -d "$SD_ROOT" ] || die "SD staging tree missing: $SD_ROOT -- cannot verify the kit archives"
# polaris-astro.zip is rebuilt unconditionally, not only when the wifi kit
# happens to be present. The inner bundle builder can leave an archive behind
# that predates anything added to the tree afterwards, and the assertions below
# read the archive rather than the tree -- so a zip that does not match the tree
# it is meant to represent must be rebuilt, not reused. Rebuilding here makes the
# archive a function of the final tree, so "present in the tree" and "present in
# what the user extracts" cannot diverge.
#
# The old form wrapped this in a subshell ending with `true`, which swallowed any
# failing command inside it: a zip that errored part-way through left an archive
# on disk missing entries, the assertions then refused it, and the real cause --
# the failed zip -- was never reported. Each step is checked explicitly now.
(
  cd "$SD_ROOT" || exit 1
  command -v zip >/dev/null 2>&1 || { echo "ERROR: 'zip' is not installed -- cannot produce the archives users are given" >&2; exit 1; }
  rm -f polaris-astro.zip
  zip -qrX polaris-astro.zip polaris-astro \
    || { echo "ERROR: failed to build polaris-astro.zip" >&2; exit 1; }
  if [ -d polaris-wifi ]; then
    rm -f polaris-wifi.zip
    zip -qrX polaris-wifi.zip polaris-wifi \
      || { echo "ERROR: failed to build polaris-wifi.zip" >&2; exit 1; }
  fi
  if [ -d astrometry ]; then
    rm -f astrometry-indexes.zip
    zip -qrX astrometry-indexes.zip astrometry \
      || { echo "ERROR: failed to build astrometry-indexes.zip" >&2; exit 1; }
  fi
) || die "could not produce the SD kit archives -- see the ERROR lines above"

# Membership test for a zip member, without a pipeline.
#
# `unzip -Z1 archive | grep -qx pattern` is wrong under `set -o pipefail`, and
# wrong in the direction that breaks a release: grep -q exits the moment it
# matches, unzip then dies of SIGPIPE (141), and pipefail reports 141 -- so a
# check that DID find the member returns failure and the script dies claiming the
# archive is missing something it contains. Whether it fires depends on where the
# match falls in the listing relative to the pipe buffer, which is why the
# manifest assertion passed while the licence assertion did not, on the same
# archive, seconds apart. Verified directly:
#   set -o pipefail; unzip -Z1 polaris-astro.zip | grep -qx ...  -> status 141
#   without pipefail                                             -> status 0
# Listing into a variable and matching with case has no pipeline, so there is no
# SIGPIPE to misreport.
zip_has_member() {
    local z="$1" want="$2" listing
    listing=$(unzip -Z1 "$z" 2>/dev/null) || return 1
    case $'\n'"$listing"$'\n' in
        *$'\n'"$want"$'\n'*) return 0 ;;
        *) return 1 ;;
    esac
}

# The copyleft offer must be inside the archive, not merely on disk beside it.
if [ -f "$SD_ROOT/polaris-wifi.zip" ]; then
  for f in LICENCE-wifi.txt COPYING-LGPL-2.1.txt NOTICE-iw.txt NOTICE-wpa_supplicant.txt; do
    zip_has_member "$SD_ROOT/polaris-wifi.zip" "polaris-wifi/$f" \
      || die "polaris-wifi.zip does not contain $f -- shipping copyleft binaries with no licence alongside them is an LGPL s4 violation"
  done
  # Present is not enough: a zero-byte LICENCE-wifi.txt satisfies the listing above
  # and still leaves the user with nothing to read. Read the bytes out of the archive.
  for f in LICENCE-wifi.txt COPYING-LGPL-2.1.txt NOTICE-iw.txt NOTICE-wpa_supplicant.txt; do
    sz=$(unzip -p "$SD_ROOT/polaris-wifi.zip" "polaris-wifi/$f" 2>/dev/null | wc -c)
    [ "$sz" -gt 0 ] || die "polaris-wifi.zip stores $f as an empty file -- an empty licence is not a licence"
  done
  # The offer must name the versions it offers source for.
  #
  # Read the member into a variable and match with bash's =~ rather than piping
  # unzip into grep -q: -q exits at the first match, which leaves unzip dying of
  # SIGPIPE, and pipefail then reports that as a failure of a check that actually
  # succeeded. Measured on a real candidate: 39 of 40 runs of the piped form
  # returned failure for a member that was present.
  lic_text=$(unzip -p "$SD_ROOT/polaris-wifi.zip" polaris-wifi/LICENCE-wifi.txt 2>/dev/null || true)
  [[ $lic_text =~ libnl-[0-9]+\.[0-9] ]] \
    || die "LICENCE-wifi.txt inside the zip names no libnl version -- an offer that names no version is not an offer"
  # Modes come from the archive, because boot gates auto-join on [ -x ]. Use plain
  # `unzip -Z`: with -Z1 the long-listing header is suppressed and this would read
  # empty, making the check pass vacuously.
  for b in wpa_supplicant wpa_cli wpa_passphrase iw polaris-autojoin.sh setup-wifi.sh udhcpc.script; do
    perm=$(unzip -Z "$SD_ROOT/polaris-wifi.zip" 2>/dev/null \
           | awk -v n="polaris-wifi/$b" '$NF==n {print $1}')
    [ -n "$perm" ] || die "polaris-wifi.zip does not contain $b at all"
    case "$perm" in
      *x*) ;;
      *) die "polaris-wifi.zip stores $b as '$perm' (not executable) -- boot's [ -x ] gate would skip it" ;;
    esac
  done
fi

# Prove the rooting claim rather than trusting the zip invocation: an entry that does
# not begin with its directory name unzips one level too deep, and the boot hook then
# installs nothing while still reporting success (issue #58).
#
# The expected root is stated per archive instead of derived from the filename, because
# astrometry-indexes.zip is intentionally rooted at astrometry/ -- the README tells users
# the card must end up with <SD root>/astrometry/index-41xx.fits. Deriving the root from
# the basename made this die on a correctly built indexes archive (11 entries), which is
# how this was caught: the assertion fired on real bytes rather than on my assumption.
for spec in "polaris-astro.zip:polaris-astro" "polaris-wifi.zip:polaris-wifi" "astrometry-indexes.zip:astrometry"; do
  zname="${spec%%:*}"; root="${spec##*:}"
  z="$SD_ROOT/$zname"
  [ -f "$z" ] || continue
  bad=$(unzip -Z1 "$z" | grep -vc "^$root/" || true)
  [ "$bad" = "0" ] || die "$z has $bad entr(ies) outside $root/ -- would not unzip to SD root"
done

# Assert against the finished archive, not the staging directory: a manifest that
# exists on disk but is excluded from polaris-astro.zip is exactly how .104 shipped
# without one. The user extracts the zip; the tree beside it never reaches the card.
#
# Missing is a hard failure, not a skip. Every check in this block used to sit
# behind [ -f "$SD_ROOT/polaris-astro.zip" ], so an archive that was never built
# skipped all of them and the script went on to exit 0 -- the vacuous pass this
# file's own comment calls out as issue #286's bug class, reproduced here a second
# time. The rebuild above makes absence a real anomaly rather than a normal state.
[ -f "$SD_ROOT/polaris-astro.zip" ] \
  || die "polaris-astro.zip was not produced -- every assertion below would have been skipped and the release would have shipped an unverified kit"
if [ -f "$SD_ROOT/polaris-astro.zip" ]; then
  zip_has_member "$SD_ROOT/polaris-astro.zip" "polaris-astro/polaris-astro.manifest" \
    || die "polaris-astro.zip does not contain polaris-astro.manifest -- install_astro.sh would skip byte verification and the boot sync could not detect a stale binary"
  msz=$(unzip -p "$SD_ROOT/polaris-astro.zip" polaris-astro/polaris-astro.manifest 2>/dev/null | wc -c)
  [ "$msz" -gt 0 ] || die "polaris-astro.zip stores polaris-astro.manifest as an empty file"
  # Same SIGPIPE class as above: read the member, then match against it. A
  # here-string keeps grep's original anchored semantics ("polaris-httpd" at the
  # end of any line -- manifest lines are "<sha256>  <name>") while giving grep a
  # regular file to read instead of a pipe that can be closed under it.
  manifest_text=$(unzip -p "$SD_ROOT/polaris-astro.zip" polaris-astro/polaris-astro.manifest 2>/dev/null || true)
  grep -q 'polaris-httpd$' <<< "$manifest_text" \
    || die "polaris-astro.manifest inside the zip does not cover polaris-httpd"

  # Issue #331, asserted against the archive rather than the staging tree. The
  # first attempt at this fix copied the texts on a path nothing calls, so the
  # files never existed; a check on the directory would have been vacuous and a
  # check on the tree alone would still pass if zip excluded them. polaris-solve
  # and polaris-skysim are GPL v2-or-later (qfits-an is linked in), so shipping
  # them in this archive with no licence text and no source offer is a violation,
  # not merely an unverified bundle.
  for f in LICENCE-astro.txt licenses/COPYING-GPL-2.txt \
           licenses/COPYING-LGPL-2.1.txt licenses/README-GPL.txt; do
    zip_has_member "$SD_ROOT/polaris-astro.zip" "polaris-astro/$f" \
      || die "polaris-astro.zip does not contain $f -- GPL binaries would reach the user with no licence alongside them (issue #331)"
    lsz=$(unzip -p "$SD_ROOT/polaris-astro.zip" "polaris-astro/$f" 2>/dev/null | wc -c)
    [ "$lsz" -gt 0 ] || die "polaris-astro.zip stores $f as an empty file -- an empty licence is not a licence"
  done
fi

# The SD-rooted .zip archives are excluded from astro-bundle.tar.gz. They are
# published as siblings beside FwPkt.zip by publish-astro-candidate.sh, so keeping
# them inside the tarball too stores every kit byte twice -- once extracted (which
# ASTRO-MANIFEST.sha256 covers and which the README tells users to drag onto the
# card) and once zipped. That duplication pushed astro-bundle.tar.gz to 110.50 MB,
# past GitHub's 100 MB hard limit, so the push was rejected with GH001 while every
# individual artifact (FwPkt.zip 65 MB, each SD zip) was well under it. The bundle
# now holds extracted trees + licenses + manifest; the zips live at the publication
# top level where a user is actually handed them.
tar -C "$OUT/astro-bundle" --exclude='./COPY-TO-SD-CARD-ROOT/*.zip' \
    -czf "$OUT/astro-bundle.tar.gz" .

# Reopen the finished archives and check what a user would actually unpack. This
# runs here, after every archive exists, because the verifier reports NOT_APPLICABLE
# for an absent member -- calling it earlier prints a green verdict over nothing.
# It aborts rather than warning: #58, #280, #281 and #286 all shipped while a check
# that ran against the staging directory passed.
if command -v python3 >/dev/null 2>&1; then
  python3 "$ROOT/scripts/verify-published-astro-candidate.py" "$OUT" \
    || die "artifact gate failed -- the archives a user unpacks are incomplete"
else
  die "python3 is required to run the artifact gate over the finished archives"
fi

# Verify the finished archives, from inside this producer, on every run.
#
# The checks above are per-archive and hand-written here. This runs the whole
# archive-level contract -- CRC, traversal and symlink members, non-empty copyleft
# text, executable modes, and that every sibling a shipped script references exists
# in some shipped kit -- against the bytes that were just produced.
#
# It has to be called from here. A gate that only runs when someone remembers to
# run it is not a gate: that is precisely how .99 shipped with the licence check
# present in the tree and never executed (issue #286), and how the astro kit shipped
# seven scripts at 0644 while the wifi chmod ran (issue #292).
if command -v python3 >/dev/null 2>&1; then
  python3 "$ROOT/scripts/verify-published-astro-candidate.py" "$OUT" \
    --json "$OUT/astro-bundle/artifact-conformance.json" \
    || die "produced archives failed the artifact conformance gate -- see above"
else
  die "python3 is required to verify the produced archives"
fi

echo "[3/7] generating immutable FwPkt install manifest"
python3 "$ROOT/scripts/generate-fwpkt-manifest.py" "$OUT" \
  --ubireader "${UBIREADER_EXTRACT_FILES:-/home/ian/.local/bin/ubireader_extract_files}"

echo "[4/7] running focused Astro tests"
python3 -m pytest -q "$ROOT/container/astro/tests" "$ROOT/tools/tests" \
  "$ROOT/tests/test_astro_build_wrapper.py" "$ROOT/tests/test_plate_solving_present.py" \
  > "$OUT/astro-test-transcript.txt" 2>&1
cat "$OUT/astro-test-transcript.txt"
for script in "$ROOT"/container/astro/ondisk/*.sh; do sh -n "$script"; done

echo "[5/7] running shared camera gate against this Astro packet"
set +e
bash "$ROOT/tests/run_prerelease_gate.sh" --build "$OUT/FwPkt" \
  --libgphoto2-src "$LIBSRC" > "$OUT/shared-camera-gate.txt" 2>&1
GATE_RC="$?"
set -e
cat "$OUT/shared-camera-gate.txt"
[ "$GATE_RC" -eq 0 ] || die "shared gate RED; candidate is not publishable"

echo "[6/9] recording source and feature binding"
{
  echo "candidate_variant=astro"
  echo "candidate_id=$ID"
  echo "shared_camera_baseline=$CAMERA_BASELINE"
  echo "astro_commit=$(git -C "$ROOT" rev-parse HEAD)"
  echo "stock_input=$STOCK"
  echo "catalogue_package=$CATALOG_PACKAGE"
  echo "focal_min_mm=$FMIN"
  echo "focal_max_mm=$FMAX"
  echo "sensor_width_mm=$SENSOR"
  echo "deployment=not-performed"
  echo "firmware_flash=not-performed"
  echo "hardware_qualification=not-performed"
} >> "$OUT/build-source-provenance.txt"
python3 "$ROOT/scripts/create-astro-candidate-manifest.py" --candidate-dir "$OUT" \
  --patcher "$ROOT" --camera-baseline "$CAMERA_BASELINE" \
  --astro-commit "$(git -C "$ROOT" rev-parse HEAD)" --libgphoto2 "$LIBSRC" \
  --stock "$STOCK" --display-fwver "$DISPLAY_FWVER" --build-id "$BUILD_ID" \
  --catalogue-package "$CATALOG_PACKAGE" --focal-min "$FMIN" \
  --focal-max "$FMAX" --sensor-mm "$SENSOR"

echo "[7/9] generating immutable release identity"
python3 "$ROOT/scripts/create-release-change-manifest.py" \
  --summary "$CHANGE_SUMMARY" --candidate-id "$ID" \
  --display-fwver "$DISPLAY_FWVER" --build-id "$BUILD_ID" \
  --libgphoto2 "$LIBSRC" --patcher "$ROOT" --stock "$STOCK" \
  --candidate-dir "$OUT"
CHANGE_MANIFEST_SHA256="$(sha256sum "$OUT/release-change-manifest.json" | awk '{print $1}')"
{
  echo "release_change_manifest=release-change-manifest.json"
  echo "release_change_manifest_sha256=$CHANGE_MANIFEST_SHA256"
  # Recorded, not merely enforced. A SKIP_DOCTOR=1 exception must be visible in the
  # release evidence; a variable that is set and then dropped proves nothing.
  echo "build_doctor_status=$DOCTOR_STATUS"
  echo "build_doctor_log=doctor.log"
} >> "$OUT/build-source-provenance.txt"

echo "[8/9] checking candidate identity"
python3 "$ROOT/scripts/verify-candidate-identity.py" "$OUT" --require-deployable

echo "[9/9] recording initial install status"
cat > "$OUT/install-status.txt" <<EOF
candidate_variant=astro
candidate_id=$ID
install_status=not-installed
deployment=not-performed
EOF

echo "candidate complete (build-only)"
echo "candidate=$OUT"
echo "manifest=$OUT/astro-candidate-manifest.json"
echo "FwPkt=$OUT/FwPkt.zip"
echo "AstroBundle=$OUT/astro-bundle.tar.gz"
echo "No deployment, reboot, flash, or upload was performed."
