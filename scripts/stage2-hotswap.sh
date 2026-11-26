#!/usr/bin/env bash
# HOT-SWAP IS NOT A DEPLOYMENT PATH — see AGENTS.md "HARD RULE — never build on device; deploy only
# by zip and flash". Nothing is built or installed on the head. The only sanctioned way to change what
# runs there is a workstation-built zip/FwPkt, flashed, cold-rebooted and identity-verified. `push`
# copies a locally built loader into /app and relaunches pgphoto by hand; that process is not
# attributable to any registered build, invalidates qualification evidence, and bypasses the wrapper's
# pidfile/launch-lock/crash-backoff. Use `status` (read-only) freely; use `push` only with explicit
# operator approval for one specific diagnostic, then reboot to restore the read-only image.
#
# Hot-swap the Stage-2 loader on a live Polaris head without reflashing.
#
# The camera admission gate lives entirely in libpolaris_stage2.so, which pgphoto
# loads via LD_PRELOAD. pgphoto itself is untouched, so a loader rebuild can be
# verified on real hardware in seconds instead of a full flash cycle. This is a
# development accelerator only: the shipped artifact is still a flashed FwPkt, and
# a reboot restores whatever is in the read-only image.
#
#   stage2-hotswap.sh push <loader.so>   -- back up, install, restart pgphoto
#   stage2-hotswap.sh rollback           -- restore the backup and restart
#
# Identity gate: push refuses any artifact whose md5 is not registered in
# docs/component-identity.json. On 2026-11-26 a locally built loader was installed while the
# head still reported FwVer 6.0.0.54.117, and nothing could detect it -- the release record
# carries no component hashes -- so A/B results were attributed to the wrong build. An
# unregistered artifact is an unattributable one; pass --allow-unregistered only when that is
# understood and intended.
#   stage2-hotswap.sh status             -- which loader is live, and its hash
set -euo pipefail

HOST="${STAGE2_HOST:-root@192.168.0.1}"
DIR="/app/lib/stage2"
LIVE="$DIR/libpolaris_stage2.so"
BAK="$DIR/libpolaris_stage2.so.pre-hotswap"
SSH="ssh -o BatchMode=yes -o ConnectTimeout=25 $HOST"

restart_pgphoto() {
    # The supervisor only restarts pgphoto on a USB identity change, so a killed
    # process is not respawned -- it has to be relaunched through the wrapper,
    # which re-exports LD_PRELOAD and the STAGE2_* environment.
    #
    # The wrapper guards itself with a pidfile, a launch lock and a crash-backoff
    # file. Killing pgphoto leaves all three behind, and a naive relaunch then
    # either refuses ("already owned by PID n") or races a second launcher, which
    # yields two unbound instances that never open the camera node. So: stop every
    # instance, clear the three pieces of stale state, then launch exactly once and
    # require that the survivor has actually bound the camera.
    $SSH 'set -e
      RUN=/var/run/openpolaris-pgphoto
      real_pgphotos() {
          for p in $(ls /proc | grep -E "^[0-9]+$"); do
              [ "$(readlink /proc/$p/exe 2>/dev/null)" = "/app/lib/stage2/pgphoto.stage2ondisk" ] && echo "$p"
          done
      }
      for p in $(real_pgphotos); do kill "$p" 2>/dev/null || true; done
      sleep 3
      for p in $(real_pgphotos); do kill -9 "$p" 2>/dev/null || true; done
      sleep 1
      rm -rf "$RUN.pid" "$RUN.launch.lock" "$RUN.backoff" /var/run/openpolaris-pgphoto.pid \
             /var/run/openpolaris-pgphoto.launch.lock /var/run/openpolaris-pgphoto.backoff
      cd /app && setsid nohup /app/bin/pgphoto >/tmp/pgphoto-hotswap.log 2>&1 < /dev/null &
      sleep 12
      # pgrep -f self-matches this very command string, so count by exe path.
      N=$(real_pgphotos | wc -l)
      P=$(real_pgphotos | head -1)
      BOUND=0
      [ -n "$P" ] && BOUND=$(ls -l /proc/$P/fd 2>/dev/null | grep -c "bus/usb" || true)
      echo "instances=$N pid=${P:-NONE} usb_fds=$BOUND"'
}

