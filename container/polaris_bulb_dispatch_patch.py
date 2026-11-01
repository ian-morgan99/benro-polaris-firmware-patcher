#!/usr/bin/env python3
"""Route safe Pentax Bulb requests to pgphoto's timed Bulb helper.

The stock pgphoto capture dispatcher passes the wheel value as ``bTime`` to
``capture_image_with_Burst``.  On the colour K-3 III a positive value must use
the Bulb lifecycle, but only when the camera's live Pentax conditions say that
the body is in B/lens-B/Astro mode.  A positive value in ordinary Manual mode
must remain on the normal capture path; sending it to the held-Bulb action is
what turns a perfectly ordinary M capture into a misleading ``shoot failed``.

The helper's ``GP_ERROR_CANCEL`` branch returned before the normal stop path.
This partial patch preserves the branch condition while retargeting it to that
path. It does not yet preserve cancellation through cleanup or distinguish a
held exposure from the deferred camera-timed case. See issue #251 before using
this as a firmware candidate; physical shutter closure is not established.
"""
import argparse
import os
import re
import stat
import struct
import subprocess
import sys
import tempfile
from elftools.elf.elffile import ELFFile

BURST_PROLOGUE = (0xE92D4810, 0xE28DB008, 0xE24DD0AC)
BULB_PROLOGUE = (0xE92D4810, 0xE28DB008, 0xE24DDD2F, 0xE24DD004)
# The original trampoline only checked the model.  The live conditions query
# and its literal strings need a larger, still page-local code cave.
TRAMPOLINE_SIZE = 0x300

# The stock helper's cancellation edge is stable in the supported pgphoto
# binary: ``beq`` at capture_image_with_Bulb+0x330 jumped straight to the common
# return tail, bypassing the normal stop path.  The stop path begins at +0x3a4
# and constructs/invokes the existing stop callback later in that path.  Keep
# both anchors explicit and verify the old target before changing it.
BULB_CANCEL_OFFSET = 0x330
BULB_CANCEL_OLD_TARGET_OFFSET = 0x748
BULB_CANCEL_STOP_PATH_OFFSET = 0x3a4

# Code-cave sub-layout (the trampoline is hand-assembled ARM; see
# build_trampoline). The literal pool and match strings sit after the code. The
# Stack-backed getCameraName/conditions destination buffer is NOT here: the code cave lives in
# the read-only (R+X) text segment, and getCameraName copies the lowercased
# model name into its r0 argument, so the buffer is allocated on the stack at
# run time (sub sp). getCameraName returns status (0 or -1), not a text pointer. Check
# the status and then inspect the buffer contents (issue #210).
LITERAL_POOL = 0x240
PENTAX_TEXT = 0x260
MODEL_TEXT = 0x270
CONDITIONS_KEY_TEXT = 0x290
MODE_KEY_TEXT = 0x2A4
# getCameraName reads CameraPrivateCore.a.model, not the UI display name.
# Exact label from libgphoto2 library.c's 25fb:0189 abilities entry.
MODEL_NAME = b"Pentax:K-3 Mark III (MTP mode)"
# The name uses this stack buffer.  Afterwards sp holds the widget pointer and
# sp+4 holds either its type or the char * borrowed from the widget.
NAME_BUF_BYTES = 2048
OBJDUMP = os.environ.get("OBJDUMP", "arm-linux-gnueabi-objdump")


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
        size = segment.header["p_filesz"]
        if start <= address < start + size:
            return segment.header["p_offset"] + address - start
    raise ValueError("address 0x%x is not in a file-backed LOAD segment" % address)


def encode_branch(source, target, condition=0xE, link=False):
    displacement = target - (source + 8)
    if displacement & 3 or not -(1 << 25) <= displacement < (1 << 25):
        raise ValueError("ARM branch from 0x%x to 0x%x is out of range/alignment" %
                         (source, target))
    immediate = (displacement >> 2) & 0xFFFFFF
    return (condition << 28) | 0x0A000000 | (0x01000000 if link else 0) | immediate


