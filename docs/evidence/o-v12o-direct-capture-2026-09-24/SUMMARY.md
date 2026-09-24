# o-v12o direct-capture A/B candidate — 2026-09-24

## Purpose

Restore `gp_camera_capture` to the exact resolved libgphoto2 core target. The
Stage-2 capture wrapper was introduced after o-v9p, the last broad repeated
K-3 III capture PASS. On o-v12j, o-v12k and o-v12n, capture entered that wrapper
and then faulted at an invalid low program counter before the core returned.

## Direct camera discriminator

K-3 III firmware 2.20 was attached directly as USB `25fb:0189`. A clean build
of the exact o-v12n libgphoto2 SHA, `ab0de090c`, passed:

- five valid preview JPEGs;
- shutter `1/20 -> 1/8000 -> 1/20` with read-back and restoration;
- two consecutive RAW captures twice, producing four complete, distinct DNG
  payloads (`IMGP3605` through `IMGP3608`).

After a physical USB detach/re-attach, Linux created a new USB generation but
the camera retained a vendor-mode owner. CloseSession, libusb reset, direct
reopen, a new PTP session id, vendor disable and the standard PTP USB reset
request could not recover it: OpenSession/GetDeviceInfo passed, while every
`0x9001` vendor transition returned `0x2002`. This separate direct defect is
tracked in libgphoto2 issue #83. IMAGE Transmitter evidence requires fail-closed
handling for a failed vendor transition; no guessed recovery opcode was added.

## Source and review

