# USB compatibility on; post-reboot shot refused — 2026-09-30 16:00

The user confirmed OpenPolaris was closed, disconnected all clients, reconnected
with the iPhone, and turned USB compatibility mode on. Polaris uptime was 67 s
when the refusal was collected, confirming a fresh Polaris boot. Firmware was
`6.0.0.54.44`. Exactly one control client (iPhone `192.168.0.3`) had active
9090 and 8080 connections. Pentax K-3 III was enumerated as `25fb:0189`.

## Result

At 16:00:42, Benro Connect sent capture request `SP_0151.jpg`. It reached
libgphoto2 and the Pentax camlib. The strict pre-shutter conditions query
returned PTP `0x2001`, size 576, with `field32=1`, `field36=1`, and
`field104=0`. Admission refused with reason `capture-active`; no
`InitiateCapture` was sent. The error propagated as libgphoto2 `-110`, Polaris
`state:-1005`, and `PHOTO_RECORD Fail`.

During initialization, Mlog briefly reported camera state 0 / no model at
15:59:55, then `state:1`, Pentax K-3 III, `photoFormat:2` at 15:59:58 (the
current setting is RAW+JPEG according to the earlier direct camera config
read). This confirms camera enumeration/rebind worked, but did not clear the
unsafe camera-reported capture/candidate state.

## Interpretation / guardrail

This is not an OpenPolaris contention reproduction: OpenPolaris was closed and
only one Benro Connect client was connected. It is not a failed
`InitiateCapture`: the admission guard rejected the request before shutter
initiation. The camera reports both an active capture flag and a pending
candidate. The exact underlying camera operation/file ownership is unknown;
do not weaken the guard, clear the candidate, restart the camera stack, or
submit another shutter until that state is safely understood. The pre-shutter
refusal is the correct fail-closed behavior, although the user-facing busy
failure shows recovery is not yet adequate.

No camera USB disconnect appears in the current kernel tail. Preview calls
continue to return PTP success. No second control client, daemon restart, or
additional shutter was issued by the investigator.

## Raw evidence

Complete snapshot: `raw/`. Relevant SHA-256 values:

- `raw/sd/system/log/Clog_000186.log`:
  `4b5bdbb6a45533326f40b00900b1eecf602c02030703a054c17ddaee74edfe7c`
- `raw/sd/system/log/Mlog_000186.log`:
  `74a4ad5e2e56f355b78210489e765c3a7cb92994cae3be8092ab6fddb9f48315`
- `raw/Clog.txt`:
  `d14dd7095d77bf862115c8798a43aab145271856c4e06710565258996e71fef6`
- `raw/Mlog.txt`:
  `cce03ac269c6bc3c9ea2551e093eef1619358c5aa888af129c4ba89ba36588e7`
- `raw/device-state.txt`:
  `50a0665168fc6b95f58a5f187c6d9c9bf68b9fdb42b2ba1c74e6e50adf128cc7`

Use log content timestamps and Polaris uptime for event ordering; host/device
wall-clock offsets and copied-file mtimes are not reliable.

## Preservation location — 2026-10-01

This historical assessment and its complete original raw directory are preserved
in the [verified private working-tree archive](https://github.com/ian-morgan99/PrivateResearch/blob/main/archives/pentax-workspace-convergence/20260930/patcher-main-dirty.tar.gz).
Extract its `docs/evidence/pentax-usb-compatibility-on-20260930-1600/` subtree.
This preservation note does not add a hardware test or change the original
assessment; current qualification is in `docs/HANDOVER-PENTAX-STABILITY-20260930.md`.