def build_trampoline(cave, burst, bulb, get_manufacturer, get_name, strcasestr,
                     camera_global, camera_get_single_config,
                     widget_get_type, widget_get_value, widget_free, strstr):
    # Hand-assembled ARM. Entry registers are the stock burst arguments:
    #   r0 = status, r1 = duration (bTime), r2 = newFiles.
    # Positive-duration, status-0 Pentax K-3 III (non-Monochrome) requests are
    # routed to capture_image_with_Bulb(status, duration, newFiles) only after
    # a same-session ``pentaxconditions`` read confirms raw exposure mode 9, 12
    # or 20 (B, lens-B or Astro).  The stock burst helper is used for a
    # successfully read non-B mode.  A
    # failed/invalid read for the selected model returns CAMERA_BUSY instead of
    # starting an exposure with an unknown mode.  This is one bounded read.
    #
    # Three correctness constraints the previous trampoline got wrong (issue #210):
    #   1. getCameraName copies the lowercased model name into its r0 destination
    #      buffer and returns 0 on success / -1 on error; the model check must
    #      inspect the buffer, never the return value. The buffer cannot live in
    #      the code cave (read-only text), so it is allocated on the stack.
    #   2. strcasestr/getCameraName clobber r0-r3, so the original arguments are
    #      saved on entry and reloaded before the timed-Bulb call.
    #   3. After the timed-Bulb call the trampoline must return, not fall through
    #      into the stock burst body (which would capture twice).
    do_bulb = 0x11C            # free widget, restore arguments, tail-call Bulb
    restore_fallback = 0x130   # drop buffer + reload args, then fall to fallback
    fallback = 0x138           # reconstruct prologue + resume (nothing pushed)
    pentax_lit = LITERAL_POOL
    model_lit = LITERAL_POOL + 4
    conditions_key_lit = LITERAL_POOL + 12
    mode_key_lit = LITERAL_POOL + 16
    camera_global_lit = LITERAL_POOL + 28

    def ldr_pc(instr_off, literal_off, register=1):
        # ldr rN, [pc, #imm]; PC during execution is instr address + 8.
        imm = literal_off - (instr_off + 8)
        if not 0 <= imm < 0x1000 or imm & 3:
            raise ValueError("literal pool entry is out of ldr range")
        return 0xE59F0000 | (register << 12) | imm

    def br(instr_off, target, link=False, condition=0xE):
        # Branch at blob offset instr_off (address cave + instr_off) to target.
        return encode_branch(cave + instr_off, target, link=link, condition=condition)

    MOV_R0_SP = 0xE1A0000D
    PUSH_ARGS = 0xE92D4007     # push {r0, r1, r2, lr}
    POP_ARGS = 0xE8BD4007      # pop  {r0, r1, r2, lr}
    SUB_SP_BUF = 0xE24DDB02    # sub sp, sp, #2048
    ADD_SP_BUF = 0xE28DDB02    # add sp, sp, #2048
    ADD_R1_SP_4 = 0xE28D1004
    LDR_R0_SP_4 = 0xE59D0004
    CMP_R0 = 0xE3500000
    CMP_R1 = 0xE3510000
    MOV_R2_SP = 0xE1A0200D
    MOV_R3_0 = 0xE3A03000
    LDR_R0_SP = 0xE59D0000

    words = {
        0x00: CMP_R1,
        0x04: br(0x04, cave + fallback, condition=0xD),          # ble fallback
        0x08: CMP_R0,
        0x0C: br(0x0C, cave + fallback, condition=0x1),          # bne fallback
        0x10: PUSH_ARGS,
        0x14: SUB_SP_BUF,
        0x18: br(0x18, get_manufacturer, link=True),             # bl getCameraManufacturer
        0x1C: CMP_R0,
        0x20: br(0x20, cave + restore_fallback, condition=0x0),  # beq restore (null)
        0x24: ldr_pc(0x24, pentax_lit),                          # ldr r1, ="pentax"
        0x28: br(0x28, strcasestr, link=True),                   # bl strcasestr
        0x2C: CMP_R0,
        0x30: br(0x30, cave + restore_fallback, condition=0x0),  # beq restore (not pentax)
        0x34: MOV_R0_SP,                                         # r0 = stack buffer
        0x38: br(0x38, get_name, link=True),                     # bl getCameraName
        0x3C: CMP_R0,
        0x40: br(0x40, cave + restore_fallback, condition=0x1),  # bne restore (name error)
        0x44: MOV_R0_SP,                                         # r0 = buffer
        0x48: ldr_pc(0x48, model_lit),                           # full registered label
        0x4C: br(0x4C, strcasestr, link=True),                   # bl strcasestr
        # strcasestr must match at the start AND finish at the terminating NUL.
        # This excludes prefixes, suffixes and Monochrome without another gate.
        0x50: 0xE150000D,                                       # cmp r0, sp
        0x54: br(0x54, cave + restore_fallback, condition=0x1),
        0x58: 0xE5DD0000 | len(MODEL_NAME),                     # ldrb r0, [sp, #30]
        0x5C: CMP_R0,
        0x60: br(0x60, cave + restore_fallback, condition=0x1),
        0x64: 0xE1A00000,                                       # nop; preserve query layout
        0x68: 0xE1A00000,
        # Query the same-session Pentax Conditions widget.  The widget pointer
        # is at sp; a type/char-pointer slot is at sp+4.  A failed read returns
        # an error; it must not start a stock capture of unknown mode.
        0x6C: ldr_pc(0x6C, camera_global_lit, register=0),        # &camera
        0x70: 0xE5900000,                                        # ldr r0, [r0]
        0x74: ldr_pc(0x74, conditions_key_lit),                   # "pentaxconditions"
        0x78: MOV_R2_SP,                                         # widget ** at sp
        0x7C: br(0x7C, cave + 0x164),                           # initialise widget output
        0x80: br(0x80, camera_get_single_config, link=True),
        0x84: CMP_R0,
        0x88: br(0x88, cave + 0x148, condition=0x1),            # bne error
        0x8C: LDR_R0_SP,
        0x90: CMP_R0,
        0x94: br(0x94, cave + 0x148, condition=0x0),            # beq error
        0x98: ADD_R1_SP_4,                                      # int *type
        0x9C: br(0x9C, widget_get_type, link=True),
        0xA0: CMP_R0,
        0xA4: br(0xA4, cave + 0x158, condition=0x1),
        0xA8: LDR_R0_SP_4,
        0xAC: 0xE3500002,                                       # GP_WIDGET_TEXT == 2
        0xB0: br(0xB0, cave + 0x158, condition=0x1),
        0xB4: LDR_R0_SP,
        0xB8: ADD_R1_SP_4,                                      # char **value
        0xBC: br(0xBC, cave + 0x174, link=True),                 # clear reused value slot
        0xC0: CMP_R0,
        0xC4: br(0xC4, cave + 0x158, condition=0x1),
        0xC8: LDR_R0_SP_4,                                      # borrowed char *
        0xCC: CMP_R0,
        0xD0: br(0xD0, cave + 0x158, condition=0x0),
        0xD4: ldr_pc(0xD4, mode_key_lit),
        0xD8: br(0xD8, strstr, link=True),
        0xDC: CMP_R0,
        0xE0: br(0xE0, cave + 0x158, condition=0x0),          # missing field
        0xE4: LDR_R0_SP_4 | 0x00001000,                         # r1 = text base
        0xE8: 0xE0402001,                                       # distance from text base
        0xEC: 0xE3520002,
        0xF0: br(0xF0, cave + 0x158, condition=0x3),          # no preceding delimiter
        0xF4: 0xE5501002,                                       # preceding ';'
        0xF8: 0xE351003B,
        0xFC: br(0xFC, cave + 0x158, condition=0x1),
        0x100: 0xE5501001,                                      # preceding space
        0x104: 0xE3510020,
        0x108: br(0x108, cave + 0x158, condition=0x1),
        0x10C: br(0x10C, cave + 0x180),                          # parse bounded value
        # Keep the widget alive throughout all searches, then free exactly once.
        0x110: LDR_R0_SP,
        0x114: br(0x114, widget_free, link=True),
        0x118: br(0x118, cave + restore_fallback),
        0x11C: LDR_R0_SP,
        0x120: br(0x120, widget_free, link=True),
        0x124: ADD_SP_BUF,
        0x128: POP_ARGS,
        0x12C: br(0x12C, bulb),
        # restore_fallback: drop the buffer, reload args, then run the stock path.
        0x130: ADD_SP_BUF,
        0x134: POP_ARGS,
        # fallback: reconstruct the prologue clobbered by the entry branch.
        0x138: BURST_PROLOGUE[0],
        0x13C: BURST_PROLOGUE[1],
        0x140: BURST_PROLOGUE[2],
        0x144: br(0x144, burst + 12),
        # GP_ERROR_CAMERA_BUSY (-110) means no shot was started.  Free any
        # successfully returned widget before returning to the original caller.
        0x148: ADD_SP_BUF,
        0x14C: POP_ARGS,
        0x150: 0xE3E0006D,                                      # mvn r0, #109
        0x154: 0xE12FFF1E,                                      # bx lr
        0x158: LDR_R0_SP,
        0x15C: br(0x15C, widget_free, link=True),
        0x160: br(0x160, cave + 0x148),
        0x164: MOV_R3_0,
        0x168: 0xE58D3000,                                      # str r3, [sp]
        0x16C: 0xE58D3004,                                      # str r3, [sp, #4]
        0x170: br(0x170, cave + 0x80),
        # The value slot held GP_WIDGET_TEXT (2). Never let a successful
        # callback with no output turn that enum into a borrowed pointer.
        # Tail-call get_value with the LR from 0xBC, returning to 0xC0.
        0x174: MOV_R3_0,
        0x178: 0xE58D3004,
        0x17C: br(0x17C, widget_get_value),

        # Parse the canonical, unsigned one- or two-digit %u field, requiring
        # its semicolon and an IT2 ExpMode.cs value (0..31).  A malformed or
        # unknown value is an error, not permission to start a stock capture.
        # The widget remains alive until the free paths below are reached.
        0x180: 0xE2800012,                                      # skip 18-byte key
        0x184: 0xE4D01001,                                      # first digit
        0x188: 0xE3510030,
        0x18C: br(0x18C, cave + 0x158, condition=0x3),
        0x190: 0xE3510039,
        0x194: br(0x194, cave + 0x158, condition=0x8),
        0x198: 0xE2411030,
        0x19C: 0xE4D02001,
        0x1A0: 0xE352003B,
        0x1A4: br(0x1A4, cave + 0x1D8, condition=0x0),
        0x1A8: 0xE3510000,                                      # reject leading zero
        0x1AC: br(0x1AC, cave + 0x158, condition=0x0),
        0x1B0: 0xE3520030,
        0x1B4: br(0x1B4, cave + 0x158, condition=0x3),
        0x1B8: 0xE3520039,
        0x1BC: br(0x1BC, cave + 0x158, condition=0x8),
        0x1C0: 0xE2422030,
        0x1C4: 0xE0811101,
        0x1C8: 0xE0821081,                                      # 10*first + second
        0x1CC: 0xE5D02000,
        0x1D0: 0xE352003B,
        0x1D4: br(0x1D4, cave + 0x158, condition=0x1),
        0x1D8: br(0x1D8, cave + 0x200),                          # reject duplicate keys
        0x1E0: 0xE3510009,
        0x1E4: br(0x1E4, cave + do_bulb, condition=0x0),
        0x1E8: 0xE351000C,
        0x1EC: br(0x1EC, cave + do_bulb, condition=0x0),
        0x1F0: 0xE3510014,
        0x1F4: br(0x1F4, cave + do_bulb, condition=0x0),
        0x1F8: br(0x1F8, cave + 0x110),                          # known non-B mode
        0x200: 0xE58D1008,                                      # save mode over strstr
        0x204: 0xE2400001,                                      # include first semicolon
        0x208: ldr_pc(0x208, mode_key_lit),
        0x20C: br(0x20C, strstr, link=True),                     # search remainder
        0x210: CMP_R0,
        0x214: br(0x214, cave + 0x158, condition=0x1),
        0x218: 0xE59D1008,
        0x21C: 0xE351001F,
        0x220: br(0x220, cave + 0x158, condition=0x8),
        0x224: br(0x224, cave + 0x1E0),
        pentax_lit: cave + PENTAX_TEXT,
        model_lit: cave + MODEL_TEXT,
        conditions_key_lit: cave + CONDITIONS_KEY_TEXT,
        mode_key_lit: cave + MODE_KEY_TEXT,
        camera_global_lit: camera_global,
    }
    blob = bytearray(TRAMPOLINE_SIZE)
    for offset, word in words.items():
        struct.pack_into("<I", blob, offset, word)
    blob[PENTAX_TEXT:PENTAX_TEXT + 7] = b"pentax\0"
    if len(MODEL_NAME) + 1 > CONDITIONS_KEY_TEXT - MODEL_TEXT:
        raise ValueError("registered model name overlaps the conditions key")
    blob[MODEL_TEXT:MODEL_TEXT + len(MODEL_NAME) + 1] = MODEL_NAME + b"\0"
    blob[CONDITIONS_KEY_TEXT:CONDITIONS_KEY_TEXT + 17] = b"pentaxconditions\0"
    blob[MODE_KEY_TEXT:MODE_KEY_TEXT + 19] = b"exposure-mode-raw=\0"
    return bytes(blob)


