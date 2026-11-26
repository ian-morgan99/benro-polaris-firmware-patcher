#!/usr/bin/env python3
"""k1ii-capture-trace.py -- pull a redacted, correlated log trace for one capture.

Why this exists
---------------
The two device logs answer different questions and neither is enough alone:

  * Clog (pgphoto + our loader) holds the internals: `will CAPTURE_IMAGE`, `[pentax] boundary=...`,
    `capture end -N ms`, `get file to buffer`, `[stage2] ...`. This is where the invariant ~6.1 s
    post-candidate wait and the missing RAW sibling would show up.
  * Mlog (polestar_app / mount) holds the app-facing timeline: every `SP_SendMsgToApp` with its code
    and payload. That is what the user's phone actually saw and when, so it is the record of
    "the app said Shot failed at T+3.6 s".

Pulling them by hand went wrong repeatedly this session: grepping /app/Clog.txt for loader output
returns nothing because the loader writes to the SD-rotated Clog_* file, and a plain `cat` of either
log can contain the head's auth handshake -- base64 account material (`password:`, `securityA:`)
which must never reach git. So this script records byte offsets first, slices only the window it
caused, scrubs credentials with the same patterns as
docs/evidence/v117-k1ii-regression-20261125/redact-credentials.py, and refuses to write if anything
still matches.

Output is text only -- no images, no raw JSON dumps (operator directive). Traces are small by
construction: only lines matching --grep are kept.

Usage:
  python3 scripts/k1ii-capture-trace.py --label jpgraw --bulb 0 --out docs/evidence/<dir>
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TERMINAL = {0, -1, -6, -110, -112, -1005}

# Same credential shapes the v117 evidence dir scrubs. Kept here so a trace can never be written
# without them being applied first.
REDACTIONS = [
    (re.compile(r"(password:)[A-Za-z0-9+/=]+"), r"\1[REDACTED]"),
    (re.compile(r"(securityA:)[A-Za-z0-9+/=]+"), r"\1[REDACTED]"),
    (re.compile(r"(username:)[^;\]]+"), r"\1[REDACTED]"),
    (re.compile(r"(token\"?\s*[:=]\s*)[^;\s\"]+"), r"\1[REDACTED]"),
]
ANSI = re.compile(r"\x1b\[[0-9;]*m")

DEFAULT_GREP = ("will CAPTURE|capture end|get file to buffer|savePhotoToAblum|\\[pentax\\]|"
                "\\[stage2\\]|code\\[264\\]|code\\[773\\]|SP_SendMsgToApp.*code\\[(264|773|286)\\]|"
                "capture_image_with_Bulb|blub|bulb time|get photo|-1005|-110|-112|admission refused")


def load_client():
    spec = importlib.util.spec_from_file_location("cp", REPO / "scripts" / "canary-probe.py")
    cp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cp)
    return cp


def ssh(user_host: str, cmd: str, timeout: int = 60) -> str:
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", user_host, cmd],
                       capture_output=True, text=True, timeout=timeout)
    return r.stdout


def scrub(text: str) -> tuple[str, int]:
    hits = 0
    for pat, repl in REDACTIONS:
        text, n = pat.subn(repl, text)
        hits += n
    return text, hits


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="192.168.0.1")
    ap.add_argument("--port", type=int, default=9090)
    ap.add_argument("--bind", default="192.168.0.4")
    ap.add_argument("--ssh", default="root@192.168.0.1")
    ap.add_argument("--label", required=True, help="short name for the trace file")
    ap.add_argument("--bulb", type=int, default=0, help="bulb ms (0 = timed exposure)")
    ap.add_argument("--shutter-index", type=int, default=None)
    ap.add_argument("--out", default=None, help="directory for the redacted trace")
    ap.add_argument("--grep", default=DEFAULT_GREP, help="regex of lines to keep")
    ap.add_argument("--timeout", type=float, default=150.0)
    args = ap.parse_args()

    cp = load_client()
    sd_glob = "/app/sd/system/log/Clog_*"

    def offsets() -> dict[str, int]:
        """Byte sizes of every log we care about, keyed by path.

        Tracking only the newest SD-rotated Clog was wrong: pgphoto rotates that file during normal
        operation, so a rotation mid-capture silently moved the capture's own lines into a path this
        script had never recorded an offset for -- producing a trace with no internals at all. Keep
        the three newest so a single rotation is covered.
        """
        out: dict[str, int] = {}
        newest = ssh(args.ssh, f"ls -1t {sd_glob} 2>/dev/null | head -3").split()
        for path in newest:
            out[path] = int(ssh(args.ssh, f"stat -c %s {shlex.quote(path)} 2>/dev/null || echo 0")
                            .strip() or 0)
        out["/app/Clog.txt"] = int(ssh(args.ssh, "stat -c %s /app/Clog.txt 2>/dev/null || echo 0")
                                   .strip() or 0)
        out["/app/Mlog.txt"] = int(ssh(args.ssh, "stat -c %s /app/Mlog.txt 2>/dev/null || echo 0")
                                   .strip() or 0)
        return out

    before = offsets()

    p = cp.Polaris(args.host, args.port, args.bind, timeout=10)
    p.send(284); p.wait_code(284, 5)
    p.send(820); p.wait_code(820, 10)
    p.send(823, payload=f"app:trace-{args.label};ver:1;")
    p.send(286); p.wait_code(286, 10)

    shutter_note = "unchanged"
    if args.shutter_index is not None:
        p.send(268)
        cur = None
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            try:
                c, b = p.frame(time.monotonic() + 8)
            except Exception:
                break
            if c == 268:
                cur = cp.field(b, "V")
                break
        if cur is not None and int(cur) != args.shutter_index:
            p.send(261, payload=f"s:{args.shutter_index};")
            ret = None
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                try:
                    c, b = p.frame(time.monotonic() + 8)
                except Exception:
                    break
                if c == 261:
                    ret = cp.field(b, "ret")
                    break
            shutter_note = f"{cur} -> {args.shutter_index} ret={ret}"

    timeline: list[dict] = []
    t0 = time.monotonic()
    wall_start = time.strftime("%H:%M:%S")
    payload = f"state:1;bulb:{args.bulb};c:-1;"
    p.send(264, subtype=4, payload=payload)
    deadline = t0 + args.timeout
    while time.monotonic() < deadline:
        try:
            c, b = p.frame(deadline)
        except Exception:
            break
        if c == 264:
            v = cp.field(b, "state")
            try:
                iv = int(v)
            except (TypeError, ValueError):
                continue
            timeline.append({"ms": round((time.monotonic() - t0) * 1000.0, 1),
                             "code": c, "payload": b[:200]})
            if iv in TERMINAL:
                break
        elif c == 773:
            timeline.append({"ms": round((time.monotonic() - t0) * 1000.0, 1),
                             "code": c, "payload": b[:200]})

    total_ms = round((time.monotonic() - t0) * 1000.0, 1)
    p.close()

    # Slice only what this capture produced, then scrub before anything is written or printed.
    sections: list[str] = []
    for path, off in offsets().items():
        prev = before.get(path, 0)
        if off <= prev:
            continue
        note = "" if path in before else "  (file appeared during the capture)"
        raw = ssh(args.ssh,
                  f"tail -c +{prev + 1} {shlex.quote(path)} 2>/dev/null | "
                  f"grep -aE {shlex.quote(args.grep)} | head -400")
        text, hits = scrub(ANSI.sub("", raw))
        if any(pat.search(text) for pat, _ in REDACTIONS):
            print(f"REFUSING to write: {path} still matches a credential pattern", file=sys.stderr)
            return 2
        sections.append(f"----- {path} (+{off - prev} bytes, {hits} redaction(s)){note} -----\n{text}")

    header = [f"# capture trace label={args.label}",
              f"wall_start={wall_start} total_ms={total_ms} request={payload}",
              f"shutter={shutter_note}", "", "== control-socket timeline (what the app saw) =="]
    for ev in timeline:
        header.append(f"  {ev['ms']:>9} ms  code {ev['code']}  {ev['payload']}")
    body = "\n".join(header) + "\n\n== device log slices ==\n\n" + "\n".join(sections)

    if args.out:
        outdir = Path(args.out)
        outdir.mkdir(parents=True, exist_ok=True)
        dest = outdir / f"{args.label}.trace.txt"
        dest.write_text(body)
        print(f"wrote {dest} ({len(body)} bytes)", flush=True)

    print(body[:6000], flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
