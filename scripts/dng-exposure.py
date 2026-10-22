#!/usr/bin/env python3
"""Read exposure timing out of a DNG/TIFF without any third-party library.

Raised by the #186 qualification correction: the 2026-10-21 report quoted
"5.003 s / 40.001 s / 89.999 s" as if those were exposure durations. They are
the *application's* own hold interval (`bulb time start` .. `bulb time end` in
Mlog), i.e. how long polestar_app slept. They say nothing about how long the
sensor was actually exposed. Independent confirmation needs EXIF.

DNG is TIFF-based, so the ExifIFD can be parsed directly:

  ExposureTime       33421  RATIONAL  the exposure duration the camera recorded
  ShutterSpeedValue  37385  SRATIONAL APEX; exposure time = 2 ** -value
  ISOSpeedRatings    34662  SHORT     cross-check against the requested ISO

Usage:  dng-exposure.py FILE...
Exit 0 if every file yielded an ExposureTime, 1 otherwise.

Only what this project needs is implemented: little- and big-endian TIFF, IFD0
and the ExifIFD it points to, and the four tags above. Anything unexpected is
reported rather than guessed at.
"""

import struct
import sys

TAG_EXPOSURE_TIME = 33421
TAG_SHUTTER_SPEED_VALUE = 37385
TAG_ISO = 34662
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
        if tag == TAG_EXPOSURE_TIME and isinstance(val, tuple):
            num, den = val
            out["exposure_time_s"] = (num / den) if den else None
            out["exposure_time_raw"] = f"{num}/{den}"
        elif tag == TAG_SHUTTER_SPEED_VALUE and isinstance(val, tuple):
            num, den = val
            if den:
                apex = num / den
                out["shutter_apex"] = apex
                out["exposure_from_apex_s"] = 2.0 ** (-apex)
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
            print(f"{path}: no ExposureTime tag", end="")
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