def capture_call_setup_is_valid(data, site_offset):
    expected = (0xE1A02003, 0xE51B1028, 0xE3A00000)
    if site_offset < 12 or site_offset + 4 > len(data):
        return False
    actual = tuple(struct.unpack_from("<I", data, site_offset - 12 + i * 4)[0]
                   for i in range(3))
    return actual == expected


def call_instructions(path):
    output = subprocess.check_output(
        [OBJDUMP, "-d", "--no-show-raw-insn", path],
        stderr=subprocess.DEVNULL,
    ).decode("utf-8", "replace")
    calls = []
    pattern = re.compile(r"^\s*([0-9a-f]+):\s+bl\s+([0-9a-f]+)\s+<([^>]+)>", re.M)
    for match in pattern.finditer(output):
        calls.append((int(match.group(1), 16), int(match.group(2), 16), match.group(3)))
    strcasestr_plt = re.search(r"^\s*([0-9a-f]+)\s+<strcasestr@plt>:", output, re.M)
    strstr_plt = re.search(r"^\s*([0-9a-f]+)\s+<strstr@plt>:", output, re.M)
    if not strcasestr_plt or not strstr_plt:
        raise ValueError("strcasestr@plt or strstr@plt is missing")
    return (calls, int(strcasestr_plt.group(1), 16),
            int(strstr_plt.group(1), 16), output)


