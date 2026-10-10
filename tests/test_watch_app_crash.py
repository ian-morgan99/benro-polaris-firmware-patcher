from __future__ import annotations

import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
WATCHER = ROOT / "scripts" / "watch-app-crash.sh"

# The fakes are scripted per poll, not per call: the fake `sleep` advances a tick
# and every probe resolves its behaviour from that tick. A plan string is one
# token per poll, so "ok down ok" means poll 1 healthy, poll 2 unreachable, poll
# 3 recovered. The identity check shares poll 1's token (it runs before the loop
# at the same tick) and is therefore always expected to be "ok".
_SSH_FAKE = """#!/usr/bin/env bash
set -euo pipefail
while [ "${1:-}" = "-o" ]; do shift 2; done
[ "$#" -ge 2 ] || exit 64
host=$1
shift
command=$*
printf '%s\\n' "$command" >> "$WATCH_SSH_TRACE"
tick=$(cat "$WATCH_TICK" 2>/dev/null || echo 0)
state="ok"
if [ -n "${WATCH_SSH_PLAN:-}" ]; then
  state=$(printf '%s\\n' "$WATCH_SSH_PLAN" | awk -v n="$((tick + 1))" '{print $n}')
fi
case "$state" in down) exit 255 ;; esac
case "$command" in
  'cat /app/FwVer') printf 'FwVer:6.0.0.54.62;date:2026.10.09;\\n' ;;
  'lsusb | grep -icE "05a9|25fb"')
    count=$(cat "$WATCH_POLL_STATE" 2>/dev/null || echo 0)
    count=$((count + 1))
    printf '%s' "$count" > "$WATCH_POLL_STATE"
    if [ "$count" -eq 1 ]; then printf '0\\n'; else printf '1\\n'; fi
    ;;
  *'DRIVER_COUNTERS'*) printf 'DRIVER_COUNTERS psh=936 disc=935\\n' ;;
  *'== device time / firmware =='*)
    printf 'DEVICE_SNAPSHOT\\nFwVer:6.0.0.54.62;date:2026.10.09;\\n'
    printf 'tdata_psh_info=936 tdata_disc_grp=935\\n'
    ;;
  *) echo "unexpected fake ssh command: $command" >&2; exit 65 ;;
esac
"""

_IW_FAKE = """#!/usr/bin/env bash
tick=$(cat "$WATCH_TICK" 2>/dev/null || echo 0)
state="ok"
if [ -n "${WATCH_IW_PLAN:-}" ]; then
  state=$(printf '%s\\n' "$WATCH_IW_PLAN" | awk -v n="$((tick + 1))" '{print $n}')
fi
case "$state" in
  ok) printf '%s\\n' 'Connected to 48:e7:da:d4:b5:73 (on wlp8s0)' ' SSID: polaris_d13e86' ;;
  *) printf '%s\\n' 'Not connected.' ;;
esac
"""

# Issue #170 trap: the home router answers 192.168.0.1 over Ethernet, so the
# route's outgoing interface is the only proof the answer came from the Polaris.
_IP_FAKE = """#!/usr/bin/env bash
tick=$(cat "$WATCH_TICK" 2>/dev/null || echo 0)
dev="wlp8s0"
if [ -n "${WATCH_ROUTE_PLAN:-}" ]; then
  dev=$(printf '%s\\n' "$WATCH_ROUTE_PLAN" | awk -v n="$((tick + 1))" '{print $n}')
fi
printf '%s\\n' "192.168.0.1 dev ${dev} src 192.168.0.4"
"""

# A device that is not answering at all fails ICMP too, so the ping fake follows
# the device plan unless a test overrides it to model "reachable, service down".
_PING_FAKE = """#!/usr/bin/env bash
tick=$(cat "$WATCH_TICK" 2>/dev/null || echo 0)
src=${WATCH_PING_PLAN:-${WATCH_SSH_PLAN:-}}
state="up"
if [ -n "$src" ]; then
  state=$(printf '%s\\n' "$src" | awk -v n="$((tick + 1))" '{print $n}')
fi
case "$state" in down) exit 1 ;; esac
"""

_SLEEP_FAKE = """#!/usr/bin/env bash
tick=$(cat "$WATCH_TICK" 2>/dev/null || echo 0)
printf '%s' "$((tick + 1))" > "$WATCH_TICK"
"""


def _install_fake_commands(bin_dir: Path) -> None:
    for name, body in (
        ("ssh", _SSH_FAKE),
        ("iw", _IW_FAKE),
        ("ip", _IP_FAKE),
        ("ping", _PING_FAKE),
        ("sleep", _SLEEP_FAKE),
    ):
        tool = bin_dir / name
        tool.write_text(body, encoding="utf-8")
        tool.chmod(0o755)
    python3 = bin_dir / "python3"
    python3.write_text("#!/usr/bin/env bash\nprintf 'APP_BURST_OUTPUT\\n'\n", encoding="utf-8")
    python3.chmod(0o755)


