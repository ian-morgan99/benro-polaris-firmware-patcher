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

BIAS = constants["FILE_VA_BIAS"]
SITE = constants["SITE_VA"] - BIAS
LITERAL = constants["LITERAL_VA"] - BIAS
FORMAT = constants["FORMAT_VA"] - BIAS
TAIL = constants["TAIL_VA"] - BIAS
STRCPY = constants["STRCPY_VA"]
fresh = constants["FRESH_SITE"]
patched = constants["PATCHED_SITE"]
old_literal = constants["STOCK_FORMAT_LITERAL"]
tail_word = constants["STOCK_TAIL_WORD"]


def word(value):
    return struct.pack("<I", value)


def arm_immediate(enc):
    """Decode an ARM data-processing 12-bit immediate (8 bits rotated right)."""
    rot = ((enc >> 8) & 0xF) * 2
    val = enc & 0xFF
    return val if rot == 0 else ((val >> rot) | (val << (32 - rot))) & 0xFFFFFFFF


def decode(addr, raw):
    """Minimal ARM decoder: enough to pin the properties this patch claims."""
    enc = int.from_bytes(raw, "little")
    if (enc & 0x0E000000) == 0x0A000000:  # bits[27:25] == 101 -> branch group
        imm = enc & 0x00FFFFFF
        if imm & 0x00800000:
            imm -= 0x01000000
        return ("bl" if enc & 0x01000000 else "b", addr + 8 + imm * 4)
    if (enc & 0x0FFF0F00) == 0x03A00000:  # mov Rd, #imm
        return ("mov", arm_immediate(enc))
    if (enc & 0x0FBF0000) == 0x02800000:  # add Rd, Rn, #imm
        return ("add", {"rd": (enc >> 12) & 0xF, "rn": (enc >> 16) & 0xF,
                        "imm": arm_immediate(enc)})
    return ("?", enc)


def scan(buf, base_va, off_end):
    ops = {}
    for off in range(0, off_end, 4):
        op, detail = decode(base_va + off, buf[off:off + 4])
        ops.setdefault(op, []).append((base_va + off, detail))
    return ops


assert constants["STOCK_FORMAT_LITERAL"] == old_literal
assert constants["STRCPY_VA"] == STRCPY
assert len(patched) == 28, "patch span must remain exactly seven words"

# Stock code that follows the span: mov r1,#0 / ldr / ldr / add / add / bl memset.
STOCK_TAIL = (
    word(0xE3A01000) + word(0xE59F3064) + word(0xE7943003)
    + word(0xE2830E46) + word(0xE2800008) + word(0xEBFB8978)
)


def make_binary(path, site_bytes):
    # The synthetic image must carry real code after the span.  A buffer that
    # ends at the span cannot detect a patch that overruns it, which is exactly
    # how the previous generation passed while clobbering the memset length.
    buf = bytearray(max(FORMAT + 4, LITERAL + 4, TAIL + len(STOCK_TAIL)) + 16)
    buf[FORMAT:FORMAT + 3] = b"%s\0"
    buf[SITE:SITE + len(site_bytes)] = site_bytes
    buf[LITERAL:LITERAL + 4] = old_literal
    buf[TAIL:TAIL + len(STOCK_TAIL)] = STOCK_TAIL
    with open(path, "wb") as stream:
        stream.write(buf)
    return buf


def run(target):
    return subprocess.run([sys.executable, script, target, "--in-place"],
                          capture_output=True, text=True)


path = os.path.join(work, "polestar_app")
make_binary(path, fresh)

first = run(path)
assert first.returncode == 0, first.stdout + first.stderr
out = open(path, "rb").read()
body = out[SITE:SITE + len(patched)]
assert body == patched
assert out[LITERAL:LITERAL + 4] == old_literal

ops = scan(body, constants["SITE_VA"], len(patched))

# The version copy itself: exact strcpy of mFwVer into sysFwVer.
assert STRCPY in [d for _, d in ops.get("bl", [])], ops.get("bl")
adds = [d for _, d in ops.get("add", [])]
assert {"rd": 1, "rn": 0, "imm": 0x3a8} in adds, adds   # r1 = &mFwVer
assert {"rd": 0, "rn": 0, "imm": 0x3e8} in adds, adds   # r0 = &sysFwVer

# The regression this patch exists to fix: the stock memset length must still
# be set, and it must be set *after* the strcpy so the call cannot leave a
# caller-saved r2 behind.
movs = ops.get("mov", [])
assert any(d == 0x40 for _, d in movs), "mov r2, #0x40 was not restored"
len_va = next(va for va, d in movs if d == 0x40)
call_va = min(va for va, _ in ops["bl"])
assert len_va > call_va, "memset length is set before the strcpy call"

# Nothing past the span may change.
assert out[TAIL:TAIL + len(STOCK_TAIL)] == STOCK_TAIL, "patch overran into the memset setup"

before = out
second = run(path)
assert second.returncode == 0, second.stdout + second.stderr
assert "already patched" in second.stdout
assert open(path, "rb").read() == before

# The previous generation placed the strcpy in the final word of the span and
# destroyed the memset length.  It must not be accepted as this patch's state.
r2_path = os.path.join(work, "polestar_app.r2clobber")
make_binary(r2_path, word(0xE59F10CC) + word(0xE08F1001) + word(0xE59F007C)
            + word(0xE7940000) + word(0xE2801FEA) + word(0xE2800FFA)
            + word(0xEBFB8699))
bad = run(r2_path)
assert bad.returncode != 0, bad.stdout + bad.stderr
assert "unexpected polestar_app version site" in bad.stderr

# If the instruction after the span has drifted, fail closed rather than
# silently losing the memset length again.
drift_path = os.path.join(work, "polestar_app.drift")
drift = make_binary(drift_path, fresh)
drift[TAIL:TAIL + 4] = word(0xE1A00000)
with open(drift_path, "wb") as stream:
    stream.write(drift)
drifted = run(drift_path)
assert drifted.returncode != 0, drifted.stdout + drifted.stderr
assert "refusing to clobber the memset length" in drifted.stderr

print("[test_polestar_fwver_patch] PASS: exact copy, restored memset length, tail intact")
PY
