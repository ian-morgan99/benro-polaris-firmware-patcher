#!/usr/bin/env bash
# install-astro-kit.sh -- stage a candidate's SD kit and run its installer, with
# proof. THE supported way to put the astro kit on a device after a flash.
#
# Usage:
#   ./scripts/release/install-astro-kit.sh <build-dir> [options]
#
# Options:
#   --host IP          Polaris IP (default 192.168.0.1)
#   --ssh-user USER    SSH user (default root)
#   --no-indexes       skip astrometry/ (indexes already on the card)
#   --no-wifi          skip polaris-wifi/  (refused unless --allow-partial)
#   --allow-partial    permit an incomplete kit; the omission is recorded
#   --allow-fwver-mismatch  install a kit stamped for a different firmware version
#   --no-boot          pass NO_BOOT=1 to install_astro.sh (files only, no hook)
#   --reboot           reboot and wait for 8090 instead of just reporting it
#   --skip-verify      stage + install, do not verify hashes or the port
#   --max-wait SECS    seconds to wait for 8090 after --reboot (default 600)
#   -h | --help
#
# WHY THIS EXISTS
# A firmware flash replaces the whole appfs volume, and /app/astro lives on it,
# so every flash deletes the plate solver AND the boot hook that starts it. The
# kit therefore has to be re-staged and install_astro.sh re-run after EVERY
# release, not just the first (docs/FIRMWARE-INSTALL-PROCESS.md).
#
# That step was never scripted. Each release it got done by hand, and hand
# staging drifts:
#   - scp does not work here at all. The device's sshd has no sftp-server
#     subsystem, so scp fails with "Connection closed", and legacy `scp -O`
#     hangs. Only tar streamed over ssh works, which is what release-fwpkt.sh
#     already uses for FwPkt/.
#   - hand staging usually copies polaris-astro/ only, leaving polaris-wifi/
#     stale from an earlier release on the card.
#   - nothing then checked that install_astro.sh actually ran, so a device came
#     back with the right FwVer, /app/astro empty, no boot hook and port 8090
#     closed -- and looked installed. That is exactly what testers reported as
#     "http://<ip>:8090 unreachable" against .104.
# This script stages, installs, and fails closed if the kit is not provably
# running. It never flashes firmware; run release-fwpkt.sh for that first.
#
# What it does:
#   1. Gate: candidate carries an astro bundle + ASTRO-MANIFEST.sha256, device
#      reachable, /app has room (the #312 hazard).
#   2. Stage: stream polaris-astro/ (+ polaris-wifi/, + astrometry/ on request)
#      to /app/sd as one tar stream over ssh. Never scp.
#   3. Verify staged bytes against ASTRO-MANIFEST.sha256 on-device, scoped to
#      what was staged. A truncated transfer is not an install.
#   4. Install: run /app/sd/polaris-astro/install_astro.sh on the device.
#   5. Confirm: /app/astro/polaris-httpd present and executable, boot hook
#      installed, port 8090 answering. Appends to install-receipt.txt.
set -euo pipefail

BUILD_DIR=""
HOST="192.168.0.1"
SSH_USER="root"
WITH_INDEXES=1
WITH_WIFI=1
NO_BOOT=0
DO_REBOOT=0
SKIP_VERIFY=0
MAX_WAIT=600
ALLOW_PARTIAL="${ALLOW_PARTIAL:-0}"
ALLOW_FWVER_MISMATCH="${ALLOW_FWVER_MISMATCH:-0}"

while [ $# -gt 0 ]; do
  case "$1" in
    --host) HOST="$2"; shift 2;;
    --ssh-user) SSH_USER="$2"; shift 2;;
    --no-indexes) WITH_INDEXES=0; shift;;
    --no-wifi) WITH_WIFI=0; shift;;
    --allow-partial) ALLOW_PARTIAL=1; shift;;
    --allow-fwver-mismatch) ALLOW_FWVER_MISMATCH=1; shift;;
    --no-boot) NO_BOOT=1; shift;;
    --reboot) DO_REBOOT=1; shift;;
    --skip-verify) SKIP_VERIFY=1; shift;;
    --max-wait) MAX_WAIT="$2"; shift 2;;
    -h|--help) sed -n '2,48p' "$0"; exit 0;;
    *) BUILD_DIR="$1"; shift;;
  esac
