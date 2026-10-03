#!/bin/sh
# Deterministic regression test for the code-780 exact-version patch.
set -eu

here="$(cd "$(dirname "$0")" && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT HUP INT TERM

python3 - "$work" "$here" <<'PY'
import os
import runpy
import struct
import subprocess
import sys

work, here = sys.argv[1], sys.argv[2]
script = os.path.join(here, "polestar_fwver_patch.py")
constants = runpy.run_path(script)
BIAS = 0x10000
SITE = 0x13FB80 - BIAS
LITERAL = 0x13FC54 - BIAS
FORMAT = 0xA57324 - BIAS
STRCPY = 0x21604

def words(*values):
    return b"".join(struct.pack("<I", value) for value in values)

fresh = words(0xE59F10CC, 0xE08F1001, 0xE59F007C, 0xE7940000,
              0xE2800FFA, 0xEBFB88B0, 0xE3A02040)
patched = words(0xE59F10CC, 0xE08F1001, 0xE59F007C, 0xE7940000,
                0xE2801FEA, 0xE2800FFA, 0xEBFB8699)
old_literal = struct.pack("<I", 0x0092E0FC)

# The replacement keeps the stock format-pool word untouched.  The safety
# property is now the non-variadic strcpy call, not a hand-maintained
# PC-relative format literal.
assert constants["STOCK_FORMAT_LITERAL"] == old_literal
assert constants["STRCPY_VA"] == STRCPY
assert "NEW_FORMAT_LITERAL" not in open(os.path.join(here, "polestar_fwver_patch.py"), encoding="utf-8").read()

data = bytearray(max(FORMAT + 4, LITERAL + 4, SITE + len(fresh)) + 16)
data[FORMAT:FORMAT + 3] = b"%s\0"
data[SITE:SITE + len(fresh)] = fresh
data[LITERAL:LITERAL + 4] = old_literal
path = os.path.join(work, "polestar_app")
with open(path, "wb") as stream:
    stream.write(data)

def run():
    return subprocess.run([sys.executable, script, path, "--in-place"],
                          capture_output=True, text=True)

first = run()
assert first.returncode == 0, first.stdout + first.stderr
patched_data = open(path, "rb").read()
assert patched_data[SITE:SITE + len(patched)] == patched
assert patched_data[LITERAL:LITERAL + 4] == old_literal
# Decode the three changed instructions enough to pin the actual convention:
# r1 = base + mFwVer, r0 = base + sysFwVer, then the stock strcpy PLT target.
assert patched_data[SITE + 16:SITE + 20] == struct.pack("<I", 0xE2801FEA)
assert patched_data[SITE + 20:SITE + 24] == struct.pack("<I", 0xE2800FFA)
branch = int.from_bytes(patched_data[SITE + 24:SITE + 28], "little")
imm = branch & 0x00FFFFFF
if imm & 0x00800000:
    imm -= 0x01000000
assert SITE + BIAS + 24 + 8 + (imm << 2) == STRCPY
before = patched_data
second = run()
assert second.returncode == 0, second.stdout + second.stderr
assert "already patched" in second.stdout
assert open(path, "rb").read() == before

# A stale variadic-format patch is not accepted as this patch's idempotent
# state.  It must fail closed rather than being mistaken for the safe copy.
bad_path = os.path.join(work, "polestar_app.bad")
bad_data = bytearray(before)
bad_data[SITE:SITE + len(patched)] = words(
    0xE59F10CC, 0xE08F1001, 0xE59F007C, 0xE7940000,
    0xE2802FEA, 0xE2800FFA, 0xEBFB88AF,
)
with open(bad_path, "wb") as stream:
    stream.write(bad_data)
bad = subprocess.run([sys.executable, script, bad_path, "--in-place"],
                     capture_output=True, text=True)
assert bad.returncode != 0, bad.stdout + bad.stderr
assert "unexpected polestar_app version site" in bad.stderr

print("[test_polestar_fwver_patch] PASS: fresh patch and idempotent re-run")
PY
