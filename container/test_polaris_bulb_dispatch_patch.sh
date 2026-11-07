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
    "camera_global": 0x4400,
    "camera_get_single_config": 0x4500,
    "widget_get_type": 0x4550,
    "widget_get_value": 0x4600,
    "widget_free": 0x4700,
    "strstr": 0x4800,
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
struct.pack_into(
    "<I", data, offsets["bulb"] + patch.BULB_CANCEL_OFFSET,
    patch.encode_branch(
        addresses["bulb"] + patch.BULB_CANCEL_OFFSET,
        addresses["bulb"] + patch.BULB_CANCEL_OLD_TARGET_OFFSET,
        condition=0x0,
    ),
)
# Issue #251: the outcome-preservation redirects verify the stock instructions
# they replace and their immediate neighbours. Seed them so this fixture is a
# faithful layout rather than a zero-filled body.
struct.pack_into("<I", data, offsets["bulb"] + patch.BULB_STOP_STORE_OFFSET,
                 0xE50B3010)          # str r3, [fp, #-16]
struct.pack_into("<I", data, offsets["bulb"] + patch.BULB_STOP_RELOAD_OFFSET,
                 0xE51B3058)          # ldr r3, [fp, #-88]
struct.pack_into("<I", data, offsets["bulb"] + patch.BULB_STOP_RELOAD_OFFSET + 4,
                 0xE3530000)          # cmp r3, #0
struct.pack_into("<I", data, offsets["bulb"] + patch.BULB_PUBLISH_STORE_OFFSET,
                 0xE50B0010)          # str r0, [fp, #-16]
struct.pack_into("<I", data, offsets["bulb"] + patch.BULB_PUBLISH_RESUME_OFFSET,
                 0xE24B3064)          # sub r3, fp, #100
indirect_bulb_pointer_offset = 0x400
struct.pack_into("<I", data, indirect_bulb_pointer_offset, base + offsets["bulb_function"])


def branch_target(address, word):
    displacement = word & 0xFFFFFF
    if displacement & 0x800000:
        displacement -= 1 << 24
    return address + 8 + (displacement << 2)


def check(condition, message):
    if not condition:
        raise SystemExit("FAIL: %s" % message)
    print("PASS: %s" % message)

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
      branch_target(cave + 4, word(4)) == cave + 0x138,
      "zero or negative duration falls back to the stock burst helper")
check((word(0x12C) >> 24) == 0xEA and branch_target(cave + 0x12C, word(0x12C)) == addresses["bulb"],
      "only positive Pentax K-3 III B-mode duration tail-calls the timed Bulb helper")
check(branch_target(cave + 0x144, word(0x144)) == addresses["burst"] + 12,
      "fallback reconstructs original burst prologue then resumes stock code")
# Issue #210: getCameraName returns status, so the model gate must inspect the
# name buffer (not the return value), must not clobber the capture arguments,
# and must return rather than fall through into the stock burst body.
check(word(0x34) == 0xE1A0000D and (word(0x38) >> 24) == 0xEB and
      branch_target(cave + 0x38, word(0x38)) == addresses["name"],
      "getCameraName is given a writable stack buffer, not the strcasestr result")
check(word(0x3C) == 0xE3500000 and (word(0x40) >> 28) == 0x1 and
      branch_target(cave + 0x40, word(0x40)) == cave + 0x130,
      "a getCameraName error (nonzero return) falls back instead of matching")
check(word(0x44) == 0xE1A0000D and word(0x50) == 0xE150000D and
      word(0x58) == (0xE5DD0000 | len(patch.MODEL_NAME)) and
      (word(0x54) >> 28) == 0x1 and (word(0x60) >> 28) == 0x1 and
      branch_target(cave + 0x54, word(0x54)) == cave + 0x130 and
      branch_target(cave + 0x60, word(0x60)) == cave + 0x130,
      "only a whole-buffer match of the registered model label is selected")
check(word(0x124) == 0xE28DDB02 and word(0x128) == 0xE8BD4007,
      "the timed-Bulb path restores the original (status, duration, files) arguments")
check(word(0x130) == 0xE28DDB02 and word(0x134) == 0xE8BD4007 and
      word(0x138) == patch.BURST_PROLOGUE[0],
      "the fallback path restores arguments then reconstructs the burst prologue")
