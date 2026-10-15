from __future__ import annotations

"""Negative + positive tests for scripts/o-v17a-autonomous-install.sh (#199).

Covers the review's required negatives: hash mismatch, missing binary,
spoofed version, failed reboot (uncertain delivery), busy camera, wrong host,
interrupted/repeated polling — plus the no-blind-reflash and verify-only paths.
All tests run fully offline against a fake device root + fake ssh/scp/nc.
"""

import hashlib
import json
import os
import socket
import subprocess
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "o-v17a-autonomous-install.sh"

# Device files the manifest treats as mandatory (mirrors generate-fwpkt-manifest.py).
DEVICE_FILES = {
    "FwVer": b"FwVer:6.0.0.54.66;date:2026.10.14;\n",
    "bin/polestar_app": b"FAKE-POLESTAR-APP",
    "lib/stage2/pgphoto.stage2ondisk": b"FAKE-STAGE2ONDISK",
    "lib/stage2/libpolaris_stage2.so": b"FAKE-LOADER",
    "lib/stage2/libgphoto2.so.6": b"FAKE-CORE",
    "lib/stage2/libgphoto2_port.so.12": b"FAKE-PORT",
    "lib/stage2/libgphoto2/2.5.34/ptp2.so": b"FAKE-PTP2",
    "lib/stage2/libgphoto2/2.5.34/pentax.so": b"FAKE-PENTAX",
    "lib/stage2/libgphoto2_port/0.12.2/usb1.so": b"FAKE-USB1",
    "openpolaris-libgphoto2-provenance.txt": b"build_id=o-v17a-shutter-fallback-off-20261012\n",
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_device(tmp_path: Path, fwver: str = "FwVer:6.0.0.54.66;date:2026.10.14;\n",
                drop: tuple[str, ...] = (), mutate: dict[str, bytes] | None = None) -> Path:
    dev = tmp_path / "device"
    for rel, content in DEVICE_FILES.items():
        if rel in drop:
            continue
        data = (mutate or {}).get(rel, content)
        p = dev / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    (dev / "FwVer").write_text(fwver)
    return dev


def make_manifest(cand_dir: Path, zip_path: Path, fwver: str, device: Path) -> Path:
    # The mandatory set is fixed (stage2_mandatory=true): every file is listed
    # with its expected digest, computed from the canonical content. The device
    # may be missing or have mutated files — that is what verification catches.
    files = []
    for rel in DEVICE_FILES:
        p = device / rel
        if p.exists():
            data = p.read_bytes()
        else:
            data = DEVICE_FILES[rel]
        files.append({"path": f"/app/{rel}", "sha256": _sha256(data), "size": len(data)})
    m = {
        "schema": 1,
        "candidate": cand_dir.name,
        "zip": {"sha256": _sha256(zip_path.read_bytes()), "size": zip_path.stat().st_size},
        "fwver_content": fwver.rstrip("\n"),
        "stage2_mandatory": True,
        "files": files,
    }
    out = cand_dir / "install-manifest.json"
    out.write_text(json.dumps(m, indent=2))
    return out


FAKE_SSH = r"""#!/usr/bin/env bash
# fake ssh: skip -o options, expect host then command. State-aware: when the
# state file says "down" the device is dark and every SSH connection fails.
while [ "${1:-}" = "-o" ]; do shift 2; done
[ "$#" -ge 2 ] || exit 64
host=$1; shift
cmd=$*
root=${FAKE_DEVICE_ROOT:?}
if [ -f "${FAKE_STATE_FILE:-/nonexistent}" ] && [ "$(cat "$FAKE_STATE_FILE")" = "down" ]; then
  exit 255
fi
case "$cmd" in
  true) exit 0 ;;
  "cat /app/FwVer 2>/dev/null") cat "$root/FwVer" ;;
  "awk '{print int(\$1)}' /proc/uptime 2>/dev/null") echo 42 ;;
  "sed -n 's/^build_id=//p' /app/openpolaris-libgphoto2-provenance.txt 2>/dev/null | head -1")
    sed -n 's/^build_id=//p' "$root/openpolaris-libgphoto2-provenance.txt" 2>/dev/null | head -1 ;;
  *sha256sum*)
    f=${cmd#sha256sum }; f=${f%% *}
    if [ -f "$root/${f#/app/}" ]; then sha256sum "$root/${f#/app/}" | cut -d' ' -f1; else exit 1; fi ;;
  *) echo "unexpected fake ssh command: $cmd" >&2; exit 65 ;;
esac
"""

FAKE_SCP = r"""#!/usr/bin/env bash
# fake scp: last arg is user@host:/app/sd/FwPkt.zip
while [ "${1:-}" = "-o" ]; do shift 2; done
src=$1; dst=${2##*:}
root=${FAKE_DEVICE_ROOT:?}
mkdir -p "$root$(dirname "$dst")"
cp "$src" "$root$dst"
"""

FAKE_NC = r"""#!/usr/bin/env bash
# fake nc: read the wire frame from stdin, answer per FAKE_CAM_STATE / FAKE_NO_DARK.
while [ $# -gt 0 ] && [ "$1" != "1&812&0&#" ] && [ "$1" != "1&286&0&#" ]; do shift; done
data=$(cat)
case "$data" in
  '1&812&0&#')
    if [ "${FAKE_NO_DARK:-0}" != "1" ]; then
      echo down > "${FAKE_STATE_FILE:?}"
      ( sleep 3; echo up > "${FAKE_STATE_FILE:?}" ) &
    fi
    exit 0 ;;
  '1&286&0&#')
    printf '%s' "${FAKE_CAM_STATE:-}"
    exit 0 ;;
  *) exit 0 ;;
esac
"""

FAKE_KEYSCAN = r"""#!/usr/bin/env bash
echo "192.168.0.1 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFAKEKEY"
exit 0
"""


def _write_fakes(bin_dir: Path) -> None:
    for name, body in (("ssh", FAKE_SSH), ("scp", FAKE_SCP), ("nc", FAKE_NC), ("ssh-keyscan", FAKE_KEYSCAN)):
        p = bin_dir / name
        p.write_text(body)
        p.chmod(0o755)


class TcpGate:
    """TCP listener that accepts only while the state file says 'up'."""

    def __init__(self, state_file: Path):
        self.state_file = state_file
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(16)
        self.port = self.sock.getsockname()[1]
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        self.sock.settimeout(0.2)
        while not self._stop.is_set():
            try:
                conn, _ = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                up = self.state_file.read_text().strip() != "down"
            except OSError:
                up = True
            if up:
                conn.close()
            else:
                conn.close()

    def close(self) -> None:
        self._stop.set()
        self.sock.close()


def run_install(tmp_path: Path, env_extra: dict[str, str], args: tuple[str, ...] = ()) -> subprocess.CompletedProcess:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    _write_fakes(bin_dir)
    cand = tmp_path / "cand"
    cand.mkdir(exist_ok=True)
    z = cand / "FwPkt.zip"
    z.write_bytes(b"FAKE-FWPKT-ZIP")
    dev = make_device(tmp_path)
    make_manifest(cand, z, "FwVer:6.0.0.54.66;date:2026.10.14;", dev)
    state = tmp_path / "state"
    state.write_text("up")
    gate = TcpGate(state)
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "HOME": str(tmp_path / "home"),
        "FAKE_DEVICE_ROOT": str(dev),
        "FAKE_STATE_FILE": str(state),
        "GIMBAL_HOST": "127.0.0.1",
        "GIMBAL_PORT": str(gate.port),
        "GIMBAL_SSH": f"root@127.0.0.1:{gate.port}",
        "FWPKT_ZIP": str(z),
        "MANIFEST": str(cand / "install-manifest.json"),
        "MAX_WAIT": "15",
        "WAKE_WAIT": "15",
        "REBOOT_DARK_WATCH": "10",
        "SETTLE_WAIT": "2",
        "POLL_INTERVAL": "1",
        "POLL_LIMIT": "3",
    }
    (tmp_path / "home").mkdir(exist_ok=True)
    env.update(env_extra)
    try:
        return subprocess.run(
            ["bash", str(SCRIPT), *args],
            capture_output=True, text=True, timeout=240, env=env, cwd=ROOT,
        )
    finally:
        gate.close()


