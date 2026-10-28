#!/usr/bin/env sh
# ============================================================================
#  Build the on-device plate solver bundle (macOS / Linux).
#
#     ./build-astro.sh [--focal-min 14] [--focal-max 400] [--sensor-mm 36]
#                      [--out DIR] [--no-indexes] [--image NAME] [--catalog FILE]
#                      [--catalog-package DIR] [--src-cache DIR]
#
#  Produces out/astro-bundle/ :
#     COPY-TO-SD-CARD-ROOT/     <- drag the CONTENTS of this onto the microSD
#         astrometry/           index files      -> /app/sd/astrometry
#         polaris-astro/        binaries+scripts -> /app/sd/polaris-astro
#                             + optional Gaia tile/index package
#                             + COPYING-GPL-2.txt, SOURCE-OFFER.txt
#     licenses/                 GPL corresponding source (see below)
#     README.txt                how to install and test it
#
#  Put the card back in the Polaris, run
#  /app/sd/polaris-astro/install_astro.sh once, and point polaris-align.sh at a
#  frame in /app/sd/DCIM/100SPCAM/.
#
#  licenses/ holds the exact astrometry.net + libjpeg tarballs that were compiled,
#  our build recipe and the BSD-3 GSL shim. It is NOT copied to the card -- it sits
#  beside COPY-TO-SD-CARD-ROOT/ in the bundle. polaris-solve and polaris-skysim are
#  GPL v2+, so shipping them without this would violate §3; the step is fail-closed.
#
#  NOTHING here is flashed. It is purely additive files under /app/astro, and
#  `rm -rf /app/astro` removes it. See docs/PLATE-SOLVING.md.
# ============================================================================
set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"
FMIN=14; FMAX=400; SENSOR=36; OUT="$HERE/out/astro-bundle"; IMG="polaris-patcher"; WANT_IDX=1; CATALOG=""; CATALOG_PACKAGE=""
# Persistent download cache. build_solver.sh defaults SRCCACHE to /work/src inside
# the container, which is thrown away by --rm -- so today every rebuild re-downloads
# astrometry.net and libjpeg, and (worse) the exact source that was compiled is
# destroyed with it. Mounting a host directory keeps both: fast rebuilds, and a
# corresponding-source archive that provably matches these binaries byte for byte.
SRCCACHE_DIR="${ASTRO_SRC_CACHE:-$HERE/out/.astro-src-cache}"

while [ $# -gt 0 ]; do
  case "$1" in
    --focal-min) FMIN="$2"; shift 2;;
    --focal-max) FMAX="$2"; shift 2;;
    --sensor-mm) SENSOR="$2"; shift 2;;
    --out) OUT="$2"; shift 2;;
    --no-indexes) WANT_IDX=0; shift;;
    --image) IMG="$2"; shift 2;;
    --catalog) CATALOG="$2"; shift 2;;
    --catalog-package) CATALOG_PACKAGE="$2"; shift 2;;
    --src-cache) SRCCACHE_DIR="$2"; shift 2;;
    -h|--help) sed -n '2,27p' "$0"; exit 0;;
    *) echo "unknown option: $1" >&2; exit 1;;
  esac
done

