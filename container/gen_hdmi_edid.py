#!/usr/bin/env python3
"""Generate a 256-byte EDID: base block + CEA-861 ext advertising 1920x1080@60."""
import struct

def edid_checksum(block):
    block[127] = (-sum(block[:127])) & 0xFF
    assert sum(block) % 256 == 0
    return block

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
    b[21] = 0x01                                 # gamma
    b[22] = 0x01                                 # DPMS flags
    # Preferred timing descriptor: 1920x1080@60, pixel clock 148.5 MHz
    pclk = 14850                                  # in 10 kHz units
    b[54], b[55] = pclk & 0xFF, pclk >> 8
    hactive, hblank = 1920, 280
    vactive, vblank = 1080, 45
    b[56], b[57] = hactive & 0xFF, hblank & 0xFF
    b[58] = ((hactive >> 8) << 4) | (hblank >> 8)
    b[59], b[60] = vactive & 0xFF, vblank & 0xFF
    b[61] = ((vactive >> 8) << 4) | (vblank >> 8)
    b[62] = ((88 & 0xF) << 4) | 4                # hfront 88 | vsync offset 4
    b[63] = ((44 & 0xF) << 4) | 5                # hsync width 44 | vsync width 5
    b[64:68] = bytes([0x21, 0x50, 0x81, 0x00])   # h/v image size mm
    b[68] = 0xFD                                 # range limits descriptor tag
    b[69:72] = bytes([0x00, 0x30, 0x31])
    b[72:90] = bytes([0x10, 0x1F] + [0]*16)[:18]
    name = b'POLARIS-HDMI'
    b[90:95] = bytes([0x00, 0x00, 0x00, 0xFC, len(name)])
    b[95:95+len(name)] = name
    return edid_checksum(b)

def cea_block():
    c = bytearray(128)
    c[0] = 0x02            # CEA tag
    c[1] = 0x03            # revision
    dtd_start = 8          # after 2 short video descriptors + padding byte
    c[2] = dtd_start       # byte offset of first DTD within this block
    c[3] = 0x40            # HDMI signal, no audio
    c[4] = (16 << 1) | 1   # SVD: VIC 16 (1080p60), native
    c[5] = (4 << 1) | 0    # SVD: VIC 4 (720p60), supported
    d = bytearray(18)
    d[0], d[1] = 14850 & 0xFF, 14850 >> 8
    d[2], d[3] = 1920 & 0xFF, 280 & 0xFF
    d[4] = ((1920 >> 8) << 4) | (280 >> 8)
    d[5], d[6] = 1080 & 0xFF, 45 & 0xFF
    d[7] = ((1080 >> 8) << 4) | (45 >> 8)
    d[8] = (88 & 0xF) << 4 | 4
    d[9] = (44 & 0xF) << 4 | 5
    d[10:14] = bytes([0x21, 0x50, 0x81, 0x00])
    c[dtd_start:dtd_start+18] = d
    return edid_checksum(c)

open('/tmp/hdmi-work/new_edid.bin','wb').write(bytes(base_block() + cea_block()))
print("wrote 256-byte EDID")
