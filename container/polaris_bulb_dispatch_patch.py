#!/usr/bin/env python3
"""Route positive-duration Pentax Bulb requests to pgphoto's timed Bulb helper."""
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
TRAMPOLINE_SIZE = 0x140

# Code-cave sub-layout (the trampoline is hand-assembled ARM; see
# build_trampoline). The literal pool and match strings sit after the code. The
# 128-byte getCameraName destination buffer is NOT here: the code cave lives in
# the read-only (R+X) text segment, and getCameraName copies the lowercased
# model name into its r0 argument, so the buffer is allocated on the stack at
# run time (sub sp). getCameraName always returns 0 (issue #210), so the model
# check inspects the buffer contents, never the return value.
LITERAL_POOL = 0x100
PENTAX_TEXT = 0x110
MODEL_TEXT = 0x120
MONO_TEXT = 0x130
NAME_BUF_BYTES = 136  # 128-byte name + 8-byte guard, keeps sp 8-byte aligned
OBJDUMP = os.environ.get("OBJDUMP", "arm-linux-gnueabi-objdump")


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


def encode_branch(source, target, condition=0xE, link=False):
    displacement = target - (source + 8)
    if displacement & 3 or not -(1 << 25) <= displacement < (1 << 25):
        raise ValueError("ARM branch from 0x%x to 0x%x is out of range/alignment" %
                         (source, target))
    immediate = (displacement >> 2) & 0xFFFFFF
    return (condition << 28) | 0x0A000000 | (0x01000000 if link else 0) | immediate


def build_trampoline(cave, burst, bulb, get_manufacturer, get_name, strcasestr):
    # Hand-assembled ARM. Entry registers are the stock burst arguments:
    #   r0 = status, r1 = duration (bTime), r2 = newFiles.
    # Positive-duration, status-0 Pentax K-3 III (non-Monochrome) requests are
    # routed to capture_image_with_Bulb(status, duration, newFiles) and its
    # result returned; everything else reconstructs the stock prologue and
    # resumes capture_image_with_Burst unchanged.
    #
    # Why there is no runtime "is the dial on B?" gate here (issue #205): the
    # app's capture request is `state:1;bulb:N;c:-1;` and N is the *requested
    # exposure duration*. Across every captured session log the normal-capture
    # path is always `bulb:0` and a positive `bulb:N` appears only on an explicit
    # long-exposure request (docs/evidence/*/raw/Mlog_*: 108x bulb:0, 124x
    # bulb:N>0, never a positive N on a plain timed capture). So r1 > 0 already
    # *is* the app's explicit "expose for N seconds" signal; a timed-shutter
    # capture never reaches this branch with a positive duration. Gating on the
    # physical dial would only suppress the timed helper for the exact requests
    # it exists to serve (the app drives the duration, not the dial), so the
    # duration check is the correct and sufficient gate.
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
    fallback = 0x80            # reconstruct prologue + resume (nothing pushed)
    restore_fallback = 0x78    # drop buffer + reload args, then fall to fallback
    do_bulb = 0x6C             # drop buffer + reload args, then tail-call Bulb
    pentax_lit = LITERAL_POOL
    model_lit = LITERAL_POOL + 4
    mono_lit = LITERAL_POOL + 8

    def ldr_pc(instr_off, literal_off):
        # ldr r1, [pc, #imm]; PC during execution is instr address + 8.
        imm = literal_off - (instr_off + 8)
        if not 0 <= imm < 0x1000 or imm & 3:
            raise ValueError("literal pool entry is out of ldr range")
        return 0xE59F1000 | imm

    def br(instr_off, target, link=False, condition=0xE):
        # Branch at blob offset instr_off (address cave + instr_off) to target.
        return encode_branch(cave + instr_off, target, link=link, condition=condition)

    MOV_R0_SP = 0xE1A0000D
    PUSH_ARGS = 0xE92D4007     # push {r0, r1, r2, lr}
    POP_ARGS = 0xE8BD4007      # pop  {r0, r1, r2, lr}
    SUB_SP_BUF = 0xE24DD088    # sub sp, sp, #136
    ADD_SP_BUF = 0xE28DD088    # add sp, sp, #136
    CMP_R0 = 0xE3500000
    CMP_R1 = 0xE3510000

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
        0x48: ldr_pc(0x48, model_lit),                           # ldr r1, ="K-3 Mark III"
        0x4C: br(0x4C, strcasestr, link=True),                   # bl strcasestr
        0x50: CMP_R0,
        0x54: br(0x54, cave + restore_fallback, condition=0x0),  # beq restore (not K-3 III)
        0x58: MOV_R0_SP,                                         # r0 = buffer
        0x5C: ldr_pc(0x5C, mono_lit),                            # ldr r1, ="Monochrome"
        0x60: br(0x60, strcasestr, link=True),                   # bl strcasestr
        0x64: CMP_R0,
        0x68: br(0x68, cave + restore_fallback, condition=0x1),  # bne restore (Monochrome)
        # do_bulb: reload the original arguments, then tail-call the timed helper
        # so its result is returned directly to the original caller.
        0x6C: ADD_SP_BUF,
        0x70: POP_ARGS,
        0x74: br(0x74, bulb),                                    # b capture_image_with_Bulb
        # restore_fallback: drop the buffer, reload args, then run the stock path.
        0x78: ADD_SP_BUF,
        0x7C: POP_ARGS,
        # fallback: reconstruct the prologue clobbered by the entry branch.
        0x80: BURST_PROLOGUE[0],
        0x84: BURST_PROLOGUE[1],
        0x88: BURST_PROLOGUE[2],
        0x8C: br(0x8C, burst + 12),                              # b burst_resume
        pentax_lit: cave + PENTAX_TEXT,
        model_lit: cave + MODEL_TEXT,
        mono_lit: cave + MONO_TEXT,
    }
    blob = bytearray(TRAMPOLINE_SIZE)
    for offset, word in words.items():
        struct.pack_into("<I", blob, offset, word)
    blob[PENTAX_TEXT:PENTAX_TEXT + 7] = b"pentax\0"
    blob[MODEL_TEXT:MODEL_TEXT + 13] = b"K-3 Mark III\0"
    blob[MONO_TEXT:MONO_TEXT + 11] = b"Monochrome\0"
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
    plt = re.search(r"^\s*([0-9a-f]+)\s+<strcasestr@plt>:", output, re.M)
    if not plt:
        raise ValueError("strcasestr@plt is missing")
    return calls, int(plt.group(1), 16), output


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
        )
        if (existing_branch == marker_branch and
                bytes(data[marker_off:marker_off + TRAMPOLINE_SIZE]) == marker):
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
        capture, capture_size = symbol_value(elf, "captureImage")
        if burst_size < 12 or bulb_size == 0 or bulb_function_size < 16 or capture_size == 0:
            raise ValueError("pgphoto capture functions have unexpected sizes")
        calls, strcasestr, disassembly = call_instructions(path)
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
            "strcasestr": strcasestr,
        }
        offsets = {
            key: va_to_offset(elf, value) for key, value in addresses.items()
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
        print("[polaris_bulb_dispatch] verified duration-aware Pentax dispatch")
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
        print("[polaris_bulb_dispatch] patched %s: positive-duration K-3 III requests use timed Bulb action" % output_path)
    else:
        print("[polaris_bulb_dispatch] already patched (unique verified dispatch)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