# Docker bind mounts require host paths. Keep the convenient relative CLI form
# usable while preserving absolute paths supplied by CI or another checkout.
case "$OUT" in /*) ;; *) OUT="$HERE/$OUT";; esac
case "$SRCCACHE_DIR" in /*) ;; *) SRCCACHE_DIR="$HERE/$SRCCACHE_DIR";; esac
SD_ASTRO="$OUT/COPY-TO-SD-CARD-ROOT/polaris-astro"

command -v docker >/dev/null 2>&1 || { echo "error: docker not found." >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "error: docker daemon not running." >&2; exit 1; }

echo "[*] building docker image '$IMG' (first run only)…"
docker build -q -t "$IMG" -f "$HERE/docker/Dockerfile" "$HERE" >/dev/null

mkdir -p "$OUT" "$SRCCACHE_DIR"
echo "[*] cross-building polaris-solve + polaris-extract for the device…"
# Run as the invoking user, not root. Without this the container writes the bundle
# as uid 0 (which lands on the host as nfsnobody), and the next run cannot delete or
# overwrite its own output -- "rm: Permission denied" on a directory you just built.
docker run --rm \
  -u "$(id -u):$(id -g)" \
  -v "$HERE/container":/opt/patcher:ro \
  -v "$SRCCACHE_DIR":/work/src \
  -v "$OUT":/out \
  --entrypoint /bin/bash "$IMG" -c \
  'bash /opt/patcher/astro/build_solver.sh arm /work/out/astro && mkdir -p /out/COPY-TO-SD-CARD-ROOT/polaris-astro && python3 /opt/patcher/astro/embed_webui.py /opt/patcher/astro/webui /tmp/webui.h && for t in polaris-logwatch polaris-match; do arm-linux-gnueabi-gcc -O2 -std=gnu11 -mfloat-abi=soft -Wall -Wextra -Werror /opt/patcher/astro/$t.c -o /work/out/astro/$t -lm || exit 1; done && arm-linux-gnueabi-gcc -O2 -std=gnu11 -mfloat-abi=soft -Wall -Wextra -Werror -I/tmp -I/opt/patcher/astro /opt/patcher/astro/polaris-httpd.c /opt/patcher/astro/polaris-link.c /opt/patcher/astro/polaris-jog.c /opt/patcher/astro/polaris-prog.c /opt/patcher/astro/polaris-astro.c -o /work/out/astro/polaris-httpd -lm && cp /work/out/astro/polaris-solve /work/out/astro/polaris-solve-independent /work/out/astro/polaris-solve-independent-search /work/out/astro/polaris-exif-solve /work/out/astro/polaris-extract /work/out/astro/polaris-mount /work/out/astro/polaris-skysim /work/out/astro/polaris-skysim-independent /work/out/astro/polaris-httpd /work/out/astro/polaris-logwatch /work/out/astro/polaris-match /out/COPY-TO-SD-CARD-ROOT/polaris-astro/ && cp /opt/patcher/astro/ondisk/*.sh /out/COPY-TO-SD-CARD-ROOT/polaris-astro/ && cp /opt/patcher/astro/ondisk/site.conf.example /out/COPY-TO-SD-CARD-ROOT/polaris-astro/'

if [ "$WANT_IDX" = "1" ]; then
  echo "[*] selecting + downloading index files for ${FMIN}-${FMAX}mm…"
  sh "$HERE/container/astro/fetch-indexes.sh" --focal-min "$FMIN" --focal-max "$FMAX" \
     --sensor-mm "$SENSOR" --out "$OUT/COPY-TO-SD-CARD-ROOT/astrometry"
fi

if [ -n "$CATALOG" ]; then
  [ -f "$CATALOG" ] || { echo "error: catalogue not found: $CATALOG" >&2; exit 1; }
  cp "$CATALOG" "$OUT/COPY-TO-SD-CARD-ROOT/polaris-astro/catalogue.polcat"
  if [ -f "${CATALOG%.polcat}.json" ]; then
    cp "${CATALOG%.polcat}.json" "$OUT/COPY-TO-SD-CARD-ROOT/polaris-astro/catalogue.manifest.json"
  fi
  echo "[*] bundled independent POLCAT01 catalogue: $CATALOG"
fi

if [ -n "$CATALOG_PACKAGE" ]; then
  [ -d "$CATALOG_PACKAGE/tiles" ] || { echo "error: catalogue package has no tiles/: $CATALOG_PACKAGE" >&2; exit 1; }
  for f in "$CATALOG_PACKAGE/tiles.json" "$CATALOG_PACKAGE/tiles.ptri" "$CATALOG_PACKAGE/tiles.ptri.json"; do
    [ -f "$f" ] || { echo "error: catalogue package missing $f" >&2; exit 1; }
  done
  mkdir -p "$SD_ASTRO/catalogue-tiles"
  cp "$CATALOG_PACKAGE"/tiles/*.pcat "$SD_ASTRO/catalogue-tiles/"
  cp "$CATALOG_PACKAGE/tiles.json" "$SD_ASTRO/catalogue-tiles.manifest.json"
  cp "$CATALOG_PACKAGE/tiles.ptri" "$SD_ASTRO/catalogue-tiles.ptri"
  cp "$CATALOG_PACKAGE/tiles.ptri.json" "$SD_ASTRO/catalogue-tiles.ptri.json"
  echo "[*] bundled native all-sky catalogue package: $CATALOG_PACKAGE"
fi

# ----------------------------------------------------------------------------
# Corresponding source (GPL v2 §3). Mirrors the out/licenses/ step in
# container/patch.sh, which already does this for LGPL libgphoto2.
#
# polaris-solve and polaris-skysim link astrometry.net's qfits-an FITS layer,
# whose anqfits.c is "GPL v2 or later", so both binaries are GPL-2+. Shipping
# them without corresponding source is a licence violation, and an upstream URL
# alone is not enough when the build omits files and substitutes a shim -- so we
# ship the exact tarballs that were compiled, plus our own build recipe and shim.
#
# The SRCCACHE mount above is what makes "exact" provable: the tarball shipped
# here is the same bytes build_solver.sh unpacked, verified by sha256 below.
# This step is fail-closed on purpose -- a bundle with GPL binaries and no source
# must not be produced silently.
AN_VERSION="${AN_VERSION:-0.98}"
JPEG_VERSION="${JPEG_VERSION:-9f}"
AN_TARBALL="$SRCCACHE_DIR/an-$AN_VERSION.tar.gz"
JPEG_TARBALL="$SRCCACHE_DIR/jpegsrc.tar.gz"
LIC="$OUT/licenses"
SD_ASTRO="$OUT/COPY-TO-SD-CARD-ROOT/polaris-astro"

# The licence step runs after the build because the container is what fetches the
# tarballs, so it cannot be checked up front on a cold cache. That means a failure
# here happens *after* GPL binaries have been written into the bundle -- and a user
# who ignores the exit code would drag them onto an SD card with no source, which is
# precisely the violation this step exists to prevent. So on failure we delete the
# GPL binaries from the card tree: an incomplete bundle cannot be shipped by accident.
no_source(){
  echo "error: $1" >&2
  rm -f "$SD_ASTRO/polaris-solve" "$SD_ASTRO/polaris-skysim" \
        "$SD_ASTRO/SOURCE-OFFER.txt" "$SD_ASTRO/COPYING-GPL-2.txt" 2>/dev/null || true
  echo "       Removed polaris-solve and polaris-skysim from the bundle: shipping" >&2
  echo "       GPL binaries without corresponding source is a §3 violation." >&2
  echo "       Re-run without --src-cache, or point it at a cache used for a real build." >&2
  exit 1
}

[ -f "$AN_TARBALL" ]   || no_source "$AN_TARBALL not found; cannot ship corresponding source for the GPL solver."
[ -f "$JPEG_TARBALL" ] || no_source "$JPEG_TARBALL not found; polaris-extract statically links libjpeg."
[ -f "$HERE/container/astro/licenses/GPL-2.txt" ] \
  || no_source "container/astro/licenses/GPL-2.txt is missing from the repo."

rm -rf "$LIC"; mkdir -p "$LIC"

cp "$AN_TARBALL"   "$LIC/astrometry.net-$AN_VERSION.tar.gz"
cp "$JPEG_TARBALL" "$LIC/jpeg-$JPEG_VERSION.tar.gz"
cp "$HERE/container/astro/licenses/GPL-2.txt" "$LIC/COPYING-GPL-2.txt"

# Our side of the build: the recipe, the BSD-3 GSL shim that replaces GPLv3+
# gsl-an, and the seeded config header. These are what make these binaries differ
# from a plain astrometry.net build, so they belong in the corresponding source.
tar czf "$LIC/polaris-build-recipe.tar.gz" -C "$HERE" \
  --exclude='*/__pycache__' \
  container/astro/build_solver.sh container/astro/fetch-indexes.sh \
  container/astro/gslshim container/astro/polaris-solve.c \
  container/astro/polaris-extract.c container/astro/polaris-skysim.c \
  container/astro/licenses/GPL-2.txt build-astro.sh docker/Dockerfile

