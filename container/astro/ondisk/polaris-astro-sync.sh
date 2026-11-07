#!/bin/sh
# ============================================================================
#  polaris-astro-sync.sh -- install or UPDATE the astro stack, by hash.
#
#  WHY THIS EXISTS. The boot hook used to copy the SD binaries into /app/astro
#  only when /app/astro/polaris-httpd did not already exist:
#
#      while [ $i -lt 30 ] && [ ! -x "$ASTRO/polaris-httpd" ]; do
#          cp /app/sd/polaris-astro/$_b "$ASTRO"/
#
#  Once the directory existed the SD copy was never read again -- no version
#  compare, no checksum. A user who unzipped a new release over the old one on
#  the card therefore got NO CHANGE AND NO ERROR, because the device was already
#  satisfied by a file it had installed months earlier. Same failure class as
#  issue #58 ("staged FwPkt.zip, rebooted, came back on .66"), and invisible:
#  every step reports success.
#
#  So compare bytes instead of asking whether something exists. The bundle ships
#  polaris-astro.manifest (sha256 of every load-bearing file, paths relative to
#  the astro dir). Re-copy only files whose hash differs, then verify what
#  landed and fail loudly if it does not match.
#
#  Busybox sh only -- /bin/sh is a busybox symlink on the device, so no bash
#  process substitution, no [[ ]], no arrays, and no awk interval expressions
#  (busybox awk does not enable them). sha256sum exists at /usr/bin.
#
#  Usage:
#      polaris-astro-sync.sh sync   [SRC] [DEST]   install/update; exit 0 ok
#      polaris-astro-sync.sh verify [SRC] [DEST]   0 in sync, 1 drifted,
#                                                  2 no manifest (cannot tell)
#
#  SRC defaults to /app/sd/polaris-astro, DEST to /app/astro.
#  verify exiting 2 is deliberately NOT a failure: an old card with no manifest
#  must keep working the way it always did.
# ============================================================================
set -u

MODE=${1:-sync}
SRC=${2:-/app/sd/polaris-astro}
DEST=${3:-/app/astro}
MANIFEST_NAME=polaris-astro.manifest
STAMP=.astro-installed.sha256

# Every binary the daemons need. polaris-logwatch is autosolve's trigger
# detector and polaris-match is the guider's drift measurement -- omit either
# and the feature silently does nothing. Used only on the no-manifest fallback
# path; a manifest-bearing bundle declares its own file list.
BINARIES="polaris-httpd polaris-solve polaris-solve-independent polaris-solve-independent-search polaris-exif-solve polaris-skysim-independent polaris-extract polaris-logwatch polaris-match polaris-skysim polaris-mount"

log() { echo "[astro-sync] $*"; }

hash_of() {
    # Empty on failure; callers treat "no hash" as "needs copying".
    sha256sum "$1" 2>/dev/null | cut -d' ' -f1
}

# "hash path" lines for every file the bundle declares, sorted by path. Paths
# come verbatim from the manifest, so a bundle can add a file without editing
# this script. Non-zero exit if there is no manifest.
expected_lines() {
    mf="$SRC/$MANIFEST_NAME"
    [ -f "$mf" ] || return 1
    # sha256sum writes "<hash>  <path>". Tolerate one or two spaces, skip blank
    # and comment lines, and require a plausible 64-hex digest. No {64} interval:
    # busybox awk does not support it.
    awk 'NF>=2 && $1 !~ /^#/ {
            h=$1; $1=""; sub(/^ +/,"")
            if (length(h)==64 && h ~ /^[0-9a-fA-F]+$/) print h" "$0
         }' "$mf" | sort -k2
}