def bulb_cancel_patch_word(bulb, target):
    """Retarget the stock cancel-only BEQ without changing its condition."""
    return encode_branch(bulb + BULB_CANCEL_OFFSET, target, condition=0x0)


def patch_bulb_cancel(data, offsets, addresses):
    """Make cancellation enter the helper's normal stop path."""
    cancel_off = offsets["bulb"] + BULB_CANCEL_OFFSET
    source = addresses["bulb"] + BULB_CANCEL_OFFSET
    old_target = addresses["bulb"] + BULB_CANCEL_OLD_TARGET_OFFSET
    stop_target = addresses["bulb"] + BULB_CANCEL_STOP_PATH_OFFSET
    old_word = struct.unpack_from("<I", data, cancel_off)[0]
    if old_word == bulb_cancel_patch_word(addresses["bulb"], stop_target):
        return bytes(data), False
    if old_word != encode_branch(source, old_target, condition=0x0):
        raise ValueError("capture_image_with_Bulb cancel branch is not the verified stock edge")
    patched = bytearray(data)
    struct.pack_into("<I", patched, cancel_off,
                     bulb_cancel_patch_word(addresses["bulb"], stop_target))
    return bytes(patched), True


def patch_data(data, offsets, addresses, segment):
    burst_off = offsets["burst"]
    existing_branch = struct.unpack_from("<I", data, burst_off)[0]
    current_filesz = segment["filesz"]
    current_memsz = segment["memsz"]
    original_burst = tuple(struct.unpack_from("<I", data, burst_off + offset)[0]
                           for offset in (0, 4, 8))
    if current_filesz >= TRAMPOLINE_SIZE and current_filesz == current_memsz:
        marker_filesz = current_filesz - TRAMPOLINE_SIZE
        marker_cave = segment["vaddr"] + marker_filesz
        marker_off = segment["offset"] + marker_filesz
        marker_branch = encode_branch(addresses["burst"], marker_cave)
        marker = build_trampoline(
            marker_cave, addresses["burst"], addresses["bulb"],
            addresses["manufacturer"], addresses["name"], addresses["strcasestr"],
            addresses["camera_global"], addresses["camera_get_single_config"],
            addresses["widget_get_type"], addresses["widget_get_value"], addresses["widget_free"],
            addresses["strstr"],
        )
        if (existing_branch == marker_branch and
                bytes(data[marker_off:marker_off + TRAMPOLINE_SIZE]) == marker and
                struct.unpack_from("<I", data,
                    offsets["bulb"] + BULB_CANCEL_OFFSET)[0] ==
                    bulb_cancel_patch_word(addresses["bulb"],
                        addresses["bulb"] + BULB_CANCEL_STOP_PATH_OFFSET)):
            return bytes(data), False

    if existing_branch != BURST_PROLOGUE[0] or original_burst != BURST_PROLOGUE:
        raise ValueError("capture_image_with_Burst prologue is not the verified stock sequence")
    if current_filesz != current_memsz:
        raise ValueError("executable LOAD has a non-file-backed tail; refusing to add dispatch code")
    cave = segment["vaddr"] + current_filesz
    cave_off = segment["offset"] + current_filesz
    if any(data[cave_off:cave_off + TRAMPOLINE_SIZE]):
        raise ValueError("unused executable LOAD tail is not zero-filled")
    for name, offset, size in segment["allocated_sections"]:
        if offset < cave_off + TRAMPOLINE_SIZE and cave_off < offset + size:
            raise ValueError("executable LOAD gap overlaps allocated section %s" % name)
    expected_branch = encode_branch(addresses["burst"], cave)
    trampoline = build_trampoline(
        cave, addresses["burst"], addresses["bulb"],
        addresses["manufacturer"], addresses["name"], addresses["strcasestr"],
        addresses["camera_global"], addresses["camera_get_single_config"],
        addresses["widget_get_type"], addresses["widget_get_value"], addresses["widget_free"],
        addresses["strstr"],
    )
    cave_symbol_off = offsets["bulb_function"]
    original_bulb_helper = tuple(struct.unpack_from("<I", data, cave_symbol_off + offset)[0]
                                 for offset in (0, 4, 8, 12))
    if original_bulb_helper != BULB_PROLOGUE:
        raise ValueError("captureBulbImage function entry is not the verified stock sequence")
    new_end = cave + TRAMPOLINE_SIZE
    page_alignment = max(segment["align"], 0x1000)
    if page_alignment & (page_alignment - 1):
        raise ValueError("executable LOAD alignment is not a power of two")
    next_page = (new_end + page_alignment - 1) & ~(page_alignment - 1)
    next_load_page = segment["next_vaddr"] & ~(page_alignment - 1)
    if cave_off + TRAMPOLINE_SIZE > segment["next_offset"] or next_page > next_load_page:
        raise ValueError("no non-overlapping executable LOAD gap for the Bulb dispatcher")

    patched = bytearray(data)
    struct.pack_into("<I", patched, burst_off, expected_branch)
    patched[cave_off:cave_off + len(trampoline)] = trampoline
    patched, _ = patch_bulb_cancel(patched, offsets, addresses)
    patched = bytearray(patched)
    phdr = segment["phdr_offset"]
    struct.pack_into("<I", patched, phdr + 16, current_filesz + TRAMPOLINE_SIZE)
    struct.pack_into("<I", patched, phdr + 20, current_memsz + TRAMPOLINE_SIZE)
    return bytes(patched), True


