#!/usr/bin/env python3
"""Make pgphoto actually raise a cancel, so the driver's Bulb guard can fire.

Defect (issue #251).  The shipped driver honours a cancellation request: proven
on a real K-3 III on 2026-11-05, where asking to cancel returns GP_ERROR_CANCEL
and no shutter opens and no file is made.  That code is correct and upstream.

It never runs on the device, because nothing sets the flag it reads.  Static
analysis of all three distinct shipped ``pgphoto.stage2ondisk`` builds
(PrivateResearch 7568b8d83) found ``glob_cancel`` (0x375e08, size 1) read in
three places and written in none::

    ctx_cancel_func              ldrb r2,[r2]; cmp #0; strb #0 -> return 1   (read + clear)
    action_camera_capture_movie  ldrb r3,[r3]; cmp #0; beq                    (read only)
    action_camera_wait_event     ldrb r3,[r3]; cmp #0; bne                    (read only)

Four independent access routes were enumerated and all four are closed: literal
pools whose word equals 0x5e0 (exactly four sites, all reads), immediate-offset
[rY,#1504] (none), movw/movt constructing 0x5e0 (none), and the absolute address
(one statically-resolved .got slot at 0x2f75e0, no absolute literal in
.text/.data/.data.rel.ro).  The binary contains no Thumb code, so an ARM-only
decode covers it.

So ``glob_cancel`` is zero for the whole process, ``ctx_cancel_func`` always
answers "do not cancel", and rebuilding from driver main ships a guard that is
unreachable.  Rebuilding is necessary but not sufficient: pgphoto must set the
flag.  This patch does that.

Two kinds of edit, both hand-assembled ARM, both into the executable LOAD's
unused tail (the same code-cave mechanism polaris_bulb_dispatch_patch.py uses):

SET -- each stop-capture message handler carries a compiler-generated ``nop`` in
its tail, after the last call and before the return sequence::

    0x20338  bl    #0x16728
    0x2033c  nop                       <-- replaced by a branch into the cave
    0x20340  mov   r0, r3
    0x20344  sub   sp, fp, #4
    0x20348  pop   {fp, pc}

The same shape exists in stopCaptureContinuContinuous at 0x203d4.  The cave
stores 1 into glob_cancel and branches back to the instruction after the nop.
The nop is a no-op so nothing is lost.

CLEAR -- captureImageEvent, the start-capture counterpart, gets an entry
trampoline that stores 0 into glob_cancel, replays the one instruction it
displaced, and continues.  Without this a cancel raised while nothing is
capturing would leave the flag set and poison the *next* shot: the flag is
one-shot, cleared as ctx_cancel_func reads it, so a stale 1 makes the very next
capture abort before its shutter opens.

Every trampoline ends in a plain ``b``, never ``bl`` or ``bx lr``, and the entry
hook is a plain ``b`` too.  A non-linking branch does not modify LR, so the
original return address survives and the displaced ``push {r4, fp, lr}`` can be
replayed verbatim in the cave.  The only registers touched are r12/ip (the ARM
frame-pointer-swap scratch) and r2; both were verified dead at every hook site.

Absolute addressing is used rather than GOT-relative loads because pgphoto is
ET_EXEC (entry 0x15ed8, no PIE, no ASLR), so 0x375e08 is the run-time address.
Confirmed against the binary: .got slot 0x2f75e0 already holds 0x375e08 with no
relocation naming the symbol, and glob_cancel lives in writable .bss.

Known limitation, stated rather than hidden: which message handler the Polaris
red-cancel control actually reaches is inferred from the names
"stopCaptureImageForMessage" / "stopCaptureContinuContinuous".  The binary's
strings are obfuscated so this cannot be confirmed statically, and neither
handler is reached by a direct ``bl`` (they are installed in dispatch tables).
Both are patched so either path works, but a device trace is still required to
prove the red control lands on one of them.
"""

import argparse
import os
import stat
import struct
import sys
import tempfile
from elftools.elf.elffile import ELFFile

# --- verified anchors -------------------------------------------------------

NOP = 0xE320F000
MOV_R0_R3 = 0xE1A00003
SUB_SP_FP4 = 0xE24BD004
POP_FP_PC = 0xE8BD8800