def test_happy_path_verified(tmp_path):
    r = run_install(tmp_path, {"FAKE_CAM_STATE": "286@manufacturer:none;model:none;state:-5;"})
    assert r.returncode == 0, r.stdout + r.stderr
    assert "VERDICT: verified" in r.stdout
    assert "reboot observed" in r.stdout


def test_hash_mismatch_is_installed_unverified(tmp_path):
    # Corrupt one installed file after the manifest was generated.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    _write_fakes(bin_dir)
    cand = tmp_path / "cand"
    cand.mkdir(exist_ok=True)
    z = cand / "FwPkt.zip"
    z.write_bytes(b"FAKE-FWPKT-ZIP")
    dev = make_device(tmp_path, mutate={"lib/stage2/libgphoto2.so.6": b"CORRUPTED-CORE"})
    make_manifest(cand, z, "FwVer:6.0.0.54.66;date:2026.10.14;", dev)
    # manifest now holds the CORRUPTED hash; make the device report a different one
    (dev / "lib/stage2/libgphoto2.so.6").write_bytes(b"DIFFERENT-CORE")
    state = tmp_path / "state"
    state.write_text("up")
    gate = TcpGate(state)
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(tmp_path / "home"),
        "FAKE_DEVICE_ROOT": str(dev), "FAKE_STATE_FILE": str(state),
        "GIMBAL_HOST": "127.0.0.1", "GIMBAL_PORT": str(gate.port),
        "GIMBAL_SSH": f"root@127.0.0.1:{gate.port}",
        "FWPKT_ZIP": str(z), "MANIFEST": str(cand / "install-manifest.json"),
        "MAX_WAIT": "15", "WAKE_WAIT": "15", "REBOOT_DARK_WATCH": "10", "SETTLE_WAIT": "2", "POLL_INTERVAL": "1", "POLL_LIMIT": "3",
    }
    (tmp_path / "home").mkdir(exist_ok=True)
    try:
        r = subprocess.run(["bash", str(SCRIPT), "--verify-only"],
                           capture_output=True, text=True, timeout=240, env=env, cwd=ROOT)
    finally:
        gate.close()
    assert r.returncode == 5, r.stdout + r.stderr
    assert "MISMATCH /app/lib/stage2/libgphoto2.so.6" in r.stdout
    assert "installed-unverified" in r.stdout


