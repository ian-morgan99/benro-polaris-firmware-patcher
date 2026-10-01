# Polaris USB drop and camera return — 2026-09-30

## Plain-English result

At about 12:50 the K-3 III disappeared from Polaris USB. The operator suspects
the camera battery was flat, then reports fitting a new battery and power
cycling the camera. The device log confirms a USB reset followed by disconnect;
it does not identify whether camera battery loss, cable/power, or a USB/Polaris
event initiated the reset. Polaris itself reported 28–29% battery and 10.62–
10.63 V during the interval, so the recorded Polaris battery was not flat.

The camera re-enumerated at 12:52:34 UTC. The first status probe at 12:52:45
still returned no camera, but a later probe at 12:52:58 returned the K-3 III
ready (`state=1`, `storage=2`, `photoFormat=2`). This recovery happened without
a Polaris reboot. No shutter was sent in this interval.

## Candidate identity

- Installed display/build: `6.0.0.54.43-o-v13x-camlib-prep-20260930`
- Firmware SHA/source record: patcher `575d5d8b7e31ef2d82c9a8354e6e6a517a87576c`
- Embedded libgphoto2: `fbc2e7e6544efc93cc708a1e7d2fdf2b2bf7c7cd`
- This is the already-installed o-v13x Pentax candidate, not a newly built 15a.

## Evidence and limits

- Kernel log shows Pentax `25fb:0189` on `1-1.2`, followed by USB reset and
  `USB disconnect`.
- The camera was already absent by the 12:50:54 Clog USB scan and
  `sp_Gphoto_Init ret -5`. The first 9090 read-only camera-info probe was at
  12:51:05 and returned `state=-5`, so that probe occurred after the detach and
  cannot explain the initial USB loss. No capture/shutter command was issued.
- Operator then reported new camera battery and camera off/on. Mlog recorded
  USB `add@.../1-1.2` at 12:52:34; by 12:52:58 the probe returned `state=1`.
- At snapshot time, a phone client at `192.168.0.2` had both 9090 control and
  8080 preview connections. Do not add a second control client for the next
  capture; have the operator trigger one ordinary M-mode shot in Benro Connect
  and correlate the resulting logs.
- No camera battery telemetry was available while it was absent. A flat camera
  battery is plausible from operator context but is not proven by these logs.
- The initial Bluetooth wake attempt preceded the user's successful Benro
  Connect wake; exact event-time correlation is insufficient to rule out every
  radio/wake interaction. The actual 9090 status probe was later than the USB
  detach and was read-only.

## Archived files

Raw Clog/Mlog, rotated Clog/Mlog/error log, and device/kernel snapshots are in
`raw/`. SHA-256 values:

| File | SHA-256 |
| --- | --- |
| `raw/Clog.txt` | `5cd2dceb400cecfa0767fe6a9162d97f1ced8fa7c9a3e74905dc667a2b415e7a` |
| `raw/Mlog.txt` | `0cbcef2c3f95b7c8603ef891468e329f0fd7e30ea6f09a6efdd600bd2921e68e` |
| `raw/Clog_000182.log` | `c1c062dbe6545dc3501fbb365fc50d857bf55908b58d383b71491f52c503550a` |
| `raw/Mlog_000182.log` | `26841a06cea03cb26937a96dfa4d8453f15c3007a057e77d5e4f317d33b72f33` |
| `raw/error_000182.log` | `14c7c55a71010c0930cfcdafdb399364d03454dd46d12803d7357b10b1b80d80` |
| `raw/device-snapshot.txt` | `bcbfb777b1c5616ceb8af0222ab4f0891ce6310fcd64fde2b16930d69e11e114` |
| `raw/Clog-after-camera-return.txt` | `5ff87ebe2f8b2902cd3f905957f02f47c0f5b9414e32924710acb7d977c9ea7b` |
| `raw/Mlog-after-camera-return.txt` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `raw/device-after-camera-return.txt` | `602cfca71406d322a5c67e3faf29e93386d6a903afdf8ad1d391bf0b80f1b18b` |

## Preservation location — 2026-10-01

This historical assessment and its complete original raw directory are preserved
in the [verified private working-tree archive](https://github.com/ian-morgan99/PrivateResearch/blob/main/archives/pentax-workspace-convergence/20260930/patcher-main-dirty.tar.gz).
Extract its `docs/evidence/polaris-usb-drop-20260930-1250/` subtree.
This preservation note does not add a hardware test or change the original
assessment; current qualification is in `docs/HANDOVER-PENTAX-STABILITY-20260930.md`.