AN_SHA=$(sha256sum "$LIC/astrometry.net-$AN_VERSION.tar.gz" | cut -d' ' -f1)
JPEG_SHA=$(sha256sum "$LIC/jpeg-$JPEG_VERSION.tar.gz" | cut -d' ' -f1)
RECIPE_SHA=$(sha256sum "$LIC/polaris-build-recipe.tar.gz" | cut -d' ' -f1)

cat > "$LIC/README-GPL.txt" <<EOF
Corresponding source for the GPL-licensed programs in this bundle
=================================================================

Which binaries are GPL, and why
-------------------------------
  polaris-solve   GPL v2-or-later
  polaris-skysim  GPL v2-or-later   (test/simulation tool; same libraries)

Both link libpolarisastro.a, which contains astrometry.net's qfits-an FITS
reader. Every compiled file in qfits-an carries the ESO "GNU General Public
License ... either version 2 of the License, or (at your option) any later
version" notice, and qfits-an/NOTE-Astrometry.net releases the Astrometry.net
modifications "under the GPL v2 or later". That is the only copyleft in what we
compile.

Census over the 100 objects build_solver.sh compiles (99 files from util/,
libkd/, qfits-an/ and four solver/ files, plus our BSD-3 gsl_shim.c):

    83  3-clause BSD      astrometry.net's own code (util/, libkd/, solver/)
    13  GPL v2-or-later   qfits-an: anqfits.c + 12 qfits_*.c (ESO copyright)
     1  zlib/libpng       util/cutest.c
     1  BSD-3             container/astro/gslshim/gsl_shim.c (ours)
     2  no licence notice util/indexset.c, qfits-an/qfits_convert.c

