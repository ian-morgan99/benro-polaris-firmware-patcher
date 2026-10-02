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
  canary-two-shot.py --expected-files 1  # independently established RAW-only/JPEG-only
  canary-two-shot.py --expected-files 2  # independently established RAW+JPEG
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import posixpath
import socket
import sys
import time
import uuid

_here = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "canary_probe", os.path.join(_here, "canary-probe.py"))
_cp_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cp_mod)
Polaris, field, stamp = _cp_mod.Polaris, _cp_mod.field, _cp_mod.stamp
bulb_capture_payload = _cp_mod.bulb_capture_payload
effective_shot_timeout = _cp_mod.effective_shot_timeout
resolve_bulb_shutter_index = _cp_mod.resolve_bulb_shutter_index
set_shutter = _cp_mod.set_shutter


def exposure_stem(path: str) -> str:
    return posixpath.splitext(path)[0]


def shot_satisfied(rec: dict, seen_paths: list[str], expected_files: int,
                   expected_sp_prefix: str) -> bool:
    new_files = [path for path in rec["files"] if path not in seen_paths]
    return (
        4 in rec["states"]
        and 0 in rec["states"]
        and len(new_files) == expected_files
        and len({exposure_stem(path) for path in new_files}) == 1
        and all(path.startswith(expected_sp_prefix) for path in new_files)
    )


def run_shot(p: Polaris, shot_no: int, seen_paths: list[str],
             shot_timeout: float, expected_files: int,
             expected_sp_prefix: str, run_id: str,
             bulb_seconds: int | None = None) -> dict:
    """Issue one code-264 capture and watch its lifecycle. Returns a record."""
    rec = {
        "shot": shot_no,
        "request_id": f"{run_id}-{shot_no}",
        "states": [],
        "files": [],
        "stale_candidate": None,
        "idle_confirmed": False,
        "terminal_failure": None,
    }
    p.send(264, subtype=4, payload=bulb_capture_payload(bulb_seconds))
    print(f"{stamp()} SHOT{shot_no} source=scripted request_id={rec['request_id']} "
          f"expected_sp_prefix={expected_sp_prefix!r} capture issued", flush=True)
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
        if shot_satisfied(rec, seen_paths, expected_files, expected_sp_prefix):
            print(f"{stamp()} SHOT{shot_no} IDLE and output obligation confirmed", flush=True)
            break
    return rec


def run_sequence(p: Polaris, shot_count: int, shot_timeout: float,
                 expected_files: int, expected_sp_prefix: str,
                 run_id: str, bulb_seconds: int | None = None) -> tuple[bool, list[dict], list[str]]:
    """Run captures fail-closed: a failed shot consumes the whole failure budget."""
    seen_paths: list[str] = []
    records: list[dict] = []
    for shot_no in range(1, shot_count + 1):
        rec = run_shot(p, shot_no, seen_paths, shot_timeout, expected_files,
                       expected_sp_prefix, run_id, bulb_seconds)
        records.append(rec)
        new_files = [path for path in rec["files"] if path not in seen_paths]
        ok = (
            shot_satisfied(rec, seen_paths, expected_files, expected_sp_prefix)
            and not rec["terminal_failure"]
            and not rec["stale_candidate"]
        )
        seen_paths.extend(new_files)
        print(f"{stamp()} SHOT{shot_no} source=scripted request_id={rec['request_id']} "
              f"{'PASS' if ok else 'FAIL'} "
              f"states={rec['states']} files={new_files} "
              f"idle={rec['idle_confirmed']} stale={rec['stale_candidate']} "
              f"term={rec['terminal_failure']}", flush=True)
        if not ok:
            print(f"{stamp()} STOP after SHOT{shot_no} "
                  "(failure budget exhausted; no retry or further shutter)", flush=True)
            return False, records, seen_paths
    return True, records, seen_paths


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="192.168.0.1")
    ap.add_argument("--port", type=int, default=9090)
    ap.add_argument("--bind", default="192.168.0.4")
    ap.add_argument("--shot-timeout", type=float, default=180.0)
    ap.add_argument("--expected-files", type=int, choices=(1, 2), required=True,
                    help="authoritative per-exposure output obligation; never inferred from photoFormat")
    ap.add_argument("--expected-sp-prefix", required=True,
                    help="expected Polaris SP output path prefix, e.g. /app/sd/normal/SP_")
    ap.add_argument("--bulb-seconds", type=int,
                    help="exercise Bulb for this many seconds; index is discovered from command 268")
    ap.add_argument("--bulb-shutter-index", type=int,
                    help="optional checked override for the live Bulb entry (command 277)")
    args = ap.parse_args()
    if args.shot_timeout <= 0:
        ap.error("--shot-timeout must be positive")
    if args.bulb_seconds is not None and args.bulb_seconds <= 0:
        ap.error("--bulb-seconds must be positive")

    p = Polaris(args.host, args.port, args.bind or None, timeout=10)
    try:
        # authenticate
        p.send(284)
        p.wait_code(284, 5)
        p.send(820)
        auth = p.wait_code(820, 12)
        if field(auth, "needed") == "1":
            raise RuntimeError("device requires a password")
        run_id = uuid.uuid4().hex
        p.send(823, payload=f"app:openpolaris-canary-two-shot-{run_id};ver:1;")
        print(f"{stamp()} RUN source=scripted run_id={run_id}; any overlapping "
              "manual/app/script capture invalidates this run", flush=True)

        # camera state
        p.send(286)
        cam = p.wait_code(286, 10)
        print(f"{stamp()} CAMERA {cam}", flush=True)
        if field(cam, "state") != "1":
            print(f"{stamp()} FAIL camera not ready (state != 1)", flush=True)
            return 1
        expected_files = args.expected_files
        print(f"{stamp()} OUTPUT contract=explicit expected_files={expected_files} "
              f"expected_sp_prefix={args.expected_sp_prefix!r} "
              f"photoFormat_hint={field(cam, 'photoFormat')}", flush=True)

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

        shot_timeout = effective_shot_timeout(args.shot_timeout, args.bulb_seconds)
        if args.bulb_seconds is not None:
            bulb_index = resolve_bulb_shutter_index(p, args.bulb_shutter_index)
            set_shutter(p, bulb_index)
            print(f"{stamp()} BULB requested_seconds={args.bulb_seconds} "
                  f"shutter_index={bulb_index} shot_timeout={shot_timeout}s", flush=True)

        ok, _records, seen_paths = run_sequence(
            p, shot_count=2, shot_timeout=shot_timeout,
            expected_files=expected_files,
            expected_sp_prefix=args.expected_sp_prefix, run_id=run_id,
            bulb_seconds=args.bulb_seconds)
        if not ok:
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
