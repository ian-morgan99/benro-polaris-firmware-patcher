#!/usr/bin/env python3
"""Read exposure timing out of a DNG/TIFF without any third-party library.

Raised by the #186 qualification correction: the 2026-10-21 report quoted
"5.003 s / 40.001 s / 89.999 s" as if those were exposure durations. They are
the *application's* own hold interval (`bulb time start` .. `bulb time end` in
Mlog), i.e. how long polestar_app slept. They say nothing about how long the
sensor was actually exposed. Independent confirmation needs EXIF.

DNG is TIFF-based, so the ExifIFD can be parsed directly:

  ExposureTime       33434 (0x829a)  RATIONAL   the exposure duration recorded
  ShutterSpeedValue  37385 (0x9209)  SRATIONAL  APEX; exposure = 2 ** -value
  ISOSpeedRatings    34855 (0x8827)  SHORT      cross-check the requested ISO

The tag numbers were wrong in the original version of this tool: 33421 is
FocalLengthIn35mmFilm and 34662 is SensingMethod, neither of which is exposure or
ISO. Verified against a real K-3 III capture (IMGP4113.DNG, 32,649,897 bytes):
its ExifIFD holds ExposureTime=25/1 at tag 33434, ISOSpeedRatings=400 at tag
34855, and ShutterSpeedValue as an unsigned SHORT of 16 -- not an SRATIONAL.
Because APEX is signed (Tv = -log2 seconds), an unsigned SHORT cannot represent
any exposure longer than one second, so that 16 is meaningless for a 25 s shot
and must never be converted into a duration.

Usage:  dng-exposure.py FILE...
Exit 0 if every file yielded an ExposureTime, 1 otherwise.

Only what this project needs is implemented: little- and big-endian TIFF, IFD0
and the ExifIFD it points to, and the four tags above. Anything unexpected is
reported rather than guessed at.
"""

import struct
import sys

TAG_EXPOSURE_TIME = 33434        # 0x829a -- NOT 33421 (FocalLengthIn35mmFilm)
TAG_SHUTTER_SPEED_VALUE = 37385  # 0x9209
TAG_ISO = 34855                  # 0x8827 -- NOT 34662 (SensingMethod)
TAG_EXIF_IFD = 34665
TAG_MAKE = 271
TAG_MODEL = 272
TAG_SOFTWARE = 305

# TIFF field types -> (struct char, bytes per component)
TYPES = {
    1: ("B", 1),   # BYTE
    2: ("c", 1),   # ASCII
    3: ("H", 2),   # SHORT
    4: ("I", 4),   # LONG
    5: ("II", 8),  # RATIONAL  (numerator, denominator)
    7: ("B", 1),   # UNDEFINED
    9: ("i", 4),   # SLONG
    10: ("ii", 8), # SRATIONAL
    11: ("f", 4),  # FLOAT
    12: ("d", 8),  # DOUBLE
}


class TiffError(Exception):
    pass


def _read_u16(buf, off, endian):
    return struct.unpack_from("<H" if endian == "<" else ">H", buf, off)[0]


def _read_u32(buf, off, endian):
    return struct.unpack_from("<I" if endian == "<" else ">I", buf, off)[0]


def _value(buf, off, endian, typ, count):
    """Return the decoded value for a tag whose count/type are known."""
    if typ not in TYPES:
        raise TiffError(f"unsupported TIFF field type {typ}")
    fmt, size = TYPES[typ]
    total = size * count
    # Values <= 4 bytes live inline in the 8-byte value field; longer ones are
    # stored at an offset.
    if total <= 4:
        data = buf[off:off + total]
    else:
        # A value longer than 4 bytes is always addressed by a LONG stored in
        # the first four bytes of the 8-byte value field, in both endians.
        ptr = _read_u32(buf, off, endian)
        data = buf[ptr:ptr + total]
    if len(data) < total:
        raise TiffError("truncated tag value")

    if typ == 2:  # ASCII
        return data.split(b"\x00", 1)[0].decode("ascii", "replace")
    if typ in (5, 10):  # RATIONAL / SRATIONAL: two components per value
        out = []
        for i in range(count):
            n, d = struct.unpack_from(endian + fmt, data, i * size)
            out.append((n, d))
        return out if count != 1 else out[0]
    vals = []
    for i in range(count):
        vals.append(struct.unpack_from(
            endian + fmt, data, i * size)[0])
    return vals if count != 1 else vals[0]


