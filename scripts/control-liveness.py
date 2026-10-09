#!/usr/bin/env python3
"""Control-plane liveness probe for the Polaris capture service.

Why this exists (issue #182)
----------------------------
The on-device supervisor (`camera_usb_supervisor.sh`) decides whether the capture
daemon is healthy by watching USB identity. That is the right signal for the
detach/reattach fault it was written for (#57), but it is blind to the fault seen
in the 30-capture soak (`docs/evidence/o-v16c-context-lifetime-20261009/SOAK-30.md`):
for ~19 s the daemon accepted a TCP connection and then answered *nothing* to a
read-only `284` state query, with no crash, no core file and no process restart.
USB identity never changed, so the supervisor saw a healthy device the whole time.

A TCP connection succeeding is also not proof of life -- a listening socket can
be accepted by a service whose worker is blocked. So this probe separates the
three states that actually differ, and reports latency for the healthy one:

  refused      connect() refused        -> service not listening (the state the
                                          device was in after the soak: ping
                                          answered, 22 and 9090 both refused)
  unresponsive connect ok, no reply     -> the #182 wedge signature
  healthy      reply to the probe frame -> ok, with measured round-trip

`284` is used because it is read-only (it reports preview mode/state), needs no
camera interaction, and is the exact command that went unanswered during the
wedge. Nothing is written and no capture is triggered, so this is safe to run
against a live device at any time.

Exit codes are stable so this can be wired into a supervisor or CI gate:
  0 healthy, 1 unresponsive, 2 refused/unreachable, 3 protocol error,
  5 unreachable (host gone: no route / no connect answer),
  4 wrong_network (the address is not the gimbal; see route_interface).
"""
from __future__ import annotations

import argparse
import errno
import os
import re
import socket
import subprocess
import sys
import time

PROBE_COMMAND = 284
DEFAULT_HOST = "192.168.0.1"
DEFAULT_PORT = 9090

EXIT_HEALTHY = 0
EXIT_UNRESPONSIVE = 1
EXIT_REFUSED = 2
EXIT_PROTOCOL_ERROR = 3
EXIT_WRONG_NETWORK = 4
EXIT_UNREACHABLE = 5

# "healthy" is not merely "a byte arrived". The device answers several frames
# around a session (unsolicited notifications included), so the probe looks for
# the reply that actually carries the requested code.
def parse_frame(text: str) -> tuple[int, str] | None:
    """Return (code, payload) for one `284@...`-style frame, or None if unparseable."""
    text = text.strip()
    if not text:
        return None
    if "@" in text:
        raw_code, payload = text.split("@", 1)
    else:
        parts = text.split("&", 3)
        if len(parts) != 4:
            return None
        raw_code, payload = parts[1], parts[3]
    try:
        return int(raw_code), payload
    except ValueError:
        return None


def classify(connect_error: str | None, reply_code: int | None) -> str:
    """Map what happened to one of the four states. Pure, so it is unit-testable."""
    if connect_error is not None:
        return "refused" if connect_error == "ConnectionRefusedError" else "unreachable"
    if reply_code is None:
        return "unresponsive"
    if reply_code == PROBE_COMMAND:
        return "healthy"
    return "protocol_error"


