# K-1 II direct-PC findings on v115 — 2026-11-23

Body: PENTAX K-1 Mark II fw 2.51, USB 25fb:0183, "Pentax K-1 Mark II (PTP mode)".
Driver: host x86 build of exact v115 pin 0f2f34e00040. Exposure mode Manual.

## Works (verified write + readback + body-state proof)
iso (ISO=400 confirmed via pentaxconditions, not just gphoto cache), whitebalance
(auto<->daylight), shutterspeed (00:05, 00:01), aperture (f/8, f/4).
51 widgets publish; ZERO empty choice arrays (unlike K-3 III's five).

## Cross-model failures (same as K-3 III — confirms these are not per-body)
- MF drive: manualfocusdrive -7..7 all ERROR (-1); manualfocusdrivenear/far and
  oldfocusdrivenear/far all ERROR (-1). Trace: driver sends PTP_OC 0x9016
  (old-focus family, the #303 path) and body rejects with vendor response 0xa00c.
  K-3 III used 0x9017 -> same 0xa00c. So BOTH focus opcodes are refused by the
  bodies regardless of family. See #381.
- imageformat [JPEG,RAW,RAW+JPEG] and imagequality: every write -102 Corrupted
  data, including writing the current value (JPEG). See #386.

## K-1 II differs from K-3 III (so #384 is K-3 III-specific, NOT cross-model)
- pentaxliveviewzoom writes WORK on K-1 II: 2x -> readback 2x, off -> readback off.
  On K-3 III every zoom write failed. So #384 must be scoped to K-3 III only.
- No pentaxfocuspeaking widget published at all (K-3 III has it but it no-ops).
- No pentaxpclvmode widget published at all.
- Extra oldfocusdrivenear/far toggles present (old-focus family widgets).

## Capture / preview
--capture-image and --capture-preview both -6 Unsupported operation, same as
K-3 III: body advertises no 0x4006. #316/#317 must be qualified on the Polaris
lane via wire code 264.

## Drive mode
pentaxdrivemode publishes 23 choices (vs K-3 III's 3) — single frame, continuous,
self-timer variants. current=single.
