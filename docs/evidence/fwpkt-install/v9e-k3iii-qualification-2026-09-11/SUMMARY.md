# o-v9e K-3 III qualification evidence — 2026-09-11

## Provenance

- Firmware: `o-v9e-focus-idle-wait`
- Camera: Pentax K-3 Mark III, USB `25fb:0189`
- libgphoto2: `90de508a5441cb7e2b1b02d601b15a7547d7bcee`
- ZIP MD5: `89e3714ee5f650c5d2463be11996b0ca`
- appfs MD5: `3434cd42b3d092552c9599ff338fffc3`
- On-device source logs at the end of evidence capture:
  - `/app/sd/system/log/Clog_000016.log`: 3,952,554 bytes, MD5
    `b5dbc625a69a633e3077926981e6da2e`
  - `/app/sd/system/log/Mlog_000016.log`: 497,241 bytes, MD5
    `be2d280c492671627546b81361620e77`

The device SSH server rejected SCP subsystem transfer (`scp: Connection
closed`), so the immutable path, size, and hash above identify the retained SD
logs. The exact decisive lines are reproduced below.

## PASS anchors that regressions must preserve

### Live view and manual focus

- Held port-8080 stream: 3,106,590 bytes containing 44 complete JPEG SOI/EOI
  pairs.
- Focus was issued while the preview TCP connection remained established.
- libgphoto2 logged `Pentax manual focus drive (new) returned response 0x2001`.
- Valid preview frames continued immediately after the focus operation.
- Operator confirmation: K-3 III **manual** focus controls work from the app.
- Post-test: same pgphoto/polestar processes; ports 22, 8080 and 9090 open;
  no fatal, duplicate-launch or `tdata_psh_info` signature.

Regression requirement: a capture/candidate fix must not change the model-aware
manual-focus opcode/sign/magnitude, must not retry a completed movement, and
must retain valid JPEG cadence around focus.

### Successful still capture at 14:57

Input and state sequence:

```text
14:57:31.836 code[264] state:1 ... path:/app/sd/normal/SP_0013.jpg
14:57:33.268 numOfCaptureImage 2
14:57:33.298 will CAPTURE_IMAGE
14:57:35.450 captureImageEvent ... Path:IMGP3472.JPG
14:57:35.793 ARG_CAPTURE_IMAGE 0
14:57:35.894 capture end -2625 ms
14:57:35.954 gp_filesystem_get_file /IMGP3472.JPG ret = 0
14:57:36.014 gp_file_get_data_and_size IMGP3472.JPG ret = 0
14:57:36.018 gp_camera_file_delete IMGP3472.JPG ret = 0
14:57:36.023 captureImage ret 0 p: ./IMGP3472.JPG
14:57:36.024 code[264] state:2 /app/sd/normal/SP_0013.jpg
14:57:36.138 savePhotoToAblum ... SP_0013.jpg ret 0
14:57:36.139 code[264] state:3 /app/sd/normal/SP_0013.jpg
14:57:36.144 code[264] state:5
```

Output proof: `/app/sd/normal/SP_0013.jpg` exists, is 14,076,599 bytes, and has
MD5 `8fb0f2ac1adb79d3a29955579844a497`.

Regression requirement: retain capture return 0, successful transfer/delete,
non-empty intended-format output, and terminal protocol states 2/3/5.

## FAIL anchors the fixes must change

### Second dual-format candidate blocks the next shutter at 15:02

The prior successful exposure reported `numOfCaptureImage 2`, but the current
Pentax capture path transfers/finalizes only one candidate. Five minutes later:

```text
15:02:32.061 code[264] state:1 ... path:/app/sd/normal/SP_0014.jpg
15:02:33.428 numOfCaptureImage 2
15:02:33.459 will CAPTURE_IMAGE
A previous capture's transfer candidate (1) is still pending; resolve it before capturing.
ERROR: Could not capture image.
15:02:33.465 ARG_CAPTURE_IMAGE -110
15:02:33.467 captureImage ret -110
15:02:33.467 code[264] state:-110 ...
Mlog maps this to app state:-1005
```

`/app/sd/normal/SP_0014.jpg` does not exist. The second request was refused
before firing, so this instance is not a slow current transfer and must not be
fixed by merely increasing an app timeout. See libgphoto2 #73.

Regression requirement: model a one-candidate success and a two-candidate
success; reconcile only extra candidates belonging to the same initiated
exposure with strict count/time bounds. Preserve refusal of an unknown stale
candidate discovered at the beginning of a later request/session.

### Tap autofocus remains ineffective

Manual focus PASS does not qualify autofocus. The log recorded separate
`updateCameraAutoFocus enable:1 ret:-1` and `enable:0 ret:-1` attempts. IMAGE
Transmitter 2 establishes the intended tap flow as bounded `0xd036` AF-position
SET followed by autofocus-only Pentax `0x9011` with focus mode 1. See
libgphoto2 #57.

Regression requirement: positioning and focus actuation are separate asserts;
the test must prove the selected point and exactly one AF-only operation, with
continued preview and no still-image transfer candidate.

## UI observation

The operator confirmed pinch-to-zoom works in OpenPolaris. Treat this as a UI
gesture PASS only until telemetry proves whether it is display scaling or
camera-side Pentax live-view zoom (`0xd037`).
