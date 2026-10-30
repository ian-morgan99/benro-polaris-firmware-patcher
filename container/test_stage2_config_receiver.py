"""Exercise the real collector on loopback; no camera or third-party packages."""
from pathlib import Path
import hashlib
import importlib.util
import json
import select
import socket
import subprocess
import sys
import tempfile
import time
from unittest import mock

binary = sys.argv[1]


def record(seq=1, pid=123, name="iso"):
    return (f"config-timing seq={seq} pid={pid} tid=124 op=get-single "
            f"name={name} core-ret=-2 start=1.000000000 end=2.000000000\n").encode()


def port_number():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def run_case(root, name, datagrams, extra=(), expected=0):
    port = port_number()
    output = root / name
    command = [binary, "--port", str(port), "--output", str(output),
               "--seconds", "1", *extra]
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as proc:
        try:
            assert select.select([proc.stdout], [], [], 3)[0], "collector startup timeout"
            assert proc.stdout.readline().startswith(b"READY loopback=")
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                for data in datagrams:
                    sender.sendto(data, ("127.0.0.1", port))
            _, stderr = proc.communicate(timeout=4)
            assert proc.returncode == expected, (name, proc.returncode, stderr)
        finally:
            if proc.poll() is None:
                proc.terminate()
                proc.communicate(timeout=4)
    assert output.stat().st_mode & 0o777 == 0o600
    assert output.stat().st_size <= 128 * 255
    return output.read_bytes(), stderr


with tempfile.TemporaryDirectory(prefix="stage2-receiver-test-") as directory:
    root = Path(directory)
    data, log = run_case(root, "valid", [record(1), record(2)],
                         ("--pid", "123", "--max-records", "2"))
    assert data == record(1) + record(2) and b"reason=record-limit" in log

    bad = [b"", b"junk\n", b"x" * 4096, record() + b"extra\n",
           record().replace(b"name=iso", b"name=iso\x00"), record(pid=456),
           record(seq=129), record(name="x" * 65)]
    data, log = run_case(root, "filtered", bad + [record(3)], ("--pid", "123"))
    assert data == record(3) and b"rejected=8" in log

    started = time.monotonic()
    data, log = run_case(root, "empty", [], expected=3)
    assert not data and b"reason=deadline" in log and time.monotonic() - started < 4

    data, log = run_case(root, "cap", [record(i) for i in range(1, 129)])
    assert data.count(b"config-timing") == 128 and b"reason=record-limit" in log

    # Invalid traffic must not keep the collector alive beyond its deadline.
    data, log = run_case(root, "invalid", [b"invalid"] * 512, expected=4)
    assert not data and b"reason=datagram-limit" in log

    existing = root / "existing"
    existing.write_bytes(b"preserve me")
    symlink = root / "link"
    symlink.symlink_to(existing)
    for target in (existing, symlink):
        result = subprocess.run([binary, "--port", str(port_number()), "--output", str(target)],
                                capture_output=True, timeout=3)
        assert result.returncode == 1 and existing.read_bytes() == b"preserve me"
    # A normal termination retains already received records and reports a
    # partial collection, rather than silently losing the in-memory buffer.
    port = port_number()
    output = root / "interrupted"
    with subprocess.Popen([binary, "--port", str(port), "--output", str(output),
                           "--seconds", "120"], stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE) as proc:
        try:
            assert select.select([proc.stdout], [], [], 3)[0]
            assert proc.stdout.readline().startswith(b"READY ")
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                sender.sendto(record(), ("127.0.0.1", port))
            time.sleep(0.05)
            proc.terminate()
            _, log = proc.communicate(timeout=3)
            assert proc.returncode == 130 and b"reason=interrupted" in log
            assert output.read_bytes() == record()
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.communicate(timeout=3)
    for args in (("--port", "0"), ("--seconds", "121"), ("--max-records", "129"),
                 ("--pid", "0"), ("--seconds", "+1")):
        result = subprocess.run([binary, "--port", "40000", "--output", str(root / "unused"),
                                 *args], capture_output=True, timeout=3)
        assert result.returncode == 2
        assert not (root / "unused").exists()

    # Exercise manifest generation on extracted-file fixtures, without building
    # firmware or requiring an UBIFS tool. Old candidates remain supported.
    script = Path(__file__).resolve().parents[1] / "scripts/generate-fwpkt-manifest.py"
    spec = importlib.util.spec_from_file_location("manifest", script)
    manifest = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(manifest)
    candidate = root / "candidate"
    (candidate / "FwPkt/camera").mkdir(parents=True)
    (candidate / "FwPkt/camera/appfs.ubifs").write_bytes(b"test fixture, not firmware")
    (candidate / "FwPkt.zip").write_bytes(b"test fixture, not firmware")
    appfs = root / "extracted-fixture"
    for _, path in manifest.MANDATORY_FILES:
        target = appfs / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"fixture")
    for present in (False, True):
        if present:
            (appfs / manifest.CONFIG_RECEIVER_FILE[1]).write_bytes(b"collector fixture")
        with mock.patch.object(sys, "argv", [str(script), str(candidate)]), \
             mock.patch.object(manifest, "resolve_ubireader", return_value="fixture"), \
             mock.patch.object(manifest, "extract_appfs", return_value=str(appfs)):
            assert manifest.main() == 0
        entries = json.loads((candidate / "install-manifest.json").read_text())["files"]
        receiver_entries = [entry for entry in entries if entry["path"].endswith("/stage2-config-receiver")]
        assert bool(receiver_entries) == present
        if present:
            assert receiver_entries[0]["sha256"] == hashlib.sha256(b"collector fixture").hexdigest()

print("PASS: collector bounds, validation, PID filtering, timeout, overwrite protection and manifest binding")