# The same paths, hashed from what is currently installed.
installed_lines() {
    expected_lines | while IFS= read -r line; do
        name=${line#* }
        [ -n "$name" ] || continue
        printf '%s %s\n' "$(hash_of "$DEST/$name")" "$name"
    done | sort -k2
}

case "$MODE" in
  verify)
    if ! expected_lines >/dev/null 2>&1; then
        log "no $MANIFEST_NAME in $SRC -- cannot verify (old bundle)"
        exit 2
    fi
    want=$(expected_lines)
    have=$(installed_lines)
    if [ "$want" = "$have" ]; then
        log "in sync: $DEST matches the card manifest"
        exit 0
    fi
    log "DRIFT between $SRC and $DEST:"
    # Names only, not hashes: boot logs stay readable, and the hashes are in the
    # manifest for whoever investigates.
    printf '%s\n' "$want" | while IFS= read -r line; do
        exp=${line%% *}
        name=${line#* }
        [ -n "$name" ] || continue
        cur=$(printf '%s\n' "$have" | awk -v n="$name" '$2==n {print $1}')
        if [ -z "$cur" ]; then
            echo "  missing: $name"
        elif [ "$cur" != "$exp" ]; then
            echo "  changed: $name"
        fi
    done
    exit 1
    ;;

  sync)
    if [ ! -d "$SRC" ]; then
        log "no $SRC -- nothing to install"
        exit 0
    fi
    mkdir -p "$DEST" || { log "cannot create $DEST"; exit 1; }

    # No manifest means an old card layout. Fall back to the historical
    # copy-if-missing behaviour rather than refusing to boot, but say so loudly:
    # this is exactly the state in which updates silently do nothing.
    if [ ! -f "$SRC/$MANIFEST_NAME" ]; then
        log "WARN: no $MANIFEST_NAME in $SRC -- falling back to copy-if-missing."
        log "WARN: this bundle cannot be updated in place; re-extract a current release."
        for b in $BINARIES; do
            if [ -f "$SRC/$b" ] && [ ! -f "$DEST/$b" ]; then
                cp "$SRC/$b" "$DEST/$b" 2>/dev/null
            fi
        done
        cp "$SRC"/*.sh "$DEST"/ 2>/dev/null
        chmod +x "$DEST"/* 2>/dev/null
        exit 0
    fi

    want=$(expected_lines)
    [ -n "$want" ] || { log "manifest lists no load-bearing files -- refusing"; exit 1; }

    updated=0
    missing_src=0
    verify_failed=0

    # Plain redirect, not a pipe: a piped while runs in a subshell under busybox
    # and its counters would be lost, which is how "0 files updated" gets
    # reported after work that actually happened.
    printf '%s\n' "$want" > "$DEST/.astro-want.tmp" || { log "cannot write to $DEST"; exit 1; }
    while IFS= read -r line; do
        exp=${line%% *}
        name=${line#* }
        [ -n "$name" ] || continue
        cur=$(hash_of "$DEST/$name")
        [ "$cur" = "$exp" ] && continue

        if [ ! -f "$SRC/$name" ]; then
            log "MISSING in bundle: $name"
            missing_src=$((missing_src + 1))
            continue
        fi
        # Temp name then move, so an interrupted copy never leaves a half-written
        # binary that the next boot would count as installed.
        tmp="$DEST/.$name.part"
        if cp "$SRC/$name" "$tmp" 2>/dev/null && chmod +x "$tmp" 2>/dev/null \
           && mv "$tmp" "$DEST/$name" 2>/dev/null; then
            after=$(hash_of "$DEST/$name")
            if [ "$after" = "$exp" ]; then
                log "updated $name"
                updated=$((updated + 1))
            else
                log "VERIFY FAILED after copy: $name"
                verify_failed=$((verify_failed + 1))
            fi
        else
            rm -f "$tmp" 2>/dev/null
            log "COPY FAILED: $name"
            verify_failed=$((verify_failed + 1))
        fi
    done < "$DEST/.astro-want.tmp"
    rm -f "$DEST/.astro-want.tmp"

    if [ "$missing_src" -ne 0 ] || [ "$verify_failed" -ne 0 ]; then
        # Do NOT stamp the manifest: keeping the previous stamp means the next
        # boot retries rather than declaring a partial install finished.
        log "sync incomplete ($missing_src missing, $verify_failed failed) -- not stamping"
        exit 1
    fi

    # Scripts are copied wholesale: they are small, and a partial set breaks a
    # watcher the same way a missing binary does.
    cp "$SRC"/*.sh "$DEST"/ 2>/dev/null
    chmod +x "$DEST"/* 2>/dev/null

    if [ "$updated" -eq 0 ]; then
        log "already up to date"
    else
        log "updated $updated file(s) in $DEST"
    fi

    # Refresh the ACTIVE boot hook. /app/bootapp runs /app/network_telnetd.sh, not
    # $DEST/polaris-astro-boot.sh, so updating the install directory alone leaves
    # the device running whatever hook was installed at first install -- including
    # the old copy-if-missing gate that ignores new releases entirely. Observed on
    # a real reboot: /app/astro held the new boot script while the live hook still
    # carried the pre-fix code.
    #
    # This script was itself invoked BY that hook, so never write it in place: a
    # running shell re-reads its script by offset, and overwriting it mid-run can
    # execute garbage. Temp name + mv swaps the inode instead.
    HOOK=/app/network_telnetd.sh
    if [ -f "$DEST/polaris-astro-boot.sh" ]; then
        if [ ! -f "$HOOK" ] || ! cmp -s "$DEST/polaris-astro-boot.sh" "$HOOK"; then
            if cp "$DEST/polaris-astro-boot.sh" "$HOOK.new" 2>/dev/null \
               && chmod 755 "$HOOK.new" 2>/dev/null && mv "$HOOK.new" "$HOOK" 2>/dev/null; then
                log "refreshed boot hook $HOOK"
            else
                rm -f "$HOOK.new" 2>/dev/null
                log "could not refresh boot hook $HOOK (still running the previous one)"
            fi
        fi
    fi

    # Stamp the manifest we just installed, so a later boot can tell a new card
    # payload from the same one. This is what makes an update visible at all.
    hash_of "$SRC/$MANIFEST_NAME" > "$DEST/$STAMP" 2>/dev/null
    exit 0
    ;;

  *)
    echo "usage: $0 {sync|verify} [SRC] [DEST]" >&2
    exit 2
    ;;
esac