def probe(host: str, port: int, timeout: float) -> tuple[str, float, str]:
    """Return (state, elapsed_seconds, detail). Never raises."""
    started = time.monotonic()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
    except ConnectionRefusedError as exc:
        return "refused", time.monotonic() - started, f"{type(exc).__name__}: {exc}"
    except (TimeoutError, socket.timeout) as exc:
        # Connect produced no answer at all: the host is silent, not rejecting.
        return "unreachable", time.monotonic() - started, f"{type(exc).__name__}: {exc}"
    except OSError as exc:
        # EHOSTUNREACH/ENETUNREACH mean the host went away mid-session (seen on
        # 2026-10-09 when Benro Connect crashed and the AP dropped). Calling that
        # `refused` would tell a supervisor to restart a service that is fine.
        if exc.errno in (errno.EHOSTUNREACH, errno.ENETUNREACH):
            return "unreachable", time.monotonic() - started, f"{type(exc).__name__}: {exc}"
        return "refused", time.monotonic() - started, f"{type(exc).__name__}: {exc}"
    try:
        sock.sendall(f"1&{PROBE_COMMAND}&2&-100#".encode("ascii"))
        reply_code = None
        detail = ""
        buffer = b""
        # Read until the requested code arrives or the budget runs out; earlier
        # frames are unsolicited notifications and must not be mistaken for a
        # successful probe.
        while time.monotonic() - started < timeout:
            try:
                chunk = sock.recv(65536)
            except socket.timeout:
                break
            if not chunk:
                return ("protocol_error", time.monotonic() - started,
                        "socket closed before a reply")
            buffer += chunk
            while b"#" in buffer:
                raw, buffer = buffer.split(b"#", 1)
                parsed = parse_frame(raw.decode("ascii", errors="replace"))
                if parsed and parsed[0] == PROBE_COMMAND:
                    reply_code, detail = parsed
                    return (classify(None, reply_code),
                            time.monotonic() - started, detail)
        return ("unresponsive", time.monotonic() - started,
                f"no {PROBE_COMMAND} reply within {timeout:.1f}s")
    except OSError as exc:
        return ("protocol_error", time.monotonic() - started,
                f"{type(exc).__name__}: {exc}")
    finally:
        sock.close()


def route_interface(host: str) -> str | None:
    """Return the interface `ip route get <host>` would use, or None if unknown.

    Why this is checked before probing. 192.168.0.1 is not unique on this
    network: when the host is on its LAN rather than the gimbal's own AP, the
    address belongs to the home router, which answers ping and lighttpd on :80
    and refuses 22/9090. Observed directly on 2026-10-09 -- the probe reported
    `refused` for ~40 minutes about a device that was never unreachable, because
    the Wi-Fi had dropped to the LAN. `polaris-preflight.sh` documents the same
    trap; a liveness probe that cannot tell "service down" from "wrong network"
    will keep producing that false alarm.
    """
    try:
        out = subprocess.run(["ip", "-o", "route", "get", host],
                             capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"\bdev\s+(\S+)", out)
    return match.group(1) if match else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--timeout", type=float, default=5.0,
                    help="per-attempt budget for connect and reply (default 5s)")
    ap.add_argument("--attempts", type=int, default=1,
                    help="repeat N times; the worst result is reported (default 1)")
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--iface", default=None,
                    help="interface the address must route via (default $WIFI_IFACE, "
                         "else wlp8s0, matching polaris-preflight.sh); pass '' to skip")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    if args.attempts < 1:
        print("--attempts must be >= 1", file=sys.stderr)
        return EXIT_PROTOCOL_ERROR

    expected_iface = args.iface if args.iface is not None else \
        os.environ.get("WIFI_IFACE", "wlp8s0")
    if expected_iface:
        actual = route_interface(args.host)
        if actual != expected_iface:
            print(f"RESULT state=wrong_network exit={EXIT_WRONG_NETWORK} "
                  f"route to {args.host} is via {actual or 'nowhere'}, not "
                  f"{expected_iface}; that address is being answered by another "
                  f"host (the LAN router shares it), so any result here is "
                  f"about the router, not the gimbal")
            return EXIT_WRONG_NETWORK

    worst_state = "healthy"
    worst_exit = EXIT_HEALTHY
    for attempt in range(1, args.attempts + 1):
        state, elapsed, detail = probe(args.host, args.port, args.timeout)
        if not args.quiet:
            print(f"attempt={attempt} state={state} elapsed={elapsed:.2f}s "
                  f"target={args.host}:{args.port} {detail}", flush=True)
        if state != "healthy":
            worst_state, worst_exit = state, {
                "unreachable": EXIT_UNREACHABLE,
                "unresponsive": EXIT_UNRESPONSIVE,
                "refused": EXIT_REFUSED,
                "protocol_error": EXIT_PROTOCOL_ERROR,
            }[state]
        if attempt < args.attempts:
            time.sleep(args.interval)

    if not args.quiet:
        print(f"RESULT state={worst_state} exit={worst_exit}")
    return worst_exit


if __name__ == "__main__":
    raise SystemExit(main())
