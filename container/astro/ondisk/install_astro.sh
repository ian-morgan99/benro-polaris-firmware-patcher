#!/bin/sh
# ============================================================================
#  install_astro.sh -- put the plate solver on the device. Runs ON THE DEVICE.
#
#  Purely additive: writes /app/astro, creates a site.conf if there is none,
#  and installs the boot hook. Undo with `uninstall_astro.sh`, or by hand:
#      rm -rf /app/astro && rm -f /app/network_telnetd.sh
#      (then restore /app/network_telnetd.pre-astro.sh if one exists)
#
#     SRC        bundle dir (default: this script's dir)
#     DEST       install dir (default /app/astro)
#     INDEXES    where index files live (default /app/sd/astrometry)
#     NO_BOOT=1  install the files but NOT the boot hook
# ============================================================================
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
SRC=${SRC:-$HERE}
DEST=${DEST:-/app/astro}
INDEXES=${INDEXES:-/app/sd/astrometry}
HOOK=/app/network_telnetd.sh
CONF=/app/sd/polaris-astro/site.conf

mkdir -p "$DEST" "$INDEXES"

# /app is a small UBIFS -- 68 MB on this device, and a firmware flash replaces it
# wholesale and leaves it nearly full. Every copy below is a plain cp, so running
# out of space aborts the script under set -e. It used to do that AFTER the
# binaries and BEFORE the boot hook, which is how 6.0.0.54.104 ended up with
# polaris-httpd on disk and nothing starting it at boot. Say what the space
# actually is, so the operator sees the cause instead of a bare "cp: write error".
FREE_KB=$(df -k "$DEST" 2>/dev/null | awk 'NR==2 {print $4}')
NEED_KB=$(du -sk "$SRC" 2>/dev/null | cut -f1)
if [ -n "$FREE_KB" ]; then
    echo "[astro] free on $DEST: ${FREE_KB} KB"
    if [ -n "$NEED_KB" ] && [ "$FREE_KB" -lt "$NEED_KB" ]; then
        echo "[astro] NOTE: the bundle is ${NEED_KB} KB but only ${FREE_KB} KB is free."
        echo "[astro]       The catalogue is read from /app/sd/polaris-astro, not from"
        echo "[astro]       $DEST, so the install can still finish -- whatever does not"
        echo "[astro]       fit is reported below rather than aborting the run."
    fi
fi

# Camera geometry is an extensible data file, not a camera allow-list. Preserve
# a user's edited profile and seed the bundled compatibility rows only once.
PROFILE_DIR=/app/sd/polaris-astro
mkdir -p "$PROFILE_DIR"
if [ ! -f "$PROFILE_DIR/camera-sensors.tsv" ] && [ -f "$SRC/camera-sensors.tsv" ]; then
    cp "$SRC/camera-sensors.tsv" "$PROFILE_DIR/camera-sensors.tsv"
fi
if [ -f "$SRC/camera-sensors.tsv.example" ] && [ ! -f "$PROFILE_DIR/camera-sensors.tsv.example" ]; then
    cp "$SRC/camera-sensors.tsv.example" "$PROFILE_DIR/camera-sensors.tsv.example"
fi

# ---- binaries -------------------------------------------------------------
# Every one of these is load-bearing for some feature, and a missing one fails
# SILENTLY at runtime (the feature simply never happens), so they are checked
# rather than best-effort copied.
for b in polaris-solve polaris-solve-independent polaris-solve-independent-search polaris-exif-solve polaris-skysim-independent polaris-extract polaris-mount polaris-httpd \
         polaris-logwatch polaris-match; do
    [ -f "$SRC/$b" ] || { echo "[astro] MISSING $SRC/$b" >&2; exit 1; }
    cp "$SRC/$b" "$DEST/$b"; chmod +x "$DEST/$b"
done

