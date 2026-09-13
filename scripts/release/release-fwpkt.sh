#!/usr/bin/env bash
# release-fwpkt.sh — full release pipeline: stage → verify → trigger → confirm.
#
# Usage:
#   ./scripts/release/release-fwpkt.sh <build-dir> [options]
#
# Options:
#   --host IP          Polaris IP (default 192.168.0.1)
#   --ssh-user USER    SSH user (default root)
#   --skip-trigger     stage + verify only, do not reboot
#   --skip-verify      skip the post-reboot verification (fire-and-forget)
#   --max-wait SECS    max seconds to wait for device to return (default 900)
#
# What it does:
#   1. Pre-flight: SSH reachable, /app/sd has space
#   2. Stage: stream the extracted FwPkt/ tree to /app/sd/FwPkt/
#   3. Verify: recompute MD5s on-device, compare to firmwareInfo
#   4. Trigger: sync + /sbin/reboot (on-boot watcher fires SP_UpgradeCheckFw)
#   5. Wait: poll SSH until device returns (5-10 min for NAND reflash)
#   6. Confirm: check /app/FwVer + provenance file show the expected build_id
set -euo pipefail

BUILD_DIR=""
HOST="192.168.0.1"
SSH_USER="root"
SKIP_TRIGGER=0
SKIP_VERIFY=0
MAX_WAIT=900

while [ $# -gt 0 ]; do
  case "$1" in
    --host) HOST="$2"; shift 2;;
    --ssh-user) SSH_USER="$2"; shift 2;;
    --skip-trigger) SKIP_TRIGGER=1; shift;;
    --skip-verify) SKIP_VERIFY=1; shift;;
    --max-wait) MAX_WAIT="$2"; shift 2;;
    -h|--help) sed -n '2,20p' "$0"; exit 0;;
    *) BUILD_DIR="$1"; shift;;
  esac
done

[ -n "$BUILD_DIR" ] || { echo "usage: $0 <build-dir> [options]" >&2; exit 2; }
BUILD_DIR="$(cd "$BUILD_DIR" && pwd)"
SSH="${SSH_USER}@${HOST}"
FWPKT_DIR="$BUILD_DIR/FwPkt"

[ -d "$FWPKT_DIR" ] || { echo "ERROR: $FWPKT_DIR not found" >&2; exit 2; }
[ -f "$FWPKT_DIR/firmwareInfo" ] || { echo "ERROR: firmwareInfo missing" >&2; exit 2; }

# Read the expected build_id from provenance (if present)
EXPECTED_BUILD_ID=""
if [ -f "$BUILD_DIR/build-source-provenance.txt" ]; then
  EXPECTED_BUILD_ID="$(sed -n 's/^build_id=//p' "$BUILD_DIR/build-source-provenance.txt")"
fi

echo "=== release-fwpkt.sh $(date -u +%FT%TZ) ==="
echo "Build dir:   $BUILD_DIR"
echo "Target:      $SSH"
echo "Build ID:    ${EXPECTED_BUILD_ID:-<none>}"
echo

# --- 1. Pre-flight -----------------------------------------------------------
echo "--- [1/6] Pre-flight ---"
if ! timeout 5 ssh -o BatchMode=yes -o ConnectTimeout=5 "$SSH" 'true' 2>/dev/null; then
  echo "ERROR: SSH to $SSH failed." >&2; exit 3
fi
echo "SSH: OK"

SD_FREE_KB="$(ssh -o BatchMode=yes "$SSH" 'df -k /app/sd 2>/dev/null | tail -1' | awk '{print $4}')"
echo "/app/sd free: ${SD_FREE_KB:-unknown} KB"
if [ -n "$SD_FREE_KB" ] && [ "$SD_FREE_KB" -lt 100000 ]; then
  echo "WARN: low space on /app/sd (${SD_FREE_KB} KB)" >&2
fi

# --- 2. Stage ----------------------------------------------------------------
echo "--- [2/6] Staging FwPkt/ tree to /app/sd/FwPkt/ ---"
# Remove any existing partial tree first (clean slate)
ssh -o BatchMode=yes "$SSH" 'rm -rf /app/sd/FwPkt 2>/dev/null; true'

# Stream the tree
echo "Streaming $(du -sh "$FWPKT_DIR" | cut -f1) to device..."
tar czf - -C "$BUILD_DIR" FwPkt | \
  ssh -o BatchMode=yes -o ServerAliveInterval=10 "$SSH" 'tar xzf - -C /app/sd && sync'
echo "Staged. Verifying on-device layout..."
ssh -o BatchMode=yes "$SSH" 'ls /app/sd/FwPkt/ && echo OK'