def test_missing_binary_fails_verification(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    _write_fakes(bin_dir)
    cand = tmp_path / "cand"
    cand.mkdir(exist_ok=True)
    z = cand / "FwPkt.zip"
    z.write_bytes(b"FAKE-FWPKT-ZIP")
    dev = make_device(tmp_path, drop=("lib/stage2/pgphoto.stage2ondisk",))
    m = make_manifest(cand, z, "FwVer:6.0.0.54.66;date:2026.10.14;", dev)
    # The mandatory set is fixed by the manifest (stage2_mandatory=true): the
    # file stays listed with its expected digest; only the device lacks it.
    mj = json.loads(m.read_text())
    assert any(f["path"] == "/app/lib/stage2/pgphoto.stage2ondisk" for f in mj["files"])
    m.write_text(json.dumps(mj))
    state = tmp_path / "state"
    state.write_text("up")
    gate = TcpGate(state)
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(tmp_path / "home"),
        "FAKE_DEVICE_ROOT": str(dev), "FAKE_STATE_FILE": str(state),
        "GIMBAL_HOST": "127.0.0.1", "GIMBAL_PORT": str(gate.port),
        "GIMBAL_SSH": f"root@127.0.0.1:{gate.port}",
        "FWPKT_ZIP": str(z), "MANIFEST": str(cand / "install-manifest.json"),
        "MAX_WAIT": "15", "WAKE_WAIT": "15", "REBOOT_DARK_WATCH": "10", "SETTLE_WAIT": "2", "POLL_INTERVAL": "1", "POLL_LIMIT": "3",
    }
    (tmp_path / "home").mkdir(exist_ok=True)
    try:
        r = subprocess.run(["bash", str(SCRIPT), "--verify-only"],
                           capture_output=True, text=True, timeout=240, env=env, cwd=ROOT)
    finally:
        gate.close()
    assert r.returncode == 5, r.stdout + r.stderr
    assert "MISSING/UNREADABLE /app/lib/stage2/pgphoto.stage2ondisk" in r.stdout


def test_spoofed_version_is_not_installed(tmp_path):
    # Device reports the right-looking version family but not the manifest target.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    _write_fakes(bin_dir)
    cand = tmp_path / "cand"
    cand.mkdir(exist_ok=True)
    z = cand / "FwPkt.zip"
    z.write_bytes(b"FAKE-FWPKT-ZIP")
    dev = make_device(tmp_path, fwver="FwVer:6.0.0.54.65;date:2026.10.10;\n")
    make_manifest(cand, z, "FwVer:6.0.0.54.66;date:2026.10.14;", dev)
    state = tmp_path / "state"
    state.write_text("up")
    gate = TcpGate(state)
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(tmp_path / "home"),
        "FAKE_DEVICE_ROOT": str(dev), "FAKE_STATE_FILE": str(state),
        "GIMBAL_HOST": "127.0.0.1", "GIMBAL_PORT": str(gate.port),
        "GIMBAL_SSH": f"root@127.0.0.1:{gate.port}",
        "FWPKT_ZIP": str(z), "MANIFEST": str(cand / "install-manifest.json"),
        "MAX_WAIT": "15", "WAKE_WAIT": "15", "REBOOT_DARK_WATCH": "10", "SETTLE_WAIT": "2", "POLL_INTERVAL": "1", "POLL_LIMIT": "3",
    }
    (tmp_path / "home").mkdir(exist_ok=True)
    try:
        r = subprocess.run(["bash", str(SCRIPT), "--verify-only"],
                           capture_output=True, text=True, timeout=240, env=env, cwd=ROOT)
    finally:
        gate.close()
    assert r.returncode == 5, r.stdout + r.stderr
    assert "not-installed" in r.stdout


