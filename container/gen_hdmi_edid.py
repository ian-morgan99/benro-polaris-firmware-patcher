#!/usr/bin/env python3
"""Generate a 256-byte EDID: base block + CEA-861 ext advertising 1920x1080@60.

Timing/sync/feature bytes follow the vendor's own encoding, copied verbatim from
the stock EDID blob in polestar_app (offset 0xbd4c7c) so the LT8619C source sees
exactly the field layout it was built against. Only the descriptors we intend to
change differ: the preferred-timing DTD stays 1920x1080@60 (as stock) and the CEA
block advertises VIC 16 native + VIC 4.
"""
import struct
import sys

# Verbatim stock DTD tail (bytes 62..71 of base block): hfront=88 hsync=44 stored
# as full bytes, then image size / sync-extension fields 45 00 20 40 and padding.
STOCK_DTD_TAIL = bytes.fromhex('582c4500204021000018')
# Stock bytes 90..127 verbatim: range-limits + monitor-name descriptors.
STOCK_TAIL_90_128 = bytes.fromhex('000000fd0017780f851e000a202020202020000000fc0046726569686569742048444d49016f')
# Stock second DTD (297 MHz, 3840x2160-class) kept verbatim.
STOCK_DTD2 = bytes.fromhex('04740030f2705a80b0588a006d552100001e')
# Stock range-limits descriptor (tag fd): min_vf=23 max_vf=120 min_hf=15 max_hf=85...
STOCK_RANGE_DESC = bytes.fromhex('fd0017780f851e000a202020202020202000')

def edid_checksum(block):
    block[127] = (-sum(block[:127])) & 0xFF
    assert sum(block) % 256 == 0
    return block

def dtd(pclk10k, hactive, hblank, vactive, vblank):
    """DTD with vendor sync-byte convention (full-byte hfront/hsync)."""
    d = bytearray(18)
    struct.pack_into('<H', d, 0, pclk10k)
    d[2], d[3] = hactive & 0xFF, hblank & 0xFF
    d[4] = ((hactive >> 8) << 4) | (hblank >> 8)
    d[5], d[6] = vactive & 0xFF, vblank & 0xFF
    d[7] = ((vactive >> 8) << 4) | (vblank >> 8)
    d[8:18] = STOCK_DTD_TAIL
    return d

def base_block():
    b = bytearray(128)
    b[0:8] = bytes([0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x00])
    b[8], b[9] = 0x19, 0x14                      # manufacturer "FHT" (keep stock identity)
    struct.pack_into('<H', b, 10, 0x0100)        # product code
    b[12:16] = bytes([0x01, 0, 0, 0])            # serial
    b[16] = 0x21                                 # week
    b[17] = 34                                   # year offset (2024)
    b[18] = 48                                   # max h size cm
    b[19] = 27                                   # max v size cm
    b[20] = 0x80                                 # digital input
    b[21] = 0x10                                 # gamma 2.20 (stock value)
    b[22] = 0x09                                 # DPMS flags (stock value)
    # Preferred timing descriptor: 1920x1080@60, pixel clock 148.5 MHz
    b[54:72] = dtd(14850, 1920, 280, 1080, 45)   # preferred timing (as stock)
    b[72:90] = STOCK_DTD2                        # second DTD verbatim from stock
    # Range-limits and monitor-name descriptors copied verbatim from stock
    # (vendor places the fd tag at offset 93 inside the 90..107 slot).
    b[90:128] = STOCK_TAIL_90_128
    return edid_checksum(b)

def cea_block():
    c = bytearray(128)
    c[0] = 0x02            # CEA tag
    c[1] = 0x03            # revision
    dtd_start = 8          # after 2 short video descriptors + padding byte
    c[2] = dtd_start       # byte offset of first DTD within this block
    c[3] = 0x00            # no basic audio, no YCbCr (no audio data blocks present)
    c[4] = (16 << 1) | 1   # SVD: VIC 16 (1080p60), native
    c[5] = (4 << 1) | 0    # SVD: VIC 4 (720p60), supported
    c[dtd_start:dtd_start+18] = dtd(14850, 1920, 280, 1080, 45)
    return edid_checksum(c)

if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else '/tmp/hdmi-work/new_edid.bin'
    open(out, 'wb').write(bytes(base_block() + cea_block()))
    print("wrote 256-byte EDID to", out)
