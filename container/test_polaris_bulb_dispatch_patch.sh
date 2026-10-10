#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PATCHER_ROOT="$ROOT" PYTHONPATH="$ROOT/container" python3 - <<'PY'
import struct

import polaris_bulb_dispatch_patch as patch

base = 0x1000
addresses = {
    "burst": 0x1100,
    "bulb": 0x3100,
    "manufacturer": 0x4100,
    "name": 0x4200,
    "strcasestr": 0x4300,
}
offsets = {key: value - base for key, value in addresses.items()}
offsets["bulb_function"] = 0x300
segment = {
    "offset": 0,
    "vaddr": base,
    "filesz": 0x1000,
    "memsz": 0x1000,
    "align": 0x1000,
    "phdr_offset": 0x40,
    "next_offset": 0x2000,
    "next_vaddr": 0x5000,
    "allocated_sections": [],
}
data = bytearray(0x5000)
struct.pack_into("<I", data, segment["phdr_offset"] + 16, segment["filesz"])
struct.pack_into("<I", data, segment["phdr_offset"] + 20, segment["memsz"])
for i, word in enumerate(patch.BURST_PROLOGUE):
    struct.pack_into("<I", data, offsets["burst"] + i * 4, word)
for i, word in enumerate(patch.BULB_PROLOGUE):
    struct.pack_into("<I", data, offsets["bulb_function"] + i * 4, word)
indirect_bulb_pointer_offset = 0x400
struct.pack_into("<I", data, indirect_bulb_pointer_offset, base + offsets["bulb_function"])


def branch_target(address, word):
    displacement = word & 0xFFFFFF
    if displacement & 0x800000:
        displacement -= 1 << 24
    return address + 8 + (displacement << 2)


def check(condition, message):
    if not condition:
        raise SystemExit(f"FAIL: {message}")
    print(f"PASS: {message}")

cave = segment["vaddr"] + segment["filesz"]
cave_off = segment["offset"] + segment["filesz"]
patched, changed = patch.patch_data(data, offsets, addresses, segment)
check(changed, "fresh binary gets patched")
entry = struct.unpack_from("<I", patched, offsets["burst"])[0]
check(branch_target(addresses["burst"], entry) == cave,
      "burst helper enters the new executable LOAD tail")
tramp = patched[cave_off:cave_off + patch.TRAMPOLINE_SIZE]
word = lambda offset: struct.unpack_from("<I", tramp, offset)[0]
check(word(0) == 0xE3510000 and (word(4) >> 28) == 0xD and
      branch_target(cave + 4, word(4)) == cave + 0x74,
      "zero or negative duration falls back to the stock burst helper")
check(branch_target(cave + 0x6C, word(0x6C)) == addresses["bulb"],
      "only positive Pentax K-3 III duration calls the timed Bulb helper")
check(branch_target(cave + 0x80, word(0x80)) == addresses["burst"] + 12,
      "fallback reconstructs original burst prologue then resumes stock code")
check(tramp[0x90:0x97] == b"pentax\0" and
      tramp[0x97:0xA4] == b"K-3 Mark III\0" and
      tramp[0xA4:0xAF] == b"Monochrome\0",
      "vendor, tested model, and explicitly excluded Monochrome are encoded")
new_filesz = struct.unpack_from("<I", patched, segment["phdr_offset"] + 16)[0]
new_memsz = struct.unpack_from("<I", patched, segment["phdr_offset"] + 20)[0]
check(new_filesz == segment["filesz"] + patch.TRAMPOLINE_SIZE and
      new_memsz == segment["memsz"] + patch.TRAMPOLINE_SIZE,
      "executable LOAD is extended by exactly the code-cave length")
check(tuple(struct.unpack_from("<I", patched, offsets["bulb_function"] + i * 4)[0]
            for i in range(4)) == patch.BULB_PROLOGUE and
      struct.unpack_from("<I", patched, indirect_bulb_pointer_offset)[0] ==
            base + offsets["bulb_function"],
      "original captureBulbImage function and indirect table pointer are preserved")
repeat_segment = dict(segment, filesz=new_filesz, memsz=new_memsz)
repeated, changed = patch.patch_data(patched, offsets, addresses, repeat_segment)
check(not changed and repeated == patched, "reapplication is idempotent")
call_site = 0x8100
valid_disassembly = "\n".join([
    "  80f4:\tmov\tr2, r3",
    "  80f8:\tldr\tr1, [fp, #-40]\t@ duration",
    "  80fc:\tmov\tr0, #0",
    "  8100:\tbl\t102548 <capture_image_with_Burst>",
])
check(patch.capture_call_setup_is_valid(valid_disassembly, call_site),
      "only the proven (status=0, duration=bTime, file buffer) caller is patched")
invalid_disassembly = valid_disassembly.replace("ldr\tr1, [fp, #-40]", "ldr\tr1, [fp, #-44]")
check(not patch.capture_call_setup_is_valid(invalid_disassembly, call_site),
      "unexpected duration argument layout is rejected")

short_gap = dict(segment, next_offset=cave_off + patch.TRAMPOLINE_SIZE - 1)
try:
    patch.patch_data(data, offsets, addresses, short_gap)
except ValueError as error:
    check("no non-overlapping executable LOAD gap" in str(error),
          "insufficient executable segment gap is rejected")
else:
    raise SystemExit("FAIL: overlapping code cave was accepted")

nonzero_gap = bytearray(data)
nonzero_gap[cave_off] = 0xAA
try:
    patch.patch_data(nonzero_gap, offsets, addresses, segment)
except ValueError as error:
    check("not zero-filled" in str(error),
          "nonzero executable LOAD tail is rejected")
else:
    raise SystemExit("FAIL: nonzero executable gap was overwritten")

overlap = dict(segment, allocated_sections=[(".allocated", cave_off, 4)])
try:
    patch.patch_data(data, offsets, addresses, overlap)
except ValueError as error:
    check("overlaps allocated section" in str(error),
          "code cave overlapping an allocated section is rejected")
else:
    raise SystemExit("FAIL: allocated-section overlap was accepted")

bad_burst = bytearray(data)
struct.pack_into("<I", bad_burst, offsets["burst"], 0xE1A00000)
try:
    patch.patch_data(bad_burst, offsets, addresses, segment)
except ValueError as error:
    check("prologue" in str(error), "unknown burst function layout is rejected")
else:
    raise SystemExit("FAIL: changed burst prologue was accepted")

bad_bulb = bytearray(data)
struct.pack_into("<I", bad_bulb, offsets["bulb_function"], 0xE1A00000)
try:
    patch.patch_data(bad_bulb, offsets, addresses, segment)
except ValueError as error:
    check("captureBulbImage function entry" in str(error),
          "unexpected captureBulbImage entry is rejected")
else:
    raise SystemExit("FAIL: unexpected captureBulbImage entry was accepted")

import os
root = os.environ["PATCHER_ROOT"]
patch_sh = open(os.path.join(root, "container", "patch.sh"), encoding="utf-8").read()
gate_sh = open(os.path.join(root, "tests", "run_prerelease_gate.sh"), encoding="utf-8").read()
check(patch_sh.count("polaris_bulb_dispatch_patch.py") >= 3,
      "patcher applies and post-repack audits the dispatch in both build modes")
check("polaris_bulb_dispatch_patch.py \"$PGPHOTO_BIN\" --check" in gate_sh,
      "prerelease package gate checks the installed pgphoto binary")

print("[test_polaris_bulb_dispatch_patch] ALL PASS")
PY
