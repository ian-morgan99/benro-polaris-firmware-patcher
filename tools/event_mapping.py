#!/usr/bin/env python3
"""
event_mapping.py — Map EventMsgProc case bodies to SP_EVENT_* event names.

For each case body in an EventMsgProc addls dispatch, decode the first
~32 bytes of code which contain a PIC-style literal pool reference to a
format string literal. Match the format string's tail against the
SP_EVENT_* name table in rodata to produce a {msgId: event_name} map.

Format string lookup pattern (ARM PIC):
    ldr  r3, [pc, #X]    ; r3 = [ins_addr + 8 + X] = literal
    add  r3, pc, r3      ; r3 = (ins_addr + 4) + literal
    str  r3, [sp]        ; push format string VA
    ; ... then call HI_LOG_Print or SP_EventPub

The literal at (ins_addr + 8 + X) is a 32-bit value. The final VA is
(literal + ins_addr + 4).

Usage:
    python3 tools/event_mapping.py <elf> <case_bodies_json>

case_bodies_json is a JSON file mapping msgId (int) to case body VA (int):
    {"1025": 260304, "1026": 260496, ...}

Output:
    msgId  case_body  fmt_va      fmt_text            event_name
"""
import json
import sys
from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM


def find_format_string(elf, case_body_va: int) -> str | None:
    """Decode first 32 bytes of case body to find the format string VA,
    then read the format string from rodata."""
    text = elf.get_section_by_name('.text')
    text_data = text.data()
    text_addr = text['sh_addr']

    rodata = elf.get_section_by_name('.rodata')
    rodata_data = rodata.data()
    rodata_addr = rodata['sh_addr']

    body = text_data[case_body_va - text_addr: case_body_va - text_addr + 40]
    md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
    md.skipdata = True
    ins_list = list(md.disasm(body, case_body_va))
    if len(ins_list) < 3:
        return None
    if ins_list[0].mnemonic != 'ldr' or ins_list[1].mnemonic != 'add':
        return None
    # Extract the displacement from the ldr op_str like "[pc, #0x1d8]"
    import re
    m = re.search(r'#(0x[0-9a-fA-F]+|\d+)', ins_list[0].op_str)
    if not m:
        return None
    disp = int(m.group(1), 0)
    literal_addr = ins_list[0].address + 8 + disp
    # Read the 4-byte literal
    if literal_addr < text_addr or literal_addr + 4 > text_addr + len(text_data):
        return None
    import struct
    literal = struct.unpack('<I', text_data[literal_addr - text_addr: literal_addr + 4 - text_addr])[0]
    fmt_va = (literal + ins_list[1].address) & 0xFFFFFFFF
    # Read format string from rodata
    if fmt_va < rodata_addr or fmt_va >= rodata_addr + len(rodata_data):
        # Format string may be in .text (literal pool) — read from there instead
        if fmt_va < text_addr or fmt_va >= text_addr + len(text_data):
            return None
        chunk = text_data[fmt_va - text_addr:]
    else:
        chunk = rodata_data[fmt_va - rodata_addr:]
    # Read up to NUL or 80 chars
    end = chunk.find(b'\x00')
    if end < 0:
        end = min(80, len(chunk))
    return chunk[:end].decode('latin-1', errors='replace')


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 1
    elf_path = sys.argv[1]
    bodies_path = sys.argv[2]
    with open(bodies_path) as f:
        bodies = {int(k): v for k, v in json.load(f).items()}

    with open(elf_path, 'rb') as f:
        elf = ELFFile(f)
        # Collect all SP_EVENT_* / SP_EVEN_* / SP_EVENE_* strings from rodata
        rodata = elf.get_section_by_name('.rodata')
        rdata = rodata.data()
        raddr = rodata['sh_addr']
        import re
        # Split on NUL bytes and find event name strings
        event_re = re.compile(rb'^SP_EVEN[E_]?[A-Z_]*$')
        events: dict[str, int] = {}
        i = 0
        while i < len(rdata):
            if rdata[i] == 0:
                i += 1
                continue
            end = rdata.find(b'\x00', i)
            if end < 0:
                break
            s = rdata[i:end]
            if event_re.match(s):
                events[s.decode()] = raddr + i
            i = end + 1

        print(f'# Found {len(events)} SP_EVENT_* event names in rodata')
        for msgid, body_va in sorted(bodies.items()):
            fmt = find_format_string(elf, body_va)
            if fmt is None:
                print(f'  0x{msgid:04x} (0x{body_va:05x}) <no format>')
                continue
            # Strip trailing newlines/CR for matching
            fmt_clean = fmt.rstrip('\n\r')
            # Find event name that is a prefix of fmt_clean
            best = None
            for ev in events:
                if fmt_clean.startswith(ev) and (best is None or len(ev) > len(best)):
                    best = ev
            extra = fmt_clean[len(best):] if best else ''
            print(f'  0x{msgid:04x} (0x{body_va:05x}) {fmt!r:30s} -> {best}{extra!r}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
