#!/usr/bin/env bash
# Build and fingerprint the additive Astro bundle for the active feature branch.
#
# This is deliberately separate from build-release-candidate.sh: this branch's
# contract is BUILD-ONLY. It never reads, patches, packages, uploads, installs,
# or flashes FwPkt. The only output is an Astro bundle that can be copied to the
# Polaris SD card later, after its contents have been reviewed.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEFAULT_ID="astro-native-platesolve-$(date -u +%Y%m%dT%H%M%SZ)"
ID="${ASTRO_BUILD_ID:-$DEFAULT_ID}"
OUT=""
IMAGE="${POLARIS_PATCHER_IMAGE:-polaris-patcher-pentax}"
CATALOG_PACKAGE=""
SRC_CACHE="${ASTRO_SRC_CACHE:-$ROOT/out/.astro-src-cache}"
WANT_INDEXES=1
WANT_WIFI=1
FORCE=0
ALLOW_MAIN=0
ALLOW_DIRTY=0
RUN_TESTS=1
WANT_ZIP=0

ORIGINAL_ARGS=("$@")

usage() {
  cat >&2 <<'EOF'
usage: scripts/build-astro-bundle.sh [options]

Build the additive native-C Astro bundle. This does not build or modify FwPkt.

options:
  --id ID                    output id (default: timestamped astro id)
  --out DIR                  output directory under out/
  --image NAME               Docker image (default: polaris-patcher-pentax)
  --catalog-package DIR      native Gaia tile package to include
  --no-indexes               do not fetch astrometry.net FITS indexes
  --no-wifi                  omit the station-mode wifi kit (bundle then cannot
                             join a network; only for solver-only rebuilds)
  --src-cache DIR            persistent upstream-source cache
  --force                    remove the selected existing output directory first
  --allow-main               permit a development build from main
  --allow-dirty              permit uncommitted source (recorded in provenance)
  --no-tests                 skip the focused Astro test and syntax gates
  --zip                      also emit SD-rooted zips for end users
  -h, --help                 show this help

--zip writes three archives rooted so that unzipping them AT THE SD CARD ROOT
drops each directory where the device expects it:

  polaris-astro.zip      -> polaris-astro/   (binaries, scripts, manifest)
  astrometry-indexes.zip -> astrometry/      (only if indexes were built)
  polaris-wifi.zip       -> polaris-wifi/    (only if the wifi kit was built)

The astro zip is what a user replaces on every release; the index and wifi zips
are one-time copies and never change between releases, so they are kept separate
rather than re-downloaded each time. Both archives are rooted at the directory itself,
never wrapped in a build-id folder -- a wrapper would land the payload one level
too deep and the boot hook would silently install nothing.

The normal controlled path requires the clean feature/astro-native-platesolve
branch and writes only to out/<id> plus the ignored source cache.
EOF
  exit 2
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

while [ $# -gt 0 ]; do
  case "$1" in
    --id)
      [ $# -ge 2 ] || usage
      ID="$2"
      shift 2
      ;;
    --out)
      [ $# -ge 2 ] || usage
      OUT="$2"
      shift 2
      ;;
    --image)
      [ $# -ge 2 ] || usage
      IMAGE="$2"
      shift 2
      ;;
    --catalog-package)
      [ $# -ge 2 ] || usage
      CATALOG_PACKAGE="$2"
      shift 2
      ;;
    --no-indexes)
      WANT_INDEXES=0
      shift
      ;;
    --no-wifi)
      WANT_WIFI=0
      shift
      ;;
    --src-cache)
      [ $# -ge 2 ] || usage
      SRC_CACHE="$2"
      shift 2
      ;;
    --force)
      FORCE=1
      shift
      ;;
    --allow-main)
      ALLOW_MAIN=1
      shift
      ;;
    --allow-dirty)
      ALLOW_DIRTY=1
      shift
      ;;
    --no-tests)
      RUN_TESTS=0
      shift
      ;;
    --zip)
      WANT_ZIP=1
      shift
      ;;
    -h|--help)
      usage
      ;;
    *)
      echo "ERROR: unknown option: $1" >&2
      usage
      ;;
  esac
done

case "$ID" in
  (*[!a-zA-Z0-9._-]*) die "invalid build id: $ID" ;;
esac

command -v realpath >/dev/null 2>&1 || die "realpath is required"
ROOT_REAL="$(realpath -m "$ROOT")"
if [ -z "$OUT" ]; then
  OUT="$ROOT/out/$ID"