done

[ -n "$BUILD_DIR" ] || { echo "usage: $0 <build-dir> [options]" >&2; exit 2; }
BUILD_DIR="$(cd "$BUILD_DIR" && pwd)"
SSH="${SSH_USER}@${HOST}"
SD_ROOT="$BUILD_DIR/astro-bundle/COPY-TO-SD-CARD-ROOT"
KIT_MANIFEST="$BUILD_DIR/astro-bundle/ASTRO-MANIFEST.sha256"

# sshd here has no sftp-server subsystem, so scp cannot work at all. Everything
# goes through one tar stream over a single ssh session.
# ServerAliveCountMax is raised deliberately: the kit stream is ~70 MB and the
# remote `tar xzf` + `sync` on vfat runs at ~2.1 MB/s, so the session is silent
# for well over the 30 s that ServerAliveInterval=10 with the default
# ServerAliveCountMax=3 will tolerate. Without this the stream is killed mid-
# transfer on a device that is behaving normally.
SSH_ARGS=(-o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=10 -o ServerAliveCountMax=60)

# The device runs busybox sh (no bash), so anything piped to `sh -s` is POSIX.
probe_device() {
  ssh "${SSH_ARGS[@]}" "$SSH" 'sh -s' <<'PROBE_EOF'
HTTPD=0; HOOK=0; PORT=0
[ -x /app/astro/polaris-httpd ] && HTTPD=1
grep -q "polaris-astro boot hook" /app/network_telnetd.sh 2>/dev/null && HOOK=1
netstat -ltn 2>/dev/null | grep -q ":8090" && PORT=1
echo "httpd=$HTTPD hook=$HOOK port8090=$PORT"
PROBE_EOF
}

# Station-mode join state, read before a reboot is issued. Kept as a function in
# the same shape as probe_device: a heredoc written inline inside "$( ... )"
# swallows the lines that follow it, which turned STATE into an unbound variable
# and made every verification step report "polaris-httpd is missing" on a device
# that was fine.
probe_wifi() {
  ssh "${SSH_ARGS[@]}" "$SSH" 'sh -s' <<'WIFI_EOF'
AJ=0; WC=0; SSID=-
[ -f /app/sd/polaris-wifi/autojoin ] && AJ=1
[ -f /app/sd/polaris-wifi/wpa.conf ] && WC=1
if [ "$WC" = "1" ]; then
    SSID=$(sed -n 's/^[[:space:]]*ssid="\(.*\)"/\1/p' /app/sd/polaris-wifi/wpa.conf | head -1)
fi
echo "autojoin=$AJ wpaconf=$WC ssid=$SSID"
WIFI_EOF
}

# --- 1. Gate -----------------------------------------------------------------
echo "--- [1/5] Gate: candidate kit, device, free space ---"
[ -d "$SD_ROOT/polaris-astro" ] || {
  echo "ERROR: $SD_ROOT/polaris-astro not found." >&2
  echo "       This candidate carries no astro kit. Build it with" >&2
  echo "       scripts/build-astro.sh, or use the camera-only packet." >&2
  exit 2
}
[ -f "$SD_ROOT/polaris-astro/install_astro.sh" ] || {
  echo "ERROR: install_astro.sh missing from the kit" >&2; exit 2
}
[ -f "$KIT_MANIFEST" ] || {
  echo "ERROR: $KIT_MANIFEST not found -- staged bytes cannot be verified." >&2
  echo "       A kit with no manifest has shipped before and installed nothing." >&2
  exit 2
}
grep -q 'polaris-httpd$' "$KIT_MANIFEST" || {
  echo "ERROR: $KIT_MANIFEST does not cover polaris-httpd" >&2; exit 2
}

