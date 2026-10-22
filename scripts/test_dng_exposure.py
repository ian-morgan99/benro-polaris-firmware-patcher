#!/usr/bin/env python3
"""Self-test for scripts/dng-exposure.py using synthetic TIFF/DNG files.

The #186 qualification correction requires that exposure duration be read from
EXIF rather than inferred from the app's sleep interval, so the reader itself
must be provably correct before its output is quoted as evidence. These fixtures
are built byte-by-byte, so a parse that agrees with the values written is proof
the offsets, endian handling and RATIONAL decoding are right.
"""

import os
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
READER = os.path.join(HERE, "dng-exposure.py")

TAG_MODEL = 272
TAG_SOFTWARE = 305
TAG_EXIF_IFD = 34665
TAG_EXPOSURE_TIME = 33421
TAG_SHUTTER_SPEED_VALUE = 37385
TAG_ISO = 34662


def build_tiff(endian, exposure, apex, iso, model="PENTAX K-3 MARK III"):
    """Build a minimal two-IFD TIFF. Returns (bytes, expected_exposure_seconds).

    A TIFF IFD entry is 12 bytes: tag(2) type(2) count(4) value-or-offset(4). The
    value field is only 4 bytes, so anything larger -- an ASCII Model string or an
    8-byte RATIONAL -- must live in a heap and be referenced by offset. That is
    exactly the path the reader's pointer branch takes, which is what this test
    exists to exercise.

    Layout (offsets computed, not accumulated):
        header(8) | IFD0(2 entries) | ExifIFD(3 entries) | heap
    """
    e = "<" if endian == "II" else ">"
    num, den = exposure
    ascii_bytes = model.encode("ascii") + b"\x00"
    if len(ascii_bytes) % 2:
        ascii_bytes += b"\x00"

    ifd0_off = 8
    ifd0_size = 2 + 2 * 12 + 4
    exif_off = ifd0_off + ifd0_size
    exif_size = 2 + 3 * 12 + 4
    heap_off = exif_off + exif_size
    exp_off = heap_off + len(ascii_bytes)
    apex_off = exp_off + 8

    def entry(tag, typ, count, four_bytes):
        if len(four_bytes) != 4:
            raise AssertionError((tag, len(four_bytes)))
        return struct.pack(e + "HHI", tag, typ, count) + four_bytes

    # IFD0: Model (ASCII -> heap pointer), then the ExifIFD pointer.
    ifd0 = struct.pack(e + "H", 2)
    ifd0 += entry(TAG_MODEL, 2, len(ascii_bytes), struct.pack(e + "I", heap_off))
    ifd0 += entry(TAG_EXIF_IFD, 4, 1, struct.pack(e + "I", exif_off))
    ifd0 += struct.pack(e + "I", 0)

    # ExifIFD: the two rationals are 8 bytes so they go in the heap; ISO is a
    # single SHORT and stays inline, left-justified in the 4-byte field.
    exif = struct.pack(e + "H", 3)
    exif += entry(TAG_EXPOSURE_TIME, 5, 1, struct.pack(e + "I", exp_off))
    exif += entry(TAG_SHUTTER_SPEED_VALUE, 10, 1, struct.pack(e + "I", apex_off))
    exif += entry(TAG_ISO, 3, 1, struct.pack(e + "H", iso) + b"\x00\x00")
    exif += struct.pack(e + "I", 0)

    heap = bytearray()
    heap += ascii_bytes
    heap += struct.pack(e + "II", num, den)
    heap += struct.pack(e + "ii", apex[0], apex[1])

    assert len(ifd0) == ifd0_size, (len(ifd0), ifd0_size)
    assert len(exif) == exif_size, (len(exif), exif_size)
    assert len(heap) == len(ascii_bytes) + 16, len(heap)

    out = bytearray()
    out += b"II" if endian == "II" else b"MM"
    out += struct.pack(e + "HI", 42, ifd0_off)
    out += ifd0
    out += exif
    out += heap
    assert len(out) == apex_off + 8, (len(out), apex_off + 8)
    return bytes(out), num / den


def run(path):
    proc = subprocess.run([sys.executable, READER, path], capture_output=True,
                          text=True, check=False)
    return proc.returncode, proc.stdout.strip()


def main():
    failures = 0
    cases = [
        ("II", (5, 1), (-32768, 32768), 100),      # 1.0 s, apex 1 -> 0.5 s (mismatch expected)
        ("MM", (40, 1), (-131072, 32768), 200),    # 40.0 s, apex 4 -> 1/16 s
        ("II", (90, 1), (-294912, 32768), 640),    # 90.0 s, apex 9 -> 1/512 s
        ("MM", (1, 8), (98304, 32768), 1600),      # 0.125 s, apex -3 -> 8 s
    ]
    for endian, exposure, apex, iso in cases:
        blob, expected = build_tiff(endian, exposure, apex, iso)
        with tempfile.NamedTemporaryFile(suffix=".dng", delete=False) as fh:
            fh.write(blob)
            path = fh.name
        try:
            rc, out = run(path)
            ok = rc == 0 and f"({expected:.3f} s)" in out and f"iso={iso}" in out
            print(f"[{'PASS' if ok else 'FAIL'}] endian={endian} "
                  f"exposure={exposure[0]}/{exposure[1]} iso={iso} -> rc={rc}")
            print(f"        {out}")
            if not ok:
                failures += 1
        finally:
            os.unlink(path)

    # A non-TIFF file must be reported, not crash.
    with tempfile.NamedTemporaryFile(suffix=".dng", delete=False) as fh:
        fh.write(b"not a tiff at all, far too long to be mistaken for one")
        path = fh.name
    try:
        rc, out = run(path)
        ok = rc == 1 and "ERROR" in out
        print(f"[{'PASS' if ok else 'FAIL'}] non-TIFF rejected -> rc={rc} {out}")
        if not ok:
            failures += 1
    finally:
        os.unlink(path)

    # Truncated file must be reported, not crash.
    blob, _ = build_tiff("II", (5, 1), (-32768, 32768), 100)
    with tempfile.NamedTemporaryFile(suffix=".dng", delete=False) as fh:
        fh.write(blob[:len(blob) // 2])
        path = fh.name
    try:
        rc, out = run(path)
        ok = rc == 1 and "ERROR" in out
        print(f"[{'PASS' if ok else 'FAIL'}] truncated TIFF rejected -> rc={rc} {out}")
        if not ok:
            failures += 1
    finally:
        os.unlink(path)

    print(f"\n{'ALL PASS' if failures == 0 else str(failures) + ' FAILED'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