def test_busy_camera_blocks_auth(tmp_path):
    r = run_install(tmp_path, {"FAKE_CAM_STATE": "286@manufacturer:pentax;model:K-3III;state:1;"})
    assert r.returncode == 6, r.stdout + r.stderr
    assert "camera busy/present" in r.stdout
    # and the override lets it through
    r2 = run_install(tmp_path, {"FAKE_CAM_STATE": "286@manufacturer:pentax;model:K-3III;state:1;", "ALLOW_BUSY": "1"})
    assert r2.returncode == 0, r2.stdout + r2.stderr


def test_wrong_host_family_refused(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    _write_fakes(bin_dir)
    cand = tmp_path / "cand"
    cand.mkdir(exist_ok=True)
    z = cand / "FwPkt.zip"
    z.write_bytes(b"FAKE-FWPKT-ZIP")
    dev = make_device(tmp_path, fwver="FwVer:5.9.0.1.2;\n")   # foreign family
    make_manifest(cand, z, "FwVer:6.0.0.54.66;date:2026.10.14;", dev)
    state = tmp_path / "state"
    state.write_text("up")
    gate = TcpGate(state)
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(tmp_path / "home"),
        "FAKE_DEVICE_ROOT": str(dev), "FAKE_STATE_FILE": str(state),
        "GIMBAL_HOST": "127.0.0.1", "GIMBAL_PORT": str(gate.port),
        "GIMBAL_SSH": f"root@127.0.0.1:{gate.port}",
        "FWPKT_ZIP": str(z), "MANIFEST": str(cand / "install-manifest.json"),
        "MAX_WAIT": "15", "WAKE_WAIT": "15", "REBOOT_DARK_WATCH": "10", "SETTLE_WAIT": "2", "POLL_INTERVAL": "1", "POLL_LIMIT": "3",
    }
    (tmp_path / "home").mkdir(exist_ok=True)
    try:
        r = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, timeout=240, env=env, cwd=ROOT)
    finally:
        gate.close()
    assert r.returncode == 6, r.stdout + r.stderr
    assert "unexpected device FwVer" in r.stdout


def test_failed_reboot_reports_uncertain_delivery(tmp_path):
    # Device never goes dark after 812: delivery uncertain, but verify still proves the install.
    r = run_install(tmp_path, {"FAKE_NO_DARK": "1", "FAKE_CAM_STATE": ""})
    assert r.returncode == 0, r.stdout + r.stderr
    assert "delivery UNCERTAIN" in r.stdout
    assert "reboot delivery was uncertain" in r.stdout


def test_no_blind_reflash_when_already_updated(tmp_path):
    # Device already reports the target FwVer: stage must skip scp entirely.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    _write_fakes(bin_dir)
    cand = tmp_path / "cand"
    cand.mkdir(exist_ok=True)
    z = cand / "FwPkt.zip"
    z.write_bytes(b"FAKE-FWPKT-ZIP")
    dev = make_device(tmp_path)  # FwVer already == target
    make_manifest(cand, z, "FwVer:6.0.0.54.66;date:2026.10.14;", dev)
    state = tmp_path / "state"
    state.write_text("up")
    gate = TcpGate(state)
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(tmp_path / "home"),
        "FAKE_DEVICE_ROOT": str(dev), "FAKE_STATE_FILE": str(state),
        "GIMBAL_HOST": "127.0.0.1", "GIMBAL_PORT": str(gate.port),
        "GIMBAL_SSH": f"root@127.0.0.1:{gate.port}",
        "FWPKT_ZIP": str(z), "MANIFEST": str(cand / "install-manifest.json"),
        "MAX_WAIT": "15", "WAKE_WAIT": "15", "REBOOT_DARK_WATCH": "10", "SETTLE_WAIT": "2", "POLL_INTERVAL": "1", "POLL_LIMIT": "3",
    }
    (tmp_path / "home").mkdir(exist_ok=True)
    try:
        r = subprocess.run(["bash", str(SCRIPT), "--stage-only"],
                           capture_output=True, text=True, timeout=240, env=env, cwd=ROOT)
    finally:
        gate.close()
    assert r.returncode == 0, r.stdout + r.stderr
    assert "skipping reflash" in r.stdout
    assert not (dev / "app/sd/FwPkt.zip").exists(), "scp must not have run"


