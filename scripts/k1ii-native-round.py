#!/usr/bin/env python3
"""One native v114 camera-on window. Run --plan to see the operator steps."""
import argparse
import contextlib
import hashlib
import http.client
import json
from pathlib import Path
import runpy
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
CANARY = runpy.run_path(str(HERE / "canary-probe.py"))
VERSION = "6.0.0.54.114"
MODELS = {"k1ii": "pentax k-1 mark ii", "k3iii": "pentax k-3 mark iii"}
CONTROLS = (
    ("shutter", 268, 261, "s"),
    ("iso", 265, 258, "iso"),
    ("wb", 266, 259, "wb"),
    ("ev", 267, 260, "ev"),
    ("aperture", 275, 276, "fNum"),
)
PLAN = """Keep Benro Connect connected for wake. Leave its controls untouched.
1. When prompted, turn on the K-1 II with the dial in M. Press Enter once.
2. The runner checks the five settings, then samples native preview.
3. When prompted, turn off only the camera and press Enter. Leave Polaris on.
The runner keeps native replies on the PC and retrieves Polaris logs after power-off.
"""


def field(payload, name):
    return CANARY["field"](payload, name)


def request(client, code, payload="-100", timeout=6):
    start = time.monotonic()
    client.send(code, payload=payload)
    result = client.wait_code(code, timeout)
    print(f"TIMING code={code} seconds={time.monotonic() - start:.3f}", flush=True)
    return result


def info(client, code):
    reply = request(client, code)
    options = (field(reply, "R") or "").split(",")
    if options[-1] == "":
        options.pop()
    selected = field(reply, "V")
    if not options or not all(options) or selected is None or not selected.isascii() or not selected.isdecimal():
        raise ValueError(f"invalid option domain: {reply!r}")
    index = int(selected)
    permission = field(reply, "RD")
    if not 0 <= index < len(options) or permission not in ("0", "1"):
        raise ValueError(f"invalid option index or permission: {reply!r}")
    return index, tuple(options), permission


def observe(client, get, domain, wanted, seconds=18):
    deadline = time.monotonic() + seconds
    matches = 0
    while time.monotonic() < deadline:
        current, choices, rd = info(client, get)
        if choices != domain or rd != "0":
            raise ValueError("setting domain changed")
        matches = matches + 1 if current == wanted else 0
        if matches == 2:
            return True
        time.sleep(1)
    return False


def round_trip(client, case):
    name, get, put, key = case
    first = info(client, get)
    second = info(client, get)
    print(f"BASELINE {name} first={first!r} second={second!r}", flush=True)
    if first != second or first[2] != "0" or len(first[1]) < 2:
        return {"outcome": "blocked-unstable-or-readonly"}
    original, domain, _ = first
    target = original + 1 if original + 1 < len(domain) else original - 1
    if name == "shutter" and any("bulb" in domain[i].lower() for i in (original, target)):
        return {"outcome": "blocked-bulb-domain"}
    result = {"original": domain[original], "target": domain[target], "restoration": "unknown"}
    print(f"SET_INTENT {name} original={domain[original]!r} target={domain[target]!r}", flush=True)
    ack = request(client, put, f"{key}:{target};")
    if field(ack, key) != str(target) or field(ack, "ret") is None:
        raise RuntimeError(f"{name}: ambiguous SET reply, original {domain[original]!r}")
    if field(ack, "ret") != "0":
        result["outcome"] = "refused"
        result["restoration"] = "original-observed" if observe(client, get, domain, original) else "unknown"
        return result
    target_seen = observe(client, get, domain, target)
    result["outcome"] = "native-readback-match" if target_seen else "accepted-unconfirmed"
    current, choices, rd = info(client, get)
    if choices == domain and rd == "0" and current in (original, target):
        # The preceding SET was acknowledged. Reassert the known original once,
        # even if reads still show the old value, to cover delayed application.
        restore = request(client, put, f"{key}:{original};")
        if field(restore, key) == str(original) and field(restore, "ret") == "0":
            if observe(client, get, domain, original):
                result["restoration"] = "original-observed"
    return result


