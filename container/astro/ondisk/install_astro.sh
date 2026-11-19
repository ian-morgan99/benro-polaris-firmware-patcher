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
#     HOOK       boot hook path (default /app/network_telnetd.sh)
#     CONF       site.conf path (default /app/sd/polaris-astro/site.conf)
#     PROFILE_DIR camera profile dir (default /app/sd/polaris-astro)
#     NO_BOOT=1  install the files but NOT the boot hook
# ============================================================================
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
SRC=${SRC:-$HERE}
DEST=${DEST:-/app/astro}
INDEXES=${INDEXES:-/app/sd/astrometry}
# HOOK and CONF were hardcoded while SRC/DEST/INDEXES were overridable, which made
# the boot-hook path untestable: a test could exercise $DEST but never the hook, so
# the "hook installed" claim was never actually executed off-device. Defaults are
# unchanged; overriding them exists so the fail-closed hook check can be tested.
HOOK=${HOOK:-/app/network_telnetd.sh}
CONF=${CONF:-/app/sd/polaris-astro/site.conf}
# Same reason as HOOK/CONF: this was hardcoded, so no test could run the script
# without it trying to write the real /app. Default is unchanged.
PROFILE_DIR=${PROFILE_DIR:-/app/sd/polaris-astro}
# Derived rather than hardcoded so that overriding HOOK also redirects the
# backup. On-device the name is unchanged: /app/network_telnetd.sh becomes
# /app/network_telnetd.pre-astro.sh, which is what uninstall_astro.sh and the
# manual recovery note in this header both refer to.
HOOK_BACKUP=${HOOK%.sh}.pre-astro.sh

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

# ---- everything else the manifest declares ---------------------------------
# The two loops above copy a hardcoded list of binaries plus *.sh. The manifest
# is not limited to those: build-astro-candidate.sh writes VERSION into the kit
# and generates polaris-astro.manifest from the finished tree, so VERSION is
# listed -- but nothing copied it. Verification then compared /app/astro/VERSION
# against a hash of a file that was never placed there, reported
# "VERIFY FAILED: VERSION", and exited 1.
#
# The exit is what made this so damaging rather than merely noisy. The boot hook
# is installed further down this script, so the early exit meant the hook was
# never written: the kit's files were on the device but nothing started them at
# boot. A device came back from a flash with the firmware updated, /app/astro
# populated, and no astro stack running -- while the installer's own output said
# the install was "NOT verified" rather than "not installed", which points at the
# copy step instead of at the missing hook.
#
# Copying by manifest rather than by name is deliberate: polaris-astro-sync.sh
# already derives its file list from the manifest so "a bundle can add a file
# without editing this script". install_astro.sh was the odd one out, and that
# asymmetry is exactly how VERSION slipped through -- the build script's comment
# claims the sync path delivers manifest entries to /app/astro, which was true of
# the sync script and false of the installer.
if [ -f "$SRC/polaris-astro.manifest" ]; then
    while IFS= read -r line; do
        set -- $line
        name=$2
        if [ -z "$name" ]; then
            continue
        fi
        if [ ! -f "$SRC/$name" ]; then
            # The manifest promises a file the bundle does not carry. Leave it for
            # the verification block below to report: silently skipping would put
            # us back to claiming success over an incomplete install.
            continue
        fi
        if [ -e "$DEST/$name" ]; then
            # Already copied by the binary or script loops above. Re-copying is
            # harmless but pointless, and skipping keeps the executable bits those
            # loops set.
            continue
        fi
        d=$(dirname "$name")
        if [ "$d" != "." ] && [ ! -d "$DEST/$d" ]; then
            mkdir -p "$DEST/$d"
        fi
        cp "$SRC/$name" "$DEST/$name"
        # Preserve executability only where the source has it. VERSION and other
        # data files must not be made executable.
        if [ -x "$SRC/$name" ]; then
            chmod +x "$DEST/$name"
        fi
    done < "$SRC/polaris-astro.manifest"
fi