check(struct.unpack_from("<I", patched,
      offsets["bulb"] + patch.BULB_CANCEL_OFFSET)[0] ==
      patch.bulb_cancel_patch_word(addresses["bulb"],
          addresses["bulb"] + patch.BULB_CANCEL_STOP_PATH_OFFSET),
      "Bulb cancellation reaches the existing normal stop path")
check(struct.unpack_from("<I", patched, offsets["bulb"] + patch.BULB_CANCEL_OFFSET)[0] >> 28 == 0,
      "cancel branch retains its original EQ condition")
# Issue #251: cancellation is recorded in the helper's return slot, and two stock
# stores overwrite it afterwards. Both must be redirected to a conditional record
# so a successful cleanup or publication cannot report a cancelled capture as a
# completed one. The two records use opposite rules on purpose: a failed shutter
# closure outranks the cancellation, while a failed image retrieval after a
# cancellation must not replace it.
stop_redirect = struct.unpack_from("<I", patched,
                                   offsets["bulb"] + patch.BULB_STOP_STORE_OFFSET)[0]
check(stop_redirect >> 28 == 0xE and
      branch_target(addresses["bulb"] + patch.BULB_STOP_STORE_OFFSET, stop_redirect) ==
      cave + patch.BULB_KEEP_CANCEL_OFFSET,
      "the stop-path store redirects to its conditional record")
check(word(patch.BULB_KEEP_CANCEL_OFFSET) == 0xE3530000 and
      (word(patch.BULB_KEEP_CANCEL_OFFSET + 4) >> 28) == 0x0 and
      branch_target(cave + patch.BULB_KEEP_CANCEL_OFFSET + 4,
                    word(patch.BULB_KEEP_CANCEL_OFFSET + 4)) ==
      addresses["bulb"] + patch.BULB_STOP_RELOAD_OFFSET,
      "a successful stop leaves the saved outcome untouched and needs no scratch")
check(word(patch.BULB_KEEP_CANCEL_OFFSET + 8) == 0xE50B3010 and
      branch_target(cave + patch.BULB_KEEP_CANCEL_OFFSET + 12,
                    word(patch.BULB_KEEP_CANCEL_OFFSET + 12)) ==
      addresses["bulb"] + patch.BULB_STOP_RELOAD_OFFSET,
      "a failed stop is still recorded, so an open shutter outranks the cancel")
publish_redirect = struct.unpack_from("<I", patched,
                                      offsets["bulb"] + patch.BULB_PUBLISH_STORE_OFFSET)[0]
check(publish_redirect >> 28 == 0xE and
      branch_target(addresses["bulb"] + patch.BULB_PUBLISH_STORE_OFFSET,
                    publish_redirect) == cave + patch.BULB_KEEP_PUBLISH_OFFSET,
      "the publication store redirects to its conditional record")
check(word(patch.BULB_KEEP_PUBLISH_OFFSET) == 0xE51B1010 and
      word(patch.BULB_KEEP_PUBLISH_OFFSET + 4) == 0xE3510000 and
      (word(patch.BULB_KEEP_PUBLISH_OFFSET + 8) >> 28) == 0x1 and
      branch_target(cave + patch.BULB_KEEP_PUBLISH_OFFSET + 8,
                    word(patch.BULB_KEEP_PUBLISH_OFFSET + 8)) ==
      addresses["bulb"] + patch.BULB_PUBLISH_RESUME_OFFSET,
      "any saved outcome survives publication, so a cancel outranks a failed retrieval")
check(word(patch.BULB_KEEP_PUBLISH_OFFSET + 12) == 0xE50B0010 and
      branch_target(cave + patch.BULB_KEEP_PUBLISH_OFFSET + 16,
                    word(patch.BULB_KEEP_PUBLISH_OFFSET + 16)) ==
      addresses["bulb"] + patch.BULB_PUBLISH_RESUME_OFFSET,
      "a normal capture still records a genuine publication failure")
check(patch.TRAMPOLINE_SIZE == 0x300 and
      patch.BULB_KEEP_CANCEL_OFFSET + 16 <= patch.LITERAL_POOL and
      patch.BULB_KEEP_PUBLISH_OFFSET >= patch.MODE_KEY_TEXT + 19,
      "the outcome records reuse unused cave words without growing the trampoline")