def stream(host, out):
    connection = http.client.HTTPConnection(host, 8080, timeout=13)
    started = time.monotonic()
    frames = []
    data = b""
    total = 0
    try:
        connection.request("GET", "/?action=stream")
        response = connection.getresponse()
        print(f"MJPEG HTTP={response.status} header_s={time.monotonic()-started:.3f} headers={response.getheaders()!r}", flush=True)
        deadline = time.monotonic() + 32
        while time.monotonic() < deadline and total < 2 * 1024 * 1024 and len(frames) < 3:
            try:
                chunk = response.read1(16384)
            except TimeoutError:
                break
            if not chunk:
                break
            total += len(chunk)
            data += chunk
            while True:
                start = data.find(b"\xff\xd8")
                if start < 0:
                    data = data[-1:]
                    break
                data = data[start:]
                end = data.find(b"\xff\xd9", 2)
                if end < 0:
                    break
                jpeg, data = data[:end + 2], data[end + 2:]
                receipt = {"seconds": round(time.monotonic() - started, 3),
                           "bytes": len(jpeg), "sha256": hashlib.sha256(jpeg).hexdigest()}
                frames.append(receipt)
                (out / f"native-frame-{len(frames)}.jpg").write_bytes(jpeg)
                print(f"MJPEG_FRAME {receipt!r}", flush=True)
        return {"body_bytes": total, "jpeg_marker_pairs": frames}
    finally:
        connection.close()


def device_snapshot(host, output, require_clean=False):
    remote = r"""date -u
cat /app/FwVer /proc/uptime /app/openpolaris-libgphoto2-provenance.txt
if test -e /app/sd/FwPkt || test -e /app/sd/FwPkt.zip; then echo FW_PACKET_PRESENT; fi
lsusb
ps
cat /proc/mounts
find /app/sd/normal -type f -exec ls -l {} \; 2>/dev/null
dmesg | tail -100
"""
    receipt = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
                              "-o", "ConnectTimeout=7", f"root@{host}", remote],
                             capture_output=True, timeout=25, check=True)
    output.write_bytes(receipt.stdout)
    if require_clean and (f"FwVer:{VERSION};".encode() not in receipt.stdout or
                          b"FW_PACKET_PRESENT" in receipt.stdout.splitlines() or
                          any(line.startswith(b"Bus ") and b"ID 25fb:" in line
                              for line in receipt.stdout.splitlines()) or
                          b"tar xzf - -C /app/sd" in receipt.stdout):
        raise RuntimeError("preflight requires v114, no staged firmware or transfer, and no Pentax body on USB")


