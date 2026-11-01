# o-v18b (`.72`) install — VERIFIED 2026-10-26

Candidate: `o-v18b-bulb-duration-from-body-20261026` -> `FwVer:6.0.0.54.72;date:2026.10.26;`
zip md5 `e457f01a76c585cd2c1dafb653317d65`, sha256 `1ff55db12ffd290da2b677d77172a3224d09f3197d82d40dd16460ae6613831b`
Provenance: libgphoto2 `749d38f6d`, patcher `cd892ba`
Built from: fresh clones of both repos at published `main`.

## Verdict: VERIFIED
- Regression pack 16/0 before patching (test-gp-port is no-ci, needs real ports)
- All six `firmwareInfo` MD5s matched on-device before reboot
- Device went dark; **uptime reset 10238s -> 14s** proves a real boot
- `INSTALLED BUILD IDENTITY: PASS`; Mlog shows `SP_EVENT_UPGRADE_SUCCESS` then
  `SP_DelUpgradeFiles: remove /app/sd/FwPkt`
- Flashed `ptp2.so` contains the duration-from-body change and its new log line

## What this candidate ships
One libgphoto2 change (#239 follow-up): the deferred camera-timed Bulb capture now
uses the duration the body reports (`bulb_timer_seconds` in the pre-capture
conditions) instead of measuring how long pgphoto slept between the start and stop
edges. `.71` measured that interval, which contains the body's countdown as well as
the exposure, so it could overshoot.

## One transient failure during install
First staging attempt died mid-stream at ~50 MB:
`tar: -: Wrote only 6144 of 10240 bytes`. The device was healthy (106 G free, a
64 MB dd write at 103.7 MB/s, no mmc/I-O errors in dmesg) and host `tar czf` over the
whole tree exits 0, so this was a broken pipe, not a device write failure. The
partial `/app/sd/FwPkt` was removed immediately, because an incomplete tree is a
reboot hazard: the on-boot watcher would consume it. A retry staged cleanly and all
MD5s verified.

## Pending physical qualification
Timed Bulb still correct, and the x-second countdown followed by an x-second capture
should no longer double. The new log line reports the seconds the body gave, which
settles whether the visible countdown is the body's B-mode timer (inherent, not
removable from our layer) or pgphoto's own sleep.
