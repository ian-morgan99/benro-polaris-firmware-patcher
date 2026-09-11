# o-v9e K-1 II qualification baseline — 2026-09-11

## Provenance and identity

- Firmware: `o-v9e-focus-idle-wait`
- libgphoto2: `90de508a5441cb7e2b1b02d601b15a7547d7bcee`
- Camera: USB `25fb:0183`; pgphoto identified `PENTAX K-1 Mark II`
- Hot-swap from K-3 III completed without a pgphoto/polestar restart.
- Ports 22, 8080 and 9090 remained open throughout.

## Coverage

| Feature | Result | Evidence |
|---|---|---|
| Camera discovery/config tree | PASS with severe latency/noise | Model and configuration tree loaded, but repeated generic single-config calls return `-2` |
| Live-view startup | DEGRADED PASS | About 30 seconds of failures before PC-LV started; then complete ~28 KiB JPEGs arrived |
| Live-view continuity around focus | PASS | Complete JPEG received after each focus attempt |
| Manual focus Near | FAIL physical application | Correct old-family `0x9016`, amount 5, direction 0, raw `0x2001`; operator saw no movement |
| Manual focus Far | FAIL physical application | Correct old-family `0x9016`, amount 5, direction 1, raw `0x2001`; controls reported ineffective; dispatch delayed ~11 s |
| Other camera controls | FAIL/UNQUALIFIED | Operator reports camera controls do not seem to work; no further writes issued after common failure emerged |
| Runtime stability | PASS | K-1 II remained enumerated; same processes alive; ports healthy |
| Capture | NOT TESTED in this round | Stop write testing until control-plane contention is isolated |

## Decisive log sequence

Live view first produced repeated failures approximately every 4–6 seconds:

```text
gp_camera_get_single_config ... failed: -2
...
Pentax preview stage read-PC-LV returned 0x02ff.
Pentax preview stage start-PC-LV returned 0x2001.
Pentax preview stage get-frame returned 0x2001 (27908 bytes, 14 attempts, 441 ms).
Pentax preview stage get-frame returned 0x2001 (27921 bytes, 1 attempts, 2 ms).
```

Near focus while the preview connection remained established:

```text
Pentax manual focus drive (old): amount=5, direction=0 (Near), opcode=0x9016.
Pentax manual focus drive (old) returned response 0x2001.
updateCameraManualFocus focus:2 ret:0
```

The operator observed no movement.

Far focus began at 15:15:12 but generic-config failures continued while pgphoto
retried the integration call. The actual operation did not complete until
15:15:23:

```text
gp_camera_get_single_config ... failed: -2
Pentax manual focus drive (old): amount=5, direction=1 (Far), opcode=0x9016.
Pentax manual focus drive (old) returned response 0x2001.
updateCameraManualFocus focus:-2 ret:0
setFocusMode ... value:-2 ret 0
Pentax preview stage get-frame returned 0x2001 (29257 bytes, 1 attempts, 2 ms).
```

## Interpretation and next boundary

v9e improves dispatch reliability but does not make K-1 II writes observably
apply. A raw `0x2001` is only an acknowledgement. The common runtime symptom is
pgphoto's periodic generic-config polling repeatedly returning `-2` and
contending with writes. Do not increase focus displacement, repeat completed
lens operations, or mark a control PASS from `ret:0`.

Before changing libgphoto2, reproduce from a clean exact SHA with K-1 II
attached directly to the PC. If direct near/far and restored setting writes
apply, ownership is pgphoto/Polaris scheduling and the fix must serialize or
pause background config polling around a write. If the same exact lower-level
operation acknowledges without application directly, fix the model-specific
libgphoto2 path and add a hardware-backed regression there.

## Regression requirements

- Preserve eventual K-1 II PC-LV JPEG delivery; require a bounded startup time.
- No concurrent generic-config poll during a write transaction.
- Near and Far each dispatch exactly once and require operator-visible movement;
  raw `0x2001` alone is insufficient.
- One advertised ISO, shutter and aperture value must apply, be verified through
  fresh conditions, and be restored exactly.
- Preserve K-3 III v9e live-view/manual-focus PASS behavior.
