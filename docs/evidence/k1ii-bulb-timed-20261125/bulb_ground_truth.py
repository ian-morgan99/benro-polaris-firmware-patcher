#!/usr/bin/env python3
"""K-1 II / K-3 III timed-Bulb ground truth: request N seconds, read what the body shot.

Restored into git after /tmp/exif was wiped mid-session (scripts and both ground-truth
JPEGs were lost with it). Nothing measurement-related belongs in /tmp on this host.

Port is discovered by USB product id on every run. The K-1 II moved from usb:001,011 to
usb:001,013 after files were deleted from the card; a hardcoded port silently targets
nothing. PIDs: 0x0183 K-1 II, 0x0189 K-3 III.

Three separate things get measured, because conflating them caused a wrong conclusion:
  1. what the driver derived and wrote (driver log "applying N s")
  2. how long the body took to publish output (stop-edge wall time)
  3. what the body actually exposed for (EXIF ExposureTime, a RATIONAL - see read_exif.py)

Requires POLARIS_PENTAX_DRIVER_PREFIX built by scripts/build-host-driver-prefix.sh
(pentax_research_capture=true) and tools/pentax_bulb_direct.c compiled against it.
"""
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from read_exif import exposure_seconds, parse_tiff  # noqa: E402

P = Path(os.environ.get("POLARIS_PENTAX_DRIVER_PREFIX",
                        "/home/ian/polaris-v101/out/v117-host-driver-prefix"))
os.environ.update(LD_LIBRARY_PATH=str(P / "lib"), LC_ALL="C")
os.environ["CAMLIBS"] = str(next((P / "lib").glob("libgphoto2/*/")))
os.environ["IOLIBS"] = str(next((P / "lib").glob("libgphoto2_port/*/")))

MODELS = {0x0183: "Pentax K-1 Mark II (PTP mode)",
          0x0189: "Pentax K-3 Mark III (PTP mode)"}
HELPER = os.environ.get("BULB_HELPER", "/tmp/k1ii_bulb_direct")


def find_port(pid):
    for d in Path("/sys/bus/usb/devices").glob("*/"):
        if not (d / "idVendor").exists():
            continue
        if int((d / "idVendor").read_text().strip(), 16) != 0x25FB:
            continue
        if int((d / "idProduct").read_text().strip(), 16) == pid:
            return "usb:%03d,%03d" % (int((d / "busnum").read_text()),
                                      int((d / "devnum").read_text()))
    return None


PID = int(sys.argv[1], 16) if len(sys.argv) > 1 else 0x0183
HOLD = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
OUTDIR = Path(sys.argv[3]) if len(sys.argv) > 3 else HERE / "shots"
MODEL = MODELS[PID]
PORT = find_port(PID)
if not PORT:
    sys.exit(f"no Pentax pid=0x{PID:04x} on the bus (is the body in PTP mode?)")
if not Path(HELPER).exists():
    sys.exit(f"helper missing: {HELPER}\n  cc -O2 -I$PREFIX/include/gphoto2 "
             f"tools/pentax_bulb_direct.c -o {HELPER} -L$PREFIX/lib "
             f"-lgphoto2 -lgphoto2_port")
print(f"{MODEL}  port={PORT} (discovered)  hold={HOLD}s")

OUTDIR.mkdir(parents=True, exist_ok=True)


def gp(*args, timeout=300):
    r = subprocess.run(["gphoto2", "--port", PORT, "--camera", MODEL, *args],
                       capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout + r.stderr


def cfg(name):
    _, out = gp("--get-config", f"/main/settings/{name}")
    m = re.search(r"(?m)^Current:\s*(.+)", out)
    return m.group(1).strip() if m else "?"


def files():
    """{name: gphoto2 1-based index}. Do not assume list order matches numbering."""
    _, out = gp("--list-files", timeout=90)
    return {m.group(2): int(m.group(1)) + 1
            for m in re.finditer(r"^#(\d+)\s+(\S+)", out, re.M)}


orig = cfg("capturetarget")
before = files()
print(f"capturetarget={orig}  card files={len(before)}")

switched = False
if orig != "Memory card":
    gp("--set-config", "capturetarget=1")
    now = cfg("capturetarget")
    switched = (now == "Memory card")
    print(f"switch attempt -> readback={now}  "
          + ("OK" if switched else
             "BUG: set_config reported success but target unchanged (silent no-op)"))

try:
    seen, stop = {}, threading.Event()

    def poll():
        t0 = time.monotonic()
        while not stop.is_set():
            try:
                n = len(files())
            except Exception:
                time.sleep(3)
                continue
            if n not in seen:
                seen[n] = time.monotonic() - t0
                print(f"  [{time.monotonic()-t0:5.1f}s] files={n}")
            time.sleep(3)

    th = threading.Thread(target=poll, daemon=True)
    th.start()
    t0 = time.monotonic()
    r = subprocess.run([HELPER, PORT, MODEL, str(HOLD), "1", "1"],
                       capture_output=True, text=True, timeout=420)
    wall = time.monotonic() - t0
    stop.set()
    th.join(timeout=8)

    applied = re.findall(r"applying (\d+) s shutter speed", r.stdout)
    edges = re.findall(r"start=(\S+) stop=(\S+)", r.stdout)
    print(f"\ndriver returned {wall:.1f}s  applied={applied}  edges={edges}")

    after = files()
    new = [f for f in after if f not in before]
    grew = [t for n, t in sorted(seen.items()) if n > len(before)]
    if grew:
        print(f"card file appeared at {grew[0]:.1f}s vs driver return {wall:.1f}s -> "
              + ("wait is AVOIDABLE overhead" if grew[0] < wall - 4
                 else "wait matches body-side latency (exposure, not polling)"))
    print(f"new files: {new}")

    for name in sorted(new):
        out = OUTDIR / f"{int(HOLD)}s_{name}"
        gp("--get-file", str(after[name]), "--filename", str(out), timeout=420)
        # gphoto2 nests under the store path; find whatever it wrote.
        got = sorted(OUTDIR.rglob(name), key=lambda p: p.stat().st_mtime, reverse=True)
        if not got:
            print(f"  {name}: download failed")
            continue
        f = got[0]
        buf = f.read_bytes()
        i = buf.find(b"Exif\0\0")
        t = parse_tiff(buf, i + 6) if i >= 0 else None
        s = exposure_seconds(t) if t else None
        if s is None:
            print(f"  {name}: no ExposureTime ({len(buf)} bytes)")
            continue
        want = int(applied[-1]) if applied else HOLD
        ok = abs(s - want) < 0.25
        print(f"  {name}: EXIF exposure {s:.3f}s  requested={HOLD}s "
              f"driver_asked={want}s -> {'PASS' if ok else 'FAIL'}")
finally:
    if switched and orig != "Memory card":
        gp("--set-config", "capturetarget=0")
        print(f"restored capturetarget -> {cfg('capturetarget')}")
