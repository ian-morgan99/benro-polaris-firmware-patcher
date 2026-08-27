#!/usr/bin/env python3
"""Phase E geometry patcher: parameterize the hardcoded HDMI input timing.

Rewrites the immediate operands at every site that hardcodes width/height/fps
for the HDMI input chain, so a build can target a different static timing
(e.g. 1280x720@60) without touching control flow.

Live sites (always patched — these run on every boot):
  0x13c390/94/98  SP_CreateHdmiTask args to SP_HdmiViInit(fps, h, w)
  0x13e2a4/ac     SP_VI_SetMipiAttr MIPI BT1120 width/height

Dead sites (only with --include-dead; inside the proven-unreachable RTSP/VENC
tree — SP_GetVencStreamProc has zero callers):
  0x13cea4/ac, 0x13d0b8/c0   SP_HdmiVencCreateChn branches A/B (w/h)
  0x1729ec/f0/f4             StartRtspVideoView (fps/h/w; already 1080p in stock)
  0x1734dc/f4/fc             RTSP_Init (fps/w/h)

Usage:
  hdmi_geometry_patch.py <in> <out> [--width W --height H --fps F] [--include-dead]

Idempotent; refuses in-place writes; fails loudly on unexpected bytes.
"""
import hashlib
import sys


def enc_mov_imm(rd, imm):
    """ARM MOV immediate (rotated-operand form). None if not encodable."""
    for rot in range(16):
        sh = (2 * rot) % 32
        x = ((imm << sh) | (imm >> ((32 - sh) % 32 or 32))) & 0xFFFFFFFF if sh else imm
        if x <= 0xFF:
            return 0xE3A00000 | (rot << 8) | (rd << 12) | x
    return None


def enc_movw(rd, imm):
    """ARM MOVW (ARMv7). Use for values not rot-encodable (e.g. 1080)."""
    if not 0 <= imm <= 0xFFFF:
        raise ValueError(imm)
    imm4 = (imm >> 12) & 0xF
    i = (imm >> 11) & 1
    imm3 = (imm >> 8) & 7
    imm8 = imm & 0xFF
    return 0xE3000000 | (i << 26) | (imm4 << 16) | (rd << 12) | (imm3 << 8) | imm8


def enc_any(rd, imm):
    e = enc_mov_imm(rd, imm)
    return e if e is not None else enc_movw(rd, imm)


def word(v):
    return v.to_bytes(4, 'little')


# file offset -> (register, role). Expected old bytes are computed from stock
# constants (1920x1080@30 / 1280x720) and asserted before writing.
LIVE_SITES = [
    # SP_CreateHdmiTask: mov r2,#30 ; movw r1,#1080 ; mov r0,#1920 ; bl SP_HdmiViInit
    (0x13c390 - 0x10000, 'fps', 2),
    (0x13c394 - 0x10000, 'h',   1),
    (0x13c398 - 0x10000, 'w',   0),
    # SP_VI_SetMipiAttr: mov r3,#1920 -> [fp,-192] ; movw r3,#1080 -> [fp,-188]
    (0x13e2a4 - 0x10000, 'w',   3),
    (0x13e2ac - 0x10000, 'h',   3),
]

DEAD_SITES = [
    # SP_HdmiVencCreateChn branch A: mov r3,#1280/[fp,-108]; mov r3,#720/[fp,-104]
    (0x13cea4 - 0x10000, 'w', 3),
    (0x13ceac - 0x10000, 'h', 3),
    # branch B: same pattern
    (0x13d0b8 - 0x10000, 'w', 3),
    (0x13d0c0 - 0x10000, 'h', 3),
    # StartRtspVideoView: mov r2,#30 ; movw r1,#1080 ; mov r0,#1920 ; bl VencStart
    (0x1729ec - 0x10000, 'fps', 2),
    (0x1729f0 - 0x10000, 'h',   1),
    (0x1729f4 - 0x10000, 'w',   0),
    # RTSP_Init: mov r3,#30/[fp,-16]; mov r3,#1280/[fp,-28]; mov r3,#720/[fp,-32]
    (0x1734dc - 0x10000, 'fps', 3),
    (0x1734f4 - 0x10000, 'w',   3),
    (0x1734fc - 0x10000, 'h',   3),
]

STOCK = {'w': 1920, 'h': 1080, 'fps': 30}
DEAD_STOCK_W_H = (1280, 720)   # VENC + RTSP sites carry 1280x720 in stock


def main():
    args = sys.argv[1:]
    if len(args) < 2:
        sys.exit(__doc__)
    inp, outp = args[0], args[1]
    width, height, fps = STOCK['w'], STOCK['h'], STOCK['fps']
    include_dead = False
    it = iter(args[2:])
    for a in it:
        if a == '--width':
            width = int(next(it))
        elif a == '--height':
            height = int(next(it))
        elif a == '--fps':
            fps = int(next(it))
        elif a == '--include-dead':
            include_dead = True
        else:
            sys.exit(f"unknown arg {a}")
    if inp == outp:
        sys.exit("refusing in-place write: input and output are the same file")

    targets = {'w': width, 'h': height, 'fps': fps}
    sites = list(LIVE_SITES)
    if include_dead:
        sites += DEAD_SITES

    data = bytearray(open(inp, 'rb').read())
    changed = already = 0
    for off, role, rd in sites:
        new = word(enc_any(rd, targets[role]))
        cur = bytes(data[off:off+4])
        if cur == new:
            already += 1
            continue
        # expected stock value at this offset
        if (off, role) in [(o, r) for o, r, _ in DEAD_SITES] and role in ('w', 'h'):
            stock_val = DEAD_STOCK_W_H[0 if role == 'w' else 1]
        else:
            stock_val = STOCK[role]
        old = word(enc_any(rd, stock_val))
        if cur != old:
            sys.exit(
                f"offset {hex(off)} ({role}, r{rd}): found {cur.hex()}, expected "
                f"{old.hex()} (stock) or {new.hex()} (already patched) — wrong firmware?")
        data[off:off+4] = new
        changed += 1

    open(outp, 'wb').write(data)
    print(f"geometry patched to {width}x{height}@{fps}: "
          f"{changed} sites written, {already} already patched "
          f"(dead sites {'included' if include_dead else 'skipped'})")
    print("md5:", hashlib.md5(bytes(data)).hexdigest())


if __name__ == '__main__':
    main()
