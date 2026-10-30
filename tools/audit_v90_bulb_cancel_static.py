#!/usr/bin/env python3
"""Read-only audit of cancellation routes in one exact saved v90 pgphoto ELF.

This verifies instruction/literal anchors, not physical shutter behaviour.
It does not patch bytes, emulate a camera, or clear the Bulb release block.
"""
import argparse
import hashlib
from pathlib import Path
import struct

from elftools.elf.elffile import ELFFile

EXPECTED = "8973d9486e0207446cc111234ed39e878676ce1f3edca2967a97db86c8d9eaac"


def audit(path):
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != EXPECTED:
        raise ValueError("refusing unknown executable: sha256=" + digest)
    with path.open("rb") as stream:
        elf = ELFFile(stream)
        loads = [dict(segment.header) for segment in elf.iter_segments()
                 if segment["p_type"] == "PT_LOAD"]
        symbols = {symbol.name: symbol["st_value"]
                   for table in elf.iter_sections() if table["sh_type"] == "SHT_SYMTAB"
                   for symbol in table.iter_symbols()}

    def offset(address):
        for segment in loads:
            if segment["p_vaddr"] <= address < segment["p_vaddr"] + segment["p_filesz"]:
                return segment["p_offset"] + address - segment["p_vaddr"]
        raise ValueError("non-file-backed address: " + hex(address))

    def word(address):
        return struct.unpack_from("<I", data, offset(address))[0]

    def relative(literal, instruction):
        return (word(literal) + instruction + 8) & 0xffffffff

    def text(address):
        start = offset(address)
        return data[start:data.index(b"\0", start)].decode("ascii")

    def require(condition, description):
        if not condition:
            raise ValueError("anchor mismatch: " + description)

    require(symbols["captureImage"] == 0x208b0, "message handler")
    require(symbols["capture_image_with_Bulb"] == 0x101aac, "shared helper")
    require(text(relative(0x20ef0, 0x208f8)) == "state", "message state key")
    require(text(relative(0x20f00, 0x20958)) == "b", "message b key")
    require(relative(0x20f24, 0x20ac4) == symbols["bulb.11463"], "positive Bulb global")
    require(relative(0x20f2c, 0x20b04) == symbols["bulb.11463"], "zeroed Bulb global")
    require(word(0x20ad4) == 0xe51b3014 and word(0x20ad8) == 0xe3530000 and
            word(0x20adc) == 0x0a000007, "state zero enters the stop branch")
    got = relative(0x20ee8, 0x208c8)
    require(word(got + word(0x20f18)) == symbols["gp_params"], "message gp_params")
    require(word(0x20b18) == 0xe2833a01 and word(0x20b1c) == 0xe3a02000 and
            word(0x20b20) == 0xe5c320d0, "clear gp_params+0x10d0 byte")
    bulb_got = relative(0x102228, 0x101ac8)
    require(word(bulb_got + word(0x102230)) == symbols["gp_params"], "helper gp_params")
    require(word(0x101bc0) == 0xe2833a01 and word(0x101bc4) == 0xe3a02001 and
            word(0x101bc8) == 0xe5c320d0, "helper sets keep-exposing byte")
    require(word(0x101de8) == 0xe2833a01 and word(0x101dec) == 0xe5d330d0 and
            word(0x101df0) == 0xe2233001 and word(0x101dfc) == 0x0affffc5,
            "helper reads keep-exposing byte and loops while set")
    require(word(0x101dd8) == 0xe3730034 and word(0x101ddc) == 0xea00001b,
            "v90 unconditional stop branch after cancel comparison")
    require(word(0x101ee0) == 0xe51b3058 and word(0x101ee4) == 0xe50b3010,
            "stop callback overwrites saved return code")
    cancel_got = relative(0xf7034, 0xf6ff0)
    require(word(cancel_got + word(0xf7038)) == symbols["glob_cancel"], "separate context flag")
    require(word(0xf7014) == 0xe5c32000 and word(0xf7018) == 0xe3a03001,
            "context callback consumes cancellation flag")
    print("PASS: exact v90 SHA and cancellation instruction/literal anchors verified")
    print("MESSAGE STOP: captureImage, positive stored b + state=0 -> gp_params+0x10d0=0")
    print("CONTEXT CANCEL: ctx_cancel_func consumes the separate glob_cancel byte")
    print("DEFECT: v90 branches to stop unconditionally before reading the message-stop flag")
    print("DEFECT: stop callback result overwrites the helper's saved result")
    print("LIMIT: binary control flow only; no UI transport trace, camera action, or release clearance")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pgphoto", type=Path)
    args = parser.parse_args()
    try:
        audit(args.pgphoto)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, str(error) + "\n")
