#!/usr/bin/env bash
# camera-layer-report.sh — classify a "camera not recognised" symptom by layer (#297)
#
# READ-ONLY. It never restarts, kills, unbinds, rebinds, writes to the device, or
# touches /var/run. Everything it does is reading sysfs, /proc and the WebUI.
#
# Why this exists. #297 asks for evidence at five layers before anyone may claim K-3 III
# recognition works. Before this, answering it meant a dozen hand-typed SSH commands, and
# the answers were easy to misread: on the device that prompted it, `lsusb` showed the
# camera present, pgphoto was running, and polaris-httpd was serving -- all three true, and
# the camera still invisible. The layers that actually differ are the ones nobody was
# looking at: whether pgphoto has a camlib mapped, whether it holds a USB handle, and
# whether anything has ever connected to its port.
#
# The vocabulary is deliberately #297's: PASS / FAIL / UNKNOWN, never a bare exit code.
# UNKNOWN means "this layer could not be measured", which is different from FAIL ("measured
# and wrong"), and conflating the two is how a device that cannot be reached gets recorded
# as a device that is broken.
#
# Usage:
#   scripts/diagnostic/camera-layer-report.sh                       # default device
#   scripts/diagnostic/camera-layer-report.sh --user-host root@192.168.0.1 --out /tmp/lay
#   scripts/diagnostic/camera-layer-report.sh --expect 25fb:0189    # assert a specific camera
#
# Exit codes:
#   0    every measured layer passed
#   1    at least one layer FAILED (the report says which)
#   2    some layer was UNKNOWN / device unreachable -- not a pass, not a failure
set -uo pipefail

USER_HOST=${USER_HOST:-root@192.168.0.1}
WEBUI=${WEBUI:-http://192.168.0.1:8090}
EXPECT=""
OUT=""
SSH_OPTS="-o StrictHostKeyChecking=no -o BatchMode=yes -o ConnectTimeout=8"

while [ $# -gt 0 ]; do
  case "$1" in
    --user-host) USER_HOST="$2"; shift 2;;
    --webui)     WEBUI="$2"; shift 2;;
    --expect)    EXPECT="$2"; shift 2;;
    --out)       OUT="$2"; shift 2;;
    -h|--help)   sed -n '1,30p' "$0"; exit 0;;
    *) echo "unknown argument: $1" >&2; exit 2;;
  esac
done

say() { printf '%s\n' "$*"; }
hr() {
  local label="-- $* "
  local pad=$((78 - ${#label}))
  [ "$pad" -lt 0 ] && pad=0
  printf '%s%s\n' "$label" "$(printf -- '-%.0s' $(seq 1 "$pad"))"
}

# One SSH call per layer group rather than one per file: each round trip on this device
# takes seconds, and a report assembled from 30 separate connections can straddle a
# restart and describe a state that never existed.
dsh() { timeout 90 ssh $SSH_OPTS "$USER_HOST" "$1" 2>/dev/null; }

TMPR=$(mktemp "${TMPDIR:-/tmp}/camera-layers.XXXXXX")
exec > >(tee "${OUT:-$TMPR}") 2>&1
trap 'rm -rf "$TMPR"' EXIT

VERDICT_PASS=0; VERDICT_FAIL=0; VERDICT_UNKNOWN=0
record() { # record <layer> <PASS|FAIL|UNKNOWN> <detail>
  printf '[%s] %s -- %s\n' "$2" "$1" "$3"
  case "$2" in PASS) VERDICT_PASS=$((VERDICT_PASS+1));;
                FAIL) VERDICT_FAIL=$((VERDICT_FAIL+1));;
                *)    VERDICT_UNKNOWN=$((VERDICT_UNKNOWN+1));; esac
}

say "camera layer report -- $(date -u +%FT%TZ)"
say "device: $USER_HOST   webui: $WEBUI"
[ -n "$EXPECT" ] && say "expected camera idVendor:idProduct = $EXPECT"
say ""

# ---------------------------------------------------------------------------
# LAYER 1: kernel/USB enumeration
# ---------------------------------------------------------------------------
hr "layer 1: USB enumeration"
L1=$(dsh 'for d in /sys/bus/usb/devices/*/idVendor; do p=${d%idVendor}; v=$(cat $d 2>/dev/null); pr=$(cat ${p}idProduct 2>/dev/null); n=$(cat ${p}product 2>/dev/null); [ -n "$v" ] && printf "%s %s:%s %s\n" "${p%/}" "$v" "$pr" "$n"; done')
if [ -z "$L1" ]; then
  record "layer1-usb" UNKNOWN "no sysfs USB output -- device unreachable or ssh failed"