- Patcher commit: `073f471` (PR #138)
- Registry commit: `b4d2300`
- libgphoto2: `ab0de090c63e707afccc6d425c1c596799952341`
- Build id: `6.0.0.54.24-o-v12o-direct-capture`

All five runnable Stage-2 host tests pass. The host lacked
`arm-linux-gnueabi-gcc`; the canonical container build subsequently compiled
the ARM loader and passed its architecture/ABI/symbol gates.

## Artifact and gates

- Registry id: `o-v12o-direct-capture-20260924`
- PrivateResearch commit: `9f44f54`
- zip MD5: `ec140c6041a939555fe562a238084721`
- zip SHA-256:
  `3b5ba628ef6e4a48b37958462aee512c51342e698df4b79e16d5746d87d3b5cd`
- appfs MD5: `ab13820a561201500ef7b8162e782afc`

The clean matched-stack build passed ARM ABI, glibc ceiling, symbol resolution,
wrapper, appfs content, six-entry firmware manifest and package-layout gates.
The pre-release gate reported 3 PASS, 0 FAIL, 1 stock-path SKIP; the skipped
manifest prerequisite was independently passed by the build and private-upload
re-verification.

## Deployment status

Installation in progress. At 2026-09-24 the registered extracted `FwPkt` tree
was tar-streamed to the empty `/app/sd/FwPkt` target while the 9090 keepalive
remained active. Independent remote `du` checks showed monotonic growth and the
stream exited zero. On-card MD5 verification matched all six `firmwareInfo`
entries exactly:

- config `1905e2d041be62b679f7dc6c64ab9d3a`;
- uImage `5f6a0c1861a254371c4a956b57f26685`;
- rootfs `778b27bcade9ddc6ea4a7cb45254c551`;
- appfs `ab13820a561201500ef7b8162e782afc`;
- polaris403 `4facafa7d29c1e6c2a125b8309c9b901`;
- polaris413 `c0299d06a15f5c2fbecb9a6db76a29c5`.

The staged FwVer was `6.0.0.54.24-o-v12o-direct-capture`. After stopping the
keepalive, `sync; /sbin/reboot` produced a proven SSH drop and the normal
watcher consumed `/app/sd/FwPkt`. Post-boot identity and runtime proof passed:

- active SSID/BSSID/interface: `polaris_d13e86`, `48:E7:DA:D4:B5:73`,
  `wlp8s0`; route source `192.168.0.4`;
- `/app/FwVer`: `6.0.0.54.24-o-v12o-direct-capture`;
- installed provenance: libgphoto2
  `ab0de090c63e707afccc6d425c1c596799952341`, patcher
  `073f4718eaaded48eb9d1ebcc695d0bbd97554a3`;
- stage2/legacy core MD5 pair both `5973e8c8999b1f4f01be70a9cafdb7ba`;
- stage2/legacy port MD5 pair both `ad50e83594397aef48b63ed2375890cc`;
- stage2/legacy `ptp2.so` both `ad48c745594640a35e09a398fe2572b5`;
- stage2/legacy `usb1.so` both `4423bba29bf8c5d899598841ec3e6310`;
- PID 250 maps the stage2 core, port and `libpolaris_stage2.so`; it remained
  unchanged across four samples spanning 31 seconds;
- one polestar and one pgphoto process; listeners 22/8080/9090 present;
- no `capture-shim: gp_camera_capture`, SIGSEGV, `No iolibs`, or `state:-2`
  signature in Clog.

The camera is still attached to the PC, so the camlib/iolib are not expected in
the daemon maps yet. Physical capture qualification remains pending camera
power-cycle and attachment to Polaris.

### First attached-camera canary

The K-3 III was subsequently power-cycled and attached to Polaris as USB
`25fb:0189`. Code 286 reported the expected model and `state:1`, but incorrectly
reported `photoFormat:2`. The daemon's authoritative `imageformat` widget read
showed `Current: RAW+JPEG` and `numOfCaptureImage 2`.

The fail-closed two-shot canary stopped after its first shutter. Exposure
initiation passed (`state:1`) and the camera emitted the first object event,
`/IMGP3609.JPG` (`state:4`). Transfer then failed before any 773 file event:

```
gp_filesystem_get_file from sd //IMGP3609.JPG ret = -108
captureImage ret -108
```

The client consequently received lifecycle `[1, 4, -108]`; it did not issue a
second shutter. pgphoto PID remained 3840 across the attempt. This proves the
o-v12n pre-dispatch SIGSEGV is removed and exposes the next first divergence:
the legacy daemon supplies folder `sd` and doubled-slash filename to the
filesystem transfer for the first RAW+JPEG object. No timeout workaround is
justified. Raw evidence is under this directory's `raw/` subtree.

The working wake handoff starts NetworkManager's
saved-profile association first, then sends the bare GATT connect while that
association is already pending. This produced `ServicesResolved: yes` and the
Wi-Fi activation completed even though BlueZ later reported no BR/EDR profile.
Identity was then proven independently:

- SSID `polaris_d13e86`, BSSID `48:E7:DA:D4:B5:73`, interface `wlp8s0`;
- `192.168.0.1 dev wlp8s0 src 192.168.0.4`;
- installed FwVer `6.0.0.54.23-o-v12n-companion-ownership`;
- installed provenance `ab0de090c` / patcher `7bcbc39`;
- one polestar PID and one pgphoto PID; listeners 22/8080/9090 present.

This corrects the earlier failed sequencing: beginning Wi-Fi association eight
seconds after the short wake connection was too late. No characteristic write
or BLE pairing was required.

Next: compare this exact path construction with the last working packaged
capture and with direct libgphoto2 at the installed SHA; correct the owning
source boundary, rebuild/install canonically, then restart the matrix. Do not
issue another shutter on o-v12o until the `sd //IMGP3609.JPG` divergence is
understood.

### Successor fix and artifact

The first divergence is now understood. Reconciliation initially required
zero companions and only increased that obligation from post-primary
GetAllConditions samples. The same required pre-shutter readiness sample had
already reported RAW+JPEG, but that value could disappear/change after primary
finalization. The loop therefore returned with zero extras, leaving Benro's
legacy `sd` listing empty.

libgphoto2 commit [`d8c0c0026`](https://github.com/ian-morgan99/libgphoto2/commit/d8c0c0026bfcb6ad3f53b828eb4961d73ca4171a)
preserves the output obligation from the existing pre-shutter readiness sample
and passes it as reconciliation's minimum count. Later samples may increase,
but never erase, that count. This is camera-mode-driven one-versus-two-object
waiting, not a fixed delay. Focused Pentax tests and host `ptp2.so` compile
passed.

Successor registry id: `o-v12p-mode-contract-20260924`:

- build id `6.0.0.54.25-o-v12p-mode-contract`;
- zip MD5 `dd5c0615e36f1f7c92773936422dcddf`;
- zip SHA-256
  `7223f7b4cf3abd53ed0da98abddb5d15a9b6d38b6f0371e8ded1bb141fda428a`;
- appfs MD5 `d7c7162c4ae0913c29f67ce21a1a0081`;
- PrivateResearch commit `161aaf5`.

The clean ARM matched-stack build passed architecture/ABI/symbol, wrapper,
appfs, six-entry manifest and package gates. The pre-release gate reported
3 PASS, 0 FAIL, 1 stock-path SKIP; private upload independently passed package
structure and all six manifest hashes.

o-v12p was then tar-streamed as the extracted registered tree to the empty
`/app/sd/FwPkt` target. On-device MD5 verification matched all six
`firmwareInfo` values: config `1905e2d041be62b679f7dc6c64ab9d3a`, uImage
`5f6a0c1861a254371c4a956b57f26685`, rootfs
`778b27bcade9ddc6ea4a7cb45254c551`, appfs
`d7c7162c4ae0913c29f67ce21a1a0081`, polaris403
`4facafa7d29c1e6c2a125b8309c9b901`, and polaris413
`c0299d06a15f5c2fbecb9a6db76a29c5`. Staged FwVer is
`6.0.0.54.25-o-v12p-mode-contract`. Reboot/install and post-boot proof remain
pending at this checkpoint.

## Required physical matrix

1. JPEG-only: three captures.
2. RAW-only: three captures.
3. RAW+JPEG: two captures, both objects per exposure.
4. Pixel Shift RAW+JPEG: four physical actuations, one DNG/JPEG composite pair,
   followed by another valid shutter.
5. Preview demand/stop/restore, stable pgphoto PID/session and stable USB.
6. Camera power-generation recovery with capture-mode restoration.
7. Surprise USB detach: invalidate the old generation and fail visibly without
   restart churn; automatic vendor recovery remains blocked by libgphoto2 #83.

K-1 II and Canon R5 Mark II remain unqualified until physically rerun.
