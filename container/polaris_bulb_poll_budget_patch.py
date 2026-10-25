#!/usr/bin/env python3
"""Give pgphoto's post-release file poll enough time to cover a Pentax dark frame.

Defect (issue #230, proven statically against ``pgphoto.stage2ondisk`` shipped in
``6.0.0.54.69``, md5 2e3383301c7691a360175ca6889e26c8):

``capture_image_with_Bulb`` (``gpManager.c:3185-3348``) holds the shutter for exactly the
requested duration -- ``gpManager.c:3241`` compares elapsed milliseconds against the caller's
``duration_ms`` stored verbatim at ``gpManager.c:3185``. That is correct and must not change:
``setCameraStatus(0)`` runs at ``gpManager.c:3345``, *after* that loop, so widening the hold
bound would lengthen the exposure itself.

After release it polls for the produced file with ``wait_and_handle_event(timeout = 10 ms)``
(``gpManager.c:3287``; the timeout is milliseconds -- ``gpManager.c:989`` multiplies it by 1000
to get microseconds), bounded by an iteration count chosen at ``gpManager.c:3308``::

    0x102048  ldr  r2, [fp, #-0x1c]   ; files seen so far
    0x10204c  ldr  r3, [fp, #-0x24]   ; expected file count (numOfCaptureImage)
    0x102050  cmp  r2, r3
    0x102054  blt  #0x102060          ; still waiting -> long budget
    0x102058  mov  r3, #2             ; nothing outstanding -> poll twice
    0x10205c  b    #0x102064
    0x102060  mov  r3, #0x258         ; 600 iterations
    0x102064  str  r3, [fp, #-0x14]

600 x 10 ms is ~6 s. With noise reduction enabled the body writes a dark frame roughly as long
as the exposure before the file appears: measured on ``6.0.0.54.69`` with the dial on B and NR
on, a 40 s exposure delivered its file at ``capture end -83196 ms``, i.e. ~43 s after release.
Six seconds cannot cover that, so the loop exits at ``gpManager.c:3313``, ``gpManager.c:3322``
returns -1, and Benro Connect reports "shot failed" while the camera is still writing.

This patch raises only the "still waiting" budget. The hold bound, the release point and the
fast path (``mov r3, #2``) are untouched.

Known limitation, stated rather than hidden: the raised budget is a flat constant, so it covers
exposures up to roughly its own length with noise reduction on and still fails beyond that.
Duration-aware scaling would need ``duration_ms`` (``[fp, #-0xcc]``) divided by the poll
granularity, which is not expressible in one instruction; it is left as a follow-up rather than
smuggled in as hand-derived reciprocal-multiplication magic numbers.
"""

import argparse
import os
import stat
import struct
import sys
import tempfile
from elftools.elf.elffile import ELFFile

BULB_SYMBOL = "capture_image_with_Bulb"

# Poll granularity, asserted from gpManager.c:3287 (mov r0, #0xa) and gpManager.c:989.
POLL_INTERVAL_MS = 10

# Stock "still waiting" budget: mov r3, #0x258 == 600 iterations (~6 s).
STOCK_WAIT_BUDGET = 0xE3A03F96
STOCK_WAIT_ITERATIONS = 600

# The budget register, fixed by the store below (str r3, [fp, #-0x14]).
BUDGET_REGISTER = 3

# The branch that skips it, and the store that consumes it. Both are required as context so an
# unrelated `mov r3, #600` elsewhere in the binary cannot be mistaken for this site.
STOCK_SKIP_BRANCH = 0xEA000000          # b <the store>, i.e. branch displacement 0
STOCK_BUDGET_STORE = 0xE50B3014         # str r3, [fp, #-0x14]

# 10000 x 10 ms = 100 s of post-release polling. Covers the measured worst case (a 40 s
# exposure with NR lands its file ~43 s after release) with margin, while a genuine failure --
# no file ever arrives -- stays bounded at 100 s instead of stalling indefinitely.
NEW_WAIT_ITERATIONS = 10000