# captureImageEvent's first instruction, replayed by the clear trampoline.
CAPTURE_EVENT_FIRST = 0xE92D4810          # push {r4, fp, lr}

# glob_cancel: a one-byte global in writable .bss.  ET_EXEC, so this is also the
# run-time address; confirmed by .got slot 0x2f75e0 holding it unrelocated.
GLOB_CANCEL_ADDRESS = 0x375E08

SCRATCH_ADDRESS = 12                       # ip / r12
SCRATCH_VALUE = 2                          # r2

# clear (6 words) + two set trampolines (5 words each) = 16 words.
CAVE_SIZE = 0x40
CLEAR_WORDS = 6
SET_WORDS = 5
# A set trampoline is SET_WORDS long, so its stride is SET_WORDS * 4 bytes.  Using
# a rounder 0x10 would overlap the previous trampoline's last word.
SET_STRIDE = SET_WORDS * 4
SET_BASE = CLEAR_WORDS * 4


def encode_movw(register, immediate):
    """ARM A1 MOVW.  Layout confirmed against a real instruction in the target:
    ``movw r3,#0x53b`` is 0xe300353b -- bits[27:24]=3, bit21=0, imm4=[19:16],
    Rd=[15:12], imm12=[11:0]."""
    if not 0 <= register <= 15 or not 0 <= immediate <= 0xFFFF:
        raise ValueError("movw operands out of range: r%d, #0x%x" % (register, immediate))
    return ((0xE << 28) | (0x3 << 24) | (((immediate >> 12) & 0xF) << 16)
            | (register << 12) | (immediate & 0xFFF))


def encode_movt(register, immediate):
    """ARM A1 MOVT.  Same field order as MOVW with bits[23:20]=4, confirmed
    against ``movt r0,#0x31`` == 0xe3400031 in the target."""
    if not 0 <= register <= 15 or not 0 <= immediate <= 0xFFFF:
        raise ValueError("movt operands out of range: r%d, #0x%x" % (register, immediate))
    return ((0xE << 28) | (0x3 << 24) | (1 << 22) | (((immediate >> 12) & 0xF) << 16)
            | (register << 12) | (immediate & 0xFFF))


def encode_mov_immediate(register, value):
    """ARM A1 MOV immediate.  ``mov r2,#0`` == 0xe3a02000 and
    ``mov r2,#1`` == 0xe3a02001 in the target."""
    if not 0 <= register <= 15:
        raise ValueError("mov register out of range")
    for rotate in range(16):
        candidate = ((value >> (2 * rotate)) | (value << (32 - 2 * rotate))) & 0xFFFFFFFF
        if candidate < 256 and \
                ((candidate >> (2 * rotate)) | (candidate << (32 - 2 * rotate))) & 0xFFFFFFFF == value:
            return (0xE << 28) | (0x1 << 25) | (0xD << 21) | (register << 12) \
                   | (rotate << 8) | candidate
    raise ValueError("%#x is not an encodable ARM rotated-8-bit immediate" % value)


def encode_strb(register, base_register):
    """ARM A1 STRB with no offset.  ``strb r2,[r3]`` == 0xe5c32000 in the target
    (base 0xe5c00000, Rn=[19:16], Rt=[15:12])."""
    return 0xE5C00000 | (base_register << 16) | (register << 12)


def encode_branch(source, target):
    """ARM A1 B (non-linking).  A plain branch leaves LR alone, which is what
    lets the entry hook replay ``push {r4, fp, lr}`` with the caller's real
    return address still in LR.  ``b #0xf7020`` == 0xea000000 at 0xf700c."""
    displacement = target - (source + 8)
    if displacement & 3 or not -(1 << 25) <= displacement < (1 << 25):
        raise ValueError("ARM branch from 0x%x to 0x%x is out of range/unaligned"
                         % (source, target))
    return (0xE << 28) | 0x0A000000 | ((displacement >> 2) & 0xFFFFFF)


def encode_load_address(register, address):
    """Two instructions, MOVW then MOVT, building a full 32-bit address."""
    return [encode_movw(register, address & 0xFFFF),
            encode_movt(register, (address >> 16) & 0xFFFF)]


