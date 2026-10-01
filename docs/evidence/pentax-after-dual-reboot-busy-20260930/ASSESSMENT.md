# Post-reboot busy refusal — 2026-09-30

The user confirmed they manually rebooted both the Pentax and Polaris before
this test. This corrects the preceding assessment, which was made from a
pre-reboot sample and incorrectly inferred that Polaris had not rebooted.

## Device state observed after the reboot

- Correct Polaris AP identity was verified (`polaris_d13e86`, BSSID
  `48:e7:da:d4:b5:73`) and route to `192.168.0.1` used Wi-Fi.
- Installed firmware: `6.0.0.54.44`.
- Polaris uptime was about 8 minutes when the busy report was investigated,
  consistent with a recent reboot.
- Pentax K-3 III remained enumerated as USB `25fb:0189`.
- The persisted startup Clog shows camera enumeration at `usb:001,003`,
  `Pentax session already open from a previous connection; observing camera
  state`, and `gp_camera_init ret 0`. Mlog reports storage-state transition
  `0 -> 1` and `SP_EVENT_APP_CONNECT`.
- Live Clog contains multiple successful Pentax preview fetches (`0x2001`,
  about 62–70 KB, 17–21 ms each), so preview traffic reached the camera.

## Reported failure and limits

The user then reported Benro Connect showed “shoot failed. camera is busy.”
The current snapshot has no corresponding `code[264]`, `capture_image`,
`InitiateCapture`, or terminal lifecycle event in the captured device logs.
The live `Mlog.txt` was empty, while the archived Mlog ended at startup. Thus
the available logs do not prove that a shutter request reached the Polaris
capture handler or Pentax. This points to an earlier refusal (potentially
client/UI/session state), but missing live Mlog means it is not yet proven to
be a client-side bug.

No USB disconnect/reset is visible in the captured current kernel tail; the
camera was still enumerated at collection. No additional control client,
shutter command, daemon restart, or reboot was issued by the investigator.

## Evidence files

Raw snapshot: `raw/` (captured immediately after the reported refusal).
SHA-256:

- `raw/Clog.txt`: `4b8df2c4220eda64c907b4ce10e35f7fd9e4de600d308f42c52ee4c6c22616c2`
- `raw/Mlog.txt`: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` (empty)
- `raw/sd/system/log/Clog_000184.log`: `e1c06ffba1543739b9abe89a44a613b0bd913df8e8935e16188a5458a19d8424`
- `raw/sd/system/log/Mlog_000184.log`: `5149623b93457eada082c7ff79a83acaca91752b5d23fb6a05d1a5a4d0664da2`
- `raw/device-state.txt`: `56039ef55aac14bd7fb928ad6fb87553493eedd4ea9fff3563d3feead5980129`

The host and Polaris clocks were not aligned during collection; use the log
sequence and reboot uptime, not file mtimes, to correlate events.

## Preservation location — 2026-10-01

This historical assessment and its complete original raw directory are preserved
in the [verified private working-tree archive](https://github.com/ian-morgan99/PrivateResearch/blob/main/archives/pentax-workspace-convergence/20260930/patcher-main-dirty.tar.gz).
Extract its `docs/evidence/pentax-after-dual-reboot-busy-20260930/` subtree.
This preservation note does not add a hardware test or change the original
assessment; current qualification is in `docs/HANDOVER-PENTAX-STABILITY-20260930.md`.