def encode_movw(register, immediate):
    """Encode an ARM A1 MOVW (16-bit immediate).

    Layout, confirmed against two MOVWs in the target binary (``movw r3,#0xc8d`` is
    ``0xe3003c8d`` and ``movw r3,#0x4dd3`` is ``0xe3043dd3``):
    ``cond 0011 imm4 Rd imm12`` -- bits [27:24] are 3, [23:20] are 0, imm4 is [19:16],
    Rd is [15:12] and imm12 is [11:0].
    """
    if not 0 <= register <= 15 or not 0 <= immediate <= 0xFFFF:
        raise ValueError("movw operands out of range: r%d, #0x%x" % (register, immediate))
    return ((0xE << 28) | (0x3 << 24) | (((immediate >> 12) & 0xF) << 16)
            | (register << 12) | (immediate & 0xFFF))


def decode_movw(instruction):
    """Return (register, immediate) if the word is an unconditional A1 MOVW, else None."""
    if (instruction >> 28) != 0xE or ((instruction >> 24) & 0xF) != 0x3:
        return None
    if ((instruction >> 20) & 0xF) != 0x0:
        return None
    register = (instruction >> 12) & 0xF
    immediate = (((instruction >> 16) & 0xF) << 12) | (instruction & 0xFFF)
    return register, immediate


def decode_mov_immediate(instruction):
    """Return (register, immediate) for an unconditional A1 MOV, else None.

    ``cond 001 Rd rotate-imm8``: the immediate is an 8-bit value rotated right by twice the
    4-bit rotate field.
    """
    if (instruction >> 28) != 0xE or ((instruction >> 25) & 0x7) != 0x1:
        return None
    if ((instruction >> 20) & 0x1) != 0:      # S bit must be clear for a plain mov
        return None
    register = (instruction >> 12) & 0xF
    rotate = (instruction >> 8) & 0xF
    value = instruction & 0xFF
    if rotate:
        immediate = ((value >> (2 * rotate)) | (value << (32 - 2 * rotate))) & 0xFFFFFFFF
    else:
        immediate = value
    return register, immediate


def symbol_value(elf, name):
    hits = []
    for section in elf.iter_sections():
        if section.header["sh_type"] not in ("SHT_SYMTAB", "SHT_DYNSYM"):
            continue
        for symbol in section.iter_symbols():
            if symbol.name == name and symbol.entry["st_shndx"] != "SHN_UNDEF":
                hits.append((symbol.entry["st_value"], symbol.entry["st_size"]))
    if len(hits) != 1:
        raise ValueError("expected one defined %s symbol, found %d" % (name, len(hits)))
    return hits[0]


def va_to_offset(elf, address):
    for segment in elf.iter_segments():
        if segment.header["p_type"] != "PT_LOAD":
            continue
        start = segment.header["p_vaddr"]
        size = segment.header["p_filesz"]
        if start <= address < start + size:
            return segment.header["p_offset"] + address - start
    raise ValueError("address 0x%x is not in a file-backed LOAD segment" % address)


def find_wait_budget(data, offset, size):
    """Locate the "still waiting" poll budget inside capture_image_with_Bulb.

    Returns ``(position, already_patched)``. The site is identified by the context that does not
    change when it is patched -- the branch that skips it and the store that consumes it -- so one
    search recognises both the stock ``mov r3, #600`` and the raised ``movw r3, #10000``. That is
    what lets ``--check`` verify a shipped binary rather than only an unpatched one.

    Searched by instruction shape rather than fixed address, because the address moves between
    pgphoto builds while this sequence does not.
    """
    candidates = []
    # A candidate at ``position`` reads words at position-4 and position+4, so the last legal
    # position is size-8. range()'s stop must therefore be past it, otherwise a budget sitting at
    # the end of the function is never seen.
    for position in range(4, size - 7, 4):
        preceding = struct.unpack_from("<I", data, offset + position - 4)[0]
        following = struct.unpack_from("<I", data, offset + position + 4)[0]
        if preceding != STOCK_SKIP_BRANCH or following != STOCK_BUDGET_STORE:
            continue
        word = struct.unpack_from("<I", data, offset + position)[0]
        if word == STOCK_WAIT_BUDGET:
            candidates.append((position, False))
        elif decode_movw(word) == (BUDGET_REGISTER, NEW_WAIT_ITERATIONS):
            candidates.append((position, True))
    if len(candidates) != 1:
        raise ValueError(
            "expected exactly one post-release file-poll budget site, found %d; this pgphoto "
            "does not match the analysed gpManager.c:3308 shape" % len(candidates))
    return candidates[0]


