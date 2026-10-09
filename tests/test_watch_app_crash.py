from __future__ import annotations

import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
WATCHER = ROOT / "scripts" / "watch-app-crash.sh"


def _install_fake_commands(bin_dir: Path) -> None:
    ssh = bin_dir / "ssh"
    ssh.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
while [ "${1:-}" = "-o" ]; do shift 2; done
[ "$#" -ge 2 ] || exit 64
host=$1
shift
command=$*
printf '%s\\n' "$command" >> "$WATCH_SSH_TRACE"
case "$command" in
  'cat /app/FwVer') printf 'FwVer:6.0.0.54.62;date:2026.10.09;\\n' ;;
  'lsusb | grep -icE "05a9|25fb"')
    count=$(cat "$WATCH_POLL_STATE" 2>/dev/null || echo 0)
    count=$((count + 1))
    printf '%s' "$count" > "$WATCH_POLL_STATE"
    if [ "$count" -eq 1 ]; then printf '0\\n'; else printf '1\\n'; fi
    ;;
  *'== device time / firmware =='*)
    printf 'DEVICE_SNAPSHOT\nFwVer:6.0.0.54.62;date:2026.10.09;\n'
    ;;
  *) echo "unexpected fake ssh command: $command" >&2; exit 65 ;;
esac
""",
        encoding="utf-8",
    )
    ssh.chmod(0o755)

    iw = bin_dir / "iw"
    iw.write_text(
        "#!/usr/bin/env bash\nprintf '%s\\n' 'Connected to 48:e7:da:d4:b5:73 (on wlp8s0)' ' SSID: polaris_d13e86'\n",
        encoding="utf-8",
    )
    iw.chmod(0o755)

    ip = bin_dir / "ip"
    ip.write_text(
        "#!/usr/bin/env bash\nprintf '%s\\n' '192.168.0.1 dev wlp8s0 src 192.168.0.4'\n",
        encoding="utf-8",
    )
    ip.chmod(0o755)

    python3 = bin_dir / "python3"
    python3.write_text(
        "#!/usr/bin/env bash\nprintf 'APP_BURST_OUTPUT\\n'\n",
        encoding="utf-8",
    )
    python3.chmod(0o755)


def _run_watcher(tmp_path: Path, replay: str) -> str:
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
            "WATCH_MAX_POLLS": "3",
            "WATCH_REPLAY": replay,
            "WATCH_SSH_TRACE": str(tmp_path / f"ssh-{replay}.trace"),
            "WATCH_POLL_STATE": str(tmp_path / f"poll-{replay}.state"),
        }
    )
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
