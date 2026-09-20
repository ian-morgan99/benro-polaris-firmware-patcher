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

Idempotent: if the replacement bytes are already present, exits 0.
Fails loudly if neither anchor nor replacement is found.
"""
import sys

ANCHOR = bytes.fromhex("1c301be5" "fa2fa0e3" "920303e0" "1c300be5")
REPL   = bytes.fromhex("1c301be5" "0030a0e3" "000000e1" "1c300be5")

def main():
    if len(sys.argv) < 2:
        print("usage: polestar_bulb_patch.py <polestar_app> [--in-place]", file=sys.stderr)
        return 2
    path = sys.argv[1]
    in_place = "--in-place" in sys.argv

    with open(path, "rb") as f:
        data = bytearray(f.read())

    if REPL in data:
        print("[polestar_bulb_patch] already patched (replacement bytes present)")
        return 0

    idx = data.find(ANCHOR)
    if idx < 0:
        print("[polestar_bulb_patch] FATAL: anchor not found — "
              "unexpected polestar_app binary (firmware drift?)", file=sys.stderr)
        return 1

    data[idx:idx+len(REPL)] = REPL
    print("[polestar_bulb_patch] patched at file offset 0x%x "
          "(mul r3,r2,r3 -> mov r3,#0; bulb pre-shot delay zeroed)" % idx)

    if in_place:
        with open(path, "wb") as f:
            f.write(data)
    else:
        out = path + ".patched"
        with open(out, "wb") as f:
            f.write(data)
        print("[polestar_bulb_patch] wrote %s" % out)
    return 0

if __name__ == "__main__":
    sys.exit(main())
