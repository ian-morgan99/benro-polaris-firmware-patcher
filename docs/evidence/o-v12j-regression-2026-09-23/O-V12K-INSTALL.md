# o-v12k clean A/B install and first canary (2026-09-23)

## Artifact

- Registry id: `o-v12k-lvrevert-20260923`
- Build id: `6.0.0.54.21-o-v12k-lvrevert`
- Zip MD5: `e8b70b868442d01622b1df4232cfd7b8`
- Zip SHA-256: `17af50c22ac4589c3e8f8f3578a5cff43f1f8e64ca660cf93ec609d30d5db21a`
- Appfs MD5: `6c27469c27a2f78b00a8ede940d84965`
- libgphoto2: `6da9612a618b2ce96a8f317d8bc953c173f9a0d2`
- patcher: `892d36b0668b7df049433ca2f45163afe81260a7`
- Private artifact commit: `61e9c94`

The build used clean detached/standalone Git trees. Matched-stack ABI, symbol,
loader, package-layout, appfs-content and firmwareInfo gates passed. A first
archive-input build was deliberately rejected because its generated provenance
left `git_commit` blank; it was neither published nor staged.

## Canonical installation

Before staging, identity was proved with Polaris BSSID `48:E7:DA:D4:B5:73`,
route to `192.168.0.1` over `wlp8s0`, and installed o-v12j FwVer/provenance.
The SD target was empty. The complete extracted tree was streamed to
`/app/sd/FwPkt`; all six on-device MD5 checks passed. `/sbin/reboot` triggered
the normal watcher. The device went dark, returned after about 60 seconds, and
Mlog recorded `SP_EVENT_UPGRADE_SUCCESS` followed by removal of
`/app/sd/FwPkt`.

Post-boot identity matched the artifact exactly. The K-3 III enumerated as
`25fb:0189`. Stage-2 and stock core hashes matched (`5973e8c8...`), as did both
port-library copies (`ad50e835...`). Process maps proved the Stage-2 loader,
core and port in use. The wrapper environment had the expected CAMLIBS, IOLIBS,
library paths and preview backoff, with no forced `STAGE2_PENTAX_KEEP_LV=0`.

## First live canary and capture failure

With the camera attached and preview traffic active, Clog initially showed
valid Pentax preview frames (`0x2001`, non-zero JPEG sizes) and no unsolicited
capture entry. The bounded full canary then stopped preview and issued exactly
one deliberate shutter frame. The app acknowledged `state:1`, but no file or
completion event arrived. No second shutter was issued.

Archived Clog `Clog_000136.log` proves the same first divergence as o-v12j:
the daemon reads `RAW+JPEG`, reports `numOfCaptureImage 2`, enters
`capture[1]`, and then Stage-2 dies before `real gp_camera_capture returned`.
This run reports `SIGSEGV si_addr=pc=0x0047004c`. The restarted daemon cannot
reopen the PTP session (`OpenSession` `0x02ff` then `0x02fa`) and emits
`state:-10`, while USB enumeration continues to show `25fb:0189`.

Therefore o-v12k is a **failed capture candidate**. The clean A/B shows that
removing `a710c09` is necessary for architecture/isolation, but not sufficient
to fix the shutter crash. Since the crash occurs after entering the real
synchronous core call and before reconciliation, the next source isolation is
the libgphoto2 delta from hardware-working `c0592d178` to `971c8727e`; the later
async-trigger guard in `6da9612a6` is not on this synchronous call path.

## Next bounded physical tests

1. Do not issue another shutter on o-v12k.
2. Return to a candidate based on the last hardware-working libgphoto2 SHA,
   with the unsafe connection-time Live View delta still absent.
3. After a physical camera USB/power reset, take one deliberate normal still.
4. Only if it passes, take two consecutive RAW+JPEG stills.
5. Only if those pass, repeat Pixel Shift RAW+JPEG and confirm the camera-declared
   two-file obligation without treating four physical sensor exposures as four
   host files.
6. Thermal qualification remains separate: the final design must make Live View
   demand-owned and stop it after the last consumer instead of forcing a camera
   property during every init.
