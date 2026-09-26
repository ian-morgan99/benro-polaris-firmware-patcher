#!/usr/bin/env python3
"""Two-shot canary: one 9090 session, two consecutive code-264
captures with no reconnect, no pgphoto restart, and no USB re-plug.

Gate per shot:
  - capture ack state:1 -> completion state:4;
  - all expected NEW file events (773) for that exposure;
  - camera returns to idle state:0 before the next shutter is issued;
  - no negative state (e.g. -10, -1005), no stale candidate (a 773 repeating
    a previous shot's path), and companion files share one exposure stem.

Usage:
  canary-two-shot.py            # handshake + preview off + TWO captures
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import posixpath
import socket
import sys
import time

_here = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "canary_probe", os.path.join(_here, "canary-probe.py"))
_cp_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cp_mod)
Polaris, field, stamp = _cp_mod.Polaris, _cp_mod.field, _cp_mod.stamp


def expected_file_count(photo_format: str | None) -> int:
    """Benro photoFormat 2 is RAW+JPEG; other modes publish one file."""
    return 2 if photo_format == "2" else 1


def exposure_stem(path: str) -> str:
    return posixpath.splitext(path)[0]


def shot_satisfied(rec: dict, seen_paths: list[str], expected_files: int) -> bool:
    new_files = [path for path in rec["files"] if path not in seen_paths]
    return (
        4 in rec["states"]
        and 0 in rec["states"]
        and len(new_files) == expected_files
        and len({exposure_stem(path) for path in new_files}) == 1
    )


def run_shot(p: Polaris, shot_no: int, seen_paths: list[str],
             shot_timeout: float, expected_files: int) -> dict:
    """Issue one code-264 capture and watch its lifecycle. Returns a record."""
    rec = {
        "shot": shot_no,
        "states": [],
        "files": [],
        "stale_candidate": None,
        "idle_confirmed": False,
        "terminal_failure": None,
    }
    p.send(264, subtype=4, payload="state:1;bulb:0;c:-1;")
    print(f"{stamp()} SHOT{shot_no} capture issued", flush=True)
    deadline = time.monotonic() + shot_timeout
    while True:
        try:
            code, payload = p.frame(deadline)
        except (TimeoutError, socket.timeout) as exc:
            rec["terminal_failure"] = f"timeout:{exc}"
            break
        if code == 773:
            path = field(payload, "path")
            if path:
                if path in seen_paths:
                    rec["stale_candidate"] = path
                    print(f"{stamp()} SHOT{shot_no} STALE-CANDIDATE {path!r}", flush=True)
                elif path not in rec["files"]:
                    rec["files"].append(path)
                    print(f"{stamp()} SHOT{shot_no} FILE {path}", flush=True)
        elif code == 775:
            print(f"{stamp()} SHOT{shot_no} STORAGE {payload}", flush=True)
        elif code == 264:
            value = field(payload, "state")
            if value is None:
                continue
            try:
                st = int(value)
            except ValueError:
                print(f"{stamp()} SHOT{shot_no} BAD-STATE {value!r}", flush=True)
                rec["terminal_failure"] = f"bad-state:{value}"
                break
            rec["states"].append(st)
            print(f"{stamp()} SHOT{shot_no} CAPTURE state={st} lifecycle={rec['states']}", flush=True)
            if st < 0:
                rec["terminal_failure"] = f"state:{st}"
                break
        # ignore other codes
        if 0 in rec["states"]:
            rec["idle_confirmed"] = True
        if shot_satisfied(rec, seen_paths, expected_files):
            print(f"{stamp()} SHOT{shot_no} IDLE and output obligation confirmed", flush=True)
            break
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="192.168.0.1")
    ap.add_argument("--port", type=int, default=9090)
    ap.add_argument("--bind", default="192.168.0.4")
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
        p.send(823, payload="app:openpolaris-canary-two-shot;ver:1;")

        # camera state
        p.send(286)
        cam = p.wait_code(286, 10)
        print(f"{stamp()} CAMERA {cam}", flush=True)
        if field(cam, "state") != "1":
            print(f"{stamp()} FAIL camera not ready (state != 1)", flush=True)
            return 1
        photo_format = field(cam, "photoFormat")
        expected_files = expected_file_count(photo_format)
        print(f"{stamp()} OUTPUT photoFormat={photo_format} expected_files={expected_files}", flush=True)

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

        seen_paths: list[str] = []
        records = []
        for shot_no in (1, 2):
            rec = run_shot(p, shot_no, seen_paths, args.shot_timeout, expected_files)
            records.append(rec)
            new_files = [f for f in rec["files"] if f not in seen_paths]
            seen_paths.extend(new_files)
            ok = (
                bool(new_files)
                and 4 in rec["states"]
                and rec["idle_confirmed"]
                and not rec["terminal_failure"]
                and not rec["stale_candidate"]
                and len(new_files) == expected_files
                and len({exposure_stem(path) for path in new_files}) == 1
            )
            print(f"{stamp()} SHOT{shot_no} {'PASS' if ok else 'FAIL'} "
                  f"states={rec['states']} files={new_files} "
                  f"idle={rec['idle_confirmed']} stale={rec['stale_candidate']} "
                  f"term={rec['terminal_failure']}", flush=True)
            if not ok:
                print(f"{stamp()} STOP after SHOT{shot_no} (fail-closed; no further shutter)", flush=True)
                return 1

        print(f"{stamp()} TWO-SHOT PASS files={seen_paths}", flush=True)
        return 0
    finally:
        p.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"{stamp()} FAIL {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1)