def _walk_ifd(buf, ifd_off, endian, depth=0):
    """Yield (tag, typ, count, value) for every entry in an IFD."""
    if depth > 4:
        return
    if ifd_off + 2 > len(buf):
        raise TiffError("IFD offset outside file")
    n = _read_u16(buf, ifd_off, endian)
    if n > 2000:
        raise TiffError(f"implausible IFD entry count {n}")
    for i in range(n):
        e = ifd_off + 2 + i * 12
        if e + 12 > len(buf):
            raise TiffError("IFD entry outside file")
        tag = _read_u16(buf, e, endian)
        typ = _read_u16(buf, e + 2, endian)
        count = _read_u32(buf, e + 4, endian)
        try:
            val = _value(buf, e + 8, endian, typ, count)
        except TiffError:
            val = None
        yield tag, typ, count, val
    # next IFD (we do not follow them; ExifIFD is reached via tag 34665)


def read_exposure(path):
    """Return a dict of the timing fields found in one DNG/TIFF."""
    with open(path, "rb") as fh:
        buf = fh.read()
    if len(buf) < 8:
        raise TiffError("file too small to be TIFF")
    bom = buf[:2]
    if bom == b"II":
        endian = "<"
    elif bom == b"MM":
        endian = ">"
    else:
        raise TiffError(f"not a TIFF/DNG (magic {bom!r})")
    if _read_u16(buf, 2, endian) != 42:
        raise TiffError("TIFF version marker 42 not found")

    out = {}
    ifd0 = _read_u32(buf, 4, endian)
    exif_off = None
    for tag, typ, count, val in _walk_ifd(buf, ifd0, endian):
        if tag == TAG_EXIF_IFD:
            exif_off = val
        elif tag in (TAG_MAKE, TAG_MODEL, TAG_SOFTWARE):
            out[("make", "model", "software")[
                (TAG_MAKE, TAG_MODEL, TAG_SOFTWARE).index(tag)]] = val

    if exif_off is None:
        raise TiffError("no ExifIFD pointer (tag 34665) in IFD0")

    for tag, typ, count, val in _walk_ifd(buf, exif_off, endian):
        if tag == TAG_EXPOSURE_TIME:
            if isinstance(val, tuple):
                num, den = val
                out["exposure_time_s"] = (num / den) if den else None
                out["exposure_time_raw"] = f"{num}/{den}"
            else:
                out["exposure_time_unexpected"] = f"type={typ} value={val!r}"
        elif tag == TAG_SHUTTER_SPEED_VALUE:
            # Derive a duration only from a signed value. Pentax writes this tag
            # as an unsigned SHORT, which cannot encode APEX < 0 and therefore
            # cannot express any exposure longer than 1 s; on the real K-3 III
            # file it reads 16 for a 25 s shot. Record it, never convert it.
            if isinstance(val, tuple):
                num, den = val
                if den:
                    apex = num / den
                    out["shutter_apex"] = apex
                    out["exposure_from_apex_s"] = 2.0 ** (-apex)
            else:
                out["shutter_apex_unsigned_type"] = typ
                out["shutter_apex_raw"] = val
        elif tag == TAG_ISO:
            out["iso"] = val
    return out


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    rc = 0
    for path in argv[1:]:
        try:
            info = read_exposure(path)
        except (OSError, TiffError) as exc:
            print(f"{path}: ERROR {exc}")
            rc = 1
            continue
        et = info.get("exposure_time_s")
        apex = info.get("exposure_from_apex_s")
        if et is None:
            note = info.get("exposure_time_unexpected")
            print(f"{path}: no usable ExposureTime tag (tag {TAG_EXPOSURE_TIME})"
                  + (f" -- found {note}" if note else ""), end="")
        else:
            print(f"{path}: exposure_time={info.get('exposure_time_raw')} "
                  f"({et:.3f} s)", end="")
            if apex is not None:
                tol = max(0.02, 0.02 * apex)
                verdict = "AGREE" if abs(et - apex) <= tol else "MISMATCH"
                print(f" apex-derived={apex:.3f}s {verdict}", end="")
        if info.get("iso") is not None:
            print(f" iso={info['iso']}", end="")
        if info.get("model"):
            print(f" model={info['model']!r}", end="")
        print()
        if et is None:
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