# Which kit directories travel this run, decided BEFORE touching the device: an
# incomplete kit should be refused in milliseconds, not after a connection attempt.
#
# astrometry/ is ~1 GB of indexes and is usually already on the card, so
# --no-indexes is the common case after a flash and stays freely omissible.
#
# polaris-wifi/ is different, and refusing to omit it is deliberate. Both kit
# archives are "repeat every release" per docs/FIRMWARE-INSTALL-PROCESS.md; only
# astrometry-indexes.zip is documented as a one-time copy that never changes.
#
# The reason is NOT credential loss -- wpa.conf lives on the card at
# /app/sd/polaris-wifi/wpa.conf and polaris-astro.zip carries no wpa.conf, so
# extracting one archive cannot remove the other's configuration. The real hazard
# is that the boot hook executes /app/sd/polaris-wifi/polaris-autojoin.sh and its
# binaries: omitting the kit leaves a stale wifi stack running against new astro
# code, an untested combination that only gets exercised on the next reboot.
# Omitting it used to be silent -- the run still ended "installed-verified" -- so
# it fails closed here rather than relying on the operator remembering. This is the
# hazard the script's own header describes ("hand staging usually copies
# polaris-astro/ only, leaving polaris-wifi/ stale").
DIRS=(polaris-astro)
SKIPPED=""
if [ "$WITH_WIFI" = "1" ]; then
  DIRS+=(polaris-wifi)
elif [ "${ALLOW_PARTIAL:-0}" != "1" ]; then
  echo "ERROR: refusing to stage a kit without polaris-wifi/ (--no-wifi)." >&2
  echo "       The supported route pushes the whole bundle every release:" >&2
  echo "       docs/FIRMWARE-INSTALL-PROCESS.md says extract BOTH archives on" >&2
  echo "       every release; only astrometry-indexes.zip is a one-time copy." >&2
  echo "       polaris-wifi/ carries the station-mode join that runs at boot, so" >&2
  echo "       omitting it leaves a stale wifi stack executing against new astro" >&2
  echo "       code -- exercised only on the next reboot, which is the worst time" >&2
  echo "       to find it." >&2
  echo "       Re-run without --no-wifi, or add --allow-partial if this card" >&2
  echo "       genuinely cannot take it (the omission is recorded in the receipt)." >&2
  exit 2
else
  SKIPPED=" polaris-wifi"
fi
[ "$WITH_INDEXES" = "1" ] && DIRS+=(astrometry)
for d in "${DIRS[@]}"; do
  [ -d "$SD_ROOT/$d" ] || { echo "ERROR: $SD_ROOT/$d not found" >&2; exit 2; }
done
echo "  staging: ${DIRS[*]}"
# Explicit if, not `[ -n "$SKIPPED" ] && echo`: under set -e a short-circuit that
# evaluates false returns 1 and aborts the script, which is how this gate managed
# to fail every normal (complete-kit) run.
if [ -n "$SKIPPED" ]; then
  echo "  WARNING: deliberately NOT staged:$SKIPPED (--allow-partial)"
fi

EXPECTED_BUILD_ID=""
[ -f "$BUILD_DIR/build-source-provenance.txt" ] && \
  EXPECTED_BUILD_ID="$(sed -n 's/^build_id=//p' "$BUILD_DIR/build-source-provenance.txt")"

if ! ssh "${SSH_ARGS[@]}" "$SSH" 'echo ok' >/dev/null 2>&1; then
  echo "ERROR: cannot reach $SSH over ssh." >&2; exit 3
fi
echo "  device reachable: $SSH"

# --- kit / firmware alignment -------------------------------------------------
# The kit is stamped at build time with the firmware version it was built against
# (polaris-astro/VERSION, written by scripts/build-astro-bundle.sh --fwver). Read
# that and compare it with what the head actually runs before staging anything.
#
# WHY THIS IS A GATE AND NOT A NOTE. Kit and firmware are built separately and
# deployed together, so a mismatch is entirely possible and was previously
# invisible: astro-v112 shipped as an SD-kit-only release while the head still ran
# .110, and nothing on the device could express which kit was installed. The
# reverse case -- flashing a new appfs under an old kit -- is worse, because the
# boot hook then runs kit code that was never built for that appfs.
#
# An unstamped kit (built before --fwver existed) is allowed with a warning: it is
# the common case for older out/ directories and refusing it would block every
# historical candidate. A stamp that DISAGREES is a hard failure, because that is
# a positive statement that these two artefacts were not built as a pair.
KIT_FWVER=""
[ -f "$SD_ROOT/polaris-astro/VERSION" ] && \
  KIT_FWVER="$(sed -n 's/^firmware_version=//p' "$SD_ROOT/polaris-astro/VERSION")"
