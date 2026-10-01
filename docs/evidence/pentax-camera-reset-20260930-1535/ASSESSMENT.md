# Camera reset report — 2026-09-30 15:35 (Polaris log time)

## Evidence captured

At approximately 15:40 local time, collected the live Polaris `Clog_000183.log`,
`Mlog_000183.log`, kernel ring buffer, firmware version, uptime, and USB listing.
The raw snapshot is in `raw/`. SHA-256:

| File | SHA-256 |
| --- | --- |
| `raw/Clog_000183.log` | `5b792a7e237878f1735546dabf6b07d9b276cb64d7c99736d4bb205e32b7126a` |
| `raw/Mlog_000183.log` | `242515fd66cd7509fc9ff0b56b99d8c7c0c2e1e6e8cecc4e49adf5d8c01d383c` |
| `raw/kernel-and-state.txt` | `e472c2a8dc0b7f207dd72ec316384c2090d6365483103ca8769bebd7590af718` |

## What the evidence says

- The Polaris was still running, not rebooted: uptime was about 35 minutes at
  collection. Its installed firmware reported `6.0.0.54.44`.
- The Pentax K-3 III was attached when checked (`25fb:0189`, USB bus 001 device
  004). That confirms it was present at collection, not what happened on the
  camera LCD at 15:35.
- At 15:33:23, Benro Connect submitted a capture request for
  `/app/sd/normal/SP_0151.jpg`. The capture path returned `-110`, which was
  reported to the app as `-1005` / `PHOTO_RECORD Fail`. No successful capture
  completion is recorded for that request.
- Mlog continues to 15:39 with gimbal telemetry. It contains no camera-offline
  (`manufacturer:none`, `state:0/-5`) transition at 15:35; its last camera status
  before the failed request reports the Pentax as `state:1`.
- The kernel ring buffer contains a USB reset, a disconnect of Pentax USB device
  3, and re-enumeration as device 4, followed by resets of device 4. The ring
  buffer output available here has no usable event timestamps. The sequence
  therefore proves USB reset/disconnect activity occurred during this boot,
  but does not prove it occurred at the reported 15:35 time. Clog records a
  later successful camera enumeration at 15:31:33, so the earlier USB sequence
  is not enough to attribute the user-reported reset to 15:35.

## Attribution and safety

The report is consistent with a camera/USB or camera-session interruption, but
the collected evidence does **not** establish that the camera itself rebooted
at 15:35 or identify the trigger. Polaris remained up; the camera was enumerated
again when checked. The 15:33 capture failed before success and the app may
remain in a busy/pending state. No additional shutter request, control socket,
daemon restart, or reboot was issued by the investigator during this check.

Do not treat this as a successful camera reset/recovery test. Preserve the
camera/app state until the next explicitly bounded diagnostic action; do not
submit another shutter while the app reports busy.

## Preservation location — 2026-10-01

This historical assessment and its complete original raw directory are preserved
in the [verified private working-tree archive](https://github.com/ian-morgan99/PrivateResearch/blob/main/archives/pentax-workspace-convergence/20260930/patcher-main-dirty.tar.gz).
Extract its `docs/evidence/pentax-camera-reset-20260930-1535/` subtree.
This preservation note does not add a hardware test or change the original
assessment; current qualification is in `docs/HANDOVER-PENTAX-STABILITY-20260930.md`.
