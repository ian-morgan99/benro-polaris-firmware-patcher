# o-v13c physical canary: capture succeeds, retrieval fails

Date: 2026-09-26

## Identity

- Polaris AP/BSSID: `polaris_d13e86` / `48:E7:DA:D4:B5:73`
- Route: `192.168.0.1 dev wlp8s0 src 192.168.0.4`
- Firmware: `6.0.0.54.27-o-v13c-boundary-trace`
- libgphoto2: `4868d3649b4a363679ea7ed9d695fbd153063827`
- patcher: `8b075f50d36f6b6f0ba3c0815b7c8478fdbc60f4`
- camera: Pentax K-3 III, USB `25fb:0189`
- Stage-2 and stock `libgphoto2.so.6` MD5:
  `390194dd561de4bde4eb7ed701401507`

## Gate

Command:

```text
./tests/run_prerelease_gate.sh --canary --expected-files 1
```

Result: 36 deterministic checks passed and the camera-ready probe passed. The
physical canary failed, so the overall gate was RED. No second shutter was sent
after that failure during this run.

## First divergent boundary

The capture itself completed successfully:

1. code 264 entered state 1;
2. Pentax preconditions passed;
3. `InitiateCapture` returned PTP OK `0x2001`;
4. the camera produced `IMGP3634.JPG`;
5. code 264 emitted state 4;
6. real `gp_camera_capture()` returned `0`.

The subsequent Benro retrieval logged
`gp_filesystem_get_file from sd //IMGP3634.JPG ret = -108`, then emitted
terminal state `-108`. There was no 773 publication event and no
`/app/sd/normal/SP_0100.jpg`.

This reproduces the previously unclosed o-v12o virtual-root handoff defect on
the current convergence candidate. It is not an `InitiateCapture`, exposure,
candidate-transfer, or next-shutter-admission failure. The next discriminator
belongs at the Stage-2/pgphoto boundary: correlate process/session/filesystem
identity between `gp_camera_capture` publication and the later
`gp_filesystem_get_file` call.

A read-only, fresh-session card listing after the failure found no
`IMGP3634.JPG` in `/` or `/store_00010001`. The transferred candidate therefore
exists only in the publishing libgphoto2 filesystem/cache context; a later
session cannot recover it as a physical card object.

## Evidence hashes

- `canary-shot.txt`:
  `2ad85a594af7b2d94501450f054c18350020714c2c9b903ebc9059ba400ca129`
- `Clog-capture-window.txt`:
  `500c038e9a73ab9fc337ac1500e2576bb158c2a8898b295d4e9ebcd061c4d260`
- `Mlog-capture-window.txt`:
  `07b14e2275ea3ceeff4d75a6e8f54774c1514519738c7892a1f8851b0e717536`

After evidence collection the Polaris AP and Bluetooth radio disappeared. A
subsequent direct exact-stack capture command did not start because SSH was
already unavailable; it sent no shutter.
