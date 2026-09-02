#!/usr/bin/env python3
"""
find_callers.py -- Find all BL (branch-with-link) call sites in an ARM ELF.

Workaround for capstone's broken `ins.operands[0]` accessor for ARM `bl`
instructions in polestar_app (and similar binaries). We parse `ins.op_str`
with a regex instead.

Usage:
    python3 find_callers.py <elf> [--func NAME] [--addr 0xADDR] [--list-unique]
                                 [--json] [--filter-prefix prefix]
                                 [--bl-only] [--include-bx]

Outputs:
    For each call site: caller_address  target_address  (mnemonic op_str)
    Or with --json: structured JSON.
    Or with --list-unique: just unique targets with their call site count.

The bug being worked around: see
docs/evidence/polestar-disasm-2026-09-01/10-capstone-operand-bug.md
"""
import argparse
import capstone
import json
import re
import sys
from collections import defaultdict
from elftools.elf.elffile import ELFFile

BL_TARGET = re.compile(r'#?(0x[0-9a-fA-F]+)')
BX_REG = re.compile(r'(r\d+)')


def iter_text(elf_path):
    """Yield (code_bytes, base_addr, section_name) for each executable section."""
    with open(elf_path, 'rb') as f:
        ef = ELFFile(f)
        for sec in ef.iter_sections():
            if sec.name in ('.text', '.init', '.fini', '.plt'):
                yield sec.data(), sec['sh_addr'], sec.name


def collect_callers(elf_path, include_bx=False):
    """Return dict: target_addr -> set of caller addresses."""
    callers = defaultdict(set)
    md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_ARM)
    md.skipdata = True
    for code, base, _name in iter_text(elf_path):
        for ins in md.disasm(code, base):
            if ins.mnemonic == 'bl':
                m = BL_TARGET.search(ins.op_str)
                if m:
                    try:
                        callers[int(m.group(1), 16)].add(ins.address)
                    except ValueError:
                        pass
            elif include_bx and ins.mnemonic in ('blx', 'bx'):
                # BLX with immediate also has the immediate in op_str
                if ins.mnemonic == 'blx':
                    m = BL_TARGET.search(ins.op_str)
                    if m:
                        try:
                            callers[int(m.group(1), 16)].add(ins.address)
                        except ValueError:
                            pass
                # BX/BLX with register are indirect, skip
    return callers


def resolve_addr_to_name(elf_path, addr):
    """Find symbol at addr (or -1 if not found)."""
    with open(elf_path, 'rb') as f:
        ef = ELFFile(f)
        for sec in ef.iter_sections():
            if sec.name in ('.symtab', '.dynsym'):
                for s in sec.iter_symbols():
                    if s['st_info']['type'] == 'STT_FUNC' and s['st_value'] == addr:
                        return s.name
    return None


def list_funcs(elf_path):
    """Yield (addr, size, name) for all STT_FUNC symbols."""
    with open(elf_path, 'rb') as f:
        ef = ELFFile(f)
        for sec in ef.iter_sections():
            if sec.name in ('.symtab', '.dynsym'):
                for s in sec.iter_symbols():
                    if s['st_info']['type'] == 'STT_FUNC' and s['st_size'] > 0:
                        yield s['st_value'], s['st_size'], s.name


def main():
    p = argparse.ArgumentParser()
    p.add_argument('elf', help='path to ELF')
    p.add_argument('--func', help='show callers of this function (by name)')
    p.add_argument('--addr', help='show callers of this address (hex)')
    p.add_argument('--list-unique', action='store_true',
                   help='just list unique target addresses with caller counts')
    p.add_argument('--json', action='store_true', help='emit JSON')
    p.add_argument('--filter-prefix', help='only show targets whose resolved name starts with prefix')
    p.add_argument('--include-bx', action='store_true', help='also include blx immediate')
    args = p.parse_args()

    callers = collect_callers(args.elf, include_bx=args.include_bx)

    if args.list_unique:
        for tgt in sorted(callers):
            n = len(callers[tgt])
            name = resolve_addr_to_name(args.elf, tgt) or ''
            if args.filter_prefix and not name.startswith(args.filter_prefix):
                continue
            print(f"0x{tgt:08x}  {n:>5}  {name}")
        return

    if args.func:
        target_addr = None
        for a, sz, n in list_funcs(args.elf):
            if n == args.func:
                target_addr = a
                break
        if target_addr is None:
            print(f"function not found: {args.func}", file=sys.stderr)
            sys.exit(2)
    elif args.addr:
        target_addr = int(args.addr, 16)
    else:
        print("specify --func, --addr, or --list-unique", file=sys.stderr)
        sys.exit(2)

    sites = sorted(callers.get(target_addr, set()))
    if args.json:
        out = {
            'target': f"0x{target_addr:08x}",
            'name': resolve_addr_to_name(args.elf, target_addr),
            'count': len(sites),
            'callers': [f"0x{a:08x}" for a in sites],
        }
        print(json.dumps(out, indent=2))
    else:
        tgt_name = resolve_addr_to_name(args.elf, target_addr) or ''
        print(f"=== Callers of 0x{target_addr:08x} ({tgt_name}) ===")
        print(f"Total: {len(sites)} unique call sites")
        for a in sites:
            print(f"  0x{a:08x}")


if __name__ == '__main__':
    main()