def validate_encodings():
    """Prove every encoder against bytes harvested from the real binary.

    A wrong encoding silently corrupts a live process; polestar_fwver_patch.py
    documents exactly that failure mode, where a misplaced ``bl strcpy`` destroyed
    an adjacent ``mov r2,#0x40`` and gave memset an undefined length.  Every form
    used here is therefore checked against a word taken from pgphoto itself.
    """
    checks = [
        (encode_movw(3, 0x53B), 0xE300353B, "movw r3,#0x53b @0x201d0"),
        (encode_movt(0, 0x31), 0xE3400031, "movt r0,#0x31 @0x15f40"),
        (encode_mov_immediate(2, 0), 0xE3A02000, "mov r2,#0"),
        (encode_mov_immediate(2, 1), 0xE3A02001, "mov r2,#1"),
        (encode_strb(2, 3), 0xE5C32000, "strb r2,[r3]"),
        (encode_branch(0x16CB0, 0x16CB8), 0xEA000000, "b #0x16cb8 @0x16cb0"),
    ]
    for produced, expected, label in checks:
        if produced != expected:
            raise AssertionError("%s: encoded %#010x, binary has %#010x"
                                 % (label, produced, expected))
    # The address build must reproduce the flag's address exactly.
    low = encode_movw(SCRATCH_ADDRESS, GLOB_CANCEL_ADDRESS & 0xFFFF)
    high = encode_movt(SCRATCH_ADDRESS, (GLOB_CANCEL_ADDRESS >> 16) & 0xFFFF)
    rebuilt = (((high >> 16) & 0xF) << 28) | ((high & 0xFFF) << 16) \
              | (((low >> 16) & 0xF) << 12) | (low & 0xFFF)
    if rebuilt != GLOB_CANCEL_ADDRESS:
        raise AssertionError("movw/movt rebuilds %#x, not %#x" % (rebuilt, GLOB_CANCEL_ADDRESS))


def symbol_value(elf, name):
    hits = []
    for section in elf.iter_sections():
        if section.header["sh_type"] not in ("SHT_SYMTAB", "SHT_DYNSYM"):
            continue
        for symbol in section.iter_symbols():
            if symbol.name == name and symbol.entry["st_shndx"] != "SHN_UNDEF":
                hits.append((symbol.entry["st_value"], symbol.entry["st_size"]))
    unique = sorted(set(hits))
    if len(unique) != 1:
        raise ValueError("expected one defined %s symbol, found %d" % (name, len(unique)))
    return unique[0]


def va_to_offset(elf, address):
    for segment in elf.iter_segments():
        if segment.header["p_type"] != "PT_LOAD":
            continue
        start = segment.header["p_vaddr"]
        if start <= address < start + segment.header["p_filesz"]:
            return segment.header["p_offset"] + address - start
    raise ValueError("address 0x%x is not in a file-backed LOAD segment" % address)


def find_tail_slots(data, text):
    """Find the stop handlers' tail hook slots by shape.

    The bare shape ``bl; <slot>; mov r0,r3; sub sp,fp,#4; pop {fp,pc}`` occurs
    eight times in .text, so shape alone is not an anchor -- the caller restricts
    hits to inside a named stop handler and requires exactly two.  A build missing
    either handler then fails loudly instead of half-patching.

    ``<slot>`` is accepted as either the stock nop or a branch, because once this
    patch has run the nop is gone.  That is what lets --check verify a shipped
    candidate rather than only an unpatched one; whether the branch really points
    at our cave is confirmed later by content, not here.
    """
    offset, size = text["offset"], text["size"]
    slots = []
    for position in range(0, size - 20, 4):
        words = struct.unpack_from("<5I", data, offset + position)
        if words[2] != MOV_R0_R3 or words[3] != SUB_SP_FP4 or words[4] != POP_FP_PC:
            continue
        if (words[0] >> 26) != 0x3A:          # preceding instruction must be a bl
            continue
        word = words[1]
        unconditional_branch = (word >> 28) == 0xE and (word >> 25) & 0x7 == 0x5
        if word != NOP and not unconditional_branch:
            continue
        # words[0] is the bl at ``position``, so the slot itself -- the word being
        # replaced -- is one word later.
        slots.append((text["vaddr"] + position + 4, word))
    return slots