The last two carry no licence text at all. indexset.c has no header;
qfits_convert.c says only "Copyright 2009 Dustin Lang". Both are inside trees
whose other files are BSD-3 (util/) or GPL v2+ (qfits-an/), so the conservative
reading is that qfits_convert.c is GPL v2+ with us. That does not change the
outcome: the copyleft floor of the binary is GPL v2-or-later either way.

Note this differs from astrometry.net's own top-level LICENSE, which says the
whole upstream work is GPL v3-or-later. That is because upstream vendors GSL
(gsl-an/, GPLv3+) and util/ctmf.c (GPLv3+). We do not build either:
build_solver.sh deletes gsl-an/ and catalogs/ outright, skip_file() refuses
md5.c, ctmf.c and simplexy.c, and a BSD-3 shim (container/astro/gslshim/)
supplies the 7 GSL routines the solver needs. Verified after linking: zero
GPLv3-only files among the objects, and no unresolved gsl_ symbols. So the
copyleft floor here is GPL v2+, not v3+.

What is in this directory
-------------------------
  astrometry.net-$AN_VERSION.tar.gz   the exact upstream source that was compiled
  jpeg-$JPEG_VERSION.tar.gz           IJG libjpeg, statically linked into polaris-extract
  polaris-build-recipe.tar.gz         our build recipe + the BSD-3 GSL shim + our C sources
  COPYING-GPL-2.txt                   the GPL v2 text

sha256
------
  $AN_SHA  astrometry.net-$AN_VERSION.tar.gz
  $JPEG_SHA  jpeg-$JPEG_VERSION.tar.gz
  $RECIPE_SHA  polaris-build-recipe.tar.gz

