# o-v13r StarShoot discriminator harness (post-o-v13q, #158)

## Status

**Source-level prerelease — NO new FwPkt artifact.** Adds the host-side
hardware-discriminator harness for the attached 16c0:29a0 StarShoot and
records the USB-compatibility-off capture failure evidence.

## Exact inputs

- Patcher `main`: `95695e2` (this release), clean and equal to `origin/main`
- Supersedes: `o-v13q-frame-ownership-20260929` (`f248ec4`)

## Changes since o-v13q

- **StarShoot discriminator harness** (`container/test_starshoot_discriminator.c`):
  exercises the adapter's exact transfer encoding (class OUT control,
  bRequest 0x41, opcode word) against the attached camera — IS_CAMARA_INIT
  handshake + bounded bulk IN on EP 0x81 for one frame. Fail-closed with
  distinct exit codes (0 handshake+frame / 1 handshake only / 2 open-claim
  only / 3 not enumerated / 4 open failed); alternate encodings probed as
  evidence when the primary fails. Hardware-gated, so it is NOT in the
  deterministic suite.
- **USB-compat-off failure evidence** (`docs/evidence/usb-compat-off-2026-09-29/`):
  Polaris C/M/error logs + dmesg collected read-only after the
  capture-failure/reboot, SHA-256 indexed.

## Deterministic verification

- `tests/run_deterministic.sh`: 14 passed, 0 failed, 2 prerequisite skips — see deterministic-suite.txt
- Offline prerelease gate: GREEN (14 container + 24 Python) — see offline-gate.txt
- Harness compiles clean (`gcc -O2 -std=gnu11 -Wall`, zero warnings)

## Still open (per TA updates on #158/#159, 2026-09-29 08:49)

- #158: run the discriminator with USB write access (sudo/udev rule);
  ScanQHYCCD=0 from the INDI/QHY SDK probe means protocol/driver match is
  still unproven; ARMv6 SDK lib is hard-float — not packageable for the
  soft-float glibc 2.24 target. Issue stays open until a frame is proven on target.
- #159: frame-store ownership fix (e1502e0) accepted as memory-safety
  improvement; NOT end-to-end iPolar support — no device attached, not linked
  into shipped runtime, no Y16 frame captured yet.