DEVICE_FWVER="$(ssh "${SSH_ARGS[@]}" "$SSH" \
  'sed -n "s/^FwVer:\([^;]*\).*/\1/p" /app/FwVer 2>/dev/null | head -1' || true)"
DEVICE_FWVER="${DEVICE_FWVER%$'\r'}"

if [ -z "$KIT_FWVER" ] || [ "$KIT_FWVER" = "unknown" ]; then
  echo "  kit firmware stamp: none (built without --fwver; alignment not checkable)"
elif [ -z "$DEVICE_FWVER" ]; then
  echo "  WARNING: head reports no /app/FwVer; cannot verify alignment."
  echo "           Kit expects firmware $KIT_FWVER."
elif [ "$KIT_FWVER" != "$DEVICE_FWVER" ]; then
  echo "ERROR: kit and firmware are not a matched pair." >&2
  echo "         kit built for : $KIT_FWVER" >&2
  echo "         head runs     : $DEVICE_FWVER" >&2
  echo "       Deploy them together, or build the kit against the running firmware" >&2
  echo "       with scripts/build-astro-bundle.sh --fwver $DEVICE_FWVER." >&2
  echo "       Override with --allow-fwver-mismatch only if you have checked that" >&2
  echo "       this kit genuinely works on $DEVICE_FWVER." >&2
  [ "${ALLOW_FWVER_MISMATCH:-0}" = "1" ] || exit 2
  echo "  WARNING: proceeding despite the mismatch (--allow-fwver-mismatch)."
else
  echo "  kit/firmware aligned: $KIT_FWVER"
fi

# /app is a 68 MB ubifs and a flash leaves it nearly full. install_astro.sh
# copies binaries into it before writing the boot hook, so a short write there
# costs autostart -- issue #312. Say what is there before starting.
APP_FREE_KB="$(ssh "${SSH_ARGS[@]}" "$SSH" 'df -k /app 2>/dev/null | awk "NR==2{print \$4}"' || true)"
case "$APP_FREE_KB" in (*[!0-9]*|'') APP_FREE_KB=0;; esac
echo "  /app free: $((APP_FREE_KB / 1024)) MB"
if [ "$APP_FREE_KB" -lt 3072 ]; then
  echo "ERROR: only $((APP_FREE_KB / 1024)) MB free on /app; the kit needs ~3 MB plus" >&2
  echo "       headroom, and a short write after the binaries skips autostart (#312)." >&2
  echo "       Free /app or re-flash before installing." >&2
  exit 3
fi

