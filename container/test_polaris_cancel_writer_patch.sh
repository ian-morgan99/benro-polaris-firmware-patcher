#!/usr/bin/env bash
# Offline unit test for the pgphoto cancel writer (issue #251).
# Runs on the host with no container, no qemu and no camera: patch_data() works
# on bytes.  Where the real shipped pgphoto is present it is also exercised, but
# that is optional so the test still passes in a checkout without firmware.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHONPATH="$ROOT/container" python3 - "$ROOT" <<'PY'
import os
import struct
import sys

import polaris_cancel_writer_patch as patch

ROOT = sys.argv[1]


def check(condition, message):
    if not condition:
        raise SystemExit("FAIL: %s" % message)
    print("PASS: %s" % message)


# ---------------------------------------------------------------- encoders
# Every word below was harvested from the analysed pgphoto, so the layouts are
# pinned to real bytes rather than to a reading of the ARM manual.  This matters:
# an earlier draft of this patch used hand-derived bit layouts that encoded
# "mov r2,#0" as "and r2,r0,#0" and "strb r2,[ip]" as a post-indexed str.  Those
# would have shipped a pgphoto that corrupted memory instead of cancelling.
check(patch.encode_movw(3, 0x53B) == 0xE300353B, "encode_movw reproduces movw r3,#0x53b")
check(patch.encode_movt(0, 0x31) == 0xE3400031, "encode_movt reproduces movt r0,#0x31")
check(patch.encode_mov_immediate(2, 0) == 0xE3A02000, "encode_mov_immediate reproduces mov r2,#0")
check(patch.encode_mov_immediate(2, 1) == 0xE3A02001, "encode_mov_immediate reproduces mov r2,#1")
check(patch.encode_strb(2, 3) == 0xE5C32000, "encode_strb reproduces strb r2,[r3]")
check(patch.encode_branch(0x16CB0, 0x16CB8) == 0xEA000000, "encode_branch reproduces a zero-displacement b")
patch.validate_encodings()
check(True, "validate_encodings() accepts every encoder against harvested bytes")

# The flag address must survive the two-instruction MOVW/MOVT build exactly.
low = patch.encode_movw(patch.SCRATCH_ADDRESS, patch.GLOB_CANCEL_ADDRESS & 0xFFFF)
high = patch.encode_movt(patch.SCRATCH_ADDRESS, (patch.GLOB_CANCEL_ADDRESS >> 16) & 0xFFFF)
rebuilt = (((high >> 16) & 0xF) << 28) | ((high & 0xFFF) << 16) \
          | (((low >> 16) & 0xF) << 12) | (low & 0xFFF)
check(rebuilt == patch.GLOB_CANCEL_ADDRESS,
      "movw+movt rebuild the cancel flag address %#x" % patch.GLOB_CANCEL_ADDRESS)

# ---------------------------------------------------------------- cave layout
CAVE = 0x2DF924
CLEAR_SITE = 0x20198
SET_SITES = [0x2033C, 0x203D4]
blob = patch.build_cave(CAVE, CLEAR_SITE, SET_SITES)

check(len(blob) == patch.CAVE_SIZE, "cave blob is exactly %d bytes" % patch.CAVE_SIZE)


def word(at):
    return struct.unpack_from("<I", blob, at)[0]


def branch_target(at):
    """Decode a plain B at ``at`` inside the blob back to its absolute target."""
    immediate = word(at) & 0xFFFFFF
    if immediate & 0x800000:
        immediate -= 0x1000000
    return (CAVE + at + 8) + immediate * 4


check(word(0x00) == low and word(0x04) == high, "clear trampoline loads the flag address")
check(word(0x08) == patch.encode_mov_immediate(patch.SCRATCH_VALUE, 0),
      "clear trampoline moves 0 into the value register")
check(word(0x0C) == patch.encode_strb(patch.SCRATCH_VALUE, patch.SCRATCH_ADDRESS),
      "clear trampoline stores the byte")
check(word(0x10) == patch.CAPTURE_EVENT_FIRST,
      "clear trampoline replays the displaced push {r4, fp, lr}")
check(branch_target(0x14) == CLEAR_SITE + 4,
      "clear trampoline returns to the instruction after the displaced word")

for index, site in enumerate(SET_SITES):
    at = patch.SET_BASE + index * patch.SET_STRIDE
    check(word(at) == low and word(at + 4) == high,
          "set trampoline %d loads the flag address" % index)
    check(word(at + 8) == patch.encode_mov_immediate(patch.SCRATCH_VALUE, 1),
          "set trampoline %d moves 1 into the value register" % index)
    check(word(at + 12) == patch.encode_strb(patch.SCRATCH_VALUE, patch.SCRATCH_ADDRESS),
          "set trampoline %d stores the byte" % index)
    check(branch_target(at + 16) == site + 4,
          "set trampoline %d returns to the instruction after its nop" % index)

