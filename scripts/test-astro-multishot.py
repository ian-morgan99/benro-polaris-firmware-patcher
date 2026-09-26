#!/usr/bin/env python3
"""Bounded Polaris multi-shot simulation using the proven capture command.

This does not invoke the unqualified native timelapse composite.  It performs
an authenticated 9090 handshake, suspends preview, then issues ordinary camera
captures at a fixed interval.  Every shot must produce post-request code 264
lifecycle evidence and a non-empty code 773 SP_ADD_FILE path; the script stops
on a negative state, ambiguous completion, disconnect, or timeout.
"""

from __future__ import annotations

import argparse
import posixpath
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
        # Current production firmware replies as ``code@payload#``.  The
        # simulator and some older captures use request-shaped
        # ``1&code&type&payload#`` replies, so accept both forms.
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


def authenticate(p: Polaris) -> None:
    p.send(284)
    p.wait_code(284, 5)
    p.send(820)
    auth = p.wait_code(820, 12)
    needed = field(auth, "needed")
    if needed == "1":
        raise RuntimeError("device requires a password; this bounded test has none")
    p.send(823, payload="app:openpolaris-astro-test;ver:1;")


def suspend_preview(p: Polaris) -> bool:
    p.send(292)
    preview = p.wait_code(292, 10)
    state = field(preview, "state")
    print(f"{stamp()} PREVIEW initial_state={state}", flush=True)
    if state != "0":
        p.send(291, payload="state:0;")
        stopped = p.wait_code(291, 15)
        if field(stopped, "state") != "0" or field(stopped, "ret") not in (None, "0"):
            raise RuntimeError(f"preview stop was not accepted: {stopped}")
        p.send(292)
        confirmed = p.wait_code(292, 10)
        if field(confirmed, "state") != "0":
            raise RuntimeError(f"preview remained on: {confirmed}")
    print(f"{stamp()} PREVIEW confirmed_off", flush=True)
    return state != "0"


def restore_preview(p: Polaris, was_on: bool) -> None:
    if not was_on:
        return
    p.send(291, payload="state:1;")
    started = p.wait_code(291, 15)
    if field(started, "state") != "1" or field(started, "ret") not in (None, "0"):
        raise RuntimeError(f"preview restore was not accepted: {started}")
    p.send(292)
    confirmed = p.wait_code(292, 10)
    if field(confirmed, "state") != "1":
        raise RuntimeError(f"preview was not restored: {confirmed}")
    print(f"{stamp()} PREVIEW restored_on", flush=True)


def capture(p: Polaris, number: int, timeout: float,
            expected_files: int = 1, seen_paths: set[str] | None = None) -> list[str]:
    if seen_paths is None:
        seen_paths = set()
    p.send(264, subtype=4, payload="state:1;bulb:0;c:-1;")
    deadline = time.monotonic() + timeout
    states: list[int] = []
    files: list[str] = []
    while True:
        code, payload = p.frame(deadline)
        if code == 773:
            path = field(payload, "path")
            if path:
                if path in seen_paths:
                    raise RuntimeError(f"shot {number}: stale file event {path!r}")
                if path not in files:
                    files.append(path)
                    print(f"{stamp()} SHOT {number} file={path}", flush=True)
        elif code == 264:
            value = field(payload, "state")
            if value is not None:
                try:
                    state = int(value)
                except ValueError:
                    raise RuntimeError(f"shot {number}: invalid state {value!r}")
                states.append(state)
                print(f"{stamp()} SHOT {number} state={state} lifecycle={states}", flush=True)
                if state < 0:
                    raise RuntimeError(
                        f"shot {number}: terminal failure state {state}; lifecycle={states}"
                    )
        if len(files) > expected_files:
            raise RuntimeError(f"shot {number}: excess file events {files!r}")
        if len(files) == expected_files and len({posixpath.splitext(f)[0] for f in files}) != 1:
            raise RuntimeError(f"shot {number}: files do not share an exposure stem: {files!r}")
        if 4 in states and 0 in states and len(files) == expected_files:
            print(
                f"{stamp()} SHOT {number} PASS lifecycle={states} files={files}",
                flush=True,
            )
            seen_paths.update(files)
            return files


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="192.168.0.1")
    parser.add_argument("--port", type=int, default=9090)
    parser.add_argument("--bind", default="192.168.0.4")
    parser.add_argument("--shots", type=int, default=3)
    parser.add_argument("--interval", type=float, default=10.0,
                        help="seconds after a completed shot before the next shutter")
    parser.add_argument("--shot-timeout", type=float, default=120.0)
    parser.add_argument("--expected-files", type=int, choices=(1, 2), required=True,
                        help="authoritative output obligation; never inferred from photoFormat")
    parser.add_argument("--execute", action="store_true",
                        help="required acknowledgement that shutters will be released")
    args = parser.parse_args()
    if not args.execute:
        parser.error("refusing to release the shutter without --execute")
    if not 1 <= args.shots <= 20:
        parser.error("--shots must be between 1 and 20")
    if args.interval < 0:
        parser.error("--interval must be non-negative")

    print(f"{stamp()} START host={args.host}:{args.port} shots={args.shots} "
          f"interval={args.interval}s bind={args.bind}", flush=True)
    p = Polaris(args.host, args.port, args.bind or None, timeout=10)
    preview_was_on = False
    try:
        authenticate(p)
        p.send(286)
        camera = p.wait_code(286, 10)
        if field(camera, "state") != "1":
            raise RuntimeError(f"camera not ready: {camera}")
        expected_files = args.expected_files
        print(f"{stamp()} OUTPUT contract=explicit expected_files={expected_files} "
              f"photoFormat_hint={field(camera, 'photoFormat')}", flush=True)
        preview_was_on = suspend_preview(p)
        seen_paths: set[str] = set()
        for number in range(1, args.shots + 1):
            capture(p, number, args.shot_timeout, expected_files, seen_paths)
            if number != args.shots:
                print(f"{stamp()} INTERVAL sleeping={args.interval}s", flush=True)
                time.sleep(args.interval)
    finally:
        try:
            restore_preview(p, preview_was_on)
        finally:
            p.close()
    print(f"{stamp()} PASS shots={args.shots}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"{stamp()} FAIL {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1)