case "${1:-}" in
    status)
        $SSH "md5sum $LIVE; ls -la $LIVE; [ -f $BAK ] && md5sum $BAK || echo '(no backup)'"
        ;;
    push)
        NEW="${2:?usage: stage2-hotswap.sh push <loader.so>}"
        ALLOW="${3:-}"
        [ -f "$NEW" ] || { echo "no such file: $NEW" >&2; exit 1; }
        LOCAL_MD5="$(md5sum "$NEW" | cut -d' ' -f1)"
        echo "local md5:  $LOCAL_MD5"

        # Identity gate. Refuse bytes that belong to no recorded build: the head keeps
        # reporting its package FwVer no matter which loader is preloaded, so an
        # unregistered artifact silently mislabels every result taken afterwards.
        REG="$(cd "$(dirname "$0")/.." && pwd)/docs/component-identity.json"
        LABEL="unknown"
        if [ -f "$REG" ]; then
            LABEL="$(LOCAL_MD5="$LOCAL_MD5" REG="$REG" python3 - <<'PY'
import json, os
reg = json.loads(open(os.environ["REG"]).read())
for art in reg["components"]["libpolaris_stage2.so"]["artifacts"]:
    if art["md5"] == os.environ["LOCAL_MD5"]:
        print("%s [%s]" % (art["label"], art["status"]))
        break
else:
    print("UNREGISTERED")
PY
)"
            echo "identity:   $LABEL"
            # Patterns must be anchored at both ends: the label is "name [STATUS]", so an
            # unanchored DIAGNOSTIC-NEVER-SHIP* never matched and a diagnostic build installed.
            case "$LABEL" in
                *UNREGISTERED*|*DIAGNOSTIC-NEVER-SHIP*)
                    if [ "$ALLOW" != "--allow-unregistered" ]; then
                        echo "REFUSED: $LABEL"
                        echo "  Registered builds live in docs/component-identity.json. Either rebuild a"
                        echo "  registered source, add an entry with its commit, or pass"
                        echo "  --allow-unregistered to accept that this session's results are provisional."
                        exit 1
                    fi
                    echo "WARNING: proceeding with $LABEL; results are provisional."
                    ;;
            esac
        else
            echo "WARNING: registry absent ($REG); identity cannot be verified."
        fi

        # Back up once. Never let a second push overwrite the pristine backup,
        # otherwise rollback stops being able to restore the shipped loader.
        $SSH "[ -f $BAK ] || cp -a $LIVE $BAK; md5sum $BAK"
        cat "$NEW" | $SSH "cat > $LIVE.new && chmod 755 $LIVE.new && mv $LIVE.new $LIVE && sync && md5sum $LIVE"

        # Ledger: answers 'what was running when this evidence was collected' after the fact.
        LEDGER="$(cd "$(dirname "$0")/.." && pwd)/docs/component-deploys.jsonl"
        LOCAL_MD5="$LOCAL_MD5" LABEL="$LABEL" NEW="$NEW" HOST="${HOST#root@}" python3 - <<'PY' >> "$LEDGER"
import datetime, json, os, subprocess
print(json.dumps({
    "utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "host": os.environ["HOST"],
    "component": "libpolaris_stage2.so",
    "md5": os.environ["LOCAL_MD5"],
    "label": os.environ["LABEL"],
    "source_file": os.environ["NEW"].split("/")[-1],
    "patcher_commit": subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                                     capture_output=True, text=True).stdout.strip() or None,
}))
PY
        echo "ledger:     appended docs/component-deploys.jsonl"
        echo "--- restarting pgphoto ---"
        restart_pgphoto
        ;;
    rollback)
        $SSH "[ -f $BAK ] || { echo 'no backup present' >&2; exit 1; }
              cp -a $BAK $LIVE && md5sum $LIVE"
        echo "--- restarting pgphoto ---"
        restart_pgphoto
        ;;
    *)
        echo "usage: stage2-hotswap.sh {status|push <loader.so>|rollback}" >&2
        exit 2
        ;;
esac