# polaris-skysim is copied here too, and deliberately NOT in the loop above: it is
# optional so the Astrometry.net-only bundle stays installable. It must still land
# before the verification block below, because build-astro-candidate.sh lists it in
# polaris-astro.manifest and that check compares every listed entry against $DEST.
# Copying it afterwards made any bundle carrying a manifest fail VERIFY FAILED on
# polaris-skysim alone and exit 1 -- the same class of bug that previously hit the
# *.sh entries. polaris-guide.sh and polaris-autosolve.sh invoke "$ASTRO/polaris-skysim"
# by name, so it has to be in $DEST; it is 608 KB.
if [ -f "$SRC/polaris-skysim" ]; then
    cp "$SRC/polaris-skysim" "$DEST/polaris-skysim"; chmod +x "$DEST/polaris-skysim"
fi

# ---- scripts (copied before verification) ----------------------------------
# The manifest lists *.sh as well as the binaries, so these have to be in place
# before the hashes are compared. They used to be copied afterwards, which meant
# that simply shipping a polaris-astro.manifest would have made every install
# report VERIFY FAILED on all twenty-odd scripts and exit 1 -- the fix for one
# silent no-op would have become a hard failure on every device.
for s in "$SRC"/*.sh; do
    [ -f "$s" ] || continue
    cp "$s" "$DEST/"; chmod +x "$DEST/$(basename "$s")"
done

# ---- verify what actually landed ------------------------------------------
# Existence checks alone are not enough: they pass against a stale binary. This
# installer was previously "cp and hope", so re-running it over an existing
# /app/astro could report success while leaving the OLD server in place -- the
# same silent no-op that made new releases do nothing on already-installed
# devices (see polaris-astro-sync.sh). If the bundle declares a manifest, compare
# bytes and fail loudly on any mismatch.
if [ -f "$SRC/polaris-astro.manifest" ] && command -v sha256sum >/dev/null 2>&1; then
    drift=0
    while IFS= read -r line; do
        # sha256sum writes "<hash>  <name>" with TWO spaces, so ${line#* } leaves
        # a leading space on the name and every comparison fails. Word-split
        # instead: it collapses runs of whitespace and needs no external tool.
        set -- $line
        exp=$1; name=$2
        [ -n "$name" ] || continue
        cur=$(sha256sum "$DEST/$name" 2>/dev/null | cut -d' ' -f1)
        if [ "$cur" != "$exp" ]; then
            echo "[astro] VERIFY FAILED: $name (installed hash does not match the bundle)" >&2
            drift=$((drift + 1))
        fi
    done < "$SRC/polaris-astro.manifest"
    if [ "$drift" -ne 0 ]; then
        echo "[astro] install NOT verified: $drift file(s) differ -- refusing to claim success" >&2
        exit 1
    fi
    echo "[astro] verified every manifest entry against $DEST"
else
    echo "[astro] NOTE: no polaris-astro.manifest in $SRC; installed files are unverified."
    echo "[astro]       Re-extract the current release zip to get update-safe installs."
fi

# ---- boot hook (installed here, deliberately early) ------------------------
# /app/bootapp runs /app/network_telnetd.sh at boot if it exists. The SSH option
# of the firmware patcher uses THE SAME FILE, so overwriting it blindly would
# silently remove ssh access -- which is how you would then be locked out of
# fixing it. Anything already there is preserved and chained instead.
#
# This block used to sit at the end of the script. A firmware flash replaces
# /app, so the very next install runs against a nearly full UBIFS; the catalogue
# copy hit ENOSPC, set -e killed the script, and the boot hook was never written.
# The binaries were already in place by then, so the device looked installed --
# polaris-httpd present, port closed, nothing at boot. Installing the hook while
# there is still guaranteed space means a later failure costs the optional data,
# not autostart.
if [ "${NO_BOOT:-0}" = "1" ]; then
    echo "[astro] NO_BOOT=1 -- boot hook not installed; start things by hand"
elif [ -f "$SRC/polaris-astro-boot.sh" ]; then
    if [ -f "$HOOK" ] && ! grep -q "polaris-astro boot hook" "$HOOK" 2>/dev/null; then
        cp "$HOOK" /app/network_telnetd.pre-astro.sh
        chmod +x /app/network_telnetd.pre-astro.sh
        echo "[astro] existing $HOOK preserved as /app/network_telnetd.pre-astro.sh"
        echo "[astro]   (it will be run first at every boot, so ssh keeps working)"
    fi
    cp "$SRC/polaris-astro-boot.sh" "$HOOK"
    chmod 755 "$HOOK"
    echo "[astro] boot hook installed -> $HOOK"
else
    echo "[astro] WARNING: no polaris-astro-boot.sh in the bundle; nothing will"
    echo "[astro]          start at boot."
fi

# ---- catalogue data: deliberately NOT copied -------------------------------
# The kit carries ~18.7 MB of POLCAT01 solve data (catalogue-tiles/, .ptri,
# manifests). It used to be mirrored into $DEST here, and that mirror is the
# single largest reason /app runs out of space: /app is a 68 MB ubifs and the
# mirror is 89% of the kit. On a freshly flashed camera the copy hit ENOSPC,
# set -e killed the script between the binaries and the boot hook, and the device
# booted with the files present and nothing starting -- issue #312.
#
# Nothing reads it from $DEST. Every consumer resolves it on the SD card and
# nothing anywhere overrides those defaults:
#   polaris-align.sh / polaris-guide.sh / polaris-frame-watch.sh /
#   polaris-autosolve.sh / polaris-astro-boot.sh ->
#     INDEPENDENT_CATALOG       ${...:-/app/sd/polaris-astro/catalogue.polcat}
#     INDEPENDENT_CATALOG_DIR   ${...:-/app/sd/polaris-astro/catalogue-tiles}
#     INDEPENDENT_TRIANGLE_INDEX ${...:-/app/sd/polaris-astro/catalogue-tiles.ptri}
# Grepping the tree for a non-/app/sd catalogue path returns nothing, and strings
# on the shipped polaris-httpd finds no /app/astro/catalogue* reference. So this
# is not a fallback for a missing card -- if the card is gone the solve fails
# either way, because nothing would look in $DEST.
#
# polaris-skysim was already copied, above with the other binaries -- see the note
# there about why it has to precede the manifest check.
if [ -d "$SRC/catalogue-tiles" ] || [ -f "$SRC/catalogue.polcat" ]; then
    echo "[astro] solve data stays on the SD card at /app/sd/polaris-astro -- that is"
    echo "[astro]       where every solver reads it, and /app is too small to hold it."
fi

# (scripts were copied earlier, before the manifest check -- see that block)
echo "[astro] installed -> $DEST"

# ---- config ---------------------------------------------------------------
if [ ! -f "$CONF" ]; then
    mkdir -p "$(dirname "$CONF")"
    if [ -f "$SRC/site.conf.example" ]; then
        cp "$SRC/site.conf.example" "$CONF"
        echo "[astro] created $CONF from the example"
        echo "[astro]     Your location is OPTIONAL here — set it in the web app"
        echo "[astro]     (Settings > Observing site, GPS or by hand) and it is saved back."
    fi
else
    echo "[astro] kept your existing $CONF"
fi

# ---- boot hook ------------------------------------------------------------
# Installed above, immediately after the binaries are verified and before any
# optional data is copied. See that block for why it moved: leaving it here meant
# an ENOSPC in the catalogue copy skipped it entirely, so a flashed device had the
# server on disk and no way to start it.

# ---- index files ----------------------------------------------------------
if ls "$INDEXES"/index-*.fits >/dev/null 2>&1; then
    echo "[astro] found $(ls "$INDEXES"/index-*.fits | wc -l) index file(s) in $INDEXES"
else
    echo "[astro] NO index files in $INDEXES -- NOTHING WILL SOLVE until they are"
    echo "[astro] there. Copy the astrometry/ directory from the bundle to the card."
fi

cat <<TXT

[astro] Next:
    1. Reboot, or run: $HOOK
    2. Open http://<polaris ip>:8090/
    3. Set your location in the web app (Settings > Observing site) — optional,
       needed only for alignment and go-to; saved to $CONF automatically.

[astro] Solve a frame by hand (focal is read from EXIF; pass one to override):
    $DEST/polaris-align.sh /app/sd/normal/SP_0001.jpg

[astro] Talk to the mount (add --dry-run to send nothing):
    $DEST/polaris-mount --lat <deg> --lon <deg> pose
TXT