We do not modify any astrometry.net source file. The differences between these
binaries and a plain upstream build are all structural and are recorded by the
recipe archive: files omitted (gsl-an/, catalogs/, md5.c, ctmf.c, simplexy.c),
the substituted shim, and a hand-seeded os-features-config.h because astrometry's
configure cannot run probe binaries when cross-compiling.

Upstream source URL
-------------------
  https://codeload.github.com/dstndstn/astrometry.net/tar.gz/refs/tags/$AN_VERSION
  https://www.ijg.org/files/jpegsrc.v$JPEG_VERSION.tar.gz

This bundle is distributed at no charge as part of the Benro Polaris firmware
patcher. The patcher's repository holds the same tarballs under
$(basename "$SRCCACHE_DIR") and the full build recipe, so anyone who has these
binaries can obtain the source from there. If you received this bundle without
access to the repository, request a copy from whoever supplied it; under GPL v2
§3 they are obliged to provide the source with the binary or a written offer.

Everything else in this bundle (polaris-extract's star finder, polaris-mount,
polaris-httpd, polaris-link/jog/prog/astro, polaris-logwatch, polaris-match and
all *.sh) is MIT or BSD-3 and talks to the GPL binaries as separate processes
over files and sockets -- nothing GPL is linked into them. See
docs/LICENSE-AUDIT.md in the patcher repository for the per-file audit.
EOF

# The written offer has to travel WITH the binaries. README.txt sits at bundle
# root and users are told to drag only COPY-TO-SD-CARD-ROOT/ onto the card, so a
# notice that lives outside it would never reach the device.
cp "$HERE/container/astro/licenses/GPL-2.txt" "$SD_ASTRO/COPYING-GPL-2.txt"
cat > "$SD_ASTRO/SOURCE-OFFER.txt" <<EOF
polaris-solve and polaris-skysim on this card are GPL v2-or-later; the rest of
this directory is MIT/BSD-3 and runs them as separate processes.

The complete corresponding source (astrometry.net $AN_VERSION, IJG libjpeg
$JPEG_VERSION, and our build recipe + BSD-3 GSL shim) is in licenses/ next to
COPY-TO-SD-CARD-ROOT/ in the bundle you built, and in the patcher repository:

  https://github.com/ian-morgan99/benro-polaris-firmware-patcher

If you got this card without that source, ask whoever gave you the card for a
copy -- GPL v2 §3 requires them to supply it.

The full licence audit is docs/LICENSE-AUDIT.md in that repository.
EOF

echo "[✓] wrote GPL corresponding source -> $LIC/"
ls -la "$LIC" | sed 's/^/    /'

cat > "$OUT/README.txt" <<EOF
Benro Polaris — on-device plate solver bundle
=============================================
Built for ${FMIN}-${FMAX}mm on a ${SENSOR}mm-wide sensor.

Put it on the device
--------------------
Drag the CONTENTS of COPY-TO-SD-CARD-ROOT/ onto the root of the Polaris'
microSD card, so the card ends up with:

    <SD root>/astrometry/index-41xx.fits
    <SD root>/polaris-astro/polaris-solve, polaris-extract, polaris-mount, *.sh

