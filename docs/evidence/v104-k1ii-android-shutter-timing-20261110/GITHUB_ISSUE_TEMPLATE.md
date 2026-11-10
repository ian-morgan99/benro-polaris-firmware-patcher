# GitHub Issue: v104 K1 II Android — shutter release timing wrong (0.4s shutter took ~14.6s)

**Title:** [v104] K1 II Android: shutter release timing wrong — 0.4s exposure took ~14.6s, duration reported as 0

**Labels:** bug, v104, k1-ii, pentax, android, shutter-timing

**Device:** Benro Polaris, FwVer:6.0.0.54.104, date:2026.11.10, build_id=v104  
**Camera:** Pentax K-1 II  
**Client:** Android phone (Benro Connect app)  
**Logs:** `docs/evidence/v104-k1ii-android-shutter-timing-20261110/`

---

## Summary

On v104 with an Android client, setting a 0.4s shutter speed and capturing resulted in a capture that took ~14.6 seconds total, with the camera reporting `duration:0`. The shutter was NOT open for the expected 0.4s — the capture duration was massively longer than requested.

## Observed Behavior

### Shutter timing — WRONG

From `Clog-shutter-timing-3.txt`:

```
[09:55:59:749] updateCaptureInfo: ----shutter speed 0.400000     <- user set 0.4s (4/10)
[09:55:59:749] current_shutter: configInfo:s:4/10; ret:0 sValue 4/10
[09:55:59:753] numOfCaptureImage: 2                              <- RAW+JPEG
[09:55:59:753] capture_image: ----capture
[09:55:59:783] capture_image: ---- will CAPTURE_IMAGE            <- capture command sent
[libgphoto2] gp_camera_capture: enter camera=0x3851a8 type=0 ...
[pentax] capture=3 boundary=camlib-enter transfer=0 recovery=1 output_pending=0
[pentax] capture=3 boundary=preconditions-enter
[pentax] capture=3 boundary=preconditions-return ptp=0x2001 size=568
[pentax] capture=3 boundary=initiate-enter focus=2 companions=1
[pentax] capture=3 boundary=initiate-return ptp=0x2001
New file is in location /K1II8723.JPG on the camera
--- new file name K1II8723.JPG
[09:56:08:306] captureImageEvent:0 Path:K1II8723.JPG            <- file created ~8.5s later
[09:56:08:306] SP_sendMsg success code:264 val[state:4;K1II8723.JPG]
[09:56:14:412] capture end -14660 ms                             <- capture end ~14.6s after command
[09:56:14:438] captureImage ret 0 p: ./K1II8723.JPG
```

### Timing analysis

| Event | Timestamp | Elapsed from capture command |
|-------|-----------|------------------------------|
| Capture command sent | 09:55:59:783 | 0s |
| File created on camera | 09:56:08:306 | ~8.5s |
| Capture end | 09:56:14:412 | ~14.6s |

**Expected:** 0.4s exposure → capture should complete in well under 1 second  
**Actual:** ~14.6 seconds total — 36x longer than expected

### Camera reports duration:0

From `Mlog-shutter-timing-3.txt`:

```
[09:56:14:463] code[773] val[type:1;path:/app/sd/normal/SP_0585.jpg;size:1806007;cTime:2026-11-10 09:56:14;duration:0;]
```

The `duration:0` field confirms the camera/app did not record a meaningful exposure duration.

### Shutter speed was correctly set

```
[09:55:59:749] updateCaptureInfo: ----shutter speed 0.400000
[09:55:59:749] current_shutter: configInfo:s:4/10; ret:0 sValue 4/10
[09:55:59:749] SP_sendMsg success code:268 val[RD:0;V:19;R:...00-00,;]
```

The shutter speed parameter was correctly set to 4/10 (0.4s), but the actual exposure duration was not 0.4s.

---

## Pattern Summary

This is the same root cause as the shutter speed not sticking issue (issue #18): the shutter value reads back correctly (`u32ShutterUs 400000` = 0.4s) but the actual capture does not use that duration. The PTP `SetDevicePropValue` for shutter speed may be accepted by the camera but not actually applied to the exposure.

---

## Files

All logs saved under `docs/evidence/v104-k1ii-android-shutter-timing-20261110/`:

| File | Size | Description |
|------|------|-------------|
| `Mlog-shutter-timing-3.txt` | 2,648 bytes | Mlog with capture event (duration:0) |
| `Clog-shutter-timing-3.txt` | 9,145 bytes | Clog with full capture timing sequence |
| `Mlog-shutter-timing-2.txt` | 14,198 bytes | Earlier Mlog (shutter parameter change) |
| `Clog-shutter-timing-2.txt` | 28,908 bytes | Earlier Clog (shutter parameter change) |
| `Mlog-shutter-timing.txt` | 7,535 bytes | Initial Mlog pull |
| `Clog-shutter-timing.txt` | 13,429 bytes | Initial Clog pull |

Key log lines:
- `Clog-shutter-timing-3.txt` lines 67-95: shutter set to 0.4s, capture command, file created ~8.5s later, capture end ~14.6s later
- `Mlog-shutter-timing-3.txt` line 14: `duration:0` in the file event

---

## Steps to Reproduce (Android)

1. Connect K1 II to Polaris running v104 (FwVer:6.0.0.54.104)
2. Set shutter speed to 0.4s (4/10)
3. Capture an image
4. Observe: capture takes ~14.6s total, not ~0.4s
5. Observe: `duration:0` reported in the file event

## Expected Behavior

- 0.4s shutter speed → capture completes in well under 1 second
- `duration` field reflects the actual exposure time

## Actual Behavior

- 0.4s shutter speed → capture takes ~14.6 seconds total
- `duration:0` reported

---

**Note:** This is v104 test evidence from Android client testing. The device is running build_id=v104, display_fwver=6.0.0.54.104, libgphoto2 commit=806c3bda62d6c0c23ca7a3091fb42f3d7894172b, patcher commit=1e88637cf61d152f94e23f6e139adec4b9fa80c2.