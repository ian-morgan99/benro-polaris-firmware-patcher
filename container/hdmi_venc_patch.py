#!/usr/bin/env python3
"""Patch SP_HdmiVencCreateChn channel geometry 1280x720 -> 1920x1080.
Usage: hdmi_venc_patch.py <in> <out>. Idempotent; fails loudly on partial patches."""
import hashlib, sys

SITES = {                      # file offset = vaddr - 0x10000 (RX segment)
    0x13cea4 - 0x10000: (bytes.fromhex('053ca0e3'), bytes.fromhex('783ea0e3')),  # mov #1280 -> mov #1920
    0x13ceac - 0x10000: (bytes.fromhex('2d3ea0e3'), bytes.fromhex('383400e3')),  # mov #720  -> movw #1080
    0x13d0b8 - 0x10000: (bytes.fromhex('053ca0e3'), bytes.fromhex('783ea0e3')),
    0x13d0c0 - 0x10000: (bytes.fromhex('2d3ea0e3'), bytes.fromhex('383400e3')),
}

def main(inp, outp):
    if inp == outp:
        sys.exit("refusing in-place write: input and output are the same file")
    data = bytearray(open(inp, 'rb').read())
    changed = 0
    already = 0
    for off, (old, new) in SITES.items():
        cur = bytes(data[off:off+4])
        if cur == new:
            already += 1
            continue
        if cur != old:
            sys.exit(f"offset {hex(off)}: found {cur.hex()}, expected {old.hex()} or "
                     f"{new.hex()} — wrong firmware or partially patched input")
        data[off:off+4] = new
        changed += 1
    open(outp, 'wb').write(data)
    print(f"venc geometry patched: {changed} sites written, {already} already patched")
    print("md5:", hashlib.md5(bytes(data)).hexdigest())

if __name__ == '__main__':
    main(*sys.argv[1:3])