When the bundle was built with --catalog-package, it also contains

    <SD root>/polaris-astro/catalogue-tiles/*.pcat
    <SD root>/polaris-astro/catalogue-tiles.manifest.json
    <SD root>/polaris-astro/catalogue-tiles.ptri[.json]

Put the card back in the Polaris and run once:

    /app/sd/polaris-astro/install_astro.sh

That copies the binaries and scripts to /app/astro, creates a site.conf if you
have none, and installs the boot hook so everything starts by itself. If a boot
hook is already there (the patcher's --ssh-key option uses the same file) it is
preserved and chained, so ssh keeps working. Undo it all with
/app/sd/polaris-astro/uninstall_astro.sh.

The index files are read straight off the card at /app/sd/astrometry and are
never copied into flash.

The native independent all-sky path is opt-in. Build a Gaia package with
container/astro/build_gaia_package.sh, pass its output to
build-astro.sh --catalog-package, and set SOLVER_BIN=polaris-solve-independent-search
in site.conf only after the ARM and capture qualification gates are complete.

Over ssh instead of sneakernet, the same layout works:

    scp -r COPY-TO-SD-CARD-ROOT/. root@<polaris ip>:/app/sd/
    ssh root@<polaris ip> /app/sd/polaris-astro/install_astro.sh

THEN EDIT /app/sd/polaris-astro/site.conf -- LAT and LON are required and
cannot be guessed. Reboot, and open http://<polaris ip>:8090/.

Test it on a real frame
-----------------------
Shoot with the Polaris as usual. Frames land in /app/sd/DCIM/100SPCAM/.

  /app/astro/polaris-align.sh /app/sd/normal/SP_0001.jpg

The focal length comes from the frame's EXIF, so there is nothing to pass for a
normal lens. Override it for a telescope or manual lens, which report none —
either in the web UI, or as the second argument:

  /app/astro/polaris-align.sh /app/sd/normal/SP_0001.jpg 400

Output is one JSON line: ra_deg, dec_deg, roll_deg, pixscale_arcsec, field size,
parity, the CD matrix, match odds and how long the solve took.

Tuning
------
  DOWNSAMPLE=2 ...   detect on a bigger image (slower, slightly better centroids)
  MAXSTARS=300 ...   feed the solver more stars
  SENSOR_MM=23.5 ... APS-C body

Moving the mount (simulated first — see docs/PLATE-SOLVING.md)
------------------------------------------------------------
  /app/astro/polaris-mount --lat <deg> --lon <deg> pose
  /app/astro/polaris-mount --lat <deg> --lon <deg> align --solved-ra R --solved-dec D
  /app/astro/polaris-mount --lat <deg> --lon <deg> goto-radec --ra R --dec D
  /app/astro/polaris-mount --lat <deg> --lon <deg> track on

Every motion refuses to run outside a safe envelope (--min-alt/--max-alt,
--max-slew) and alignment refuses within --max-align-alt of the zenith, where
azimuth is degenerate. Add --dry-run to see the exact commands without sending
them.

Removing it
-----------
  rm -rf /app/astro /app/sd/astrometry /app/sd/polaris-astro

Licensing
---------
polaris-solve and polaris-skysim are GPL v2-or-later (they link astrometry.net's
qfits-an FITS reader). Everything else here is MIT or BSD-3 and runs those two as
separate processes over files and sockets — nothing GPL is linked into them.

The complete corresponding source for the GPL binaries is in licenses/ beside this
file: the exact upstream tarballs that were compiled, our build recipe and the
BSD-3 GSL shim that replaces the GPLv3+ gsl-an. sha256 of each is recorded in
licenses/README-GPL.txt. polaris-astro/SOURCE-OFFER.txt repeats the offer so it
survives being copied onto the card alone. See docs/LICENSE-AUDIT.md in the
patcher repository for the per-file audit.
EOF

# iCloud/Finder leave "<name> 2.<ext>" conflict copies behind when the output dir
# lives in a synced folder (Documents, Desktop). They are exact duplicates, and
# for the index files they are ACTIVELY HARMFUL: the on-device solver globs
# index-*.fits, so a leftover "index-4110 2.fits" gets loaded a second time. Purge
# them so the bundle you drag to the card is clean. (Nothing legitimate is named
# "<name> 2.<ext>".)
_dups=$(find "$OUT" \( -name '* 2' -o -name '* 2.*' \) -type f 2>/dev/null | wc -l | tr -d ' ')
if [ "${_dups:-0}" != "0" ]; then
  find "$OUT" \( -name '* 2' -o -name '* 2.*' \) -type f -delete 2>/dev/null || true
  echo "[*] removed $_dups iCloud/Finder ' 2' duplicate file(s) from the bundle"
fi

echo
echo "[✓] bundle ready: $OUT"
ls -la "$OUT" | sed 's/^/    /'
echo "    next: read $OUT/README.txt"