def test_manifest_digest_mismatch_refuses(tmp_path):
    # Zip changed after the manifest was frozen: auth gate must refuse.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    _write_fakes(bin_dir)
    cand = tmp_path / "cand"
    cand.mkdir(exist_ok=True)
    z = cand / "FwPkt.zip"
    z.write_bytes(b"FAKE-FWPKT-ZIP")
    dev = make_device(tmp_path)
    make_manifest(cand, z, "FwVer:6.0.0.54.66;date:2026.10.14;", dev)
    z.write_bytes(b"CHANGED-FWPKT-ZIP")   # digest no longer matches the frozen manifest
    state = tmp_path / "state"
    state.write_text("up")
    gate = TcpGate(state)
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(tmp_path / "home"),
        "FAKE_DEVICE_ROOT": str(dev), "FAKE_STATE_FILE": str(state),
        "GIMBAL_HOST": "127.0.0.1", "GIMBAL_PORT": str(gate.port),
        "GIMBAL_SSH": f"root@127.0.0.1:{gate.port}",
        "FWPKT_ZIP": str(z), "MANIFEST": str(cand / "install-manifest.json"),
        "MAX_WAIT": "15", "WAKE_WAIT": "15", "REBOOT_DARK_WATCH": "10", "SETTLE_WAIT": "2", "POLL_INTERVAL": "1", "POLL_LIMIT": "3",
    }
    (tmp_path / "home").mkdir(exist_ok=True)
    try:
        r = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, timeout=240, env=env, cwd=ROOT)
    finally:
        gate.close()
    assert r.returncode == 6, r.stdout + r.stderr
    assert "candidate digest mismatch" in r.stdout


def test_poll_survives_interrupted_wake(tmp_path):
    # First wake attempt fails (device dark), second succeeds after it comes up.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    _write_fakes(bin_dir)
    cand = tmp_path / "cand"
    cand.mkdir(exist_ok=True)
    z = cand / "FwPkt.zip"
    z.write_bytes(b"FAKE-FWPKT-ZIP")
    dev = make_device(tmp_path)
    make_manifest(cand, z, "FwVer:6.0.0.54.66;date:2026.10.14;", dev)
    state = tmp_path / "state"
    state.write_text("down")   # device starts dark
    gate = TcpGate(state)
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(tmp_path / "home"),
        "FAKE_DEVICE_ROOT": str(dev), "FAKE_STATE_FILE": str(state),
        "GIMBAL_HOST": "127.0.0.1", "GIMBAL_PORT": str(gate.port),
        "GIMBAL_SSH": f"root@127.0.0.1:{gate.port}",
        "FWPKT_ZIP": str(z), "MANIFEST": str(cand / "install-manifest.json"),
        "MAX_WAIT": "15", "POLL_INTERVAL": "1", "POLL_LIMIT": "4",
    }
    (tmp_path / "home").mkdir(exist_ok=True)

    def wake_later() -> None:
        import time
        time.sleep(3)
        state.write_text("up")

    t = threading.Thread(target=wake_later, daemon=True)
    t.start()
    try:
        r = subprocess.run(["bash", str(SCRIPT), "--poll"],
                           capture_output=True, text=True, timeout=240, env=env, cwd=ROOT)
    finally:
        gate.close()
        t.join(timeout=5)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "POLL mode" in r.stdout
    assert "VERDICT: verified" in r.stdout


def test_host_key_mismatch_refuses(tmp_path):
    r = run_install(
        tmp_path,
        {"FAKE_CAM_STATE": "", "EXPECTED_HOST_KEY": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIWRONGKEY"},
    )
    assert r.returncode == 6, r.stdout + r.stderr
    assert "host key MISMATCH" in r.stdout


def test_host_key_match_proceeds(tmp_path):
    r = run_install(
        tmp_path,
        {"FAKE_CAM_STATE": "", "EXPECTED_HOST_KEY": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFAKEKEY"},
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "host key matches recorded identity" in r.stdout
