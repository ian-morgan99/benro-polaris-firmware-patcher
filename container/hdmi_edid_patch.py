#!/usr/bin/env python3
"""Replace the 256-byte default EDID blob in polestar_app.
Usage: hdmi_edid_patch.py <polestar_app_in> <edid_256.bin> <polestar_app_out>
Idempotent: detects an already-patched input and passes it through."""
import hashlib, sys

EDID_OFF = 0xbd4c7c          # file offset of the 256-byte default EDID blob
EXPECT_FIRST16 = bytes.fromhex('00ffffffffffff001914010001010101')

def main(inp, edid_path, outp):
    data = bytearray(open(inp, 'rb').read())
    edid = open(edid_path, 'rb').read()
    assert len(edid) == 256, "EDID must be exactly 256 bytes"
    cur = bytes(data[EDID_OFF:EDID_OFF+256])
    if cur == edid:
        print("already patched"); open(outp,'wb').write(data); return
    assert cur[:16] == EXPECT_FIRST16, \
        f"unexpected bytes at {hex(EDID_OFF)}: {cur[:16].hex()} — wrong firmware?"
    assert sum(edid[:128]) % 256 == 0 and sum(edid[128:]) % 256 == 0, "bad EDID checksums"
    data[EDID_OFF:EDID_OFF+256] = edid
    open(outp, 'wb').write(data)
    print("patched:", hashlib.md5(bytes(data)).hexdigest())

main(*sys.argv[1:4])