def inspect_binary(path):
    with open(path, "rb") as stream:
        elf = ELFFile(stream)
        if elf.elfclass != 32 or elf.little_endian is False or elf.header["e_machine"] != "EM_ARM":
            raise ValueError("pgphoto must be a 32-bit little-endian ARM executable")
        burst, burst_size = symbol_value(elf, "capture_image_with_Burst")
        bulb, bulb_size = symbol_value(elf, "capture_image_with_Bulb")
        bulb_function, bulb_function_size = symbol_value(elf, "captureBulbImage")
        manufacturer, _ = symbol_value(elf, "getCameraManufacturer")
        name, _ = symbol_value(elf, "getCameraName")
        camera_global, _ = symbol_value(elf, "camera")
        camera_get_single_config, _ = symbol_value(elf, "gp_camera_get_single_config")
        widget_get_type, _ = symbol_value(elf, "gp_widget_get_type")
        widget_get_value, _ = symbol_value(elf, "gp_widget_get_value")
        widget_free, _ = symbol_value(elf, "gp_widget_free")
        capture, capture_size = symbol_value(elf, "captureImage")
        if burst_size < 12 or bulb_size == 0 or bulb_function_size < 16 or capture_size == 0:
            raise ValueError("pgphoto capture functions have unexpected sizes")
        calls, strcasestr, strstr, disassembly = call_instructions(path)
        if not re.search(r"^\s*0*%x\s+<captureImage>:" % capture, disassembly, re.M):
            raise ValueError("captureImage disassembly/symbol anchor mismatch")
        if not re.search(r"^\s*0*%x\s+<capture_image_with_Burst>:" % burst, disassembly, re.M):
            raise ValueError("burst-helper disassembly/symbol anchor mismatch")
        direct = [call for call in calls if call[1] == burst and capture <= call[0] < capture + capture_size]
        if len(direct) != 1:
            raise ValueError("expected one captureImage -> burst-helper call, found %d" % len(direct))
        caller_site = direct[0][0]
        caller_file_offset = va_to_offset(elf, caller_site)
        stream.seek(0)
        binary_data = stream.read()
        if not capture_call_setup_is_valid(binary_data, caller_file_offset):
            raise ValueError("captureImage burst call arguments differ from (status=0, duration=bTime, files)")

        loads = []
        for index, segment in enumerate(elf.iter_segments()):
            if segment.header["p_type"] != "PT_LOAD":
                continue
            item = {
                "offset": segment.header["p_offset"],
                "vaddr": segment.header["p_vaddr"],
                "filesz": segment.header["p_filesz"],
                "memsz": segment.header["p_memsz"],
                "flags": segment.header["p_flags"],
                "align": segment.header["p_align"],
                "phdr_offset": elf.header["e_phoff"] + index * elf.header["e_phentsize"],
            }
            loads.append(item)
        executable = [item for item in loads
                      if item["flags"] & 1 and
                      item["vaddr"] <= burst < item["vaddr"] + item["filesz"]]
        if len(executable) != 1:
            raise ValueError("expected one executable LOAD for burst helper, found %d" % len(executable))
        segment = executable[0]
        following = [item for item in loads if item["offset"] > segment["offset"]]
        following.sort(key=lambda item: item["offset"])
        if not following:
            raise ValueError("executable LOAD has no following segment to bound code-cave extension")
        segment["next_offset"] = following[0]["offset"]
        segment["next_vaddr"] = following[0]["vaddr"]
        segment["allocated_sections"] = [
            (section.name, section.header["sh_offset"], section.header["sh_size"])
            for section in elf.iter_sections()
            if section.header["sh_flags"] & 0x2 and
            section.header["sh_type"] != "SHT_NOBITS" and
            section.header["sh_size"]
        ]

        addresses = {
            "burst": burst,
            "bulb": bulb,
            "manufacturer": manufacturer,
            "name": name,
            "camera_global": camera_global,
            "camera_get_single_config": camera_get_single_config,
            "widget_get_type": widget_get_type,
            "widget_get_value": widget_get_value,
            "widget_free": widget_free,
            "strstr": strstr,
            "strcasestr": strcasestr,
        }
        # ``camera`` is a writable global in .bss, so it has no file-backed
        # offset.  The trampoline embeds its virtual address as a literal; it
        # is never read through the file-offset map.
        offsets = {
            key: va_to_offset(elf, value) for key, value in addresses.items()
            if key != "camera_global"
        }
        offsets["bulb_function"] = va_to_offset(elf, bulb_function)
        data = bytearray(binary_data)
    return data, offsets, addresses, segment


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pgphoto")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--in-place", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()

    try:
        data, offsets, addresses, segment = inspect_binary(args.pgphoto)
        patched, changed = patch_data(data, offsets, addresses, segment)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print("[polaris_bulb_dispatch] FATAL: %s" % error, file=sys.stderr)
        return 1

    if args.check:
        if changed:
            print("[polaris_bulb_dispatch] FATAL: timed Bulb dispatch marker missing", file=sys.stderr)
            return 1
        print("[polaris_bulb_dispatch] verified K-3 III live-mode Bulb dispatch and cancel-to-stop")
        return 0

    if changed:
        output_path = args.pgphoto if args.in_place else args.pgphoto + ".patched"
        if args.in_place:
            directory = os.path.dirname(os.path.abspath(output_path))
            mode_bits = stat.S_IMODE(os.stat(output_path).st_mode)
            fd, temporary = tempfile.mkstemp(prefix=".pgphoto-bulb-", dir=directory)
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
        print("[polaris_bulb_dispatch] patched %s: K-3 III live-mode gate, cancel-to-stop, and timed Bulb route" % output_path)
    else:
        print("[polaris_bulb_dispatch] already patched (unique verified dispatch)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