# --- 2. Stage ----------------------------------------------------------------
echo "--- [2/5] Staging kit to /app/sd as one tar stream over ssh ---"
# Staging is additive on the card and never touches a configured site.conf: the
# bundle ships site.conf.example only, and install_astro.sh is the sole writer
# of /app.
TOTAL_KB="$(du -sk "${DIRS[@]/#/$SD_ROOT/}" | awk '{s+=$1} END{print s+0}')"
echo "  streaming $((TOTAL_KB / 1024)) MB ..."
tar czf - -C "$SD_ROOT" "${DIRS[@]}" | \
  ssh "${SSH_ARGS[@]}" "$SSH" 'tar xzf - -C /app/sd && sync'
echo "  staged."

# --- 3. Verify staged bytes --------------------------------------------------
if [ "$SKIP_VERIFY" = "1" ]; then
  echo "--- [3/5] SKIPPED (--skip-verify) ---"
else
  echo "--- [3/5] Verifying staged kit against ASTRO-MANIFEST.sha256 ---"
  # Scope the manifest to what was actually staged: astrometry/ is excluded by
  # default and its absence must not read as corruption. Manifest paths are
  # relative to COPY-TO-SD-CARD-ROOT, e.g. ./polaris-astro/polaris-httpd.
  #
  # Anchor on the path FIELD, not the line start: sha256sum emits
  # "<hash>  ./path", so a ^\./ pattern matches nothing and this step would
  # abort every run -- or, if the abort were relaxed, verify zero files and call
  # that a pass. Same two-space separator that broke install_astro.sh (#312).
  SCOPE="$(IFS='|'; echo "${DIRS[*]}")"
  SCOPED="$(mktemp)"
  grep -E "[[:space:]]\./(${SCOPE})/" "$KIT_MANIFEST" > "$SCOPED" || true
  COUNT="$(wc -l < "$SCOPED" | tr -d ' ')"
  if [ "$COUNT" -eq 0 ]; then
    echo "ERROR: manifest has no entries for ${DIRS[*]}" >&2
    rm -f "$SCOPED"; exit 4
  fi
  # sha256sum -c prints one "OK" line per file; anything else is a mismatch or a
  # missing file. Feed the scoped manifest to it over the same ssh session.
  BAD="$(ssh "${SSH_ARGS[@]}" "$SSH" 'cd /app/sd && sha256sum -c - 2>&1 | grep -av ": OK$"' < "$SCOPED" | head -40 || true)"
  rm -f "$SCOPED"
  if [ -n "$BAD" ]; then
    echo "ERROR: staged kit does not match the candidate manifest:" >&2
    echo "$BAD" | sed 's/^/    /' >&2
    exit 4
  fi
  echo "  $COUNT staged files verified byte-for-byte."
fi

# --- 4. Install --------------------------------------------------------------
echo "--- [4/5] Running install_astro.sh on the device ---"
INSTALL_CMD="/app/sd/polaris-astro/install_astro.sh"
[ "$NO_BOOT" = "1" ] && INSTALL_CMD="NO_BOOT=1 $INSTALL_CMD"
# Capture the exit status. install_astro.sh exits 1 on every FATAL boot-hook path
# (missing hook, hash mismatch, no polaris-astro-boot.sh), and this script runs
# under set -e, so the || rc=$? is what keeps the run alive long enough to report
# it rather than dying inside the substitution with no output at all.
INSTALL_RC=0
INSTALL_OUT="$(ssh "${SSH_ARGS[@]}" "$SSH" "sh -c '$INSTALL_CMD' 2>&1")" || INSTALL_RC=$?
echo "$INSTALL_OUT" | sed 's/^/    /'
if [ "$INSTALL_RC" != "0" ]; then
  echo "ERROR: install_astro.sh exited $INSTALL_RC on the device." >&2
  echo "       Its own output is above; it exits non-zero when the boot hook is" >&2
  echo "       missing, empty, or does not match the bundle -- in every one of" >&2
  echo "       those cases nothing starts at boot and port 8090 stays closed." >&2
  exit 5
fi
# Match on the marker only, never the full sentence. install_astro.sh's success
# line was extended to "boot hook installed and verified ->" when it gained a
# sha256 check of the installed hook; grepping the old exact wording made this
# gate reject a successful install (exit 5) while the device was in fact fully
# installed. The marker survives wording changes; the exit status above is the
# real authority and this line only confirms the positive path announced itself.
if [ "$NO_BOOT" != "1" ] && ! printf '%s\n' "$INSTALL_OUT" | grep -q 'boot hook installed'; then
  echo "ERROR: install_astro.sh exited 0 but never reported installing the boot hook." >&2
  echo "       Without it nothing starts at boot and port 8090 stays closed." >&2
  exit 5
fi

# --- 5. Confirm --------------------------------------------------------------
if [ "$SKIP_VERIFY" = "1" ]; then
  echo "--- [5/5] SKIPPED (--skip-verify) ---"
else
  echo "--- [5/5] Confirming the kit is installed and serving ---"

  # A reboot can move or drop the address this script is talking to. If station-
  # mode autojoin is configured, the head joins the home network at boot and may
  # come back on a different lease -- or not at all if the join fails while the
  # AP has been moved onto the home channel. Say so BEFORE rebooting, and name
  # the recovery address, rather than letting the operator discover it by finding
  # the device gone. This is the check that would have caught today's outage.
  if [ "$DO_REBOOT" = "1" ]; then
    WIFI_STATE="$(probe_wifi)" || WIFI_STATE="autojoin=? wpaconf=? ssid=?"
    echo "  wifi: $WIFI_STATE"
    if printf '%s\n' "$WIFI_STATE" | grep -q 'autojoin=1'; then
      if printf '%s\n' "$WIFI_STATE" | grep -q 'wpaconf=0'; then
        echo "  WARNING: autojoin is enabled but wpa.conf is absent -- the join will"
        echo "           fail at boot. The head should still be reachable on its AP."
      else
        printf '%s\n' "$WIFI_STATE" | grep -q 'ssid=' && \
          echo "  autojoin is ON: after reboot expect a new DHCP lease, not necessarily $HOST."
        echo "  Recovery if it does not answer: join the AP polaris_d13e86 -> root@192.168.0.1"
        echo "  Join failure reason, if any: /app/sd/polaris-wifi/autojoin.log on the card."
      fi
    fi
  fi

  STATE="$(probe_device)"
  echo "  $STATE"

  if [ "$DO_REBOOT" = "1" ] && ! printf '%s\n' "$STATE" | grep -q 'port8090=1'; then
    echo "  not listening yet; rebooting so the boot hook runs, waiting up to ${MAX_WAIT}s ..."
    ssh "${SSH_ARGS[@]}" "$SSH" 'sync; /sbin/reboot' >/dev/null 2>&1 || true
    WAITED=30
    sleep 30
    BACK=0
    while [ "$WAITED" -lt "$MAX_WAIT" ]; do
      if curl -fsS -m 5 -o /dev/null "http://${HOST}:8090/" 2>/dev/null; then
        echo "  8090 answering after ${WAITED}s."
        STATE="$(probe_device)"
        echo "  $STATE"
        BACK=1
        break
      fi
      sleep 15; WAITED=$((WAITED + 15))
    done
    # STATE currently holds the PRE-reboot probe. If the device did not come back
    # on this address, reporting those stale values would claim "httpd=1 hook=1
    # port8090=1" for a head that is unreachable -- which is precisely how a
    # station-mode join failure reads as a successful install. The only honest
    # answer after a reboot that did not return is a hard failure naming the
    # likely cause, because the address itself may have moved.
    if [ "$BACK" != "1" ]; then
      echo "ERROR: device did not come back on $HOST within ${MAX_WAIT}s." >&2
      echo "       The reboot was issued; nothing here can say whether it booted." >&2
      echo "       Most likely the station-mode join moved or dropped the address:" >&2
      echo "         - join the AP (polaris_d13e86) and reach it at 192.168.0.1, or" >&2
      echo "         - check your router's DHCP table for a new lease." >&2
      echo "       /app/sd/polaris-wifi/autojoin.log on the card records why a join" >&2
      echo "       failed. Do NOT re-run this script blind: it cannot verify anything" >&2
      echo "       it cannot reach, and the kit may already be installed correctly." >&2
      exit 6
    fi
  fi

  printf '%s\n' "$STATE" | grep -q 'httpd=1' || {
    echo "ERROR: /app/astro/polaris-httpd is missing or not executable." >&2; exit 5
  }
  if [ "$NO_BOOT" != "1" ] && ! printf '%s\n' "$STATE" | grep -q 'hook=1'; then
    echo "ERROR: boot hook not installed -- nothing will start at boot." >&2; exit 5
  fi
  if ! printf '%s\n' "$STATE" | grep -q 'port8090=1'; then
    echo "ERROR: port 8090 is not listening." >&2
    echo "       The kit is on disk but nothing is serving it. Reboot the device" >&2
    echo "       (the boot hook starts polaris-httpd), or re-run with --reboot." >&2
    exit 5
  fi
  echo "  http://$HOST:8090/ is serving."
fi

# --- receipt -----------------------------------------------------------------
VERIFIED_AT="$(date -u +%FT%TZ)"
{
  [ -n "$EXPECTED_BUILD_ID" ] && echo "build_id=$EXPECTED_BUILD_ID"
  echo "kit_target=$SSH"
  echo "kit_dirs=${DIRS[*]}"
  echo "kit_firmware_expected=${KIT_FWVER:-unstamped}"
  echo "head_firmware_actual=${DEVICE_FWVER:-unknown}"
  if [ -n "$SKIPPED" ]; then
    echo "kit_omitted=${SKIPPED# } (allow-partial)"
  fi
  echo "no_boot=$NO_BOOT"
  echo "kit_status=installed-verified"
  echo "verified_at=$VERIFIED_AT"
} >> "$BUILD_DIR/install-receipt.txt"
echo
echo "=== install-astro-kit.sh complete ==="
echo "Kit status: installed-verified (appended to $BUILD_DIR/install-receipt.txt)"