def _run_watcher(tmp_path: Path, replay: str, polls: int = 3, **plan: str) -> str:
    bin_dir = tmp_path / f"bin-{replay}"
    bin_dir.mkdir()
    _install_fake_commands(bin_dir)
    out = tmp_path / f"watch-{replay}.log"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}{os.pathsep}{env['PATH']}",
            "POLARIS_SSH": "root@polaris",
            "WATCH_INTERVAL": "0",
            "WATCH_MAX_POLLS": str(polls),
            "WATCH_REPLAY": replay,
            "WATCH_SSH_TRACE": str(tmp_path / f"ssh-{replay}.trace"),
            "WATCH_POLL_STATE": str(tmp_path / f"poll-{replay}.state"),
            "WATCH_TICK": str(tmp_path / f"tick-{replay}.state"),
        }
    )
    env.update(plan)
    result = subprocess.run(
        [str(WATCHER), str(out)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return out.read_text(encoding="utf-8")


def test_watcher_snapshots_native_logs_before_optional_replay(tmp_path):
    output = _run_watcher(tmp_path, replay="1")

    pre = output.index("device snapshot: before diagnostic replay")
    pre_data = output.index("DEVICE_SNAPSHOT", pre)
    replay = output.index("separate host app-burst replay")
    replay_data = output.index("APP_BURST_OUTPUT", replay)
    post = output.index("device snapshot: after diagnostic replay")
    post_data = output.index("DEVICE_SNAPSHOT", post)
    assert pre < pre_data < replay < replay_data < post < post_data
    assert "watch stop: reached WATCH_MAX_POLLS=3" in output


def test_watcher_does_not_replay_diagnostics_by_default(tmp_path):
    output = _run_watcher(tmp_path, replay="0")

    assert "device snapshot: before diagnostic replay" in output
    assert "APP_BURST_OUTPUT" not in output
    assert "device snapshot: after diagnostic replay" not in output


def test_snapshot_carries_the_driver_counters(tmp_path):
    # The #171 counters have to be inside the same record as the crash evidence.
    output = _run_watcher(tmp_path, replay="0")

    snap = output.index("device snapshot: before diagnostic replay")
    assert "tdata_psh_info=936 tdata_disc_grp=935" in output[snap:]


def test_transport_loss_is_attributed_not_recorded_as_camera_state(tmp_path):
    # The #187 misreading: a failed SSH used to be logged as
    # "CAMERA_STATE change: 1 -> ?", which made a transport loss look like a
    # camera observation. It must be a link-state event instead.
    output = _run_watcher(tmp_path, replay="0", WATCH_SSH_PLAN="ok down down")

    assert "LINK_STATE change: OK -> DEVICE_UNREACHABLE" in output
    camera_lines = [ln for ln in output.splitlines() if "CAMERA_STATE change" in ln]
    assert camera_lines == [ln for ln in camera_lines if "-> 0" in ln]
    assert len(camera_lines) == 1


def test_camera_is_not_polled_while_the_link_is_down(tmp_path):
    # No camera query may be issued against a device that is not answering.
    _run_watcher(tmp_path, replay="0", WATCH_SSH_PLAN="ok down down")

    trace = (tmp_path / "ssh-0.trace").read_text(encoding="utf-8")
    # One camera query (the healthy first poll) and no counter sampling, because
    # the link never came back inside the window.
    assert len([ln for ln in trace.splitlines() if "lsusb" in ln]) == 1
    assert len([ln for ln in trace.splitlines() if "DRIVER_COUNTERS" in ln]) == 0


def test_service_down_is_distinguished_from_data_path_loss(tmp_path):
    # ICMP answering while SSH does not is the control-liveness.py "refused"
    # signature, not a lost radio path.
    output = _run_watcher(
        tmp_path, replay="0", WATCH_SSH_PLAN="ok down down", WATCH_PING_PLAN="up up up"
    )

    assert "LINK_STATE change: OK -> DEVICE_SSH_DOWN" in output
    assert "DEVICE_UNREACHABLE" not in output


def test_host_side_deauth_is_reported_as_link_loss_with_reason(tmp_path):
    # A host-side deauth must not be blamed on the device.
    output = _run_watcher(tmp_path, replay="0", WATCH_IW_PLAN="ok lost ok")

    assert "LINK_STATE change: OK -> LINK_LOSS_HOST" in output
    assert "reason=no verified Polaris BSSID" in output
    assert "DEVICE_UNREACHABLE" not in output


def test_route_off_the_wifi_interface_is_link_loss_not_reachability(tmp_path):
    # Issue #170: the home router answers 192.168.0.1 over Ethernet, so a route
    # that left the Wi-Fi interface must never be read as "the Polaris is up".
    output = _run_watcher(tmp_path, replay="0", WATCH_ROUTE_PLAN="wlp8s0 enp11s0 wlp8s0")

    assert "LINK_STATE change: OK -> LINK_LOSS_HOST" in output
    assert "reason=route to 192.168.0.1 uses 'enp11s0', not wlp8s0" in output


def test_driver_counters_are_sampled_on_recovery(tmp_path):
    # Issue #171's counters must be captured inside the failure window; sampling
    # only from a separate camera-off run is what left the correlation unprovable.
    output = _run_watcher(tmp_path, replay="0", WATCH_SSH_PLAN="ok down ok")

    recovered = output.index("LINK_STATE change: DEVICE_UNREACHABLE -> OK")
    counters = output.index("DRIVER_COUNTERS", recovered)
    assert recovered < counters


def test_camera_is_reobserved_after_recovery(tmp_path):
    # Forcing re-observation means the first post-recovery poll is a fresh
    # reading, and a camera-present device is snapshotted again.
    output = _run_watcher(tmp_path, replay="0", WATCH_SSH_PLAN="ok down ok")

    recovered = output.index("LINK_STATE change: DEVICE_UNREACHABLE -> OK")
    resnapshot = output.index("device snapshot: before diagnostic replay", recovered)
    assert recovered < resnapshot
