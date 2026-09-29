# o-v13t strict admission and per-path recovery candidate

Status: **package-gated; not installed; physical Pentax test pending.** The
preceding installed candidate's failed canary may have left output/session state
unresolved, so this artifact was not installed and no further shutter was sent.

## Plain English

The recovery is no longer one generic “camera busy” response. Each known path
has its own reason and safe next action: unreadable PTP readiness, unsafe camera
activity, exposure already active, unresolved output candidate, transfer in
progress, and `InitiateCapture` failure. Every shutter now goes through the
same authoritative pre-shutter check. A failed `InitiateCapture` is logged and
is never automatically replayed. Candidate data is preserved when ownership is
uncertain. These safeguards prevent another shutter from compounding an
unresolved operation; they do not yet prove the Pentax hardware will recover.

## Source and build provenance

- Patcher: `94c4882721607460242dffb2e49286c9b81bf21c`, `main`, clean.
- libgphoto2: `f05f6582662997975676d434015b08e20e83100e`, `main`, clean.
- Harness: `0355f6f643ae7c154ea42a2f751d14fa1dbcb135`, `main`.
- Release build: `6.0.0.54.39-o-v13t-strict-admission`, version `2.5.34`,
  selected camlibs `ptp2,pentax`; stock packet `firmware/FwPkt.zip`.
- ZIP: `out/o-v13t-strict-admission-20260929/FwPkt.zip`.
- ZIP MD5: `1d49a01b8289db8811c75768b0224f7c`.
- ZIP SHA-256: `e023d4e2b5f79946f2a3ee0173c7d067a4fdfe9ff4073ae0729383e3bb2a3cb9`.
- appfs MD5: `8a6ced8f9b78f5f1005c66ff9d12895e`.
- PrivateResearch artifact commit: `4a27c8b29` (pushed to private `main`).

## Test evidence

- libgphoto2 deterministic fresh regression build: **13/13 passed**. The
  no-CI serial-control fixture was excluded because the host lacks a supported
  DTR/CTS fixture; no test was weakened.
- Production `ptp2.so` build: passed.
- Patcher offline gate: **14 container + 24 Python checks passed**.
- Package and firmwareInfo gate: **4 passed, 0 failed, 0 skipped**.
- Harness: **62 passed** at `0355f6f643ae7c154ea42a2f751d14fa1dbcb135`.
  This verifies deterministic software contracts only, not Pentax hardware.
- Final package-content check: extracted appfs from the exact output ZIP.
  `lib/stage2/libgphoto2.so.6`, stock-path `/lib/libgphoto2.so.6`, both
  `ptp2.so` copies, and `/bin/pgphoto` matched their generated build-bundle
  counterparts by SHA-256. Stage-2 selected camlibs are `ptp2,pentax`.
- Adapter caveat: StarShoot adapter compiled. iPolar adapter compile-check was
  skipped because libuvc headers are missing in this environment. This
  Pentax-focused candidate does not claim new UVC qualification.
- Physical camera tests: **not run**. Not installed; no claim of capture pass.

## Changed recovery behavior

libgphoto2 implementation details and generic-caller recovery semantics are in
`ian-morgan99/libgphoto2/docs/pentax/CAPTURE-RECOVERY.md`. Patcher/Stage-2
boundary diagnosis is in `docs/PENTAX-CAPTURE-RECOVERY.md`. The critical
remaining boundary is an operation accepted by the camera but no candidate or
completion exposed to pgphoto: preserve the session, do not retry, obtain the
PTP boundary trace, and only then decide whether a session reset is safe.
