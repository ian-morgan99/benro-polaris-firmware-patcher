# o-v13q iPolar frame-ownership hardening (post-o-v13p)

## Status

**Source-level prerelease — NO new FwPkt artifact.** Closes the buffer-safety
finding from the 2026-09-29 final source review (REVIEW.md): the iPolar
callback previously overwrote the same buffer exposed to consumers and copied
without validating `frame->data_bytes` against the full source span.

## Exact inputs

- Patcher `main`: `0a2d591` (this release), clean and equal to `origin/main`
- Supersedes: `o-v13p-adapter-hardening-20260929` (`08fff54`)

## Changes since o-v13p

- `e1502e0` — iPolar frame ownership: new `stage2_ipolar_frames.{h,c}`
  (3-slot ring, immutable leased slots, mutex-protected publish, generation +
  session_generation invalidation on reconnect). The callback now validates
  `data_bytes >= full source span` (stride-aware, checked arithmetic) and
  publishes a tightly-packed copy; consumers acquire/release views instead of
  reading a shared buffer. Deterministic test: `test_ipolar_frame_store`.
- `0a2d591` — build gate: `patch.sh` now compile-checks
  `stage2_ipolar_frames.c` (plain C+pthread, no libuvc dependency) with the
  same cross-toolchain + soft-float ABI flags as the other adapter gates.
- `c555804`, `8e5181f`, `9e4a729`, `8744a06`, `7715705` — CURRENT-STATE
  alignment checkpoint + live preflight/canary evidence records.

## Deterministic verification

- `container/test_ipolar_frame_store.sh`: PASS (bounds, immutable leases,
  reconnect generation) — see frame-store-test.txt
- Offline prerelease gate: GREEN (13 container + 24 Python) — see offline-gate.txt
- Both adapter TUs compile clean with patch.sh flags (zero warnings)

## Still open (per final source review)

- StarShoot hardware discriminator (handshake + one frame from 16c0:29a0)
- Linking both adapters into the stage2 runtime build (compile-check only today)
- libgphoto2 `main` StarShoot UVC inventory correction (separate repo)
