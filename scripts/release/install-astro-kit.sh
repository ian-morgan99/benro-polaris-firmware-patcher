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
#   --no-wifi          skip polaris-wifi/
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

while [ $# -gt 0 ]; do
  case "$1" in
    --host) HOST="$2"; shift 2;;
    --ssh-user) SSH_USER="$2"; shift 2;;
    --no-indexes) WITH_INDEXES=0; shift;;
    --no-wifi) WITH_WIFI=0; shift;;
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
SSH_ARGS=(-o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=10)

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

EXPECTED_BUILD_ID=""
[ -f "$BUILD_DIR/build-source-provenance.txt" ] && \
  EXPECTED_BUILD_ID="$(sed -n 's/^build_id=//p' "$BUILD_DIR/build-source-provenance.txt")"

if ! ssh "${SSH_ARGS[@]}" "$SSH" 'echo ok' >/dev/null 2>&1; then
  echo "ERROR: cannot reach $SSH over ssh." >&2; exit 3
fi
echo "  device reachable: $SSH"

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

# Which kit directories travel this run. astrometry/ is ~1 GB of indexes and is
# usually already on the card, so --no-indexes is the common case after a flash.
DIRS=(polaris-astro)
[ "$WITH_WIFI" = "1" ] && DIRS+=(polaris-wifi)
[ "$WITH_INDEXES" = "1" ] && DIRS+=(astrometry)
for d in "${DIRS[@]}"; do
  [ -d "$SD_ROOT/$d" ] || { echo "ERROR: $SD_ROOT/$d not found" >&2; exit 2; }
done
echo "  staging: ${DIRS[*]}"

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
INSTALL_OUT="$(ssh "${SSH_ARGS[@]}" "$SSH" "sh -c '$INSTALL_CMD' 2>&1")"
echo "$INSTALL_OUT" | sed 's/^/    /'
if [ "$NO_BOOT" != "1" ] && ! printf '%s\n' "$INSTALL_OUT" | grep -q 'boot hook installed ->'; then
  echo "ERROR: install_astro.sh did not report the boot hook being installed." >&2
  echo "       Without it nothing starts at boot and port 8090 stays closed." >&2
  exit 5
fi

# --- 5. Confirm --------------------------------------------------------------
if [ "$SKIP_VERIFY" = "1" ]; then
  echo "--- [5/5] SKIPPED (--skip-verify) ---"
else
  echo "--- [5/5] Confirming the kit is installed and serving ---"
  STATE="$(probe_device)"
  echo "  $STATE"

  if [ "$DO_REBOOT" = "1" ] && ! printf '%s\n' "$STATE" | grep -q 'port8090=1'; then
    echo "  not listening yet; rebooting so the boot hook runs, waiting up to ${MAX_WAIT}s ..."
    ssh "${SSH_ARGS[@]}" "$SSH" 'sync; /sbin/reboot' >/dev/null 2>&1 || true
    WAITED=30
    sleep 30
    while [ "$WAITED" -lt "$MAX_WAIT" ]; do
      if curl -fsS -m 5 -o /dev/null "http://${HOST}:8090/" 2>/dev/null; then
        echo "  8090 answering after ${WAITED}s."
        STATE="$(probe_device)"
        echo "  $STATE"
        break
      fi
      sleep 15; WAITED=$((WAITED + 15))
    done
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
  echo "no_boot=$NO_BOOT"
  echo "kit_status=installed-verified"
  echo "verified_at=$VERIFIED_AT"
} >> "$BUILD_DIR/install-receipt.txt"
echo
echo "=== install-astro-kit.sh complete ==="
echo "Kit status: installed-verified (appended to $BUILD_DIR/install-receipt.txt)"