# --- 3. Verify MD5s ----------------------------------------------------------
# NOTE: the device runs busybox sh (no bash). The script below is POSIX-only.
echo "--- [3/6] Verifying firmwareInfo MD5s on-device ---"
ssh -o BatchMode=yes "$SSH" 'sh -s' << 'VERIFY_EOF'
set -e
cd /app/sd/FwPkt
FAIL=0
while IFS= read -r line; do
  # Parse: "KEY size:N;KEY MD5:hash;"
  key=$(echo "$line" | sed -n "s/^\([a-zA-Z0-9]*\) size:.*/\1/p")
  [ -z "$key" ] && continue
  expected_md5=$(echo "$line" | sed -n "s/.*${key} MD5:\\([0-9a-fA-F][0-9a-fA-F]*\\);.*/\\1/p")
  # Find the file: camera/KEY[.ubifs] or gimbal/KEY_*.bin
  file=""
  if [ -f "camera/$key" ]; then file="camera/$key"
  elif [ -f "camera/${key}.ubifs" ]; then file="camera/${key}.ubifs"
  elif [ -f "gimbal/${key}_2.0.0.22.bin" ]; then file="gimbal/${key}_2.0.0.22.bin"
  else
    # Try glob for gimbal files
    file=$(ls gimbal/"${key}"_*.bin 2>/dev/null | head -1 || true)
  fi
  if [ -z "$file" ] || [ ! -f "$file" ]; then
    echo "  MISSING: $key (expected MD5 $expected_md5)"
    FAIL=1; continue
  fi
  actual_md5=$(md5sum "$file" | cut -d" " -f1)
  if [ "$actual_md5" = "$expected_md5" ]; then
    echo "  OK: $key ($actual_md5)"
  else
    echo "  MISMATCH: $key expected=$expected_md5 actual=$actual_md5"
    FAIL=1
  fi
done < firmwareInfo
if [ $FAIL -eq 0 ]; then
  echo "All MD5s verified. Ready to trigger."
else
  echo "MD5 verification FAILED." >&2
  exit 1
fi
VERIFY_EOF

# --- 4. Trigger --------------------------------------------------------------
if [ "$SKIP_TRIGGER" = "1" ]; then
  echo "--- [4/6] SKIPPED (--skip-trigger) ---"
else
  echo "--- [4/6] Triggering reboot (on-boot watcher will run SP_UpgradeCheckFw) ---"
  ssh -o BatchMode=yes "$SSH" 'sync; /sbin/reboot' 2>/dev/null || true
  echo "Reboot sent. Device will be dark for 5-10 min (NAND reflash)."
fi

# --- 5. Wait -----------------------------------------------------------------
if [ "$SKIP_TRIGGER" = "1" ] || [ "$SKIP_VERIFY" = "1" ]; then
  echo "--- [5/6] SKIPPED ---"
else
  echo "--- [5/6] Waiting up to ${MAX_WAIT}s for device to return ---"
  # Phase A: wait for the device to actually go DOWN (reboot in progress).
  # Without this, a fast first probe can succeed before the reboot takes
  # effect and we'd "confirm" against a half-rebooted box.
  echo "  Phase A: waiting for device to go dark..."
  down=0
  while [ $down -lt 60 ]; do
    if ! timeout 5 ssh -o BatchMode=yes -o ConnectTimeout=5 "$SSH" 'true' 2>/dev/null; then
      down=999; break
    fi
    sleep 5
    down=$(( down + 5 ))
  done
  if [ $down -ge 999 ]; then
    echo "  Device is dark (reboot in progress)."
  else
    echo "  WARN: device still up after 60s; reboot may not have taken. Continuing."
  fi
  # Phase B: wait for SSH to return (NAND reflash + boot, 5-10 min).
  elapsed=0
  while [ $elapsed -lt $MAX_WAIT ]; do
    if timeout 5 ssh -o BatchMode=yes -o ConnectTimeout=5 "$SSH" 'true' 2>/dev/null; then
      echo "Device back after ~${elapsed}s."
      break
    fi
    sleep 15
    elapsed=$(( elapsed + 15 ))
    [ $(( elapsed % 60 )) -eq 0 ] && echo "  ...still waiting (${elapsed}s)"
  done
  if [ $elapsed -ge $MAX_WAIT ]; then
    echo "WARN: device not back after ${MAX_WAIT}s. Best-effort verify follows."
  fi
  # Settle for polestar_app to finish init
  sleep 30
fi

# --- 6. Confirm --------------------------------------------------------------
if [ "$SKIP_VERIFY" = "1" ]; then
  echo "--- [6/6] SKIPPED (--skip-verify) ---"
else
  echo "--- [6/6] Confirming install ---"
  REMOTE_FWVER="$(ssh -o BatchMode=yes "$SSH" 'cat /app/FwVer 2>/dev/null' || echo '<unreachable>')"
  echo "/app/FwVer: $REMOTE_FWVER"

  if [ -n "$EXPECTED_BUILD_ID" ]; then
    if echo "$REMOTE_FWVER" | grep -q "$EXPECTED_BUILD_ID"; then
      echo "PASS: /app/FwVer contains build_id '$EXPECTED_BUILD_ID'"
    else
      echo "WARN: /app/FwVer does not contain expected build_id '$EXPECTED_BUILD_ID'"
      echo "  (the sw: version shown in Benro Connect is set by polestar_app at runtime;"
      echo "   the FwVer file is the on-disk identity. Check Mlog for SP_SendMsgToApp code 780.)"
    fi
  fi

  # Check provenance (libgphoto2 build info)
  PROVENANCE="$(ssh -o BatchMode=yes "$SSH" 'cat /app/openpolaris-libgphoto2-provenance.txt 2>/dev/null' || echo '<none>')"
  if [ -n "$PROVENANCE" ]; then
    echo "Provenance:"
    echo "$PROVENANCE" | sed 's/^/  /'
  fi

  # Check Mlog for the upgrade result
  UPGRADE_LOG="$(ssh -o BatchMode=yes "$SSH" 'grep -aiE "CHECK_FW|UPGRADE|FwVer|SP_UpgradeCheckFw" /app/Mlog.txt 2>/dev/null | tail -10' || true)"
  if [ -n "$UPGRADE_LOG" ]; then
    echo "Recent upgrade log lines:"
    echo "$UPGRADE_LOG" | sed 's/^/  /'
  fi
fi

echo
echo "=== release-fwpkt.sh complete ==="