# The trampolines must not overlap.  An earlier draft spaced them by 0x10 while
# each is 5 words (0x14) long, so set trampoline B overwrote set trampoline A's
# return branch and both stop handlers would have jumped into the middle of the
# wrong routine.
for index in range(len(SET_SITES)):
    start = patch.SET_BASE + index * patch.SET_STRIDE
    end = start + patch.SET_WORDS * 4
    check(end <= patch.CAVE_SIZE, "set trampoline %d fits inside the cave" % index)
    if index + 1 < len(SET_SITES):
        nxt = patch.SET_BASE + (index + 1) * patch.SET_STRIDE
        check(nxt >= end, "set trampolines %d and %d do not overlap" % (index, index + 1))

# Every trampoline must end in a plain branch, never bl or bx lr.  A linking
# branch would overwrite LR and destroy the caller's return address, which is
# exactly what makes replaying push {r4, fp, lr} correct.
for at in (0x14, patch.SET_BASE + 16, patch.SET_BASE + patch.SET_STRIDE + 16):
    encoding = word(at)
    check((encoding >> 28) == 0xE and (encoding >> 25) & 0x7 == 0x5 and not (encoding >> 24) & 1,
          "trampoline word at +%#x is a non-linking branch" % at)

# ---------------------------------------------------------------- synthetic patch
SEG_VA = 0x10000
SEG_OFF = 0x0
SEG_FSZ = 0x2CF924
CLEAR_OFF = CLEAR_SITE - SEG_VA
SET_OFFSETS = [s - SEG_VA for s in SET_SITES]

NOP = patch.NOP
BL = 0xEBFFD8FA          # any bl; only its opcode class is inspected


def synthetic():
    data = bytearray(b"\x00" * (SEG_FSZ + 0x1000))
    struct.pack_into("<I", data, CLEAR_OFF, patch.CAPTURE_EVENT_FIRST)
    for off in SET_OFFSETS:
        struct.pack_into("<I", data, off, NOP)
    return data


segment = {"offset": SEG_OFF, "vaddr": SEG_VA, "filesz": SEG_FSZ, "memsz": SEG_FSZ,
           "flags": 5, "align": 0x10000, "phdr_offset": 0x94,
           "next_offset": SEG_OFF + SEG_FSZ + 0x1000, "next_vaddr": SEG_VA + SEG_FSZ + 0x1000,
           "allocated_sections": []}
layout = {"clear": {"address": CLEAR_SITE, "offset": CLEAR_OFF},
          "set": [{"address": s, "offset": o, "handler": "h"} for s, o in zip(SET_SITES, SET_OFFSETS)],
          "segment": segment}

data = synthetic()
patched, changed, detail = patch.patch_data(bytes(data), layout)
check(changed, "patch_data reports a change on a stock binary")
check(struct.unpack_from("<I", patched, CLEAR_OFF)[0] == patch.encode_branch(CLEAR_SITE, detail["cave"]),
      "captureImageEvent entry branches into the cave")
for index, (site, off) in enumerate(zip(SET_SITES, SET_OFFSETS)):
    expected = patch.encode_branch(site, patch.set_trampoline_address(detail["cave"], index))
    check(struct.unpack_from("<I", patched, off)[0] == expected,
          "stop handler %d branches to its own trampoline" % index)
check(struct.unpack_from("<I", patched, segment["phdr_offset"] + 16)[0] == SEG_FSZ + patch.CAVE_SIZE,
      "p_filesz grew by the cave size")
check(struct.unpack_from("<I", patched, segment["phdr_offset"] + 20)[0] == SEG_FSZ + patch.CAVE_SIZE,
      "p_memsz grew by the cave size")

# Idempotence: re-running over our own output must be a no-op.  This is what lets
# --check verify a shipped candidate and keeps a rebuild from double-patching.
again, changed_again, _ = patch.patch_data(patched, layout)
check(not changed_again, "patch_data is idempotent")
check(again == patched, "second run leaves the bytes identical")

# A second patch appended after ours must not defeat detection: the cave is found
# by content, not by filesz - CAVE_SIZE.
extended = bytearray(patched)
extra = patch.CAVE_SIZE
struct.pack_into("<I", extended, segment["phdr_offset"] + 16, SEG_FSZ + patch.CAVE_SIZE + extra)
struct.pack_into("<I", extended, segment["phdr_offset"] + 20, SEG_FSZ + patch.CAVE_SIZE + extra)
extended[SEG_OFF + SEG_FSZ + patch.CAVE_SIZE:SEG_OFF + SEG_FSZ + patch.CAVE_SIZE + extra] = b"\x00" * extra
neighbour = dict(segment)
neighbour["filesz"] = SEG_FSZ + patch.CAVE_SIZE + extra
neighbour["memsz"] = SEG_FSZ + patch.CAVE_SIZE + extra
moved_layout = dict(layout, segment=neighbour)
_, changed_moved, _ = patch.patch_data(bytes(extended), moved_layout)
check(not changed_moved,
      "cave still detected after a later patch extends the same LOAD tail")

# ---------------------------------------------------------------- rejections
bad = bytearray(synthetic())
struct.pack_into("<I", bad, CLEAR_OFF, 0xE1A00000)   # not push {r4, fp, lr}
try:
    patch.patch_data(bytes(bad), layout)
    raise SystemExit("FAIL: accepted a foreign captureImageEvent prologue")
