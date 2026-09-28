# o-v13d-pubfix (libgphoto2 75f9e4b1e) — install + live gate, 2026-09-26

## Build
- Source: ian-morgan99/libgphoto2 `fix/pentax-capture-publication-145` @ 75f9e4b1e
  (clean clone; provenance git_commit=75f9e4b1efb88e61adf60dbe4480ad45e8851a4d, no dirty hash)
- Build: out/o-v13d-pubfix-20260926, FwPkt.zip md5=1c36788493ae478299d832c5c7517204
- build_id 6.0.0.54.28-o-v13d-pubfix

## Install (release-fwpkt.sh) — PASS
- Staged /app/sd/FwPkt tree, all six firmwareInfo MD5s verified on-device
- /sbin/reboot; device dark ~75s; SP_EVENT_UPGRADE_SUCCESS; /app/sd/FwPkt removed
- /app/FwVer = 6.0.0.54.28-o-v13d-pubfix; provenance file matches 75f9e4b1e

## Live two-shot gate (canary-two-shot.py --expected-files 2) — FAIL (environmental)
Reproducible across 4 attempts (22:21, 22:36, 23:02, 23:25 UTC):
- 264 capture acks state:1 immediately
- ~18s later the camera re-enumerates: fresh PTP session init burst
  (286 manufacturer + 282 format + 265/266/267/275 param queries)
- USB supervisor restarts pgphoto on identity change (PID churn:
  10085 -> 21491 -> 4498 -> 14004 -> 25536 -> 30042)
- In-flight capture is lost; no state:4, no 773 file events, no files on SD
  (newest /app/sd/normal still SP_0102 from 17:44, pre-install)
- dmesg: repeated "usb 1-1.2: reset high-speed USB device number 3"
  (6 resets; count stable when idle, +1 per capture attempt)
- A forced clean re-enumeration (authorized 0->1) did NOT fix it: the next
  capture still triggered a fresh session init ~18s in.

## Diagnosis
The K-3 III's USB link is marginal after the FwPkt reboot: each capture
triggers a camera-side re-enumeration (PTP session teardown/re-init), which
the stage-2 USB supervisor treats as an identity change and restarts pgphoto,
killing the in-flight capture. This is the known issue #119 pattern
(live-view churn / USB disappearance), not a regression from 75f9e4b1e:
o-v13c (4868d36) passed the identical gate on 2026-09-25 with a warm,
settled camera.

## Next steps
1. Power-cycle the K-3 III physically (off/on) to get a clean USB link,
   wait for full settle, then re-run:
     python3 scripts/canary-two-shot.py --expected-files 2
2. If it still fails with a warm camera, capture dmesg + Clog during one
   attempt and compare ptp2 session-init behavior vs o-v13c to rule out a
   regression in the publication fix's fs-refresh path.