def build_cave(cave, clear_site, set_sites):
    """Assemble the trampolines at ``cave``.

      +0x00  clear: store 0, replay push {r4,fp,lr}, branch back to clear_site+4
      +0x18  set A: store 1, branch back to its nop+4
      +0x28  set B: store 1, branch back to its nop+4

    All branches are non-linking so LR survives; nothing but the two scratch
    registers is touched and no stack is used.
    """
    blob = bytearray(CAVE_SIZE)

    def emit(at, words):
        for index, word in enumerate(words):
            struct.pack_into("<I", blob, at + index * 4, word)

    address_words = encode_load_address(SCRATCH_ADDRESS, GLOB_CANCEL_ADDRESS)

    clear = list(address_words) + [
        encode_mov_immediate(SCRATCH_VALUE, 0),
        encode_strb(SCRATCH_VALUE, SCRATCH_ADDRESS),
        CAPTURE_EVENT_FIRST,
        encode_branch(cave + (CLEAR_WORDS - 1) * 4, clear_site + 4),
    ]
    if len(clear) != CLEAR_WORDS:
        raise ValueError("clear trampoline is %d words, expected %d"
                         % (len(clear), CLEAR_WORDS))
    emit(0x00, clear)

    for index, site in enumerate(set_sites):
        at = SET_BASE + index * SET_STRIDE
        words = list(address_words) + [
            encode_mov_immediate(SCRATCH_VALUE, 1),
            encode_strb(SCRATCH_VALUE, SCRATCH_ADDRESS),
            # The branch's own address is cave + at, not at: omitting the base
            # encodes a displacement relative to zero and lands somewhere else.
            encode_branch(cave + at + (SET_WORDS - 1) * 4, site + 4),
        ]
        if len(words) != SET_WORDS:
            raise ValueError("set trampoline is %d words, expected %d"
                             % (len(words), SET_WORDS))
        emit(at, words)
    return bytes(blob)


def set_trampoline_address(cave, index):
    """Absolute address of the ``index``-th set trampoline inside the cave."""
    return cave + SET_BASE + index * SET_STRIDE


def find_existing_cave(data, segment, clear_site, set_sites):
    """Locate an already-written cancel cave by content.

    Detection cannot be ``filesz - CAVE_SIZE`` because polaris_bulb_dispatch_patch.py
    appends its own 0x300-byte trampoline to the same tail, in either order.  The
    trampolines embed absolute branch targets, so a candidate offset is confirmed
    by rebuilding the blob for that address and comparing bytes.
    """
    for filesz in range(segment["filesz"], CAVE_SIZE - 1, -4):
        cave = segment["vaddr"] + filesz
        off = segment["offset"] + filesz
        if bytes(data[off:off + CAVE_SIZE]) != build_cave(cave, clear_site, set_sites):
            continue
        # The three hook sites must point at exactly this cave.
        if struct.unpack_from("<I", data, segment["offset"] + (clear_site - segment["vaddr"]))[0] \
                != encode_branch(clear_site, cave):
            continue
        if any(struct.unpack_from("<I", data, segment["offset"] + (site - segment["vaddr"]))[0]
               != encode_branch(site, set_trampoline_address(cave, index))
               for index, site in enumerate(set_sites)):
            continue
        return cave
    return None


