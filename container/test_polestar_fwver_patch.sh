#!/bin/sh
# Deterministic regression test for the code-780 exact-version patch.
set -eu

here="$(cd "$(dirname "$0")" && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT HUP INT TERM

python3 - "$work" "$here" <<'PY'
import os
import struct
import subprocess
import sys

work, here = sys.argv[1], sys.argv[2]
script = os.path.join(here, "polestar_fwver_patch.py")
BIAS = 0x10000
SITE = 0x13FB80 - BIAS
LITERAL = 0x13FC54 - BIAS
FORMAT = 0xA57324 - BIAS

def words(*values):
    return b"".join(struct.pack("<I", value) for value in values)

fresh = words(0xE59F10CC, 0xE08F1001, 0xE59F007C, 0xE7940000,
              0xE2800FFA, 0xEBFB88B0, 0xE3A02040)
patched = words(0xE59F10CC, 0xE08F1001, 0xE59F007C, 0xE7940000,
                0xE2802FEA, 0xE2800FFA, 0xEBFB88AF)
old_literal = struct.pack("<I", 0x0092E0FC)
new_literal = struct.pack("<I", 0x00917798)
wrong_literal = struct.pack("<I", 0x0091779c)

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
assert patched_data[LITERAL:LITERAL + 4] == new_literal
# The literal is consumed by ADD at SITE+4; ARM reads PC as instruction+8.
assert SITE + 4 + 8 + int.from_bytes(new_literal, "little") == FORMAT

before = patched_data
second = run()
assert second.returncode == 0, second.stdout + second.stderr
assert "already patched" in second.stdout
assert open(path, "rb").read() == before

# Regression for the 15k artifact: its literal resolved four bytes after the
# intended %s string, at the date format. Reject that mixed/invalid state
# rather than declaring it already patched.
bad_path = os.path.join(work, "polestar_app.bad")
bad_data = bytearray(before)
bad_data[LITERAL:LITERAL + 4] = wrong_literal
with open(bad_path, "wb") as stream:
    stream.write(bad_data)
bad = subprocess.run([sys.executable, script, bad_path, "--in-place"],
                     capture_output=True, text=True)
assert bad.returncode != 0, bad.stdout + bad.stderr
assert "unexpected polestar_app version site" in bad.stderr

print("[test_polestar_fwver_patch] PASS: fresh patch and idempotent re-run")
PY
