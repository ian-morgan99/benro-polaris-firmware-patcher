# o-v12n clean RAW-only first-shot failure — 2026-09-24

## Result

**FAIL.** With no persistent competing 8080/9090 clients and preview already
OFF, one K-3 III RAW-only capture entered the Stage-2 capture shim and crashed
before the real `gp_camera_capture()` returned. No second shutter was sent.

## Preconditions

- FwVer: `6.0.0.54.23-o-v12n-companion-ownership`
- libgphoto2 provenance: `ab0de090c63e707afccc6d425c1c596799952341`
- K-3 III: USB `25fb:0189`, device 010, serial 8093033
- pgphoto PID before capture: 19749
- camera-info: `state:1`
- preview query: `state:0`
- camera physically set to RAW-only; pgphoto's imageformat widget independently
  logged `Current: RAW`
- camera-info still reported `photoFormat:2`; that field is not a reliable
  RAW+JPEG discriminator on this path
- zero persistent 8080/9090 clients; only the bounded canary plus a low-rate
  code-266 keepalive

## First divergence

At device time 10:07:35:

```
recv code[264] state:1 ... /SP_0082.jpg
Image Format Current: RAW
capture_image: will CAPTURE_IMAGE
[stage2] capture[1]: enter type=0 mono=35759
[stage2] *** CRASH sig=11 (SIGSEGV) si_addr=0x00004e20 pc=0x00004e20
[stage2]   slot region [0x30000000,0x30000100) si_addr is NOT in the slot region
[stage2]   pc classify: not null, not the stub, not a current slot target
[stage2]   last checkpoint reached: slots filled
```

There is no `real gp_camera_capture returned`, Pentax InitiateCapture,
candidate, transfer or reconciliation record. The physical exposure was not
proven. The client received only `state:1` and timed out after 180 seconds.

## Consequences

- At 10:07:57, 22 seconds after capture entry, Mlog records removal of wlan0,
  phy3, the Broadcom SDIO functions and `bcmdhd`.
- At 10:08:04 and thereafter, camera-info reports
  `manufacturer:none;model:none;state:-10`.
- The AP and SSH disappeared despite the 9090 keepalive.
- Turning the camera off reduced load; a later Bluetooth wake restored the AP.
- At evidence collection, polestar PID 251 remained, pgphoto had restarted as
  PID 22662, and the powered-off/transitioning camera still appeared on USB.

## Ownership and next action

This fails before the Pentax capture lifecycle implemented by libgphoto2 can
run. The invalid low program counter and repeated Stage-2 loader initialization
make the Stage-2 callback/slot/ABI boundary the first owning layer. Do not
change Pentax readiness predicates, output counting, or timeouts for this
failure.

Next work must reproduce or instrument the Stage-2 `gp_camera_capture`
pass-through target immediately before invocation, including the cached target,
slot value, process/module maps and call ABI. Preserve the collision guard and
all launch-lock/package assertions. Any fix must be built and installed through
the canonical registered FwPkt path before another shutter.

## Preserved files

The local evidence directory contains current Clog/Mlog, the active persistent
SD Clog/Mlog/error set, post-recovery device state and full dmesg. Raw logs are
kept out of the public commit; this summary and hashes are the public evidence
index.

SHA-256:

- `Clog-current.txt`: `78cb4d05993fbc95d805d07d4a91bcbc16e2df794e54c8a2060a29f443dff446`
- `Clog_000140.log`: `4c76cf31ebd038e1045374aa47b071ea5afbd9bfcb667e24524729e11a341e44`
- `Mlog-current.txt`: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- `Mlog_000140.log`: `f0a2a12d9a2575322dfdabcbcd8ed1df9c541f38003a6037e69333195a233945`
- `device-state-after-recovery.txt`: `8082b96e5740376c6e9e850caa54bd9a70aedbd8e449d7aa3635e1f51f154123`
- `dmesg-after-recovery.txt`: `c57fc2e03fda2bc1e9273c72f17320a7f435a90296a2527fedcb44186f1ac0f2`
- `error_000140.log`: `cc07035e2a86ce8cb5fdf232fb745c1c4748e325ab02e506e53f623cfca35877`