except ValueError as error:
    check("push {r4, fp, lr}" in str(error), "rejects a foreign captureImageEvent prologue")

nonzero = bytearray(synthetic())
nonzero[SEG_OFF + SEG_FSZ] = 0xE7
try:
    patch.patch_data(bytes(nonzero), layout)
    raise SystemExit("FAIL: accepted a non-zero cave tail")
except ValueError as error:
    check("zero-filled" in str(error), "refuses to write over a non-zero cave tail")

split = dict(segment, filesz=SEG_FSZ, memsz=SEG_FSZ + 0x100)
try:
    patch.patch_data(bytes(synthetic()), dict(layout, segment=split))
    raise SystemExit("FAIL: accepted a LOAD whose tail is not file-backed")
except ValueError as error:
    check("non-file-backed" in str(error), "refuses a LOAD with a non-file-backed tail")

tight = dict(segment, next_offset=SEG_OFF + SEG_FSZ + 8, next_vaddr=SEG_VA + SEG_FSZ + 8)
try:
    patch.patch_data(bytes(synthetic()), dict(layout, segment=tight))
    raise SystemExit("FAIL: accepted a cave that collides with the next LOAD")
except ValueError as error:
    check("non-overlapping" in str(error), "refuses a cave that collides with the next LOAD")

# ---------------------------------------------------------------- real binary
# The shipped pgphoto is not committed here; it lives in the PrivateResearch
# analysis tree.  Honour an explicit override, otherwise look for that sibling
# checkout.  Absent firmware skips rather than fails, so a bare clone still
# passes.
#
# Discovery used to walk all of $HOME and take sorted(candidates)[0]. That made
# the result depend on whatever happened to be on disk: a 17-byte pytest fixture
# sorts before any real path and dies with "ELFError: Magic number does not
# match", and an extracted candidate tree contains an ALREADY-PATCHED pgphoto, so
# the "recognised as unpatched" check fails on it. Build tooling legitimately
# writes both kinds of file under $HOME, so narrow the search, skip scratch
# directories, require the ELF magic, and prefer the hash-pinned fixture.
import re

SCRATCH = re.compile(
    r"(^|/)(\.cache|\.config|node_modules|pytest-of-[^/]+|"
    r"tmp\.[A-Za-z0-9]+|fwpkt-manifest-[^/]+|appfs-(payload|fwver)-audit|"
    r"ubitest|out|dist|build)(/|$)"
)

def _is_elf(path: str) -> bool:
    try:
        with open(path, "rb") as handle:
            return handle.read(4) == b"\x7fELF"
    except OSError:
        return False


candidates = []
override = os.environ.get("POLARIS_PGPHOTO")
if override and os.path.isfile(override):
    candidates.append(override)
else:
    searched = [ROOT, os.path.dirname(ROOT)]
    # The analysis tree normally sits beside this checkout under
    # ~/Documents/VSCodeProjects. Only those two named trees are searched; $HOME
    # itself is never walked, because it holds scratch that is not firmware.
    for base in (os.path.expanduser("~/Documents/VSCodeProjects"),):
        for name in ("PrivateResearch", "polaris-research"):
            candidate_root = os.path.join(base, name)
            if os.path.isdir(candidate_root):
                searched.append(candidate_root)
    for root in searched:
        for directory, dirs, files in os.walk(root):
            # Prune scratch so a stray extraction cannot be mistaken for firmware.
            dirs[:] = [d for d in dirs if not SCRATCH.search(os.path.join(directory, d))]
            if SCRATCH.search(directory):
                continue
            if "pgphoto.stage2ondisk" in files:
                candidates.append(os.path.join(directory, "pgphoto.stage2ondisk"))

candidates = [c for c in candidates if _is_elf(c)]
if not candidates:
    print("SKIP: no pgphoto.stage2ondisk found (set POLARIS_PGPHOTO to enable); "
          "real-binary checks skipped")
else:
    # Prefer the hash-pinned v90 diagnostic input: it is known to be the pristine,
    # unpatched binary this check is about. Everything else on disk may already
    # carry the cancel-writer cave.
    pinned = os.path.join(
        ROOT, "out",
        "o-v18m-k1ii-pgphoto-readiness-20261029",
        "stage2-ondisk", "ondisk", "pgphoto.stage2ondisk",
    )
    path = pinned if os.path.isfile(pinned) and _is_elf(pinned) else sorted(candidates)[0]
    data, real_layout = patch.inspect_binary(path)
    patched_real, changed_real, detail_real = patch.patch_data(data, real_layout)
    check(changed_real, "real pgphoto at %s is recognised as unpatched" % path)
    handlers = [s["handler"] for s in real_layout["set"]]
    check(sorted(handlers) == ["stopCaptureContinuContinuous", "stopCaptureImageForMessage"],
          "both stop-capture handlers are hooked in the shipped binary")
    round_trip, changed_again_real, _ = patch.patch_data(patched_real, real_layout)
    check(not changed_again_real and round_trip == patched_real,
          "real pgphoto patches idempotently")
PY