else
  printf '%s\n' "$L1"
  if [ -n "$EXPECT" ]; then
    if printf '%s\n' "$L1" | grep -qiF "$EXPECT"; then
      record "layer1-usb" PASS "$EXPECT enumerated"
    else
      record "layer1-usb" FAIL "$EXPECT not present in sysfs"
    fi
  else
    record "layer1-usb" PASS "sysfs readable (no --expect given, so no identity asserted)"
  fi
fi

# Interface class decides which camlib can serve it: 06/01/01 is PTP. A camera exposing
# only a vendor-specific interface may enumerate fine and still be unservable.
L1I=$(dsh 'for i in /sys/bus/usb/devices/*:1.*; do [ -r "$i/bInterfaceClass" ] || continue; printf "%s %s/%s/%s driver=%s\n" "${i##*/}" "$(cat $i/bInterfaceClass)" "$(cat $i/bInterfaceSubClass)" "$(cat $i/bInterfaceProtocol)" "$(basename $(readlink $i/driver 2>/dev/null) 2>/dev/null || echo none)"; done')
[ -n "$L1I" ] && printf '%s\n' "$L1I"

# ---------------------------------------------------------------------------
# LAYER 2: pgphoto process and its restart path
# ---------------------------------------------------------------------------
hr "layer 2: pgphoto process"
L2=$(dsh 'P=$(ps 2>/dev/null | grep pgphoto.stage2ondisk | grep -v grep | awk "{print \$1}" | head -1); echo "pid=${P:-none}"; [ -n "$P" ] && { echo "state=$(awk "{print \$3}" /proc/$P/stat 2>/dev/null)"; echo "wchan=$(cat /proc/$P/wchan 2>/dev/null)"; echo "threads=$(ls /proc/$P/task 2>/dev/null | wc -l)"; }; echo "--- restart lock ---"; ls -ld /var/run/openpolaris-pgphoto.restart.lock 2>&1 | head -1; LP=$(cat /var/run/openpolaris-pgphoto.restart.lock/pid 2>/dev/null); echo "lock_pid=[${LP:-empty}]"; [ -n "$LP" ] && { [ -d /proc/$LP ] && echo "lock_owner_alive=yes" || echo "lock_owner_alive=no (STALE)"; }; echo "--- supervisor ---"; ps 2>/dev/null | grep -c "[c]amera_usb_supervisor"' )
printf '%s\n' "$L2"
PGPID=$(printf '%s\n' "$L2" | sed -n 's/^pid=\([0-9]*\)$/\1/p')
if [ -z "$PGPID" ]; then
  record "layer2-pgphoto" FAIL "pgphoto.stage2ondisk is not running"
else
  record "layer2-pgphoto" PASS "running as PID $PGPID"
fi
# A lock directory whose recorded owner is gone is the #297 deadlock: every restart
# answers "refusing to race" and exits 1, so the supervisor stays quarantined forever.
if printf '%s\n' "$L2" | grep -q 'lock_owner_alive=no'; then
  record "layer2-restart-lock" FAIL "stale restart lock -- pgphoto can never be restarted (issue #297)"
elif printf '%s\n' "$L2" | grep -q 'No such file'; then
  record "layer2-restart-lock" PASS "no restart lock held"
elif printf '%s\n' "$L2" | grep -q 'lock_owner_alive=yes'; then
  record "layer2-restart-lock" UNKNOWN "restart lock held by a live pid -- a restart is in flight"
else
  record "layer2-restart-lock" UNKNOWN "could not read the restart lock state"
fi

