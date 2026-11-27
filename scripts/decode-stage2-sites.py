#!/usr/bin/env python3
"""Resolve Stage-2 refusal `site=` addresses to pgphoto function names.

The gate logs `site=%x` from __builtin_return_address(0) at the claim site, so it is a
return address inside pgphoto. pgphoto.stage2ondisk is a non-PIE ARM EXEC (Type: EXEC,
entry 0x15ed8), which means those addresses are absolute and resolvable with addr2line --
no runtime base offset to subtract. That makes "which pgphoto operation holds the claim"
answerable statically instead of by guesswork.

Defect A on v118 asked exactly that: a config claim at site 0x100540 was held 4818 ms and
grew to 5911 ms, and Clog carries no timestamps, so it could not be lined up with camera
traffic. Resolving the sites answers it directly:

    0x100540 deal_camera_control_handler   gpManager.c:2832   kind=2 CONFIG
    0x1013ac capture_image                 gpManager.c:3059   kind=0 CONTROL
    0x101b0c capture_image_with_Bulb       gpManager.c:3195   kind=0 CONTROL
    0x102cd4 updateCameraViewFinder        gpManager.c:3566   kind=0 CONTROL
    0x102ff0 updateCameraAutoFocus         gpManager.c:3635   kind=0 CONTROL
    0x102ba0 updateLivePreView             gpManager.c:3531   kind=1 PREVIEW

The binary must be the one bound to the version that produced the log. The ledger in
docs/RELEASE-VERSION-STATE.md maps display fwver to patcher/libgphoto2 commits; passing a
mismatched binary silently yields plausible wrong function names, which is worse than an
unresolved address, so --expect-build-id refuses to annotate unless the binary's build id
matches.

Usage:
  scripts/decode-stage2-sites.py --binary out/<build>/stage2-ondisk/ondisk/pgphoto.stage2ondisk \
      --input refusals.txt
  ssh root@rig 'grep -ah "admission refused" /app/sd/system/log/Clog_*.log' \
      | scripts/decode-stage2-sites.py --binary <path>
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

# kind= is enum stage2_camera_operation: CONTROL, PREVIEW, CONFIG, SET.
KIND = {0: "CONTROL", 1: "PREVIEW", 2: "CONFIG", 3: "SET"}

# tid/owner_tid/depth/held_ms/stolen were added in v118. Refusals from before that carry
# only site/kind/owner_site/last_owner_kind/generation, and those older lines are the ones
# needed to test whether defect A predates v118 -- so they must decode too. Requiring the
# newer fields silently dropped 138 of 375 lines on the first run.
REFUSE_RE = re.compile(
    r"admission refused: site=(?P<site>[0-9a-f]+) kind=(?P<kind>\d+) "
    r"owner_site=(?P<owner>[0-9a-f]+) last_owner_kind=(?P<lkind>\d+) "
    r"generation=(?P<gen>\d+)"
    r"(?:.*?held_ms=(?P<held>\d+) stolen=(?P<stolen>\d+))?"
)


def resolve(binary: str, addrs: list) -> dict:
    """addr2line in one batched call; returns {addr: 'func file:line'}."""
    cmd = ["arm-linux-gnueabi-addr2line", "-f", "-C", "-e", binary] + [f"0x{a}" for a in addrs]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "addr2line failed")
    out = proc.stdout.splitlines()
    # addr2line emits one function line then one location line per address.
    found = {}
    for i, a in enumerate(addrs):
        fn = out[2 * i] if 2 * i < len(out) else "?"
        loc = out[2 * i + 1] if 2 * i + 1 < len(out) else "?"
        found[a] = (fn, loc)
    return found


def build_id(binary: str) -> str:
    proc = subprocess.run(["readelf", "-n", binary], capture_output=True, text=True)
    m = re.search(r"Build ID: ([0-9a-f]+)", proc.stdout)
    return m.group(1) if m else ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--binary", required=True, help="pgphoto.stage2ondisk for the logged version")
    ap.add_argument("--input", help="refusal log file; default stdin")
    ap.add_argument("--expect-build-id", help="refuse to annotate unless the binary's Build ID matches")
    ap.add_argument("--summary", action="store_true", help="aggregate counts instead of per-line output")
    args = ap.parse_args()

    binary = Path(args.binary)
    if not binary.is_file():
        print(f"error: no such binary: {binary}", file=sys.stderr)
        return 1

    # A non-PIE EXEC is what makes these addresses absolute. On a PIE build the same
    # numbers would be offsets from an unreported load base, and annotating them would
    # produce confident wrong function names.
    r = subprocess.run(["readelf", "-h", str(binary)], capture_output=True, text=True)
    if "Type:" not in r.stdout or "EXEC" not in r.stdout:
        print("error: binary is not a non-PIE EXEC; site= addresses would be load-base "
              "relative and cannot be resolved without the runtime base", file=sys.stderr)
        return 1

    if args.expect_build_id:
        got = build_id(str(binary))
        if not got.startswith(args.expect_build_id):
            print(f"error: binary Build ID {got or '(none)'} does not match expected "
                  f"{args.expect_build_id}; refusing to annotate with a possibly wrong binary",
                  file=sys.stderr)
            return 1

    text = Path(args.input).read_text(errors="replace") if args.input else sys.stdin.read()
    matches = list(REFUSE_RE.finditer(text))
    if not matches:
        print("no refusal lines found", file=sys.stderr)
        return 1

    addrs = sorted({m.group("site") for m in matches} | {m.group("owner") for m in matches})
    sym = resolve(str(binary), addrs)

    def name(a):
        fn, loc = sym.get(a, ("?", "?"))
        short = loc.split("/")[-1] if "/" in loc else loc
        return f"{a} {fn} ({short})"

    if args.summary:
        counts = {}
        for m in matches:
            key = (name(m.group("site")), KIND.get(int(m.group("kind")), "?"),
                   name(m.group("owner")), KIND.get(int(m.group("lkind")), "?"))
            counts[key] = counts.get(key, 0) + 1
        print(f"{len(matches)} refusals, {len(counts)} distinct site/owner pairs")
        for (s, sk, o, ok), n in sorted(counts.items(), key=lambda kv: -kv[1]):
            print(f"  {n:5d}  {s} wants {sk:8s}  held by {o} ({ok})")
        return 0

    for m in matches:
        held = m.group("held")
        tail = (f"held_ms={held} stolen={m.group('stolen')}" if held is not None
                else "held_ms=? stolen=? (pre-v118 line)")
        print(f"{name(m.group('site'))} [{KIND.get(int(m.group('kind')), '?')}] "
              f"refused; held by {name(m.group('owner'))} "
              f"[{KIND.get(int(m.group('lkind')), '?')}] "
              f"{tail} gen={m.group('gen')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