check(tramp[patch.CONDITIONS_KEY_TEXT:patch.CONDITIONS_KEY_TEXT + 17] ==
      b"pentaxconditions\0" and
      tramp[patch.MODE_KEY_TEXT:patch.MODE_KEY_TEXT + 19] ==
      b"exposure-mode-raw=\0",
      "live Pentax conditions and bounded exposure-mode key are encoded")
check((word(0x80) >> 24) == 0xEB and
      branch_target(cave + 0x80, word(0x80)) == addresses["camera_get_single_config"] and
      branch_target(cave + 0x9C, word(0x9C)) == addresses["widget_get_type"] and
      branch_target(cave + 0xBC, word(0xBC)) == cave + 0x174 and
      word(0x174) == 0xE3A03000 and word(0x178) == 0xE58D3004 and
      branch_target(cave + 0x17C, word(0x17C)) == addresses["widget_get_value"] and

      branch_target(cave + 0x114, word(0x114)) == addresses["widget_free"] and
      branch_target(cave + 0x120, word(0x120)) == addresses["widget_free"],
      "the mode gate uses one same-session conditions/widget read and frees it")
check(word(0x164) == 0xE3A03000 and word(0x168) == 0xE58D3000 and
      word(0x16C) == 0xE58D3004,
      "widget and type slots are cleared before querying")
check((word(0xD8) >> 24) == 0xEB and
      branch_target(cave + 0xD8, word(0xD8)) == addresses["strstr"] and
      branch_target(cave + 0x10C, word(0x10C)) == cave + 0x180 and
      branch_target(cave + 0x1F8, word(0x1F8)) == cave + 0x110,
      "recognized non-B mode frees the widget and uses the stock burst path")
check((word(0xC4) >> 28) == 0x1 and
      branch_target(cave + 0xC4, word(0xC4)) == cave + 0x158 and
      branch_target(cave + 0x160, word(0x160)) == cave + 0x148,
      "a failed widget value read is freed before returning an error")
check(tramp[patch.PENTAX_TEXT:patch.PENTAX_TEXT + 7] == b"pentax\0" and
      tramp[patch.MODEL_TEXT:patch.MODEL_TEXT + len(patch.MODEL_NAME) + 1] ==
      b"Pentax:K-3 Mark III (MTP mode)\0",
      "vendor and exact registered K-3 III model label are encoded")
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

# A second patcher may append its own code cave to the same executable LOAD tail.
# polaris_cancel_writer_patch.py does exactly that.  Detection used to assume this
# patch owned the final TRAMPOLINE_SIZE bytes and computed filesz - TRAMPOLINE_SIZE,
# which then landed inside the other patch's code: --check reported a correctly
# patched binary as broken, and a rebuild could re-patch over live code.  The cave
# is located by content now, so neither order nor a neighbour matters.
neighbour_size = 0x40
shared = bytearray(patched)
struct.pack_into("<I", shared, segment["phdr_offset"] + 16, new_filesz + neighbour_size)
struct.pack_into("<I", shared, segment["phdr_offset"] + 20, new_memsz + neighbour_size)
shared[segment["offset"] + new_filesz:segment["offset"] + new_filesz + neighbour_size] = \
    b"\x00" * neighbour_size
shared_segment = dict(segment, filesz=new_filesz + neighbour_size,
                      memsz=new_memsz + neighbour_size)
shared_out, shared_changed = patch.patch_data(bytes(shared), offsets, addresses,
                                              shared_segment)
check(not shared_changed and bytes(shared_out) == bytes(shared),
      "the dispatch cave is still detected after a later patch extends the same tail")
call_site_offset = 0x100
setup_data = bytearray(0x200)
for index, instruction in enumerate((0xE1A02003, 0xE51B1028, 0xE3A00000)):
    struct.pack_into("<I", setup_data, call_site_offset - 12 + index * 4, instruction)
check(patch.capture_call_setup_is_valid(setup_data, call_site_offset),
      "only the proven (status=0, duration=bTime, file buffer) caller is patched")
struct.pack_into("<I", setup_data, call_site_offset - 8, 0xE51B102C)
check(not patch.capture_call_setup_is_valid(setup_data, call_site_offset),
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
