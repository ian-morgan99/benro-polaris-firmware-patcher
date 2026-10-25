#!/usr/bin/env python3
"""Probe two K-3 III symptoms reported against 6.0.0.54.70.

Symptom A -- "the additional B setting in the list of exposure times": command 268
returns a shutter option list. Dump it verbatim and flag every entry that does not
parse as a duration, plus where the current index points.

Symptom B -- "non-timed bulb": the app's held-shutter form is state:1;bulb:0;c:-1;
(bulb zero) or with bulb omitted entirely. Send each and record the state timeline.

Symptom A is read-only. Symptom B sends capture requests but does not write a shutter
index; on every log so far the held form is refused rather than exposing.
"""
import importlib.util
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cp", REPO / "scripts" / "canary-probe.py")
cp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cp)

HOST, PORT, BIND = "192.168.0.1", 9090, "192.168.0.4"
t0 = time.monotonic()


def stamp():
    return f"+{time.monotonic() - t0:6.2f}s"


p = cp.Polaris(HOST, PORT, BIND, timeout=10)
p.send(284); p.wait_code(284, 5)
p.send(820)
auth = p.wait_code(820, 12)
if cp.field(auth, "needed") == "1":
    raise SystemExit("device requires a password")
p.send(823, payload="app:openpolaris-shutter-probe;ver:1;")
p.send(286)
cam = p.wait_code(286, 10)
print(f"{stamp()} CAMERA {cam}", flush=True)
if cp.field(cam, "state") != "1":
    raise SystemExit(f"camera not ready: {cam}")

print("\n===== SYMPTOM A: the 268 exposure-time list =====", flush=True)
for attempt in (1, 2):
    current, options = cp.shutter_options(p, timeout=10, quiet=True)
    print(f"{stamp()} pass {attempt}: entries={len(options)} current index={current}", flush=True)
    bad = [(i, e) for i, e in enumerate(options) if cp.parse_shutter_seconds(e) is None]
    if current is not None:
        print(f"  current label: {options[current]!r} "
              f"parses to {cp.parse_shutter_seconds(options[current])}", flush=True)
    print(f"  entries that do NOT parse as a duration: {bad}", flush=True)
    print(f"  first 6: {options[:6]}", flush=True)
    print(f"  last 4:  {options[-4:]}", flush=True)
    if attempt == 1:
        time.sleep(1.5)

print("\n===== SYMPTOM B: non-timed (held) bulb =====", flush=True)
for payload in ("state:1;bulb:0;c:-1;", "state:1;c:-1;"):
    print(f"{stamp()} TX 264 {payload}", flush=True)
    p.send(264, subtype=4, payload=payload)
    states = []
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        try:
            code, body = p.frame(deadline)
        except Exception as exc:
            print(f"  {stamp()} frame error: {type(exc).__name__}: {exc}", flush=True)
            break
        if code == 264:
            st = cp.field(body, "state")
            states.append(st)
            print(f"  {stamp()} 264 state={st}", flush=True)
            if st is not None and st.startswith("-"):
                break
    print(f"  -> states observed: {states}", flush=True)
    time.sleep(1.5)

print("\n===== camera state after probes =====", flush=True)
p.send(286)
print(f"{stamp()} {p.wait_code(286, 10)}", flush=True)
