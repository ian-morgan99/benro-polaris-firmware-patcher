from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tarfile


ROOT = Path(__file__).resolve().parents[1]
PULL_SCRIPT = ROOT / "scripts" / "pull-mlog-clog.sh"


def _fake_ssh(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
while [ \"${1:-}\" = \"-o\" ]; do shift 2; done
[ \"$#\" -ge 2 ] || exit 64
host=$1
shift
command=$*
root=${FAKE_DEVICE_ROOT:?}
case \"$command\" in
  'cat /app/FwVer; ls /app/bin/polestar_app /app/bin/pgphoto')
    printf 'FwVer:6.0.0.54.62;date:2026.10.09;\\n/app/bin/polestar_app\\n/app/bin/pgphoto\\n'
    ;;
  'cat /app/Mlog.txt') cat \"$root/app/Mlog.txt\" ;;
  'cat /app/Clog.txt') cat \"$root/app/Clog.txt\" ;;
  'ls -la /app/sd') printf 'FwPkt\\n' ;;
  *'== identity =='*)
    printf '== identity ==\\nFwVer:6.0.0.54.62\\nLinux polaris\\nup 1 day\\n'
    printf '== provenance ==\\ngit_commit=test\\n== processes ==\\npgphoto\\n'
    printf '== mounts (SD card) ==\\n/dev/mmcblk0p1 /app/sd vfat\\n== sd root ==\\nFwPkt\\n'
    ;;
  'test -d /app/sd/system/log') test -d \"$root/app/sd/system/log\" ;;
  *'cd /app/sd/system/log'*'tar czf -'*)
    tar czf - -C \"$root/app/sd/system/log\" .
    ;;
  *) echo \"unexpected fake ssh command: $command\" >&2; exit 65 ;;
esac
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def test_pull_script_streams_logs_and_current_tails_without_remote_stage(tmp_path):
    device = tmp_path / "device"
    log_dir = device / "app/sd/system/log"
    (device / "app/bin").mkdir(parents=True)
    log_dir.mkdir(parents=True)
    (device / "app/Mlog.txt").write_text("live mlog\n", encoding="utf-8")
    (device / "app/Clog.txt").write_text("live clog\n", encoding="utf-8")
    (log_dir / "Mlog_000274.log").write_text("rotated mlog\n", encoding="utf-8")
    (log_dir / "Clog_000274.log").write_text("rotated clog\n", encoding="utf-8")
    (log_dir / "error_000274.log").write_text("error log\n", encoding="utf-8")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _fake_ssh(fake_bin / "ssh")
    out = tmp_path / "out"
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["FAKE_DEVICE_ROOT"] = str(device)

    result = subprocess.run(
        [str(PULL_SCRIPT), "root@polaris", str(out)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=15,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    archives = list(out.glob("polaris-logs-*.tar.gz"))
    assert len(archives) == 1
    with tarfile.open(archives[0], "r:gz") as archive:
        members = set(archive.getnames())
        assert any(name.endswith("meta.txt") for name in members)
        assert any(name.endswith("Mlog-current.txt") for name in members)
        assert any(name.endswith("Clog-current.txt") for name in members)
        assert any(name.endswith("system-log/Mlog_000274.log") for name in members)
        assert any(name.endswith("system-log/Clog_000274.log") for name in members)
        assert any(name.endswith("system-log/error_000274.log") for name in members)
        current_mlog = next(n for n in members if n.endswith("Mlog-current.txt"))
        assert archive.extractfile(current_mlog).read() == b"live mlog\n"
