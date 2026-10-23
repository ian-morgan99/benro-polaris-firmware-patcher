#!/usr/bin/env python3
"""Send the exact Benro Connect bulb request and record the state timeline.

The app sends code 264 with payload `state:1;bulb:N;c:-1;` (seen verbatim in
/app/Mlog.txt as `rcv msg from App[..]:type:4;code:264;val:state:1;bulb:40;c:-1;`).
canary-probe.py's --bulb-seconds instead writes a shutter index through 261 and
takes the start/stop action path, which libgphoto2 refuses with state:-6 whenever
PENTAX_CONDITION_BULB_TIMER is set. That refusal is not what the user sees, so to
reproduce the reported "image processing" then "shot failed" we must speak the
app's own request.

Every frame is timestamped so the deadline can be measured against the requested
duration rather than inferred.
"""
import importlib.util
import socket
import sys
import time
from pathlib import Path

# Lives in scripts/, so the repo root is one level up.
REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cp", REPO / "scripts" / "canary-probe.py")
cp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cp)

BULB_SECONDS = int(sys.argv[1]) if len(sys.argv) > 1 else 30
HOST = "192.168.0.1"
PORT = 9090
BIND = "192.168.0.4"

t0 = time.monotonic()


def stamp():
    return f"+{time.monotonic() - t0:6.2f}s"


p = cp.Polaris(HOST, PORT, BIND, timeout=10)
p.send(284)
p.wait_code(284, 5)
p.send(820)
auth = p.wait_code(820, 12)
if cp.field(auth, "needed") == "1":
    raise SystemExit("device requires a password")
p.send(823, payload="app:openpolaris-bulb-repro;ver:1;")
p.send(286)
cam = p.wait_code(286, 10)
print(f"{stamp()} CAMERA {cam}", flush=True)
if cp.field(cam, "state") != "1":
    raise SystemExit(f"camera not ready: {cam}")

# Preview on, exactly as Benro Connect leaves it during a bulb shot.
p.send(291, subtype=2, payload="state:1;")
print(f"{stamp()} PREVIEW start sent", flush=True)
time.sleep(1.0)

payload = f"state:1;bulb:{BULB_SECONDS};c:-1;"
print(f"{stamp()} TX 1&264&4&{payload}#", flush=True)
p.send(264, subtype=4, payload=payload)

deadline = time.monotonic() + max(240, (BULB_SECONDS * 3) + 60)
states = []
files = []
while time.monotonic() < deadline:
    try:
        code, body = p.frame(deadline)
    except (TimeoutError, socket.timeout) as exc:
        print(f"{stamp()} FRAME-TIMEOUT {exc}", flush=True)
        break
    if code == 264:
        st = cp.field(body, "state")
        states.append(st)
        print(f"{stamp()} 264 state={st} full={body!r}", flush=True)
        if st is not None and int(st) <= 0:
            print(f"{stamp()} TERMINAL state={st} after {time.monotonic() - t0:.1f}s "
                  f"(requested bulb={BULB_SECONDS}s)", flush=True)
            break
    elif code == 773:
        path = cp.field(body, "path")
        files.append(path)
        print(f"{stamp()} 773 FILE {path}", flush=True)
    elif code == 775:
        pass
    else:
        print(f"{stamp()} code={code} {body[:90]!r}", flush=True)

print(f"{stamp()} SUMMARY states={states} files={files}", flush=True)
