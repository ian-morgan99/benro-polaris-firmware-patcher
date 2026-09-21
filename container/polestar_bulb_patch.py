#!/usr/bin/env python3
"""Issue #120: zero the polestar_app pre-shot bulb delay.

The 264 (PHOTO_RECORD) handler in SP_MsgCameraFromAppProc parses
"state:%d;bulb:%d;c:%d;", multiplies bulb (seconds) by 1000 to get ms,
and passes it to SP_MakeNormalPhoto -> SP_SetPhotoRecodeState as a
pre-shot countdown timer. The camera's own Bulb timer (set via cmd 277
shutter index) controls the actual shutter-open duration, so the
polestar_app-side bulb_ms is redundant and causes the observed
"countdown then 1s exposure" behaviour.

Patch: replace the `mul r3, r2, r3` (bulb*1000) with `mov r3, #0` so
no pre-shot delay is applied. The surrounding ldr/str of [fp,-28] are
preserved so the store-back still happens (with zero).

Anchor (16 bytes, unique in the stock binary):
  ldr r3,[fp,#-28]   e51b301c  -> LE 1c301be5
  mov r2,#1000       e3a02ffa  -> LE fa2fa0e3
  mul r3,r2,r3       e0030392  -> LE 920303e0   <-- replaced
  str r3,[fp,#-28]   e50b301c  -> LE 1c300be5

Replacement:
  ldr r3,[fp,#-28]   e51b301c  -> LE 1c301be5   (unchanged)
  mov r3,#0          e3a03000  -> LE 0030a0e3   (zero the delay)
  nop                e1200000  -> LE 000000e1   (fill the mul slot)
  str r3,[fp,#-28]   e50b301c  -> LE 1c300be5   (unchanged)

Usage:
  polestar_bulb_patch.py <polestar_app> [--in-place]

Fail-closed semantics (issue #120 TA review). The binary is classified by the
occurrence counts of ANCHOR and REPL, and only two states are accepted:

  * FRESH:      ANCHOR==1 and REPL==0  -> patch that unique site, then re-read
                the bytes at the SAME recorded offset and verify they equal
                REPL before reporting success.
  * PATCHED:    ANCHOR==0 and REPL==1  -> idempotent no-op; the replacement is
                validated at its unique site (not by arbitrary global
                membership).

Every other combination fails closed, because it means the intended patch site
is not uniquely identified:
  * ANCHOR==0 and REPL==0  -> unexpected firmware (neither marker present).
  * ANCHOR>1               -> the handler is not unique; patching the first
                              occurrence would be a guess.
  * REPL>1                 -> the replacement bytes appear in more than one
                              place; we cannot prove which is the 264 handler.
  * ANCHOR>=1 and REPL>=1  -> mixed state: both the pre-patch and post-patch
                              sequences are present, so an unrelated REPL block
                              exists elsewhere. Refuse rather than guess.

Exit codes: 0 = patched or verified-already-patched; 1 = FATAL; 2 = usage.
"""
import sys

ANCHOR = bytes.fromhex("1c301be5" "fa2fa0e3" "920303e0" "1c300be5")
REPL   = bytes.fromhex("1c301be5" "0030a0e3" "000000e1" "1c300be5")


def count_occurrences(hay: bytearray, needle: bytes) -> int:
    n = 0
    start = 0
    while True:
        i = hay.find(needle, start)
        if i < 0:
            return n
        n += 1
        start = i + 1


def main():
    if len(sys.argv) < 2:
        print("usage: polestar_bulb_patch.py <polestar_app> [--in-place]", file=sys.stderr)
        return 2
    path = sys.argv[1]
    in_place = "--in-place" in sys.argv

    with open(path, "rb") as f:
        data = bytearray(f.read())

    a = count_occurrences(data, ANCHOR)
    r = count_occurrences(data, REPL)

    # --- PATCHED (idempotent re-run): unique replacement site, no anchor left. ---
    if a == 0 and r == 1:
        i = data.find(REPL)
        print("[polestar_bulb_patch] already patched (unique replacement site at "
              "file offset 0x%x)" % i)
        return 0

    # --- FRESH: exactly one anchor, no replacement anywhere. ---
    if a == 1 and r == 0:
        idx = data.find(ANCHOR)
        data[idx:idx + len(REPL)] = REPL
        # Post-write verification at the SAME recorded offset (not a global search).
        if bytes(data[idx:idx + len(REPL)]) != REPL:
            print("[polestar_bulb_patch] FATAL: post-write verification failed at "
                  "offset 0x%x" % idx, file=sys.stderr)
            return 1
        print("[polestar_bulb_patch] patched at file offset 0x%x "
              "(mul r3,r2,r3 -> mov r3,#0; bulb pre-shot delay zeroed); "
              "post-write bytes verified at the same site" % idx)
        if in_place:
            with open(path, "wb") as f:
                f.write(data)
        else:
            out = path + ".patched"
            with open(out, "wb") as f:
                f.write(data)
            print("[polestar_bulb_patch] wrote %s" % out)
        return 0

    # --- Fail-closed: the intended site is not uniquely identified. ---
    if a == 0 and r == 0:
        print("[polestar_bulb_patch] FATAL: neither anchor nor replacement found "
              "- unexpected polestar_app binary (firmware drift?)", file=sys.stderr)
    elif a > 1:
        print("[polestar_bulb_patch] FATAL: anchor found %d times (expected exactly "
              "1 unique site) - refusing to guess which is the 264 PHOTO_RECORD "
              "handler" % a, file=sys.stderr)
    elif r > 1:
        print("[polestar_bulb_patch] FATAL: replacement bytes present %d times "
              "(expected exactly 1 unique site) - cannot prove which is the 264 "
              "PHOTO_RECORD handler" % r, file=sys.stderr)
    else:  # a >= 1 and r >= 1 (mixed state)
        print("[polestar_bulb_patch] FATAL: mixed state - anchor present %d time(s) "
              "AND replacement present %d time(s); an unrelated REPL block exists "
              "elsewhere, so the intended site is not unique" % (a, r), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
