#!/usr/bin/env python3
"""Produce a fail-closed static plan for the unqualified ``AC 4A`` lead.

This tool is deliberately an analyser, not a firmware patcher.  The exact
`.73` application contains a helper which can queue an axis/float frame, but
the application dispatcher does not expose that helper and the MCU contract
has not been qualified.  A command slot must therefore never be selected by
guesswork and this tool never writes an application binary.

The output is a machine-readable ledger of the facts that were checked:

* exact application and matching ``polaris413`` hashes;
* ELF/load-segment identity and the dispatcher table;
* the unused dispatcher slots that are only investigation candidates;
* the existing helper signature and the available zero-filled executable
  space; and
* the gates that still prevent an implementation.

It is safe to run against a copy of a firmware payload.  It does not open a
socket, talk to a mount, alter a package, or emit a patched binary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path


FILE_VA_BIAS = 0x10000
EXPECTED_APP_SHA256 = "a5e58ffd76670cf9bdc76560a859d2e037ca4320d37bb3c2d93d482cf459ac02"
EXPECTED_GIMBAL_SHA256 = "34d3f4186185c541adb9c8e57b3e2ec13e402dfb4bb3e9b2262cbf03f1a5c112"
EXPECTED_APP_SIZE = 24_941_228
EXPECTED_GIMBAL_SIZE = 84_284

DISPATCHER_VA = 0x48128
TABLE_VA = 0x48188
TABLE_COUNT = 37
FIRST_COMMAND = 513
LAST_COMMAND = FIRST_COMMAND + TABLE_COUNT - 1
DEFAULT_COMMANDS = (515, 516, 518, 523, 527, 528)
DEFAULT_TARGET_VA = 0x4957C

HELPER_VA = 0x636E8
HELPER_SIZE = 144
UART_TX_VA = 0x5F524
CODE_CAVE_FILE_OFFSET = 0xA70980
CODE_CAVE_SIZE = 352
CODE_CAVE_VA = CODE_CAVE_FILE_OFFSET + FILE_VA_BIAS

# The complete table is pinned because choosing a free slot is only meaningful
# if all neighbouring entries are still the reviewed dispatcher.
EXPECTED_TABLE_WORDS = (
    0xEA000023, 0xEA000030, 0xEA0004F9, 0xEA0004F8,
    0xEA000049, 0xEA0004F6, 0xEA00004E, 0xEA0000AC,
    0xEA000037, 0xEA0004F2, 0xEA000146, 0xEA00015F,
    0xEA0004EF, 0xEA00015F, 0xEA000167, 0xEA0004EC,
    0xEA0004EB, 0xEA0001B9, 0xEA000259, 0xEA00027E,
    0xEA00028D, 0xEA00029C, 0xEA0002AB, 0xEA0002D9,
    0xEA0002FB, 0xEA000389, 0xEA0003C3, 0xEA0003F8,
    0xEA000432, 0xEA000433, 0xEA00043C, 0xEA000451,
    0xEA00047A, 0xEA00047B, 0xEA000486, 0xEA000496,
    0xEA0004B1,
)

# The surrounding dispatcher prologue/range check and the helper's key
# instructions are more useful than an opaque binary hash when reviewing a
# future failure report.  The hash is still the primary identity gate.
EXPECTED_DISPATCHER_PREFIX = (
    0xE24DD010, 0xE92D4810, 0xED2D8B08, 0xE28DB028,
    0xE24DDD12, 0xE24DD004, 0xE28BC004, 0xE88C000F,
)
EXPECTED_DISPATCHER_RANGE = (
    0xE2033CFF, 0xE3530C02, 0x0A000001, 0xE3E03000,
    0xEA000503, 0xE59B3008, 0xE2433C02, 0xE2433001,
    0xE3530024, 0x908FF103, 0xEA0004FC,
)
EXPECTED_HELPER_PREFIX = (
    0xE92D4800, 0xE28DB004, 0xE24DD008, 0xE50B0008,
    0xE50B100C, 0xE59F306C, 0xE08F3003, 0xE59F2068,
)
EXPECTED_HELPER_FRAME = {
    0x24: 0xE3E01053,  # mvn r1, #83 -> 0xAC
    0x28: 0xE5C21000,  # strb r1, [r2]
    0x34: 0xE3A0104A,  # mov r1, #74 -> 0x4A
    0x38: 0xE5C21001,
    0x4C: 0xE5C21002,  # axis byte
    0x68: 0xE3A01007,  # seven-byte frame
}
EXPECTED_HELPER_SEND = 0xEBFFEF6F


class AnalysisError(ValueError):
    """The supplied payload is not the exact reviewed binary."""


def va_to_file(va: int) -> int:
    if va < FILE_VA_BIAS:
        raise AnalysisError(f"VA 0x{va:x} is below the reviewed load bias")
    return va - FILE_VA_BIAS


def read_words(data: bytes, va: int, count: int) -> tuple[int, ...]:
    offset = va_to_file(va)
    end = offset + 4 * count
    if end > len(data):
        raise AnalysisError(f"VA range 0x{va:x}..0x{va + 4 * count:x} is outside the file")
    return struct.unpack(f"<{count}I", data[offset:end])


def read_word(data: bytes, va: int) -> int:
    return read_words(data, va, 1)[0]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_load_segments(data: bytes) -> list[dict[str, int]]:
    if len(data) < 52 or data[:4] != b"\x7fELF":
        raise AnalysisError("application is not an ELF file")
    elf_class, endian = data[4], data[5]
    if (elf_class, endian) != (1, 1):
        raise AnalysisError("application is not a 32-bit little-endian ELF")
    e_type, e_machine = struct.unpack_from("<HH", data, 16)
    if (e_type, e_machine) != (2, 40):
        raise AnalysisError(f"unexpected ELF type/machine: {e_type}/{e_machine}")
    phoff = struct.unpack_from("<I", data, 28)[0]
    phentsize, phnum = struct.unpack_from("<HH", data, 42)
    if phentsize != 32 or phoff + phentsize * phnum > len(data):
        raise AnalysisError("invalid ELF program-header table")
    segments = []
    for index in range(phnum):
        offset = phoff + index * phentsize
        p_type, p_offset, p_vaddr, _, p_filesz, p_memsz, p_flags, p_align = struct.unpack_from(
            "<IIIIIIII", data, offset
        )
        if p_type == 1:
            segments.append({
                "index": index,
                "offset": p_offset,
                "vaddr": p_vaddr,
                "filesz": p_filesz,
                "memsz": p_memsz,
                "flags": p_flags,
                "align": p_align,
            })
    if not segments:
        raise AnalysisError("application has no loadable segments")
    return segments


def segment_for_file(segments: list[dict[str, int]], offset: int, size: int) -> dict[str, int] | None:
    for segment in segments:
        if segment["offset"] <= offset and offset + size <= segment["offset"] + segment["filesz"]:
            return segment
    return None


def branch_target(va: int, instruction: int) -> int | None:
    """Decode an ARM B/BL instruction, returning None for another opcode."""
    if instruction & 0x0E000000 != 0x0A000000:
        return None
    immediate = instruction & 0x00FFFFFF
    if immediate & 0x00800000:
        immediate -= 0x01000000
    return (va + 8 + (immediate << 2)) & 0xFFFFFFFF


def verify_exact(path: Path, expected_size: int, expected_hash: str, label: str) -> str:
    if not path.is_file():
        raise AnalysisError(f"{label} does not exist: {path}")
    actual_size = path.stat().st_size
    if actual_size != expected_size:
        raise AnalysisError(f"{label} size {actual_size} != reviewed size {expected_size}")
    actual_hash = sha256(path)
    if actual_hash != expected_hash:
        raise AnalysisError(f"{label} SHA-256 {actual_hash} != reviewed {expected_hash}")
    return actual_hash


def analyse(app_path: Path, gimbal_path: Path, command_id: int | None = None) -> dict:
    app_hash = verify_exact(app_path, EXPECTED_APP_SIZE, EXPECTED_APP_SHA256, "polestar_app")
    gimbal_hash = verify_exact(gimbal_path, EXPECTED_GIMBAL_SIZE, EXPECTED_GIMBAL_SHA256, "polaris413")
    data = app_path.read_bytes()
    segments = parse_load_segments(data)

    if read_words(data, DISPATCHER_VA, len(EXPECTED_DISPATCHER_PREFIX)) != EXPECTED_DISPATCHER_PREFIX:
        raise AnalysisError("dispatcher prologue does not match the reviewed .73 application")
    if read_words(data, 0x4815C, len(EXPECTED_DISPATCHER_RANGE)) != EXPECTED_DISPATCHER_RANGE:
        raise AnalysisError("dispatcher command-range check does not match the reviewed .73 application")
    table = read_words(data, TABLE_VA, TABLE_COUNT)
    if table != EXPECTED_TABLE_WORDS:
        raise AnalysisError("dispatcher table differs from the reviewed .73 application")
    if read_words(data, HELPER_VA, len(EXPECTED_HELPER_PREFIX)) != EXPECTED_HELPER_PREFIX:
        raise AnalysisError("SP_GimbalSetAxsi prologue differs from the reviewed helper")
    for relative_va, expected_word in EXPECTED_HELPER_FRAME.items():
        if read_word(data, HELPER_VA + relative_va) != expected_word:
            raise AnalysisError("SP_GimbalSetAxsi frame construction differs from the reviewed helper")
    if read_word(data, HELPER_VA + 0x78) != EXPECTED_HELPER_SEND:
        raise AnalysisError("SP_GimbalSetAxsi send call differs from the reviewed helper")

    cave_file_end = CODE_CAVE_FILE_OFFSET + CODE_CAVE_SIZE
    if cave_file_end > len(data) or data[CODE_CAVE_FILE_OFFSET:cave_file_end] != b"\0" * CODE_CAVE_SIZE:
        raise AnalysisError("reviewed executable zero-filled area is not available")
    cave_segment = segment_for_file(segments, CODE_CAVE_FILE_OFFSET, CODE_CAVE_SIZE)
    if cave_segment is None or not (cave_segment["flags"] & 0x1):  # PF_X
        raise AnalysisError("reviewed zero-filled area is not inside an executable LOAD")

    entries = []
    for index, word in enumerate(table):
        entry_va = TABLE_VA + index * 4
        entries.append({
            "command_id": FIRST_COMMAND + index,
            "entry_va": f"0x{entry_va:08x}",
            "word": f"0x{word:08x}",
            "target_va": f"0x{branch_target(entry_va, word):08x}" if branch_target(entry_va, word) is not None else None,
            "reviewed_default": FIRST_COMMAND + index in DEFAULT_COMMANDS,
        })

    selected = None
    if command_id is not None:
        if command_id < FIRST_COMMAND or command_id > LAST_COMMAND:
            raise AnalysisError(f"command {command_id} is outside dispatcher range {FIRST_COMMAND}..{LAST_COMMAND}")
        if command_id not in DEFAULT_COMMANDS:
            raise AnalysisError(f"command {command_id} is not one of the six reviewed default slots")
        selected = entries[command_id - FIRST_COMMAND]

    return {
        "status": "static-only-unqualified",
        "safe_to_patch": False,
        "writes_binary": False,
        "app": {
            "path": str(app_path),
            "size": app_path.stat().st_size,
            "sha256": app_hash,
            "firmware_family": "6.0.0.54.73 / .70-identical app",
        },
        "gimbal": {
            "path": str(gimbal_path),
            "size": gimbal_path.stat().st_size,
            "sha256": gimbal_hash,
            "image": "polaris413_2.0.0.22.bin",
        },
        "dispatcher": {
            "va": f"0x{DISPATCHER_VA:08x}",
            "table_va": f"0x{TABLE_VA:08x}",
            "command_range": [FIRST_COMMAND, LAST_COMMAND],
            "default_command_ids": list(DEFAULT_COMMANDS),
            "selected": selected,
            "entries": entries,
        },
        "helper": {
            "va": f"0x{HELPER_VA:08x}",
            "size": HELPER_SIZE,
            "uart_tx_va": f"0x{UART_TX_VA:08x}",
            "frame_shape": "AC 4A <axis:u8> <rate:little-endian IEEE-754 float>",
            "direct_dispatcher_caller": False,
        },
        "code_cave": {
            "file_offset": f"0x{CODE_CAVE_FILE_OFFSET:08x}",
            "va": f"0x{CODE_CAVE_VA:08x}",
            "bytes": CODE_CAVE_SIZE,
            "executable_load": True,
            "usable_for_production": False,
        },
        "unresolved_gates": [
            "no approved command ID or application reply contract",
            "MCU J/0x4A receiver route, length/checksum and acknowledgement unqualified",
            "rate units, axis mapping, sign and tick conversion uncalibrated",
            "zero/hold, acceleration, watchdog and link-loss semantics unqualified",
            "no exact-binary candidate patch has been built, installed or physically tested",
        ],
        "decision": "retain existing positional correction only; do not send AC 4A or repurpose a default slot",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", required=True, type=Path, help="exact extracted polestar_app")
    parser.add_argument("--gimbal", required=True, type=Path, help="matching polaris413_2.0.0.22.bin")
    parser.add_argument("--command-id", type=int, help="report one reviewed default slot (analysis only)")
    parser.add_argument("--out", type=Path, help="write JSON ledger here instead of stdout")
    args = parser.parse_args(argv)
    try:
        result = analyse(args.app, args.gimbal, args.command_id)
    except (AnalysisError, OSError, struct.error) as exc:
        print(f"[polestar_rate_candidate] FATAL: {exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
