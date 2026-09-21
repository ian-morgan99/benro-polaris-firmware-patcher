#!/bin/sh
# Issue #120 deterministic tests for polestar_bulb_patch.py fail-closed
# unique-site validation (TA review): 0 anchors, 2 anchors, unrelated REPL
# bytes elsewhere, correct single patch, and idempotent re-run.
set -eu

here="$(cd "$(dirname "$0")" && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT HUP INT TERM

python3 - "$work" "$here" <<'PY'
import os, subprocess, sys

work, here = sys.argv[1], sys.argv[2]
script = os.path.join(here, "polestar_bulb_patch.py")

ANCHOR = bytes.fromhex("1c301be5" "fa2fa0e3" "920303e0" "1c300be5")
REPL   = bytes.fromhex("1c301be5" "0030a0e3" "000000e1" "1c300be5")
FILLER = b"\x00" * 64

def run(path):
    p = subprocess.run([sys.executable, script, path, "--in-place"],
                       capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr

def check(name, cond):
    print(("  PASS: " if cond else "  FAIL: ") + name)
    if not cond:
        sys.exit(1)

# 1) zero anchors (and no REPL) -> FATAL exit 1
p = os.path.join(work, "no-anchor.bin")
open(p, "wb").write(FILLER)
rc, out = run(p)
check("0 anchors -> fatal exit 1", rc == 1 and "neither anchor nor replacement" in out)

# 2) two anchors -> FATAL exit 1, binary unchanged
p = os.path.join(work, "two-anchors.bin")
open(p, "wb").write(FILLER + ANCHOR + FILLER + ANCHOR + FILLER)
rc, out = run(p)
data = open(p, "rb").read()
check("2 anchors -> fatal exit 1", rc == 1 and "anchor found 2 times" in out)
check("2 anchors -> binary unchanged (anchor still present)", data.count(ANCHOR) == 2)

# 3) unrelated REPL bytes elsewhere (with a single anchor) -> FATAL: the
#    replacement marker is not unique, so we cannot prove which site is the
#    264 PHOTO_RECORD handler.
p = os.path.join(work, "stray-repl.bin")
open(p, "wb").write(FILLER + REPL + FILLER + ANCHOR + FILLER)
rc, out = run(p)
check("unrelated REPL elsewhere -> fatal exit 1 (mixed state)", rc == 1 and "mixed state" in out)

# 4) correct single patch: one anchor, no REPL anywhere -> patched + verified.
p = os.path.join(work, "single.bin")
open(p, "wb").write(FILLER + ANCHOR + FILLER)
rc, out = run(p)
data = open(p, "rb").read()
check("1 anchor -> patched exit 0", rc == 0 and "patched at file offset" in out)
check("1 anchor -> REPL present exactly once", data.count(REPL) == 1)
check("1 anchor -> ANCHOR gone", data.count(ANCHOR) == 0)

# 5) idempotent re-run on the patched binary: unique REPL site -> exit 0, no change.
before = open(p, "rb").read()
rc, out = run(p)
after = open(p, "rb").read()
check("idempotent re-run -> exit 0 'already patched'", rc == 0 and "already patched" in out)
check("idempotent re-run -> bytes unchanged", before == after)

# 6) idempotent re-run with REPL present TWICE (corrupt/duplicated) -> FATAL.
p2 = os.path.join(work, "repl-twice.bin")
open(p2, "wb").write(FILLER + REPL + FILLER + REPL + FILLER)
rc, out = run(p2)
check("REPL present 2x on re-run -> fatal exit 1", rc == 1 and "replacement bytes present 2 times" in out)

print("[test_polestar_bulb_patch] ALL PASS")
PY