# Quarantine is the supervisor's own degraded state (#119). Counting the lines is the
# cheapest signal that it is stuck rather than merely having happened once.
LQ=$(dsh 'grep -a -c "remaining degraded (issue #119)" /app/Clog.txt 2>/dev/null || echo 0')
LQ=${LQ//[^0-9]/}; LQ=${LQ:-0}
if [ "$LQ" -gt 0 ]; then
  record "layer2-quarantine" FAIL "$LQ 'remaining degraded' lines -- supervisor is quarantining the camera"
else
  record "layer2-quarantine" PASS "no quarantine lines in /app/Clog.txt"
fi

# ---------------------------------------------------------------------------
# LAYER 3: did a session actually open? This is the layer that was never checked.
# ---------------------------------------------------------------------------
CAMLIB_MISSING=0
hr "layer 3: camera session (camlib + USB handle)"
if [ -z "${PGPID:-}" ]; then
  record "layer3-camlib" UNKNOWN "no pgphoto process to inspect"
else
  L3=$(dsh "P=\$(ps 2>/dev/null | grep pgphoto.stage2ondisk | grep -v grep | awk '{print \$1}' | head -1); echo '--- mapped camlibs/port drivers ---'; grep -oE '/[^ ]*(pentax|ptp2|usb1)\.so' /proc/\$P/maps 2>/dev/null | sort -u; echo '--- usb fds ---'; ls -l /proc/\$P/fd 2>/dev/null | grep -cE 'bus/usb'; echo '--- sockets ---'; ls -l /proc/\$P/fd 2>/dev/null | grep -c socket")
  printf '%s\n' "$L3"
  CAMLIB=$(printf '%s\n' "$L3" | sed -n '/mapped camlibs/,/usb fds/p' | grep -E '\.so$' | head -3)
  USBFD=$(printf '%s\n' "$L3" | sed -n 's/^--- usb fds ---//p;/^[0-9]*$/p' | tr -d ' \n' | head -c4)
  if [ -n "$CAMLIB" ]; then
    record "layer3-camlib" PASS "camlib mapped: $(printf '%s' "$CAMLIB" | tr '\n' ' ')"
  else
    # Verdict deferred to after layer 4. libgphoto2 loads a camlib .so when it builds its
    # abilities list during gp_camera_init/autodetect, so "no camlib mapped" means no
    # session has been opened since this process started. Whether that is a fault depends
    # on whether anything asked: pgphoto may initialise lazily on the first client request,
    # in which case an idle device looks exactly like this. Recorded as UNKNOWN with no
    # client, FAIL with a client connected and still nothing loaded.
    CAMLIB_MISSING=1
  fi
fi

# ---------------------------------------------------------------------------
# LAYER 4: is anything actually talking to pgphoto?
# ---------------------------------------------------------------------------
hr "layer 4: client connection to pgphoto (:8080)"
# pgphoto is the SERVER on :8080, so an established row carries 1F90 in the LOCAL column
# ($2), not the remote one. The first version of this filter matched only $3 and therefore
# always reported zero -- measured against a live stream request that had two connections
# open: `$3 ~ /:1F90$/` gave 0, `($2 ~ /:1F90$/ || $3 ~ /:1F90$/)` gave 2. Under-reporting
# here also forced layer 3 down its "no client" branch, so the tool was saying UNKNOWN where
# the truth was FAIL.
L4=$(dsh 'P=$(ps 2>/dev/null | grep pgphoto.stage2ondisk | grep -v grep | awk "{print \$1}" | head -1); INODE=$(ls -l /proc/$P/fd 2>/dev/null | grep -oE "socket:\[[0-9]+\]" | tr -dc 0-9); echo "pgphoto_inode=${INODE:-none}"; awk -v ino="$INODE" "\$10==ino {print \"listening_on=\"\$2}" /proc/net/tcp; echo "established_to_8080=$(awk "\$4==\"01\" && (\$2 ~ /:1F90\$/ || \$3 ~ /:1F90\$/)" /proc/net/tcp | wc -l)"')
printf '%s\n' "$L4"
EST=$(printf '%s\n' "$L4" | sed -n 's/^established_to_8080=\([0-9]*\)$/\1/p')
if [ -z "$EST" ]; then
  record "layer4-client" UNKNOWN "could not read /proc/net/tcp"
elif [ "$EST" -gt 0 ]; then
  record "layer4-client" PASS "$EST established connection(s) to :8080"
else
  # Deliberately UNKNOWN, not FAIL. polaris-httpd opens a connection to :8080 on demand,
  # when it needs the live-view stream (polaris-httpd.c: sa.sin_port = htons(8080) then
  # "GET /?action=stream HTTP/1.0"). It is not a persistent poll, so with no app or browser
  # attached zero connections is the expected idle state and proves nothing about health.
  # The TA's report on #297 recorded opcode 286 repeating state:-110 at 23:58Z; this
  # snapshot is ~01:36Z and shows no client. Different times, so neither contradicts the
  # other. Attach Benro Connect or open the WebUI and re-run to distinguish idle from broken.
  record "layer4-client" UNKNOWN "no client on :8080 right now -- httpd connects on demand for the stream, so idle is indistinguishable from a broken path; attach an app and re-run"
fi

# Layer 3 verdict, deferred until layer 4 tells us whether anything asked for a session.
if [ "${CAMLIB_MISSING:-0}" = "1" ]; then
  if [ -n "$EST" ] && [ "$EST" -gt 0 ]; then
    record "layer3-camlib" FAIL "a client is connected but no pentax.so/ptp2.so is mapped -- gp_camera_init did not load a camlib"
  else
    record "layer3-camlib" UNKNOWN "no camlib mapped and no client on :8080 -- consistent with lazy init while idle; re-run with an app attached to tell this apart from a real fault"
  fi
fi

# ---------------------------------------------------------------------------
# LAYER 5: what the application publishes
# ---------------------------------------------------------------------------
hr "layer 5: published camera identity"
# ASCOM Alpaca routes, read from container/astro/polaris-httpd.c: /api/v1/camera/0/<query>.
# The earlier guesses (/status, /camera) return "not found" -- they are not routes this
# server has. Only read-only queries are used; the POST-only guard list in polaris-httpd.c
# (/api/astro/capture, /api/stop, ...) is never touched.
ALPACA_PARAMS="ClientTransactionID=1&ClientName=camera-layer-report&DeviceNumber=0&TransID=1"
L5=""
if command -v curl >/dev/null 2>&1; then
  for path in description camerastate; do
    body=$(timeout 12 curl -sS --max-time 10 -A 'VSCode-LMStudio-Bridge' \
      "$WEBUI/api/v1/camera/0/$path?$ALPACA_PARAMS" 2>/dev/null | head -c 600)
    L5="${L5}== /api/v1/camera/0/${path} ==
${body}
"
  done
fi
printf '%s\n' "$L5" | sed '/^$/d'

STATE=$(printf '%s\n' "$L5" | sed -n '/camerastate/,/^== /p' | grep -oE '"Value":[0-9]+' | head -1 | cut -d: -f2)
if [ -z "$STATE" ]; then
  # Unreachable WebUI is a measurement gap, not evidence about the camera. Recorded as
  # UNKNOWN so nobody reads "could not probe" as "probe said broken".
  record "layer5-published" UNKNOWN "no CameraState from $WEBUI -- re-run from a host that can reach it"
else
  # ASCOM CameraState: 0 Disconnected, 1 DisconnectedPrepare, 2 Connecting, 3 Connected.
  # Anything else is a value this build does not document, so it is reported rather than
  # guessed at.
  say "CameraState=$STATE (ASCOM: 0=Disconnected 1=DisconnectedPrepare 2=Connecting 3=Connected)"
  case "$STATE" in
    3) record "layer5-published" PASS "CameraState=Connected -- identity is reaching the application" ;;
    0) record "layer5-published" FAIL "CameraState=Disconnected -- no camera session is published to the app" ;;
    1|2) record "layer5-published" UNKNOWN "CameraState=$STATE -- mid-handshake, re-run after it settles" ;;
    *) record "layer5-published" UNKNOWN "unrecognised CameraState=$STATE -- not a documented value for this build" ;;
  esac
fi

hr "verdict"
say "PASS=$VERDICT_PASS FAIL=$VERDICT_FAIL UNKNOWN=$VERDICT_UNKNOWN"
if [ "$VERDICT_FAIL" -gt 0 ]; then
  say "RESULT: at least one layer FAILED -- see the [FAIL] lines above for which one."
  say "Do not record recognition as working. Do not close #297 from this report alone."
  exit 1
elif [ "$VERDICT_UNKNOWN" -gt 0 ]; then
  say "RESULT: incomplete -- some layers could not be measured. Not a pass."
  say "UNKNOWN is not PASS. Fix the measurement gap (usually WebUI reachability) and re-run."
  exit 2
fi
say "RESULT: every measured layer passed. Recognition is still not DEVICE_VERIFIED until"
say "this ran against the exact installed candidate and was reviewed independently (#297)."
exit 0
