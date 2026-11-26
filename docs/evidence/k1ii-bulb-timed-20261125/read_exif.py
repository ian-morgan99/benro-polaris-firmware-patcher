#!/usr/bin/env python3
"""Minimal EXIF reader for Pentax ground-truth checks. No exiftool/PIL on this host.

Reads JPEG APP1 -> TIFF IFD0 + ExifIFD.

Correctness note that matters: ExposureTime (0x829A) is a RATIONAL, two uint32 per
value. An earlier version of this file read only the numerator and printed "2000",
which was then misread as 2000 ms = 2 s. The true value is 2000/100 = 20.000 s, and
that wrong reading produced a wrong conclusion about Bulb accuracy. RATIONAL and
SRATIONAL are now parsed as full pairs and reduced here, never as bare integers.

Pentax writes Bulb as ExposureTime=0 with a non-zero ShutterSpeedValue in some
firmware revisions, so both tags are always reported.
"""
import struct
import sys
from pathlib import Path

TAGS = {
    0x829A: "ExposureTime",        # RATIONAL seconds
    0x8829: "ShutterSpeedValue",   # SRATIONAL APEX; exposure = 2**-APEX
    0x9201: "ApertureValue",
    0x8822: "ExposureProgram",
    0x8827: "ISOSpeedRatings",
    0x0132: "DateTime",
    0x0131: "Software",
}


def parse_tiff(buf, base):
    """Return {tag: (type, count, value)} for IFD0 merged with ExifIFD."""
    if buf[base:base + 2] == b"II":
        e = "<"
    elif buf[base:base + 2] == b"MM":
        e = ">"
    else:
        return None
    if struct.unpack_from(e + "H", buf, base + 2)[0] != 42:
        return None
    off = struct.unpack_from(e + "I", buf, base + 4)[0]

    def ifd(o):
        tags = {}
        n = struct.unpack_from(e + "H", buf, base + o)[0]
        for i in range(n):
            p = base + o + 2 + i * 12
            tag, typ, cnt = struct.unpack_from(e + "HHI", buf, p)
            unit = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8}.get(typ, 4)
            sz = unit * cnt
            vp = p + 8
            if sz > 4:
                vp = base + struct.unpack_from(e + "I", buf, p + 8)[0]
            if typ == 2:
                val = buf[vp:vp + cnt].split(b"\0")[0].decode("ascii", "replace")
            elif typ == 5:                       # RATIONAL: 2 uint32 per count
                val = tuple(struct.unpack_from(e + f"{2 * cnt}I", buf, vp))
            elif typ == 10:                      # SRATIONAL: 2 int32 per count
                val = tuple(struct.unpack_from(e + f"{2 * cnt}i", buf, vp))
            elif typ in (3, 4):
                val = struct.unpack_from(e + ("H" if typ == 3 else "I"), buf, vp)[0]
            else:
                val = None
            tags[tag] = (typ, cnt, val)
        nxt = struct.unpack_from(e + "I", buf, base + o + 2 + n * 12)[0]
        return tags, nxt

    ifd0, _nxt = ifd(off)
    out = dict(ifd0)
    # ExifIFD is reached via tag 0x8769 (ExifOffset), not the next-IFD link.
    exif_off = out.get(0x8769, (None, None, None))[2]
    if isinstance(exif_off, int):
        try:
            sub, _ = ifd(exif_off)
            out.update(sub)
        except Exception:
            pass
    return out


def rational(t, tag):
    """Return (num, den) for a RATIONAL/SRATIONAL tag, or None."""
    v = t.get(tag, (None, None, None))[2]
    if isinstance(v, tuple) and len(v) >= 2:
        return v[0], v[1]
    return None


def exposure_seconds(t):
    """ExposureTime as float seconds, or None. Never trust a bare numerator."""
    r = rational(t, 0x829A)
    if r and r[1]:
        return r[0] / r[1]
    if r and r[1] == 0:
        return 0.0            # Pentax Bulb marker
    sv = rational(t, 0x8829)  # fall back to APEX
    if sv and sv[1]:
        return 2.0 ** (-sv[0] / sv[1])
    return None


def show(path):
    buf = Path(path).read_bytes()
    i = buf.find(b"Exif\0\0")
    if i < 0:
        print(f"{path}: no EXIF")
        return
    t = parse_tiff(buf, i + 6)
    if not t:
        print(f"{path}: unparseable TIFF")
        return
    print(f"\n{Path(path).name}  ({len(buf)} bytes)")
    for tag, name in TAGS.items():
        if tag not in t:
            continue
        typ, cnt, v = t[tag]
        extra = ""
        if tag == 0x829A:
            s = exposure_seconds(t)
            extra = f"  -> {s:.3f}s" if s is not None else ""
        elif tag == 0x8829 and isinstance(v, tuple) and len(v) >= 2 and v[1]:
            extra = f"  -> 2^-APEX = {2.0 ** (-v[0] / v[1]):.4f}s"
        print(f"  {name:18} type={typ} cnt={cnt} raw={v}{extra}")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        show(p)