def patch_data(data, layout):
    clear_site = layout["clear"]["address"]
    clear_off = layout["clear"]["offset"]
    set_sites = [s["address"] for s in layout["set"]]
    set_offsets = [s["offset"] for s in layout["set"]]
    segment = layout["segment"]

    filesz = segment["filesz"]
    memsz = segment["memsz"]

    # Recognise an already-patched binary first.  Once patched, the stock words
    # are gone -- captureImageEvent starts with a branch and the tail nops are
    # branches -- so the stock checks below would reject our own output.
    existing = find_existing_cave(data, segment, clear_site, set_sites)
    if existing is not None:
        return bytes(data), False, None

    replay = struct.unpack_from("<I", data, clear_off)[0]
    if replay != CAPTURE_EVENT_FIRST:
        raise ValueError("captureImageEvent entry is not the verified stock "
                         "'push {r4, fp, lr}' (%#010x)" % replay)
    for off in set_offsets:
        word = struct.unpack_from("<I", data, off)[0]
        if word != NOP:
            raise ValueError("stop-handler tail slot is not a nop (%#010x); the cave "
                             "was not found, so this binary is in an unexpected state"
                             % word)

    if filesz != memsz:
        raise ValueError("executable LOAD has a non-file-backed tail; refusing to add cancel code")
    cave = segment["vaddr"] + filesz
    cave_off = segment["offset"] + filesz
    if any(data[cave_off:cave_off + CAVE_SIZE]):
        raise ValueError("unused executable LOAD tail is not zero-filled")
    for name, soffset, ssize in segment["allocated_sections"]:
        if soffset < cave_off + CAVE_SIZE and cave_off < soffset + ssize:
            raise ValueError("code-cave gap overlaps allocated section %s" % name)

    new_end = cave + CAVE_SIZE
    page_alignment = max(segment["align"], 0x1000)
    if page_alignment & (page_alignment - 1):
        raise ValueError("executable LOAD alignment is not a power of two")
    next_page = (new_end + page_alignment - 1) & ~(page_alignment - 1)
    next_load_page = segment["next_vaddr"] & ~(page_alignment - 1)
    if cave_off + CAVE_SIZE > segment["next_offset"] or next_page > next_load_page:
        raise ValueError("no non-overlapping executable LOAD gap for the cancel writer")

    patched = bytearray(data)
    struct.pack_into("<I", patched, clear_off, encode_branch(clear_site, cave))
    for index, (site, off) in enumerate(zip(set_sites, set_offsets)):
        # Each stop handler branches to its own trampoline; all three hooks must
        # not land on the clear routine, which stores 0 rather than 1.
        struct.pack_into("<I", patched, off,
                         encode_branch(site, set_trampoline_address(cave, index)))
    patched[cave_off:cave_off + CAVE_SIZE] = build_cave(cave, clear_site, set_sites)

    phdr = segment["phdr_offset"]
    struct.pack_into("<I", patched, phdr + 16, filesz + CAVE_SIZE)   # p_filesz
    struct.pack_into("<I", patched, phdr + 20, memsz + CAVE_SIZE)    # p_memsz

    return bytes(patched), True, {
        "cave": cave,
        "clear_site": clear_site,
        "set_sites": set_sites,
        "flag": GLOB_CANCEL_ADDRESS,
        "bytes": CAVE_SIZE,
    }


