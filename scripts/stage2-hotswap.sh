#!/usr/bin/env bash
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
        [ -f "$NEW" ] || { echo "no such file: $NEW" >&2; exit 1; }
        echo "local md5:  $(md5sum "$NEW" | cut -d' ' -f1)"
        # Back up once. Never let a second push overwrite the pristine backup,
        # otherwise rollback stops being able to restore the shipped loader.
        $SSH "[ -f $BAK ] || cp -a $LIVE $BAK; md5sum $BAK"
        cat "$NEW" | $SSH "cat > $LIVE.new && chmod 755 $LIVE.new && mv $LIVE.new $LIVE && md5sum $LIVE"
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
