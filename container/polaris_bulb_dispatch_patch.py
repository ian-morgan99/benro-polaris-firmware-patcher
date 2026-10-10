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
TRAMPOLINE_SIZE = 0xB0
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
    addresses = {
        "fallback": cave + 0x74,
        "restore": cave + 0x70,
        "burst_resume": burst + 12,
        "pentax_literal": cave + 0x84,
        "model_literal": cave + 0x88,
        "mono_literal": cave + 0x8C,
        "pentax_text": cave + 0x90,
        "model_text": cave + 0x97,
        "mono_text": cave + 0xA4,
    }
    words = {
        0x00: 0xE3510000,  # cmp r1, #0
        0x04: encode_branch(cave + 0x04, addresses["fallback"], condition=0xD),  # ble fallback
        0x08: 0xE3500000,  # cmp r0, #0
        0x0C: encode_branch(cave + 0x0C, addresses["fallback"], condition=0x1),  # bne fallback
        0x10: 0xE92D4007,  # push {r0, r1, r2, lr}
        0x14: encode_branch(cave + 0x14, get_manufacturer, link=True),
        0x18: 0xE3500000,  # cmp r0, #0
        0x1C: encode_branch(cave + 0x1C, addresses["restore"], condition=0x0),
        0x20: 0xE59F105C,  # ldr r1, [pc, #0x5c]
        0x24: encode_branch(cave + 0x24, strcasestr, link=True),
        0x28: 0xE3500000,  # cmp r0, #0
        0x2C: encode_branch(cave + 0x2C, addresses["restore"], condition=0x0),
        0x30: encode_branch(cave + 0x30, get_name, link=True),
        0x34: 0xE3500000,  # cmp r0, #0
        0x38: encode_branch(cave + 0x38, addresses["restore"], condition=0x0),
        0x3C: 0xE59F1044,  # ldr r1, [pc, #0x44]
        0x40: encode_branch(cave + 0x40, strcasestr, link=True),
        0x44: 0xE3500000,  # cmp r0, #0
        0x48: encode_branch(cave + 0x48, addresses["restore"], condition=0x0),
        0x4C: encode_branch(cave + 0x4C, get_name, link=True),
        0x50: 0xE3500000,  # cmp r0, #0
        0x54: encode_branch(cave + 0x54, addresses["restore"], condition=0x0),
        0x58: 0xE59F102C,  # ldr r1, [pc, #0x2c]
        0x5C: encode_branch(cave + 0x5C, strcasestr, link=True),
        0x60: 0xE3500000,  # cmp r0, #0
        0x64: encode_branch(cave + 0x64, addresses["restore"], condition=0x1),
        0x68: 0xE8BD4007,  # pop {r0, r1, r2, lr}
        0x6C: encode_branch(cave + 0x6C, bulb),
        0x70: 0xE8BD4007,  # restore inputs before normal capture
        0x74: BURST_PROLOGUE[0],
        0x78: BURST_PROLOGUE[1],
        0x7C: BURST_PROLOGUE[2],
        0x80: encode_branch(cave + 0x80, addresses["burst_resume"]),
        0x84: addresses["pentax_text"],
        0x88: addresses["model_text"],
        0x8C: addresses["mono_text"],
    }
    blob = bytearray(TRAMPOLINE_SIZE)
    for offset, word in words.items():
        struct.pack_into("<I", blob, offset, word)
    blob[0x90:0x97] = b"pentax\0"
    blob[0x97:0xA4] = b"K-3 Mark III\0"
    blob[0xA4:0xAF] = b"Monochrome\0"
    return bytes(blob)


def capture_call_setup_is_valid(disassembly, site):
    lines = disassembly.splitlines()
    try:
        position = next(i for i, line in enumerate(lines)
                        if re.match(r"\s*0*%x:" % site, line))
    except StopIteration:
        return False
    prior = [re.sub(r"\s+", " ",
                    re.sub(r"^\s*[0-9a-f]+:\s+", "", line).split("@", 1)[0].strip())
             for line in lines[max(0, position - 3):position]]
    return prior == ["mov r2, r3", "ldr r1, [fp, #-40]", "mov r0, #0"]


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
        if not capture_call_setup_is_valid(disassembly, caller_site):
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
        stream.seek(0)
        data = bytearray(stream.read())
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
