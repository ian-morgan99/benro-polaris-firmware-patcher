# o-v18a (`.71`) install — VERIFIED 2026-10-26

Candidate: `o-v18a-diag-20261025` -> `FwVer:6.0.0.54.71;date:2026.10.26;`
Artifact: zip SHA-256 `b634394db2b830d1f28abbf84072d08c4b537d777b4a0c05425947d9d90c799d`
Provenance: libgphoto2 `f95bc5753`, patcher `7d534319`
Path: `scripts/release/release-fwpkt.sh` (first install using the canonical path)

## Verdict: VERIFIED
- All six `firmwareInfo` MD5s matched on-device before reboot
- Device went dark; **uptime reset 85623s -> 14s** proves a real boot, not an AP flap
- `INSTALLED BUILD IDENTITY: PASS` (build_id + display_fwver)
- Mlog: `SP_EVENT_UPGRADE_SUCCESS`, then `SP_DelUpgradeFiles: remove /app/sd/FwPkt`
- Fix present in the flashed `/app/lib/libgphoto2/2.5.27.1/ptp2.so`

## What this candidate ships
One change: Bulb with seconds selected (issue #239). A start edge no longer returns
GP_ERROR_NOT_SUPPORTED when the body's own Bulb timer is armed; it records the time and
the matching stop applies the measured hold as a shutter speed plus one timed capture.

## Two installer bugs found and fixed during this install
1. The 286 idle check read the whole socket reply, which is the device's continuous
   284/517 telemetry, so every install looked busy. Now parses only the `286@` frame.
2. `grep` returning 1 on "no 286 frame" (the idle case) tripped `set -e` and aborted
   pre-flight. Wrapped so a no-match yields an empty frame.

## Physical qualification still pending
Bulb with seconds selected on a K-3 III: select a second-count from the B list, confirm
a file is written and its ShutterSpeedValue matches the selection.
