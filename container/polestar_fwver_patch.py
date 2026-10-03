#!/usr/bin/env python3
"""Make code 780 report the exact five-part camera FwVer.

The stock polestar_app builds code 780's ``sw`` value by adding the first
four numeric components of the gimbal version to the first four components of
the camera version. That produces 8.0.0.76 when /app/FwVer is 6.0.0.54 and
discards a fifth build component.

The first attempt changed the second ``sprintf`` to use ``%s``.  That passed
static tests but made the live ``polestar_app`` die while handling code 780.
This replacement keeps the same verified source and destination fields but
uses the already imported ``strcpy`` entry point instead of changing a
variadic call's format/argument convention.  The source is the raw camera
version string in ``mFwVer`` and the destination is the existing
``sysFwVer`` field.
"""
import argparse
import struct
import sys
from pathlib import Path


# Pinned to the stock polestar_app shipped in the supported Polaris FwPkt.
# Its first LOAD maps file offset 0 to virtual address 0x10000.
FILE_VA_BIAS = 0x10000
SITE_VA = 0x13FB80
LITERAL_VA = 0x13FC54
FORMAT_VA = 0xA57324  # existing standalone "%s\0" in stock .rodata
STRCPY_VA = 0x21604   # existing strcpy@plt target in the stock ELF


def va_to_file(va: int) -> int:
    return va - FILE_VA_BIAS


def words(*values: int) -> bytes:
    return b"".join(struct.pack("<I", value) for value in values)


# 13fb80..13fb98, including the original summed-version arithmetic and call.
FRESH_SITE = words(
    0xE59F10CC, 0xE08F1001, 0xE59F007C, 0xE7940000,
    0xE2800FFA, 0xEBFB88B0, 0xE3A02040,
)

# The patched path passes global+0x3a8 (the raw mFwVer string) in r1 and calls
# the stock strcpy entry point.  The first two instructions still load the
# stock format address, but are harmless dead setup retained to keep this
# patch the same size and preserve all surrounding control flow.
PATCHED_SITE = words(
    0xE59F10CC, 0xE08F1001, 0xE59F007C, 0xE7940000,
    0xE2801FEA, 0xE2800FFA, 0xEBFB8699,
)

STOCK_FORMAT_LITERAL = struct.pack("<I", 0x0092E0FC)


def occurrences(data: bytes, needle: bytes):
    found = []
    start = 0
    while True:
        at = data.find(needle, start)
        if at < 0:
            return found
        found.append(at)
        start = at + 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("binary")
    parser.add_argument("--in-place", action="store_true")
    args = parser.parse_args()

    path = Path(args.binary)
    data = bytearray(path.read_bytes())
    site_file = va_to_file(SITE_VA)
    literal_file = va_to_file(LITERAL_VA)
    format_file = va_to_file(FORMAT_VA)

    if min(site_file, literal_file, format_file) < 0:
        print("[polestar_fwver_patch] FATAL: invalid pinned ELF offsets", file=sys.stderr)
        return 1
    if format_file + 3 > len(data) or data[format_file:format_file + 3] != b"%s\0":
        print("[polestar_fwver_patch] FATAL: pinned standalone %s format is absent", file=sys.stderr)
        return 1

    fresh = occurrences(data, FRESH_SITE)
    patched = occurrences(data, PATCHED_SITE)
    literal = bytes(data[literal_file:literal_file + 4])

    if len(fresh) == 1 and not patched and literal == STOCK_FORMAT_LITERAL:
        if fresh[0] != site_file:
            print("[polestar_fwver_patch] FATAL: version site moved; refusing drift", file=sys.stderr)
            return 1
        data[site_file:site_file + len(PATCHED_SITE)] = PATCHED_SITE
        if (bytes(data[site_file:site_file + len(PATCHED_SITE)]) != PATCHED_SITE or
                bytes(data[literal_file:literal_file + 4]) != STOCK_FORMAT_LITERAL):
            print("[polestar_fwver_patch] FATAL: post-write verification failed", file=sys.stderr)
            return 1
        print("[polestar_fwver_patch] patched SP_GetDeviceVer at file offset 0x%x; code 780 now uses exact raw mFwVer" % site_file)
        if args.in_place:
            path.write_bytes(data)
        else:
            out = path.with_name(path.name + ".patched")
            out.write_bytes(data)
            print("[polestar_fwver_patch] wrote %s" % out)
        return 0

    if len(patched) == 1 and not fresh and literal == STOCK_FORMAT_LITERAL:
        print("[polestar_fwver_patch] already patched (unique SP_GetDeviceVer site at file offset 0x%x)" % patched[0])
        return 0

    print(
        "[polestar_fwver_patch] FATAL: unexpected polestar_app version site "
        "(fresh=%d patched=%d literal=%s); refusing to guess" %
        (len(fresh), len(patched), literal.hex()),
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
