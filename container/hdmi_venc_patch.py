#!/usr/bin/env python3
"""Patch SP_HdmiVencCreateChn channel geometry 1280x720 -> 1920x1080.
Usage: hdmi_venc_patch.py <in> <out>. Idempotent."""
import sys

SITES = {                      # file offset = vaddr - 0x10000 (RX segment)
    0x13cea4 - 0x10000: (bytes.fromhex('053ca0e3'), bytes.fromhex('783ea0e3')),  # mov #1280 -> mov #1920
    0x13ceac - 0x10000: (bytes.fromhex('2d3ea0e3'), bytes.fromhex('383400e3')),  # mov #720  -> movw #1080
    0x13d0b8 - 0x10000: (bytes.fromhex('053ca0e3'), bytes.fromhex('783ea0e3')),
    0x13d0c0 - 0x10000: (bytes.fromhex('2d3ea0e3'), bytes.fromhex('383400e3')),
}

data = bytearray(open(sys.argv[1], 'rb').read())
for off, (old, new) in SITES.items():
    cur = bytes(data[off:off+4])
    if cur == new:
        continue                       # already patched
    assert cur == old, f"offset {hex(off)}: found {cur.hex()}, expected {old.hex()} — wrong firmware or wrong order"
    data[off:off+4] = new
open(sys.argv[2], 'wb').write(data)
print("venc geometry patched")