# ---- verify what actually landed ------------------------------------------
# Existence checks alone are not enough: they pass against a stale binary. This
# installer was previously "cp and hope", so re-running it over an existing
# /app/astro could report success while leaving the OLD server in place -- the
# same silent no-op that made new releases do nothing on already-installed
# devices (see polaris-astro-sync.sh). If the bundle declares a manifest, compare
# bytes and fail loudly on any mismatch.
if [ -f "$SRC/polaris-astro.manifest" ] && command -v sha256sum >/dev/null 2>&1; then
    drift=0
    checked=0
    expected=0
    while IFS= read -r line; do
        # sha256sum writes "<hash>  <name>" with TWO spaces, so ${line#* } leaves
        # a leading space on the name and every comparison fails. Word-split
        # instead: it collapses runs of whitespace and needs no external tool.
        set -- $line
        exp=$1; name=$2
        [ -n "$name" ] || continue
        expected=$((expected + 1))
        # A hash that is not 64 hex characters means the manifest itself is
        # damaged -- a partial line from bad sectors, or CRLF text written by
        # Windows. Comparing it would "pass" only by accident, and a silently
        # skipped line shrinks coverage without saying so.
        case "$exp" in
            *[!0-9a-fA-F]*|'')
                echo "[astro] MANIFEST CORRUPT: malformed hash for $name" >&2
                drift=$((drift + 1))
                continue ;;
        esac
        if [ "${#exp}" -ne 64 ]; then
            echo "[astro] MANIFEST CORRUPT: hash for $name is ${#exp} chars, expected 64" >&2
            drift=$((drift + 1))
            continue
        fi
        cur=$(sha256sum "$DEST/$name" 2>/dev/null | cut -d' ' -f1)
        if [ "$cur" != "$exp" ]; then
            echo "[astro] VERIFY FAILED: $name (installed hash does not match the bundle)" >&2
            drift=$((drift + 1))
        fi
        checked=$((checked + 1))
    done < "$SRC/polaris-astro.manifest"
    # The count is appended rather than replacing the sentence, because six
    # tracked consumers grep for "verified every manifest entry" (docs, the
    # published README template, two test suites). The phrase stays so those keep
    # working; the number makes the claim falsifiable. A manifest truncated by bad
    # sectors parses fine up to the point where it stops, so the loop simply checks
    # fewer files and reported success: reproduced with a 5-line manifest out of
    # 39, which exited 0 and installed the boot hook while 34 load-bearing files
    # went unchecked -- including polaris-httpd. An operator reading "5" where 39
    # is expected can notice; an operator reading only the word "every" cannot.
    if [ "$expected" -eq 0 ]; then
        # A zero-length or wholly unparseable manifest is not "nothing to check",
        # it is a damaged bundle. Treating it as success would put the #292 silent
        # no-op straight back: install reports fine, nothing was ever compared.
        echo "[astro] install NOT verified: $SRC/polaris-astro.manifest has no usable entries" >&2
        echo "[astro]       empty, truncated or unreadable -- re-extract the release zip" >&2
        exit 1
    fi
    if [ "$drift" -ne 0 ]; then
        echo "[astro] install NOT verified: $drift file(s) differ -- refusing to claim success" >&2
        exit 1
    fi
    # Counting parsed lines cannot detect truncation: a manifest cut short by bad
    # sectors simply has fewer lines, and every surviving line verifies fine. The
    # only way to see it is to ask the bundle what it contains and check the
    # manifest covers that. Reproduced against the shipped v114 kit with the
    # manifest cut to 5 of 39 lines: all five matched, so the loop reported
    # "verified every manifest entry", installed the boot hook and exited 0 while
    # 34 load-bearing files went unchecked -- polaris-httpd among them.
    uncovered=0
    for f in "$SRC"/*.sh; do
        [ -f "$f" ] || continue
        b=$(basename "$f")
        [ "$b" = "polaris-astro-boot.sh" ] && continue   # installed as $HOOK, not $DEST
        grep -qE "(^| )$b( |$)" "$SRC/polaris-astro.manifest" || uncovered=$((uncovered + 1))
    done
    for b in polaris-solve polaris-httpd polaris-mount polaris-extract VERSION; do
        [ -f "$SRC/$b" ] || continue
        grep -qE "(^| )$b( |$)" "$SRC/polaris-astro.manifest" || uncovered=$((uncovered + 1))
    done
    if [ "$uncovered" -ne 0 ]; then
        echo "[astro] install NOT verified: $uncovered file(s) in the bundle are not listed" >&2
        echo "[astro]       in polaris-astro.manifest, so they were never compared." >&2
        echo "[astro]       The manifest is truncated or damaged -- re-extract the release zip." >&2
        exit 1
    fi
    echo "[astro] verified every manifest entry against $DEST ($checked of $expected)"
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
        cp "$HOOK" "$HOOK_BACKUP"
        chmod +x "$HOOK_BACKUP"
        echo "[astro] existing $HOOK preserved as $HOOK_BACKUP"
        echo "[astro]   (it will be run first at every boot, so ssh keeps working)"
    fi
    cp "$SRC/polaris-astro-boot.sh" "$HOOK"
    chmod 755 "$HOOK"
    # Verify the hook landed byte-for-byte. The manifest check above only covers
    # $DEST, and $HOOK is outside it, so a truncated or ENOSPC-short write used to
    # pass silently: the installer printed "boot hook installed", exited 0, and the
    # device booted with /app/astro populated and nothing starting it. That is the
    # v104 symptom (#312) recurring through a different path -- the reordering above
    # reduces the odds of running out of space here, but only this check proves the
    # file is actually the one we meant to install.
    if [ ! -s "$HOOK" ]; then
        echo "[astro] FATAL: $HOOK is missing or empty after install." >&2
        echo "[astro]        Nothing will start at boot. Free space where it goes:" >&2
        df -k "$(dirname "$HOOK")" 2>/dev/null \
            | awk 'NR==2 {print "[astro]          " $4 " KB free on " $6}' >&2
        exit 1
    fi
    if command -v sha256sum >/dev/null 2>&1; then
        want=$(sha256sum "$SRC/polaris-astro-boot.sh" | cut -d' ' -f1)
        got=$(sha256sum "$HOOK" | cut -d' ' -f1)
        if [ "$want" != "$got" ]; then
            echo "[astro] FATAL: boot hook does not match the bundle after install." >&2
            echo "[astro]        expected $want" >&2
            echo "[astro]        actual   $got" >&2
            echo "[astro]        Nothing will start at boot. Free space where it goes:" >&2
            df -k "$(dirname "$HOOK")" 2>/dev/null \
                | awk 'NR==2 {print "[astro]          " $4 " KB free on " $6}' >&2
            exit 1
        fi
    fi
    echo "[astro] boot hook installed and verified -> $HOOK"
else
    # Not a warning any more. Every other route to autostart has already been
    # removed, so a bundle without this file cannot start Astro at boot at all,
    # and reporting success would be the same "looks installed, is not" outcome
    # as a truncated hook.
    echo "[astro] FATAL: no polaris-astro-boot.sh in $SRC; nothing will start at boot." >&2
    exit 1
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
