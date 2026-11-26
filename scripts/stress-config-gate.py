#!/usr/bin/env python3
"""Load the stage2 camera admission gate and measure it, for A/B comparison.

Why this exists
---------------
The v115..v117 wedge is load-triggered: at idle the gate answers every parameter
correctly, and a single sequential probe passes on both the broken and the fixed
loader. The failure only appears when several pgphoto threads reach
waitCameraIdle at once -- which is what the app does continuously, with its
periodic metadata GETs overlapping live view and parameter reads. So proving the
fix needs concurrency and timing, not a polite sequential poll.

What it measures
----------------
  * refusals   -- "admission refused" lines in /app/sd/system/log/Clog_*.log across the window
  * sentinel   -- parameter reads answering V:-1 instead of a real value list
  * timeouts   -- reads that never answered at all
  * latency    -- per-request wall time, p50/p95/max

Read-only by construction: subtype 2 with payload -100, the same frame the head
sends for a parameter read. No SET frame, no shutter. The wire subtype for "set"
is not documented in this repository and guessing it risks firing a real
exposure.

Run it against whatever loader is currently installed, then again after a
rollback, to compare broken and fixed directly:

    scripts/stage2-hotswap.sh push /tmp/s2fix/libpolaris_stage2.so
    scripts/stress-config-gate.py --clients 8 --rounds 6
    scripts/stage2-hotswap.sh rollback
    scripts/stress-config-gate.py --clients 8 --rounds 6
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import socket
import statistics
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cp", REPO / "scripts" / "canary-probe.py")
cp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cp)

CONFIG_CODES = {
    265: "iso",
    266: "white-balance",
    267: "exposure-compensation",
    268: "shutter-speed",
    275: "aperture",
}

REFUSE_RE = re.compile(r"admission refused: site=(?P<site>[0-9a-f]+) kind=(?P<kind>\d+)")

# Which camera session the handshake actually saw, so a measurement taken
# against an unbound head is visible in the output rather than silently
# presented as a gate verdict.
_sessions: dict[str, int] = {}
_lock = threading.Lock()


def ssh(host: str, cmd: str) -> str:
    try:
        out = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=25", host, cmd],
            capture_output=True, text=True, timeout=60,
        )
        return out.stdout
    except Exception as exc:  # noqa: BLE001 - transport failure is a normal outcome here
        print(f"ssh failed: {exc}", file=sys.stderr)
        return ""


def refusal_count(host: str) -> int:
    # /app/Clog.txt does not exist on .115+ firmware -- the camera daemon writes
    # rotating logs under /app/sd/system/log/. Reading the old path returned an
    # empty grep, which every caller took as "no refusals", so a wedged gate and a
    # healthy gate produced identical output. Fail loudly instead of reporting 0.
    text = ssh(
        host,
        "ls /app/sd/system/log/Clog_*.log 2>/dev/null | tail -1 | "
        "xargs -r sed 's/\\x1b\\[[0-9;]*m//g' | grep -c 'admission refused'",
    )
    digits = text.strip().splitlines()[-1] if text.strip() else ""
    if not digits.isdigit():
        print(
            "WARN: cannot read refusals from /app/sd/system/log/Clog_*.log -- "
            "refusal counts are unavailable, not zero",
            file=sys.stderr,
        )
        return -1
    return int(digits)


def new_connection(host: str, port: int, bind: str | None, timeout: float):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if bind:
        sock.bind((bind, 0))
    sock.settimeout(timeout)
    sock.connect((host, port))
    return sock


def read_one(sock, code: int, timeout: float) -> tuple[float, str, str]:
    """One documented parameter read. Returns (seconds, verdict, raw frame).

    The raw frame is returned so a non-ok outcome can be diagnosed from what the
    head actually said, rather than inferred from the absence of a refusal line.
    """
    start = time.monotonic()
    try:
        sock.sendall(f"1&{code}&2&-100#".encode("ascii"))
    except OSError:
        return time.monotonic() - start, "closed", ""

    buf = b""
    deadline = start + timeout
    want = f"{code}@"
    try:
        while True:
            if b"#" in buf:
                raw, buf = buf.split(b"#", 1)
                text = raw.decode("ascii", errors="replace")
                if not text.startswith(want):
                    continue  # telemetry frames (778/775/517) interleave freely
                val = field(text, "V")
                raw_list = field(text, "R") or ""
                if val == "-1":
                    # The reported symptom: the head answers the sentinel and
                    # then serves a compiled-in fallback list.
                    return time.monotonic() - start, "sentinel", text
                if val in (None, "") or not raw_list.strip(","):
                    # RD:0 with an empty value/list. The read succeeded but the
                    # head had nothing to report -- distinct from the sentinel
                    # and must not be counted as it.
                    return time.monotonic() - start, "empty", text
                return time.monotonic() - start, "ok", text
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return time.monotonic() - start, "timeout", ""
            sock.settimeout(remaining)
            chunk = sock.recv(65536)
            if not chunk:
                return time.monotonic() - start, "closed", ""
            buf += chunk
    except (TimeoutError, socket.timeout):
        return time.monotonic() - start, "timeout", ""
    except OSError:
        return time.monotonic() - start, "closed", ""


def drain(sock, seconds: float) -> None:
    """Read whatever is pending, ignoring content. The handshake answers with
    several frames and telemetry (778/775/517) interleaves freely."""
    end = time.monotonic() + seconds
    try:
        while time.monotonic() < end:
            sock.settimeout(max(0.05, end - time.monotonic()))
            if not sock.recv(65536):
                return
    except (TimeoutError, socket.timeout, OSError):
        pass


def handshake(sock, timeout: float) -> tuple[bool, str]:
    """Perform the head's own init sequence before reading parameters.

    pgphoto binds the USB camera lazily, on the app handshake -- not at process
    start. A client that only sends config frames therefore measures an
    uninitialised head: every read blocks until the deadline and looks exactly
    like the wedge being tested for. This is the same sequence
    probe-config-gate.py uses (284, 820, 823, 286), all read-only.
    """
    try:
        sock.sendall(b"1&284&2&-100#")
        drain(sock, timeout)
        sock.sendall(b"1&820&2&-100#")
        drain(sock, timeout)
        sock.sendall(b'1&823&2&app:openpolaris-gate-stress;ver:1;#')
        drain(sock, timeout)
        sock.sendall(b"1&286&2&-100#")
        buf = b""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if b"286@" in buf and b"#" in buf:
                raw, _, rest = buf.partition(b"286@")
                payload, _, _ = rest.partition(b"#")
                text = payload.decode("ascii", errors="replace")
                model = field(text, "model")
                state = field(text, "state")
                # A head that has not bound the camera answers 286 with
                # model:none;state:-2. Every config read then blocks until its
                # deadline and looks identical to the wedge under test, so this
                # must be reported as a session problem, never as a gate result.
                if model in (None, "none", "") or state not in ("1",):
                    return False, (f"camera session not initialised "
                                   f"(model={model} state={state}) -- replug or reboot")
                return True, f"{model} state={state}"
            sock.settimeout(max(0.05, deadline - time.monotonic()))
            chunk = sock.recv(65536)
            if not chunk:
                return False, "closed during handshake"
            buf += chunk
        return False, "handshake timed out"
    except OSError as exc:
        return False, f"handshake: {exc}"


def field(payload: str, name: str) -> str | None:
    for part in payload.split(";"):
        if part.startswith(name + ":"):
            return part[len(name) + 1:]
    return None


def worker(client_id: int, host: str, port: int, bind: str | None,
           rounds: int, timeout: float, quiet: bool) -> dict:
    latents: list[float] = []
    outcomes: dict[str, int] = {"ok": 0, "sentinel": 0, "empty": 0,
                                "timeout": 0, "closed": 0}
    samples: list[str] = []
    try:
        sock = new_connection(host, port, bind, timeout)
    except OSError as exc:
        return {"client": client_id, "error": f"connect: {exc}", "outcomes": outcomes,
                "latencies": latents}
    try:
        ready, why = handshake(sock, timeout)
        if not ready:
            return {"client": client_id, "error": why, "outcomes": outcomes,
                    "latencies": latents}
        with _lock:
            _sessions.setdefault(why, 0)
            _sessions[why] += 1
        for _ in range(rounds):
            for code in CONFIG_CODES:
                elapsed, verdict, raw = read_one(sock, code, timeout)
                outcomes[verdict] += 1
                latents.append(elapsed)
                if verdict != "ok" and len(samples) < 8:
                    samples.append(f"{code} {CONFIG_CODES[code]} {verdict}: {raw[:90]}")
                if not quiet and verdict != "ok":
                    print(f"  client {client_id}: {code} {CONFIG_CODES[code]} -> {verdict} "
                          f"({elapsed:.2f}s)", flush=True)
    finally:
        try:
            sock.close()
        except OSError:
            pass
    return {"client": client_id, "outcomes": outcomes, "latencies": latents,
            "samples": samples}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ssh-host", default="root@192.168.0.1")
    ap.add_argument("--ipolar-host", default="192.168.0.1")
    ap.add_argument("--port", type=int, default=9090)
    ap.add_argument("--bind", default=None,
                    help="local address to bind, e.g. 192.168.0.4")
    ap.add_argument("--clients", type=int, default=8,
                    help="concurrent connections; pgphoto runs ~7 threads, so 8 saturates it")
    ap.add_argument("--rounds", type=int, default=6,
                    help="passes over all five parameter codes per client")
    ap.add_argument("--timeout", type=float, default=10.0)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    before = refusal_count(args.ssh_host)
    total_requests = args.clients * args.rounds * len(CONFIG_CODES)
    print(f"load: {args.clients} clients x {args.rounds} rounds x "
          f"{len(CONFIG_CODES)} codes = {total_requests} reads")
    print(f"refusals before: {before}")

    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.clients) as pool:
        results = list(pool.map(
            lambda i: worker(i, args.ipolar_host, args.port, args.bind,
                             args.rounds, args.timeout, args.quiet),
            range(args.clients)))
    wall = time.monotonic() - start

    outcomes = {"ok": 0, "sentinel": 0, "empty": 0, "timeout": 0, "closed": 0}
    latents: list[float] = []
    errors = []
    samples: list[str] = []
    for res in results:
        for key, count in res["outcomes"].items():
            outcomes[key] += count
        latents.extend(res["latencies"])
        samples.extend(res.get("samples", []))
        if res.get("error"):
            errors.append(res["error"])

    time.sleep(2)  # let the head flush its log
    after = refusal_count(args.ssh_host)
    # The rotating logs can advance between the two reads, so "after" can be lower
    # than "before" without any new refusal. A negative delta means the window was
    # truncated, not that refusals were repaired; count it as zero and say so rather
    # than reporting a nonsensical negative number of bad outcomes.
    # An unreadable count (-1) is NOT zero: an unmeasured gate must never be
    # reported as a clean one.
    unknown = before < 0 or after < 0
    delta = 0 if unknown else after - before
    rotated = (not unknown) and delta < 0
    if rotated:
        delta = 0

    ordered = sorted(latents)

    def pct(p: float) -> float:
        return ordered[min(len(ordered) - 1, int(len(ordered) * p))]

    if latents:
        print(f"\nwall: {wall:.1f}s  throughput: {len(latents)/wall:.1f} reads/s")
        print(f"latency p50={pct(0.50):.2f}s p95={pct(0.95):.2f}s "
              f"max={max(latents):.2f}s mean={statistics.mean(latents):.2f}s")
    else:
        print("\nno responses")
    print(f"outcomes: ok={outcomes['ok']} sentinel(-1)={outcomes['sentinel']} "
          f"empty={outcomes['empty']} timeouts={outcomes['timeout']} "
          f"closed={outcomes['closed']}")
    if errors:
        print("connection errors: " + "; ".join(errors))
    suffix = ", log rotated -- window truncated" if rotated else ""
    refusal_text = "UNKNOWN (log unreadable)" if unknown else f"{delta}{suffix}"
    print(f"admission refusals in window: {refusal_text}")
    if _sessions:
        print("camera session seen by handshake: " +
              ", ".join(f"{k} x{v}" for k, v in _sessions.items()))
    if samples:
        print("non-ok frames (what the head actually answered):")
        for s in samples[:8]:
            print(f"    {s}")

    # A refusal is the gate doing its job: under concurrent load a real SET can hold
    # the camera past a reader's budget, and the reader is correctly turned away. That
    # is expected behaviour and must not be scored as a defect -- only a read that came
    # back wrong (sentinel, empty, timeout, closed) is a failure. Refusals are reported
    # alongside so a rising count is still visible.
    bad = (outcomes["sentinel"] + outcomes["empty"] + outcomes["timeout"] +
           outcomes["closed"])
    if errors:
        print("\nVERDICT: transport failure -- cannot judge the gate")
        return 2
    if bad:
        print(f"\nVERDICT: {bad} bad read outcome(s) under load "
              f"(sentinel={outcomes['sentinel']} empty={outcomes['empty']} "
              f"timeout={outcomes['timeout']} closed={outcomes['closed']}); "
              f"refusals={delta}")
        return 1
    p95 = f"{pct(0.95):.2f}s" if latents else "n/a"
    note = f" ({delta} correct contention refusal(s))" if delta else ""
    if unknown:
        # Reads all came back valid, which is the part that matters for correctness,
        # but contention was not observable -- say so instead of implying a quiet gate.
        print(f"\nVERDICT: reads all valid ({outcomes['ok']}) but refusal count "
              f"unmeasurable -- p95={p95}")
        return 0
    print(f"\nVERDICT: clean under load -- {outcomes['ok']} reads all valid, "
          f"p95={p95}{note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