def inspect_binary(path):
    validate_encodings()
    with open(path, "rb") as stream:
        data = stream.read()
        elf = ELFFile(stream)
        if elf.elfclass != 32 or elf.little_endian is False:
            raise ValueError("pgphoto must be a 32-bit little-endian ELF")
        if elf.header["e_machine"] != "EM_ARM":
            raise ValueError("pgphoto is not ARM (e_machine=%s)" % elf.header["e_machine"])
        if elf.header["e_type"] != "ET_EXEC":
            raise ValueError("pgphoto is %s, not ET_EXEC; absolute addressing of the "
                             "cancel flag assumes a non-PIE load address"
                             % elf.header["e_type"])

        event, event_size = symbol_value(elf, "captureImageEvent")
        if event_size <= 0:
            raise ValueError("captureImageEvent has no usable symbol size")
        handlers = {}
        for name in ("stopCaptureImageForMessage", "stopCaptureContinuContinuous"):
            address, size = symbol_value(elf, name)
            handlers[name] = (address, size)

        text = None
        for section in elf.iter_sections():
            if section.name == ".text":
                text = {"offset": section.header["sh_offset"],
                        "size": section.header["sh_size"],
                        "vaddr": section.header["sh_addr"]}
        if text is None:
            raise ValueError("pgphoto has no .text")

        flag = None
        for section in elf.iter_sections():
            if section.header["sh_type"] not in ("SHT_SYMTAB", "SHT_DYNSYM"):
                continue
            for symbol in section.iter_symbols():
                if symbol.name == "glob_cancel":
                    flag = (symbol.entry["st_value"], symbol.entry["st_size"])
        if flag is None:
            raise ValueError("pgphoto defines no glob_cancel symbol")
        if flag[1] != 1:
            raise ValueError("glob_cancel is %d bytes, not 1" % flag[1])
        if flag[0] != GLOB_CANCEL_ADDRESS:
            raise ValueError("glob_cancel is at %#x, not the analysed %#x; this build "
                             "needs its own anchor" % (flag[0], GLOB_CANCEL_ADDRESS))

        loads = []
        for index, segment in enumerate(elf.iter_segments()):
            if segment.header["p_type"] != "PT_LOAD":
                continue
            loads.append({
                "offset": segment.header["p_offset"],
                "vaddr": segment.header["p_vaddr"],
                "filesz": segment.header["p_filesz"],
                "memsz": segment.header["p_memsz"],
                "flags": segment.header["p_flags"],
                "align": segment.header["p_align"],
                "phdr_offset": elf.header["e_phoff"] + index * elf.header["e_phentsize"],
            })
        executable = [item for item in loads
                      if item["flags"] & 1 and
                      item["vaddr"] <= event < item["vaddr"] + item["filesz"]]
        if len(executable) != 1:
            raise ValueError("expected one executable LOAD holding captureImageEvent, found %d"
                             % len(executable))
        segment = executable[0]
        following = sorted((item for item in loads if item["offset"] > segment["offset"]),
                           key=lambda item: item["offset"])
        if not following:
            raise ValueError("executable LOAD has no following segment to bound the cave")
        segment["next_offset"] = following[0]["offset"]
        segment["next_vaddr"] = following[0]["vaddr"]
        segment["allocated_sections"] = [
            (section.name, section.header["sh_offset"], section.header["sh_size"])
            for section in elf.iter_sections()
            if section.header["sh_type"] != "SHT_NOBITS" and section.header["sh_size"]
        ]

        # pyelftools reads lazily, so every offset must be resolved while the
        # handle is still open; deferring these to after the with block raises
        # "seek of closed file".
        clear_offset = va_to_offset(elf, event)
        set_sites = []
        for name in ("stopCaptureImageForMessage", "stopCaptureContinuContinuous"):
            address, size = handlers[name]
            for slot, _word in find_tail_slots(data, text):
                if address <= slot < address + size:
                    set_sites.append({"address": slot,
                                      "offset": va_to_offset(elf, slot),
                                      "handler": name})

    if len(set_sites) != 2:
        raise ValueError("expected one tail nop in each stop-capture handler, found %d"
                         % len(set_sites))

    return data, {
        "clear": {"address": event, "offset": clear_offset},
        "set": sorted(set_sites, key=lambda item: item["address"]),
        "segment": segment,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pgphoto")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--in-place", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()

    try:
        data, layout = inspect_binary(args.pgphoto)
        patched, changed, detail = patch_data(data, layout)
    except (OSError, ValueError, AssertionError) as error:
        print("[polaris_cancel_writer] FATAL: %s" % error, file=sys.stderr)
        return 1

    if args.check:
        if changed:
            print("[polaris_cancel_writer] NOT PATCHED: pgphoto never raises a cancel, "
                  "so the driver's Bulb guard is unreachable", file=sys.stderr)
            return 1
        print("[polaris_cancel_writer] ok: glob_cancel is set by both stop-capture "
              "handlers and cleared at capture start")
        return 0

    if not changed:
        print("[polaris_cancel_writer] already patched, nothing to do")
        return 0

    if args.in_place:
        with open(args.pgphoto, "rb") as handle:
            mode_bits = stat.S_IMODE(os.fstat(handle.fileno()).st_mode)
        directory = os.path.dirname(os.path.abspath(args.pgphoto))
        descriptor, temporary = tempfile.mkstemp(dir=directory, prefix=".cancel-writer-")
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(patched)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, mode_bits)
            os.replace(temporary, args.pgphoto)
        except BaseException:
            if os.path.exists(temporary):
                os.unlink(temporary)
            raise
        print("[polaris_cancel_writer] patched in place: cave %#x, clear %#x, set %s, "
              "flag %#x, %d bytes"
              % (detail["cave"], detail["clear_site"],
                 ", ".join(hex(a) for a in detail["set_sites"]),
                 detail["flag"], detail["bytes"]))
        return 0

    sys.stdout.buffer.write(patched)
    return 0


if __name__ == "__main__":
    sys.exit(main())
