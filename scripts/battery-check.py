#!/usr/bin/env python3
"""Query camera battery (code 778) and append a timestamped reading to the log.

Usage:
  python3 scripts/battery-check.py            # query + append to docs/evidence/battery-log.csv
  python3 scripts/battery-check.py --no-log   # query only, print to stdout

Charge-state values observed: 1 = charging, 2 = not charging (full/idle).
"""
from __future__ import annotations

import csv
import os
import socket
import sys
import time

LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "docs", "evidence", "battery-log.csv")


def query(host: str = "192.168.0.1", port: int = 9090, bind: str | None = "192.168.0.4") -> tuple[int, int] | None:
    s = socket.socket()
    s.settimeout(20)
    if bind:
        s.bind((bind, 0))
    s.connect((host, port))
    try:
        for code in (284, 820, 823, 286):
            payload = "app:openpolaris-battery-check;ver:1;" if code == 823 else "-100"
            s.sendall(f"1&{code}&2&{payload}#".encode())
        s.sendall(b"1&778&2&-100#")
        buf = b""
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            try:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while b"#" in buf:
                    frame, buf = buf.split(b"#", 1)
                    text = frame.decode("ascii", "replace")
                    if text.startswith("778@"):
                        payload = text.split("@", 1)[1]
                        cap = charge = -1
                        for item in payload.split(";"):
                            if item.startswith("capacity:"):
                                cap = int(item.split(":", 1)[1])
                            elif item.startswith("charge:"):
                                charge = int(item.split(":", 1)[1])
                        return cap, charge
            except socket.timeout:
                break
        return None
    finally:
        s.close()


def main() -> int:
    no_log = "--no-log" in sys.argv
    result = query()
    if result is None:
        print("battery-check: no 778 response (camera unreachable?)")
        return 1
    cap, charge = result
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    state = {0: "unknown", 1: "charging", 2: "not-charging"}.get(charge, f"code-{charge}")
    print(f"{ts} battery capacity={cap}% charge_state={state} (raw charge={charge})")
    if not no_log:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        new = not os.path.exists(LOG_PATH)
        with open(LOG_PATH, "a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["timestamp_utc", "capacity_pct", "charge_state", "raw_charge"])
            w.writerow([ts, cap, state, charge])
        print(f"  appended to {os.path.relpath(LOG_PATH)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