def patch_data(data, target):
    value, size, offset = target["address"], target["size"], target["offset"]
    position, already_patched = find_wait_budget(data, offset, size)
    if already_patched:
        return bytes(data), False, None

    stock = decode_mov_immediate(STOCK_WAIT_BUDGET)
    if stock != (BUDGET_REGISTER, STOCK_WAIT_ITERATIONS):
        raise ValueError("stock budget does not decode as mov r3,#600: %r" % (stock,))
    register = stock[0]

    replacement = encode_movw(register, NEW_WAIT_ITERATIONS)
    check = decode_movw(replacement)
    if check != (register, NEW_WAIT_ITERATIONS):
        raise ValueError("replacement movw failed round-trip decode: %r" % (check,))

    patched = bytearray(data)
    struct.pack_into("<I", patched, offset + position, replacement)
    if bytes(patched) == bytes(data):
        return bytes(data), False, None

    return bytes(patched), True, {
        "address": value + position,
        "offset": offset + position,
        "register": register,
        "old_iterations": STOCK_WAIT_ITERATIONS,
        "new_iterations": NEW_WAIT_ITERATIONS,
        "new_seconds": NEW_WAIT_ITERATIONS * POLL_INTERVAL_MS // 1000,
    }


def inspect_binary(path):
    """Read the binary and resolve everything the patch needs, eagerly.

    pyelftools parses lazily, so the symbol and segment lookups must happen while the handle is
    still open. Returning plain values rather than an ELFFile keeps patch_data working on bytes
    alone and makes it testable without a file on disk.
    """
    with open(path, "rb") as handle:
        data = handle.read()
        elf = ELFFile(handle)
        if elf.header["e_machine"] != "EM_ARM":
            raise ValueError("pgphoto is not ARM (e_machine=%s)" % elf.header["e_machine"])
        if not elf.little_endian:
            raise ValueError("pgphoto is not little-endian")
        address, size = symbol_value(elf, BULB_SYMBOL)
        if size <= 0:
            raise ValueError("%s has no usable symbol size" % BULB_SYMBOL)
        offset = va_to_offset(elf, address)
    return data, {"address": address, "size": size, "offset": offset}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pgphoto")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--in-place", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()

    try:
        data, target = inspect_binary(args.pgphoto)
        patched, changed, detail = patch_data(data, target)
    except (OSError, ValueError) as error:
        print("[polaris_bulb_poll_budget] FATAL: %s" % error, file=sys.stderr)
        return 1

    if args.check:
        if changed:
            print("[polaris_bulb_poll_budget] FATAL: dark-frame poll budget missing",
                  file=sys.stderr)
            return 1
        print("[polaris_bulb_poll_budget] verified %d-iteration (%ds) post-release file poll"
              % (NEW_WAIT_ITERATIONS, NEW_WAIT_ITERATIONS * POLL_INTERVAL_MS // 1000))
        return 0

    if not changed:
        print("[polaris_bulb_poll_budget] already patched (budget verified at %d iterations)"
              % NEW_WAIT_ITERATIONS)
        return 0

    output_path = args.pgphoto if args.in_place else args.pgphoto + ".patched"
    if args.in_place:
        directory = os.path.dirname(os.path.abspath(output_path))
        mode_bits = stat.S_IMODE(os.stat(output_path).st_mode)
        fd, temporary = tempfile.mkstemp(prefix=".pgphoto-poll-", dir=directory)
        try:
            with os.fdopen(fd, "wb") as output:
                output.write(patched)
            os.chmod(temporary, mode_bits)
            os.replace(temporary, output_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    else:
        with open(output_path, "wb") as output:
            output.write(patched)

    print("[polaris_bulb_poll_budget] patched %s: mov r%d,#%d -> movw r%d,#%d at 0x%x "
          "(post-release file wait %ds)"
          % (output_path, detail["register"], detail["old_iterations"],
             detail["register"], detail["new_iterations"], detail["address"],
             detail["new_seconds"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
