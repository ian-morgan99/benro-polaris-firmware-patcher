#!/usr/bin/env python3
"""Make code 780 report the exact five-part camera FwVer.

The stock polestar_app builds code 780's ``sw`` value by adding the first
four numeric components of the gimbal version to the first four components of
the camera version. That produces 8.0.0.76 when /app/FwVer is 6.0.0.54 and
discards a fifth build component.

The first attempt changed the second ``sprintf`` to use ``%s``.  That passed
static tests but made the live ``polestar_app`` die while handling code 780.
A second attempt copied the raw version with ``strcpy`` instead, which fixed
the version string but corrupted everything else the app reported.

The reason is the instruction the copy overwrote.  The stock sequence at the
patch site ends with the version ``sprintf`` and is immediately followed by::

    0x13fb98: mov r2, #0x40      <- memset length for the following call
    0x13fb9c: mov r1, #0
    ...
    0x13fbb0: bl  memset

Placing the ``bl strcpy`` in the last word of the seven-word span destroys
that ``mov r2, #0x40``, so the later ``memset(global + 0x468, 0, r2)`` runs
with whatever ``strcpy`` left in the caller-saved ``r2``: an undefined length
on a 64-byte device-info field.  The version string is correct, but the rest
of the device-info block is non-deterministically zeroed or left stale.

This patch keeps the same verified source and destination fields and the same
seven-word footprint, but reclaims the two now-dead format-address loads at
the start of the span so the ``strcpy`` call and the restored
``mov r2, #0x40`` both fit *before* the span ends.  The instruction after the
span (``mov r1, #0`` and the ``memset`` setup) is left byte-for-byte intact.
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

# The relocated ``ldr r0, [pc, #…]`` reads the same global-slot pointer the
# stock code loaded from 0x13FC0C.  It is reached from 0x13FB80 instead of
# 0x13FB88, so its immediate is rebased accordingly.
GLOBAL_SLOT_LITERAL_VA = 0x13FC0C
# The word that immediately follows the patch span.  Stock sets the memset
# length here; the patch must never extend over it.
TAIL_VA = 0x13FB9C


def va_to_file(va: int) -> int:
    return va - FILE_VA_BIAS


def words(*values: int) -> bytes:
    return b"".join(struct.pack("<I", value) for value in values)


# 13fb80..13fb98, including the original summed-version arithmetic and call.
FRESH_SITE = words(
    0xE59F10CC, 0xE08F1001, 0xE59F007C, 0xE7940000,
    0xE2800FFA, 0xEBFB88B0, 0xE3A02040,
)

# 0x13FB80 ldr  r0, [pc, #0x84]   ; global-slot literal, rebased to 0x13FC0C
# 0x13FB84 ldr  r0, [r4, r0]      ; r0 = &globals
# 0x13FB88 add  r1, r0, #0x3a8    ; src = &mFwVer  (raw camera version)
# 0x13FB8C add  r0, r0, #0x3e8    ; dst = &sysFwVer (code 780 "sw" field)
# 0x13FB90 bl   strcpy            ; exact copy, no variadic format change
# 0x13FB94 mov  r2, #0x40         ; RESTORED: length for the stock memset below
# 0x13FB98 mov  r0, r0            ; padding; keeps the span exactly seven words
#
# The span therefore ends before 0x13FB9C, leaving the stock
# "mov r1, #0 / … / bl memset" sequence and its length argument intact.
PATCHED_SITE = words(
    0xE59F0084, 0xE7940000, 0xE2801FEA, 0xE2800FFA,
    0xEBFB869B, 0xE3A02040, 0xE1A00000,
)

STOCK_FORMAT_LITERAL = struct.pack("<I", 0x0092E0FC)

# "mov r1, #0" — the first instruction after the span, consumed by the stock
# memset.  Verified before and after the write so a future patch that grows
# past the span fails closed instead of silently corrupting device info.
STOCK_TAIL_WORD = struct.pack("<I", 0xE3A01000)


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
    tail_file = va_to_file(TAIL_VA)

    if min(site_file, literal_file, format_file, tail_file) < 0:
        print("[polestar_fwver_patch] FATAL: invalid pinned ELF offsets", file=sys.stderr)
        return 1
    if format_file + 3 > len(data) or data[format_file:format_file + 3] != b"%s\0":
        print("[polestar_fwver_patch] FATAL: pinned standalone %s format is absent", file=sys.stderr)
        return 1
    # The patch span is seven words and must end immediately before the stock
    # memset setup.  If that word is not what the stock binary has here, the
    # pinned site has drifted and the memset length would be silently lost.
    if tail_file + 4 > len(data) or bytes(data[tail_file:tail_file + 4]) != STOCK_TAIL_WORD:
        print(
            "[polestar_fwver_patch] FATAL: instruction after the patch span is not the "
            "expected stock memset setup (found %s); refusing to clobber the memset length"
            % bytes(data[tail_file:tail_file + 4]).hex(),
            file=sys.stderr,
        )
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
                bytes(data[literal_file:literal_file + 4]) != STOCK_FORMAT_LITERAL or
                bytes(data[tail_file:tail_file + 4]) != STOCK_TAIL_WORD):
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
