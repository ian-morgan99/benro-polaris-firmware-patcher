#!/usr/bin/env python3
"""o-v12n first-canary probe: authenticate on 9090, report camera state,
optionally fire exactly one capture (code 264) and watch the lifecycle.

Usage:
  canary-probe.py --probe            # handshake + camera state only
  canary-probe.py --shot            # handshake + preview off + ONE capture
"""
from __future__ import annotations

import argparse
import socket
import sys
import time


def stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class Polaris:
    def __init__(self, host: str, port: int, bind: str | None, timeout: float):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if bind:
            self.sock.bind((bind, 0))
        self.sock.settimeout(timeout)
        self.sock.connect((host, port))
        self.buffer = b""

    def close(self) -> None:
        self.sock.close()

    def send(self, code: int, subtype: int = 2, payload: str = "-100") -> None:
        frame = f"1&{code}&{subtype}&{payload}#"
        print(f"{stamp()} TX {frame}", flush=True)
        self.sock.sendall(frame.encode("ascii"))

    def frame(self, deadline: float) -> tuple[int, str]:
        while b"#" not in self.buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("response deadline expired")
            self.sock.settimeout(remaining)
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("9090 socket closed")
            self.buffer += chunk
        raw, self.buffer = self.buffer.split(b"#", 1)
        text = raw.decode("ascii", errors="replace")
        if "@" in text:
            raw_code, payload = text.split("@", 1)
        else:
            parts = text.split("&", 3)
            if len(parts) != 4:
                print(f"{stamp()} RX_UNPARSED {text}#", flush=True)
                return -1, text
            raw_code, payload = parts[1], parts[3]
        try:
            code = int(raw_code)
        except ValueError:
            code = -1
        print(f"{stamp()} RX {text}#", flush=True)
        return code, payload

    def wait_code(self, wanted: int, timeout: float) -> str:
        deadline = time.monotonic() + timeout
        while True:
            code, payload = self.frame(deadline)
            if code == wanted:
                return payload


def field(payload: str, name: str) -> str | None:
    prefix = f"{name}:"
    for item in payload.split(";"):
        if item.startswith(prefix):
            return item[len(prefix):]
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="192.168.0.1")
    ap.add_argument("--port", type=int, default=9090)
    ap.add_argument("--bind", default="192.168.0.4")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--shot", action="store_true")
    ap.add_argument("--shot-timeout", type=float, default=180.0)
    args = ap.parse_args()

    p = Polaris(args.host, args.port, args.bind or None, timeout=10)
    try:
        # authenticate
        p.send(284)
        p.wait_code(284, 5)
        p.send(820)
        auth = p.wait_code(820, 12)
        if field(auth, "needed") == "1":
            raise RuntimeError("device requires a password")
        p.send(823, payload="app:openpolaris-canary-probe;ver:1;")

        # camera state (code 286 = camera info)
        p.send(286)
        cam = p.wait_code(286, 10)
        print(f"{stamp()} CAMERA {cam}", flush=True)
        state = field(cam, "state")
        photo_format = field(cam, "photoFormat")
        model = field(cam, "model")
        print(f"{stamp()} SUMMARY model={model} state={state} photoFormat={photo_format}", flush=True)

        if args.probe:
            print(f"{stamp()} PROBE-DONE", flush=True)
            return 0

        if args.shot:
            # preview off
            p.send(292)
            preview = p.wait_code(292, 10)
            pv_state = field(preview, "state")
            print(f"{stamp()} PREVIEW initial_state={pv_state}", flush=True)
            if pv_state != "0":
                p.send(291, payload="state:0;")
                stopped = p.wait_code(291, 15)
                print(f"{stamp()} PREVIEW stop_ack={stopped}", flush=True)
                p.send(292)
                confirmed = p.wait_code(292, 10)
                print(f"{stamp()} PREVIEW confirmed={confirmed}", flush=True)

            # ONE capture
            p.send(264, subtype=4, payload="state:1;bulb:0;c:-1;")
            deadline = time.monotonic() + args.shot_timeout
            states: list[int] = []
            file_path: str | None = None
            while True:
                code, payload = p.frame(deadline)
                if code == 773:
                    path = field(payload, "path")
                    if path:
                        if file_path is not None and path != file_path:
                            print(f"{stamp()} AMBIGUOUS second file event {path!r}", flush=True)
                            break
                        file_path = path
                        print(f"{stamp()} FILE {file_path}", flush=True)
                elif code == 264:
                    value = field(payload, "state")
                    if value is None:
                        continue
                    try:
                        st = int(value)
                    except ValueError:
                        print(f"{stamp()} BAD-STATE {value!r}", flush=True)
                        break
                    states.append(st)
                    print(f"{stamp()} CAPTURE state={st} lifecycle={states}", flush=True)
                    if st < 0:
                        print(f"{stamp()} TERMINAL-FAILURE state={st}", flush=True)
                        break
                    if file_path and (4 in states or len(states) >= 2):
                        print(f"{stamp()} PASS lifecycle={states} file={file_path}", flush=True)
                        break
                # ignore other codes
            print(f"{stamp()} DONE states={states} file={file_path}", flush=True)
            return 0 if (file_path and not any(s < 0 for s in states)) else 1
    finally:
        p.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"{stamp()} FAIL {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1)
