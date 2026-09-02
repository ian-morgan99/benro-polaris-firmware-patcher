#!/usr/bin/env python3
"""
dwarf_line.py - look up (file, line) for a list of addresses via DWARF .debug_line

Usage:
    python3 tools/dwarf_line.py <elf> <addr_hex> [addr_hex ...]
    python3 tools/dwarf_line.py <elf> --range 0x3f610 0x3fa00
    python3 tools/dwarf_line.py <elf> --file sp_oms.c
    python3 tools/dwarf_line.py <elf> --sym <symbol_name>
"""
import re, subprocess, sys


def parse_readelf(elf):
    """Parse readelf -wl output. Return list of (address, file_name, line)."""
    out = subprocess.check_output(["readelf", "-wl", elf], text=True)
    # Split into compilation units
    units = re.split(r"\n  Offset:\s+0x", "\n" + out)
    entries = []
    for unit in units:
        # file name table
        m_fnt = re.search(
            r"The File Name Table \(offset 0x[0-9a-f]+\):\n(.*?)(?:\n  Offset|\n\n|\Z)",
            unit, re.S,
        )
        if not m_fnt:
            continue
        files = []
        for line in m_fnt.group(1).splitlines():
            m = re.match(r"\s+(\d+)\s+\d+\s+\d+\s+\d+\s+(.+?)\s*$", line)
            if m:
                files.append(m.group(2))
        if not files:
            continue
        # line number statements: take until next unit's Offset: header
        m_lns = re.search(r"Line Number Statements:\n(.*?)(?:\n  Offset:|\Z)", unit, re.S)
        if not m_lns:
            continue
        cur_addr = None
        cur_line = 1
        cur_file_idx = 1  # DWARF files are 1-indexed; 0 = unknown
        for stmt in m_lns.group(1).splitlines():
            # filter to lines that look like "[0x...]  ..." line program statements
            if not re.match(r"^\s+\[0x[0-9a-f]+\]\s+", stmt):
                continue
            stmt = stmt.strip()
            m = re.search(r"set Address to 0x([0-9a-fA-F]+)", stmt)
            if m:
                cur_addr = int(m.group(1), 16)
                continue
            m = re.search(
                r"Special opcode \d+: advance Address by \d+ to 0x([0-9a-fA-F]+) and Line by [+-]?\d+ to (\d+)",
                stmt,
            )
            if m:
                cur_addr = int(m.group(1), 16)
                cur_line = int(m.group(2))
                fname = files[cur_file_idx - 1] if 1 <= cur_file_idx <= len(files) else "?"
                entries.append((cur_addr, fname, cur_line))
                continue
            m = re.search(r"^\s*Copy\s*$", stmt)
            if m and cur_addr is not None:
                fname = files[cur_file_idx - 1] if 1 <= cur_file_idx <= len(files) else "?"
                entries.append((cur_addr, fname, cur_line))
                continue
            m = re.search(r"set [Ff]ile to (\d+)", stmt)
            if m:
                cur_file_idx = int(m.group(1))
    entries.sort(key=lambda e: e[0])
    return entries


def lookup(entries, addr):
    best = None
    for va, f, l in entries:
        if va > addr:
            break
        best = (f, l)
    return best


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    elf = sys.argv[1]
    args = sys.argv[2:]
    entries = parse_readelf(elf)

    if args[0] == "--range":
        start = int(args[1], 16)
        end = int(args[2], 16)
        print(f"# Address range 0x{start:08x}..0x{end:08x}")
        last_line = None
        for va, f, l in entries:
            if start <= va < end:
                if (f, l) != last_line:
                    print(f"0x{va:08x}  {f}:{l}")
                    last_line = (f, l)
        return

    if args[0] == "--file":
        target = args[1]
        print(f"# All line entries in {target}")
        for va, f, l in entries:
            if f == target:
                print(f"0x{va:08x}  {f}:{l}")
        return

    if args[0] == "--sym":
        out = subprocess.check_output(["readelf", "-s", elf], text=True)
        for line in out.splitlines():
            m = re.match(
                r"\s+\d+:\s+([0-9a-f]+)\s+(\d+)\s+FUNC\s+\S+\s+\S+\s+\d+\s+(\S+)",
                line,
            )
            if m and m.group(3) == args[1]:
                addr = int(m.group(1), 16)
                size = int(m.group(2))
                print(f"# Symbol {args[1]} @ 0x{addr:08x} (size {size})")
                for va, f, l in entries:
                    if addr <= va < addr + size:
                        print(f"0x{va:08x}  {f}:{l}")
                return
        print(f"Symbol {args[1]} not found")
        return

    for a in args:
        addr = int(a, 16)
        r = lookup(entries, addr)
        if r:
            print(f"0x{addr:08x}  ->  {r[0]}:{r[1]}")
        else:
            print(f"0x{addr:08x}  ->  (no line info)")


if __name__ == "__main__":
    main()
