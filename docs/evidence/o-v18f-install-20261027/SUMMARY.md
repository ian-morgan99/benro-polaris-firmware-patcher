# `.76` installed and verified — 2026-10-27 — capture regression reverted

Candidate `o-v18f-revert-fail-closed-bulb` -> `FwVer:6.0.0.54.76;date:2026.10.27;`
libgphoto2 `df9d72745`, patcher `27f01f5`. zip md5 `d4300126adf96f82b98e7d734cc4a03f`.

## Why `.76` exists

`.75` regressed captures: they spin forever waiting for a file that never arrives.
Operator verdict: "objectively worse than .74". Cause was libgphoto2 `e7d0cf1dd`:

1. the fail-closed shutter write returned an error and started **no capture**, and
   neither Benro Connect nor pgphoto surfaces a capture error -- they just wait for
   a file, so a refusal presents as an endless spinner;
2. a new `ptp_getdevicepropvalue(PTP_DPC_PENTAX_ShutterSpeed)` readback was added
   before the capture. That is **not a supported read path** for this property on
   this body: config.c reads the shutter speed only via GetDevicePropDesc's
   CurrentValue (`_get_Ricoh_ShutterSpeed`), and of 40 `getdevicepropvalue` calls in
   config.c, **zero** are Pentax/Ricoh. So the readback fails on every timed capture
   and the refusal fires every time -- not only when the write genuinely failed.

## What `.76` guarantees

`camlibs/ptp2/library.c` is byte-identical to `.74`: `git diff 8db3785f -- library.c`
is empty, so the capture cycle is provably the one the operator confirmed working.
The `#241` model gate and current-value fix in config.c are retained (they touch only
the shutter-list getter, and run after `pentax_identify_supported_model()` populates
`model_no` at init).

Verified on the built `ptp2.so`:
- `refusing to capture` — absent (0)
- `capturing at the camera's current setting` — present (1, same as `.74`)
- shutter-list synthesis string — present (1)

## Install verification

| check | result |
|---|---|
| gate | GREEN 14 passed / 0 failed / 1 skipped; registry hash check verified 4 artifacts |
| reboot proof | uptime reset confirmed |
| build identity | `INSTALLED BUILD IDENTITY: PASS`, `FwVer:6.0.0.54.76` read back |
| Mlog | `SP_EVENT_UPGRADE_SUCCESS` |
| installed `ptp2.so` | `/app/lib/stage2/libgphoto2/2.5.34/ptp2.so` sha256 `9f0e37f9cefadea6e4a39db97631cf262a02efbf846d4babb06901764e5820e0` — **matches the manifest exactly** |

## Blocked on hardware: camera absent (likely flat battery)

Per the operator's rule -- "if you have the polaris and port 9090 but no camera,
it's likely battery flat or wider fail" -- the rig was probed:

| signal | value | reading |
|---|---|---|
| SSH / FwVer | `6.0.0.54.76` | gimbal up and current |
| port 9090 | OPEN | app control alive |
| pgphoto | pid 250, etime 24:42, stable | **not** a restart loop |
| load average | `1.10 1.05 0.85` | baseline, not the CPU-saturation signature |
| USB vendor ids | `1a40 1d6b` (hub + xHCI only) | **no Pentax `0x25fb`** |
| hub downstream | nothing | camera not enumerated at all |

This is the **flat-battery / camera-side** branch, not wider failure: the gimbal
side is healthy (stable pgphoto, baseline load, no `checkGphotoTask` loop), and the
camera simply never appears on USB. The wider-failure signature from the 2026-09-07
incident -- pgphoto looping, load saturating, radios starving -- is absent.

**Action required (physical):** power/charge the camera body and re-seat its cable,
then confirm with `scripts/wait-for-rig.py` (expect `READY model=pentax state=1`)
before any canary. `.76` is **installed, canary pending** -- not qualified.

Rollback to the operator-confirmed `.74`:
`./scripts/release/release-fwpkt.sh out/o-v18d-shutter-list-always-populated`.