elif [[ "$OUT" != /* ]]; then
  OUT="$ROOT/$OUT"
fi
OUT="$(realpath -m "$OUT")"
case "$OUT" in
  "$ROOT_REAL/out/"*) ;;
  *) die "output must be below $ROOT/out/: $OUT" ;;
esac
[ "$OUT" != "$ROOT_REAL/out" ] || die "refusing to use the whole out/ directory as output"
[ ! -L "$OUT" ] || die "refusing to use a symlink output: $OUT"

if [[ "$SRC_CACHE" != /* ]]; then
  SRC_CACHE="$ROOT/$SRC_CACHE"
fi
SRC_CACHE="$(realpath -m "$SRC_CACHE")"

BRANCH="$(git -C "$ROOT" branch --show-current)"
if [ "$BRANCH" != "feature/astro-native-platesolve" ]; then
  if [ "$BRANCH" = "main" ] && [ "$ALLOW_MAIN" = "1" ]; then
    echo "WARNING: development Astro build from main (--allow-main)"
  else
    die "controlled Astro builds must run on feature/astro-native-platesolve (got ${BRANCH:-detached}); use --allow-main only for a deliberate development build"
  fi
fi

TREE_STATUS="$(git -C "$ROOT" status --porcelain=v1 --untracked-files=all)"
if [ -n "$TREE_STATUS" ] && [ "$ALLOW_DIRTY" != "1" ]; then
  echo "$TREE_STATUS" >&2
  die "source checkout is dirty; commit/stash it or pass --allow-dirty for a development build"
fi

git -C "$ROOT" diff --check || die "source whitespace errors detected"
command -v docker >/dev/null 2>&1 || die "docker is required by build-astro.sh"
docker info >/dev/null 2>&1 || die "docker daemon is not running"

if [ -n "$CATALOG_PACKAGE" ]; then
  if [[ "$CATALOG_PACKAGE" != /* ]]; then
    CATALOG_PACKAGE="$ROOT/$CATALOG_PACKAGE"
  fi
  CATALOG_PACKAGE="$(realpath -m "$CATALOG_PACKAGE")"
  [ -d "$CATALOG_PACKAGE/tiles" ] || die "catalogue package has no tiles/: $CATALOG_PACKAGE"
  for required in tiles.json tiles.ptri tiles.ptri.json; do
    [ -f "$CATALOG_PACKAGE/$required" ] || die "catalogue package is missing $required: $CATALOG_PACKAGE"
  done
fi

if [ -e "$OUT" ]; then
  [ "$FORCE" = "1" ] || die "output already exists: $OUT (use --force to replace this exact directory)"
  [ ! -L "$OUT" ] || die "refusing to remove a symlink output: $OUT"
  echo "[*] removing selected previous output: $OUT"
  rm -rf -- "$OUT"
fi

if [ "$RUN_TESTS" = "1" ]; then
  command -v python3 >/dev/null 2>&1 || die "python3 is required for the focused test gate"
  echo "[*] running focused Astro tests"
  python3 -m pytest -q \
    "$ROOT/container/astro/tests" \
    "$ROOT/tools/tests" \
    "$ROOT/tests/test_astro_build_wrapper.py"
  echo "[*] checking on-device shell syntax"
  for script in "$ROOT"/container/astro/ondisk/*.sh; do
    sh -n "$script"
  done
fi

HEAD="$(git -C "$ROOT" rev-parse HEAD)"
BUILD_ARGS=(--image "$IMAGE" --out "$OUT" --src-cache "$SRC_CACHE")
[ "$WANT_INDEXES" = "1" ] || BUILD_ARGS+=(--no-indexes)
[ "$WANT_WIFI" = "1" ] || BUILD_ARGS+=(--no-wifi)
[ -n "$CATALOG_PACKAGE" ] && BUILD_ARGS+=(--catalog-package "$CATALOG_PACKAGE")

echo "[*] building Astro bundle"
echo "    branch: $BRANCH"
echo "    commit: $HEAD"
echo "    output: $OUT"
echo "    indexes: $([ "$WANT_INDEXES" = "1" ] && echo enabled || echo disabled)"
echo "    catalogue: ${CATALOG_PACKAGE:-none}"
bash "$ROOT/build-astro.sh" "${BUILD_ARGS[@]}"

SD_ROOT="$OUT/COPY-TO-SD-CARD-ROOT"
SD_ASTRO="$SD_ROOT/polaris-astro"
SD_WIFI="$SD_ROOT/polaris-wifi"
[ -d "$SD_ASTRO" ] || die "build completed without COPY-TO-SD-CARD-ROOT/polaris-astro"
[ -x "$SD_ASTRO/polaris-solve" ] || die "bundle is missing native polaris-solve"
[ -x "$SD_ASTRO/polaris-solve-independent-search" ] || die "bundle is missing independent search solver"
[ -f "$SD_ASTRO/polaris-frame-watch.sh" ] || die "bundle is missing frame watcher"
[ -f "$OUT/licenses/README-GPL.txt" ] || die "bundle is missing corresponding-source notice"

# The wifi kit is the same silent-failure class as the astro manifest below: the
# boot hook checks for /app/sd/polaris-wifi/polaris-autojoin.sh and simply does
# nothing when it is absent, so a bundle that omits it reports a successful
# install while leaving auto-join permanently dead. Catch it at build time.
if [ "$WANT_WIFI" = "1" ]; then
  for b in wpa_supplicant wpa_cli wpa_passphrase iw; do
    [ -x "$SD_WIFI/$b" ] || die "bundle is missing wifi binary $b -- auto-join cannot work"
  done
  [ -x "$SD_WIFI/polaris-autojoin.sh" ] \
    || die "bundle is missing polaris-wifi/polaris-autojoin.sh -- boot's [ -x ] gate would skip auto-join"
  # The DHCP bind hook belongs in this gate for the same reason autojoin does,
  # and for a sharper one: autojoin.sh *calls* it unconditionally via
  # `udhcpc -s "$WDIR/udhcpc.script"`. BusyBox udhcpc applies no lease without
  # it, so a bundle missing this file passes every other wifi check, joins the
  # network, gets an address from the router and then discards it -- while
  # autojoin.log still says "lease obtained". Verified on hardware: installing
  # the repo's own udhcpc.script took wlan1 from no address to a working
  # default route with the AP untouched (issue #280).
  [ -x "$SD_WIFI/udhcpc.script" ] \
    || die "bundle is missing polaris-wifi/udhcpc.script -- udhcpc -s would find nothing and every lease would be granted then discarded"

  # Copyleft notices must travel INSIDE polaris-wifi.zip, not only in the
  # bundle's licenses/ directory. libnl is LGPL-2.1 and build_wifi.sh links it
  # STATICALLY (libnl-3.a) into wpa_supplicant, wpa_cli, wpa_passphrase and iw,
  # so section 4 of the LGPL requires the accompanying offer to reach the user
  # together with those binaries. polaris-astro.zip already does this with
  # COPYING-GPL-2.txt + SOURCE-OFFER.txt; a separate zip needs its own copy or
  # the notice is orphaned from the code it describes -- a user who takes only
  # the wifi zip gets four copyleft binaries and no licence at all.
  cp "$OUT/licenses/COPYING-LGPL-2.1.txt"      "$SD_WIFI/" 2>/dev/null || true
  cp "$OUT/licenses/NOTICE-iw.txt"             "$SD_WIFI/" 2>/dev/null || true
  cp "$OUT/licenses/NOTICE-wpa_supplicant.txt" "$SD_WIFI/" 2>/dev/null || true

  # Versions come from the tarball filenames that build-astro.sh actually wrote,
  # not from variables in this script's scope. WPAS_VERSION/IW_VERSION/LIBNL_VERSION
  # are defined in build-astro.sh and are NOT visible here, so interpolating them
  # would emit "libnl-, iw-" -- an offer that names no version is not an offer.
  # Deriving from the filenames also makes drift impossible: the text describes
  # exactly the archive that is sitting beside it.
  LIBNL_TGZ=$(basename "$OUT/licenses/"libnl-*.tar.gz 2>/dev/null | head -1)
  IW_TGZ=$(basename    "$OUT/licenses/"iw-*.tar.gz 2>/dev/null | head -1)
  WPAS_TGZ=$(basename  "$OUT/licenses/"wpa_supplicant-*.tar.gz 2>/dev/null | head -1)
  for tgz in "$LIBNL_TGZ" "$IW_TGZ" "$WPAS_TGZ"; do
    [ -n "$tgz" ] || die "wifi kit cannot state its corresponding source: no matching tarball in $OUT/licenses"
  done
  LIBNL_VERSION="${LIBNL_TGZ#libnl-}";   LIBNL_VERSION="${LIBNL_VERSION%.tar.gz}"
  IW_VERSION="${IW_TGZ#iw-}";            IW_VERSION="${IW_VERSION%.tar.gz}"
  WPAS_VERSION="${WPAS_TGZ#wpa_supplicant-}"; WPAS_VERSION="${WPAS_VERSION%.tar.gz}"
  # The libnl release tag dots-to-underscores, exactly as build_wifi.sh builds it
  # for the fetch URL (V=$(echo "$LIBNL_VERSION" | tr . _)). Stripping the dots
  # instead yields libnl370, which is not a real tag.
  LIBNL_TAG=$(printf '%s' "$LIBNL_VERSION" | tr . _)

  cat > "$SD_WIFI/LICENCE-wifi.txt" <<EOF
Licence and source offer for the polaris-wifi kit
=================================================

Binaries in this directory, and their licences:

  wpa_supplicant  BSD-style  (w1.fi; its COPYING states the GPL v2 option was
                              dropped for distribution after 2012-02-11)
  wpa_cli         BSD-style  (same upstream, same terms)
  wpa_passphrase  BSD-style  (same upstream, same terms)
  iw              ISC        (see NOTICE-iw.txt)

All four statically link libnl:

  libnl           LGPL-2.1   (see COPYING-LGPL-2.1.txt)

Because libnl is linked statically, section 4 of the LGPL applies to every
binary above, and this written offer accompanies them:

  The complete corresponding source for libnl-$LIBNL_VERSION, iw-$IW_VERSION and
  wpa_supplicant-$WPAS_VERSION is published beside this release in licenses/ as
  the exact upstream tarballs that were compiled ($LIBNL_TGZ, $IW_TGZ,
  $WPAS_TGZ), together with our build recipe polaris-wifi-build-recipe.tar.gz
  (which selects the static libnl link and wpa_supplicant's internal crypto,
  both of which change what these binaries contain). The sha256 of each tarball
  is recorded in licenses/README-GPL.txt.

  Upstream, if you prefer it:
    https://github.com/thom311/libnl/releases/download/libnl${LIBNL_TAG}/libnl-${LIBNL_VERSION}.tar.gz
    https://www.kernel.org/pub/software/network/iw/iw-${IW_VERSION}.tar.gz
    https://w1.fi/releases/wpa_supplicant-${WPAS_VERSION}.tar.gz

  To rebuild and relink against a modified libnl, use build_wifi.sh from the
  recipe archive; it is the script that produced these binaries.

The shell scripts in this directory (polaris-autojoin.sh, polaris-apsta.sh,
setup-wifi.sh, wifi-keepalive.sh, wifi-watch.sh, udhcpc.script) are ours and
carry the same terms as the rest of the patcher bundle.
EOF
  for f in LICENCE-wifi.txt COPYING-LGPL-2.1.txt NOTICE-iw.txt NOTICE-wpa_supplicant.txt; do
    [ -f "$SD_WIFI/$f" ] || die "wifi kit is missing $f -- shipping copyleft binaries with no licence alongside them is an LGPL s4 violation"
  done
fi

MANIFEST="$OUT/ASTRO-MANIFEST.sha256"
(
  cd "$SD_ROOT"
  find . -type f -print0 | sort -z |
    while IFS= read -r -d '' file; do
      sha256sum "$file"
    done
) > "$MANIFEST"

# The on-device manifest. ASTRO-MANIFEST.sha256 is a build-time artefact for
# humans; polaris-astro.manifest is machine-read by polaris-astro-sync.sh at boot
# and must therefore be relative to the astro directory itself, because that is
# the directory the sync script hashes against.
#
# Without it the device can only ask "does this file exist?", which is the
# question that let a new release install nothing at all (see the header of
# polaris-astro-sync.sh). Listing the files here rather than in the script means
# a bundle can add a file without editing boot code.
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

# Fail closed. A bundle whose manifest is empty or absent cannot be updated in
# place, and shipping one would recreate the exact silent no-op this exists to
# prevent -- the device falls back to copy-if-missing and reports success while
# changing nothing.
[ -s "$ASTRO_MANIFEST" ] || die "generated $ASTRO_MANIFEST is empty"
[ -f "$SD_ASTRO/polaris-astro-sync.sh" ] \
  || die "bundle has no polaris-astro-sync.sh; the device cannot update in place"
grep -q 'polaris-httpd$' "$ASTRO_MANIFEST" \
  || die "$ASTRO_MANIFEST does not cover polaris-httpd (the web UI lives inside it)"

# The on-disk scripts are copied straight out of the repo, so a script committed
# without the exec bit lands on the card without it. The boot hook now invokes
# this via sh so it still runs, but keep the bundle itself correct: an operator
# running it by hand would hit "Permission denied" and conclude the update failed.
chmod +x "$SD_ASTRO/polaris-astro-sync.sh" 2>/dev/null || true
[ -x "$SD_ASTRO/polaris-astro-sync.sh" ] \
  || die "$SD_ASTRO/polaris-astro-sync.sh is not executable in the bundle"

# SD-rooted archives, built INSIDE COPY-TO-SD-CARD-ROOT so the archive entries
# are 'polaris-astro/...' and 'astrometry/...' with no wrapper directory. A zip
# containing '<id>/polaris-astro/' unzips one level too deep and the boot hook
# then installs nothing while still reporting success -- the same silent failure
# class as issue #58, caused by packaging rather than by code.
ZIPS=""
if [ "$WANT_ZIP" = "1" ]; then
  command -v zip >/dev/null 2>&1 || die "--zip requested but 'zip' is not installed"
  (
    cd "$SD_ROOT"
    rm -f polaris-astro.zip
    zip -qrX polaris-astro.zip polaris-astro
    if [ -d astrometry ]; then
      rm -f astrometry-indexes.zip
      zip -qrX astrometry-indexes.zip astrometry
    fi
    if [ -d polaris-wifi ]; then
      rm -f polaris-wifi.zip
      zip -qrX polaris-wifi.zip polaris-wifi
    fi
  )
  ZIPS="$SD_ROOT/polaris-astro.zip"
  [ -f "$SD_ROOT/astrometry-indexes.zip" ] && ZIPS="$ZIPS $SD_ROOT/astrometry-indexes.zip"
  [ -f "$SD_ROOT/polaris-wifi.zip" ] && ZIPS="$ZIPS $SD_ROOT/polaris-wifi.zip"

  # The wifi kit's whole purpose is to be executed on the device, and boot gates
  # auto-join on [ -x ]. zip stores unix mode bits, but verify rather than trust:
  # a kit that unzips non-executable installs four dead files and reports success.
  # Note `unzip -Z1` suppresses the long-listing header and returns nothing with
  # -l, which would make this check pass vacuously -- use plain `unzip -Z`.
  if [ -f "$SD_ROOT/polaris-wifi.zip" ]; then
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
  # Prove the rooting claim instead of trusting the zip invocation: an entry that
  # does not begin with the directory name would land in the wrong place.
  for z in $ZIPS; do
    base=$(basename "$z" .zip)
    bad=$(unzip -Z1 "$z" | grep -vc "^$base/" || true)
    [ "$bad" = "0" ] || die "$z has $bad entr(ies) outside $base/ -- would not unzip to SD root"
  done
fi

PROVENANCE="$OUT/build-source-provenance.txt"
{
  echo "kind=astro-bundle"
  echo "build_id=$ID"
  echo "build_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "branch=$BRANCH"
  echo "patcher_commit=$HEAD"
  echo "source_tree_status=${TREE_STATUS:-clean}"
  echo "docker_image=$IMAGE"
  echo "indexes=$([ "$WANT_INDEXES" = "1" ] && echo enabled || echo disabled)"
  echo "catalogue_package=${CATALOG_PACKAGE:-none}"
  echo "deployment=not-performed"
  echo "firmware_release=not-produced"
  echo "firmware_flash=not-performed"
  printf 'command='
  printf '%q ' "$0" "${ORIGINAL_ARGS[@]}"
  printf '\n'
  echo "sd_tree_manifest=$(basename "$MANIFEST")"
  echo "astro_manifest=polaris-astro/$(basename "$ASTRO_MANIFEST")"
  echo "tests=$([ "$RUN_TESTS" = "1" ] && echo passed || echo skipped)"
  for z in $ZIPS; do
    echo "zip=$z"
    echo "zip_md5=$(md5sum "$z" | cut -d' ' -f1)"
    echo "zip_sha256=$(sha256sum "$z" | cut -d' ' -f1)"
  done
} > "$PROVENANCE"

AFTER_STATUS="$(git -C "$ROOT" status --porcelain=v1 --untracked-files=all)"
[ "$AFTER_STATUS" = "$TREE_STATUS" ] || die "build changed the source checkout"

echo
echo "Astro bundle ready: $OUT"
echo "Copy the CONTENTS of $SD_ROOT to the Polaris microSD root."
echo "Build mode: build-only; deployment was not performed."
echo "No FwPkt was built, changed, or flashed."
echo "Manifest: $MANIFEST"
echo "On-device manifest: $ASTRO_MANIFEST"
if [ -n "$ZIPS" ]; then
  echo
echo "SD-rooted archives (unzip each AT THE CARD ROOT, not into a subfolder):"
  for z in $ZIPS; do
    printf '  %-26s %s\n' "$(basename "$z")" "$(du -h "$z" | cut -f1)"
  done
  echo "polaris-astro.zip replaces the existing one on every release."
  echo "astrometry-indexes.zip is a one-time copy; it does not change between releases."
fi
echo "Provenance: $PROVENANCE"
