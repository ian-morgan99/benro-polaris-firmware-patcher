#!/usr/bin/env python3
"""
dispatch_decode.py — Decode an ARM addls-based switch dispatch.

An ARM `addls pc, pc, rN, lsl #2` instruction is used as a multi-way
branch dispatcher. The pattern looks like:

    cmp    rN, #MAX     ; compare case value with max case number
    addls  pc, pc, rN, lsl #2  ; if rN <= MAX, branch to B-table entry
    b      default       ; otherwise fall through to default handler

The B-table immediately follows the `addls` instruction and contains
MAX+1 ARM `B <target>` instructions (4 bytes each), one per case. Each
entry is a real ARM `B imm24` instruction — NOT a relative data word.

Decoding formula (with capstone disabled detail mode for speed):
    word_addr = b_table_base + i*4
    word      = uint32 at word_addr
    imm24     = word & 0x00FFFFFF
    target    = (word_addr + 8) + (imm24 << 2)

Usage:
    python3 tools/dispatch_decode.py <elf> <b_table_addr> <num_cases>

Example:
    python3 tools/dispatch_decode.py \\
        artifacts/polestar_app/polestar_app.original \\
        0x3f670 24
"""
import sys
import struct
from elftools.elf.elffile import ELFFile


def decode_b_table(elf_path: str, b_table: int, num_cases: int) -> dict[int, int]:
    """Return {case_index: b_target} for a B-table at the given virtual address."""
    with open(elf_path, 'rb') as f:
        elf = ELFFile(f)
        text = elf.get_section_by_name('.text')
        text_data = text.data()
        text_addr = text['sh_addr']
        symtab = elf.get_section_by_name('.symtab')

        # Resolve symbol at the B-table start if any
        tbl_sym = ''
        for s in symtab.iter_symbols():
            if s['st_value'] == b_table:
                tbl_sym = s.name
                break

        result: dict[int, int] = {}
        for i in range(num_cases):
            word_addr = b_table + i * 4
            off = word_addr - text_addr
            if off < 0 or off + 4 > len(text_data):
                continue
            word = struct.unpack('<I', text_data[off:off+4])[0]
            # B imm24 encoding: top nibble 0xA (B/BL) with bit 24 = 0 (B, not BL)
            if (word & 0x0F000000) != 0x0A000000:
                # Not a B instruction — treat as relative data word
                soff = word if word < 0x80000000 else word - 0x100000000
                target = (word_addr + 8) + soff
            else:
                imm24 = word & 0x00FFFFFF
                target = (word_addr + 8) + (imm24 << 2)
            result[i] = target & 0xFFFFFFFF

        if tbl_sym:
            print(f'# B-table at 0x{b_table:05x} ({tbl_sym})')
        return result


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        return 1
    elf_path, addr_s, n_s = sys.argv[1], sys.argv[2], sys.argv[3]
    b_table = int(addr_s, 0)
    num_cases = int(n_s)
    mapping = decode_b_table(elf_path, b_table, num_cases)
    for i, t in mapping.items():
        print(f'  case {i:3d}: B 0x{t:05x}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
