#!/usr/bin/env python3
"""Replay Benro Connect's startup query burst and print what the device answers.

Why: #187 records that the app dies ~0.8 s after connecting, immediately after
querying camera state (`265/268/275/267/266`, then `286`) -- and the device log
shows it answered every query normally before the client-side close. The app's
own crash log lives on the phone, so the cheapest way to see what it is choking
on is to ask the same questions ourselves and look at the answers.

The codes come from the Mlog trace quoted in #187:

    17:52:21.670 app queries 296/303/300/775/778/823/826/802/804/824/524
    17:52:21.673 app queries camera state 265/268/275/267/266 (type:1)
    17:52:22.399 SOCKET_CLOSE [id=2]        (~0.8 s after connect)

Read-only: nothing here triggers a capture or writes anything, so it is safe to
run against a live device while the app is connected.

A `NO_REPLY` is as interesting as a bad reply: #182 measured a ~19 s window where
the daemon accepted a connection and answered nothing at all.
"""
from __future__ import annotations

import argparse
import socket
import sys
import time

# Order matters: this is the order the app sends them (#187's Mlog trace).
IDENTITY = [780]
CAMERA_STATE = [265, 268, 275, 267, 266, 286]
STORAGE_AND_MISC = [775, 778, 296, 303, 300, 823, 826, 802, 804, 824, 524]

# Fields that a client parsing a fixed schema is most likely to reject outright.
SUSPECT_KEYS = ("state:-", "manufacturer:none", "model:none", "ret:-")


def frames(sock: socket.socket, want: int, deadline: float, buf: bytes):
    """Yield decoded frames until the one answering `want` arrives, or timeout."""
    while True:
        while b"#" in buf:
            raw, buf = buf.split(b"#", 1)
            text = raw.decode("ascii", errors="replace")
            yield text, buf
            if text.startswith(f"{want}@") or text.startswith(f"1&{want}&"):
                return
        if time.monotonic() > deadline:
            return
        try:
            chunk = sock.recv(65536)
        except (socket.timeout, TimeoutError):
            return
        if not chunk:
            return
        buf += chunk


def ask(sock: socket.socket, code: int, timeout: float) -> tuple[str, float]:
    started = time.monotonic()
    sock.sendall(f"1&{code}&2&-100#".encode("ascii"))
    buf = b""
    for text, buf in frames(sock, code, started + timeout, buf):
        if text.startswith(f"{code}@") or text.startswith(f"1&{code}&"):
            return text, time.monotonic() - started
    return "", time.monotonic() - started


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="192.168.0.1")
    ap.add_argument("--port", type=int, default=9090)
    ap.add_argument("--timeout", type=float, default=3.0)
    ap.add_argument("--group", default="camera",
                    choices=("camera", "identity", "storage", "all"),
                    help="which part of the app's startup burst to replay")
    args = ap.parse_args(argv)

    codes = {"camera": CAMERA_STATE, "identity": IDENTITY,
             "storage": STORAGE_AND_MISC,
             "all": IDENTITY + CAMERA_STATE + STORAGE_AND_MISC}[args.group]

    try:
        sock = socket.create_connection((args.host, args.port), timeout=args.timeout)
    except OSError as exc:
        print(f"connect {args.host}:{args.port} failed: {type(exc).__name__}: {exc}")
        return 2
    sock.settimeout(args.timeout)

    problems = 0
    for code in codes:
        try:
            text, elapsed = ask(sock, code, args.timeout)
        except OSError as exc:
            print(f"{code:>4} ERROR {type(exc).__name__}: {exc}")
            problems += 1
            continue
        if not text:
            print(f"{code:>4} NO_REPLY ({elapsed:.1f}s)  <-- the app waits on this")
            problems += 1
            continue
        flags = [k for k in SUSPECT_KEYS if k in text]
        note = ("  <-- " + ", ".join(flags)) if flags else ""
        print(f"{code:>4} {text}{note}")
    sock.close()
    print(f"--- {problems} of {len(codes)} queries unusable ---")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