def run(args, out):
    results = {}
    client = None
    original_preview = None
    preview_changed = False
    ready_deadline = time.monotonic() + 180
    consecutive_ready = 0
    try:
        while time.monotonic() < ready_deadline:
            try:
                if client is None:
                    client = CANARY["Polaris"](args.host, 9090, None, 5)
                status = request(client, 286)
            except OSError as exc:
                print(f"READY_RETRY {exc!r}", flush=True)
                if client is not None:
                    client.close()
                    client = None
                consecutive_ready = 0
            else:
                if field(status, "state") == "1":
                    if (field(status, "model") or "").lower() != MODELS[args.camera]:
                        raise RuntimeError("different camera is ready")
                    consecutive_ready += 1
                    if consecutive_ready == 2:
                        break
                else:
                    consecutive_ready = 0
            time.sleep(2)
        else:
            raise TimeoutError("camera never reported ready twice in one connection")
        if field(request(client, 780), "sw") != VERSION:
            raise RuntimeError("native firmware version mismatch")
        original_preview = field(request(client, 292), "state")
        if original_preview not in ("0", "1"):
            raise RuntimeError("unknown preview state")
        if original_preview == "1":
            preview_changed = True
            request(client, 291, "state:0;")
        if field(request(client, 292), "state") != "0":
            raise RuntimeError("preview off was not confirmed")
        results["baseline"] = {}
        for name, get, _, _ in CONTROLS:
            try:
                results["baseline"][name] = info(client, get)
            except ValueError as exc:
                results["baseline"][name] = {"invalid": str(exc)}
        results["settings"] = {}
        unresolved = False
        if args.manual_writes:
            for case in CONTROLS:
                try:
                    result = round_trip(client, case)
                except ValueError as exc:
                    result = {"outcome": "invalid-or-changed-domain", "reason": str(exc),
                              "restoration": "unknown"}
                results["settings"][case[0]] = result
                print(f"SETTING_RESULT {case[0]} {result!r}", flush=True)
                if result.get("restoration") == "unknown":
                    unresolved = True
                    break
        if not unresolved:
            preview_changed = True
            request(client, 291, "state:1;")
            if field(request(client, 292), "state") == "1":
                results["native_preview"] = stream(args.host, out)
            else:
                results["native_preview"] = {"outcome": "enable-not-confirmed"}
            if args.capture_files is not None:
                request(client, 291, "state:0;")
                if field(request(client, 292), "state") != "0":
                    raise RuntimeError("capture blocked: preview off unconfirmed")
                client.close()
                client = None
                with (out / "two-shot.txt").open("w") as receipt:
                    shot = subprocess.run(
                        [sys.executable, str(HERE / "canary-two-shot.py"),
                         "--host", args.host, "--expected-sw", VERSION,
                         "--expected-files", str(args.capture_files),
                         "--expected-sp-prefix", "/app/sd/normal/SP_"],
                        stdout=receipt, stderr=subprocess.STDOUT, check=False)
                results["two_shot_exit"] = shot.returncode
                client = CANARY["Polaris"](args.host, 9090, None, 5)
    except (OSError, RuntimeError, ValueError, http.client.HTTPException) as exc:
        results["error"] = str(exc)
        print(f"ROUND_INTERRUPTED {exc!r}", flush=True)
    finally:
        if client is not None:
            try:
                if preview_changed and original_preview is not None:
                    current = field(request(client, 292), "state")
                    if current in ("0", "1") and current != original_preview:
                        request(client, 291, f"state:{original_preview};")
                    results["preview_restored"] = field(request(client, 292), "state") == original_preview
            except (OSError, RuntimeError) as exc:
                results["preview_restored"] = False
                print(f"PREVIEW_RESTORE_UNCONFIRMED {exc!r}", flush=True)
            client.close()
        (out / "results.json").write_text(json.dumps(results, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera", choices=MODELS, default="k1ii")
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--manual-writes", action="store_true",
                        help="operator confirms the body is in M and permits one write/restore per field")
    parser.add_argument("--capture-files", type=int, choices=(1, 2),
                        help="also take two ordinary shots with this confirmed output count per exposure")
    parser.add_argument("--host", default="192.168.0.1")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--status-log", type=Path, help="append operator cues to a stable log path")
    args = parser.parse_args()
    if args.plan:
        print(PLAN.replace("K-1 II", {"k1ii": "K-1 II", "k3iii": "K-3 III"}[args.camera]).rstrip())
        return
    if args.out is None:
        parser.error("--out is required for a live session")
    if args.capture_files is not None and not args.manual_writes:
        parser.error("--capture-files requires the operator's Manual-mode confirmation")
    def status(message):
        line = f"{CANARY['stamp']()} {message}"
        print(line, file=sys.stderr, flush=True)
        if args.status_log:
            with args.status_log.open("a", encoding="utf-8") as log:
                log.write(line + "\n")

    args.out.mkdir(parents=True, exist_ok=False, mode=0o700)
    status(f"PREFLIGHT evidence={args.out.resolve()}")
    for attempt in range(1, 4):
        try:
            device_snapshot(args.host, args.out / "device-before.txt", require_clean=True)
            break
        except (OSError, subprocess.SubprocessError) as exc:
            status(f"PREFLIGHT SSH retry {attempt}/3: {type(exc).__name__}")
            if attempt == 3:
                raise
    print(PLAN.replace("K-1 II", {"k1ii": "K-1 II", "k3iii": "K-3 III"}[args.camera]), file=sys.stderr)
    status("TURN CAMERA ON in M (Manual), leave Benro Connect open")
    input("Press Enter once the camera is on: ")
    status(f"RUNNING transcript={(args.out / 'native-transcript.txt').resolve()}")
    try:
        with (args.out / "native-transcript.txt").open("w", buffering=1) as log:
            with contextlib.redirect_stdout(log):
                run(args, args.out)
    finally:
        status("TURN CAMERA OFF now, leave Polaris powered on")
        input("Press Enter once the camera is off: ")
        status("COLLECTING LOGS")
        print(f"Evidence directory: {args.out}", file=sys.stderr)
        try:
            device_snapshot(args.host, args.out / "device-after.txt")
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"Post-test device snapshot unavailable: {exc}", file=sys.stderr)
        collection = subprocess.run(["bash", str(HERE / "pull-mlog-clog.sh"),
                                     f"root@{args.host}", str(args.out)], check=False)
        status(f"LOG COLLECTOR EXIT={collection.returncode} evidence={args.out.resolve()}")


if __name__ == "__main__":
    main()
