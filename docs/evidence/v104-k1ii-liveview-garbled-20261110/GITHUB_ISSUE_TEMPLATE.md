# GitHub Issue: v104 K1 II — Exposure parameter changes fail and liveview cuts out

**Title:** [v104] K1 II: shutter speed/ISO/aperture changes fail on first attempt, liveview cuts out repeatedly

**Labels:** bug, v104, k1-ii, pentax, liveview, exposure

**Device:** Benro Polaris, FwVer:6.0.0.54.104, date:2026.11.10, build_id=v104  
**Camera:** Pentax K-1 II  
**Logs:** `docs/evidence/v104-k1ii-liveview-garbled-20261110/`

---

## Summary

On v104, changing exposure parameters (shutter speed, ISO, aperture) on a K1 II causes the first attempt to fail with PTP error -2110, and liveview repeatedly cuts out (drops and reconnects). Retrying the same parameter change usually succeeds, but shutter speed reads back as 0 despite `SP_SET_SHUTTER OK`.

## Observed Behavior

### Test 1: Turn on K1 II on v104
- Liveview is garbled / cuts out repeatedly

### Test 2: Change shutter speed and F-stop
- **F-stop change:** sticks (f/11 confirmed)
- **Shutter speed change:** does NOT stick — reads back as 0 despite `SP_SET_SHUTTER OK`
- Liveview keeps cutting out and coming back again

### Test 3: ISO change did not stick at first
- First ISO change fails with `SP_SET_ISO FAIL` (ret -2110)
- Second ISO change succeeds (`SP_SET_ISO OK`, ISO 6400 confirmed)
- Liveview cuts out after each parameter change

---

## Log Evidence

### Shutter speed — does not stick

From `Clog-current-2.txt` / `Mlog-current-2.txt`:

```
[09:44:56:167] Initial shutter: index 14 = 13/10 (1.3s), u32ShutterUs 1300000
[09:44:57:222] App sends code:261 val:s:12                          <- user changes to 1/2s
[09:44:57:222] SP_sendMsg success code:261 val:s:12
[09:44:57:847] camera_control_handler command 31 info shutterspeed=12 ret 0
[09:44:57:847] updateCaptureInfo: ----shutter speed 0.000000        <- BUT reads back as 0!
[09:44:57:847] SP_GetCameraShutter: u32ShutterUs 0                  <- camera reports 0
[09:44:57:847] SP_GetCameraShutter: u32ShutterIndex 12              <- index updated but value is 0
[09:44:57:847] SP_SET_SHUTTER OK                                    <- reports success despite 0 value
```

### ISO — first attempt fails, second succeeds

From `Clog-current-3.txt` / `Mlog-current-3.txt`:

```
[09:45:49:106] App sends code:258 val:iso:2                          <- user changes ISO to 400
[09:45:50:137] setCameraConfig configType 0 value: 2 ret -2110       <- FAILS
[09:45:50:138] ERROR: SP_SET_ISO FAIL
[09:45:50:138] SP_sendMsg success code:258 val:iso:2;ret:-2110

[09:46:13:478] App sends code:258 val:iso:6                          <- retry: ISO to 6400
[09:46:14:969] setCameraConfig configType 0 value: 6 ret 0           <- SUCCEEDS
[09:46:14:970] SP_SET_ISO OK
[09:46:14:970] SP_GetCameraIso: ISO 6400                             <- confirmed applied
```

### Aperture — works on retry

From `Clog-current-2.txt` / `Mlog-current-2.txt`:

```
[09:44:46:853] setCameraConfig configType 7 value: 19 ret -2110      <- first attempt fails
[09:44:47:896] setCameraConfig configType 8 value: 19 ret -2110      <- second attempt fails
[09:44:47:897] ERROR: SP_SET_FNUM FAIL
[09:44:49:423] App sends code:276 val:fNum:18                          <- retry: f/11
[09:44:50:522] camera_set_aperture configType 7 value: 18 ret 0      <- succeeds
[09:44:50:522] SP_SET_FNUM OK
[09:44:57:282] Aperture widget: Current: f/11                        <- sticks
```

### Liveview cutting out — confirmed

From `Clog-current-2.txt` / `Clog-current-3.txt`:

```
[09:45:03:212] camera_connected_to_app connected:1
[09:45:08:662] camera_connected_to_app connected:1
Pentax preview stage get-frame returned 0x2001 (21354 bytes)
----handle_sign_pipe on client close..........5
----handle_sign_pipe on client close..........4
[09:45:15:911] camera_connected_to_app connected:1
Pentax preview stage get-frame returned 0x2001 (20605 bytes)
----handle_sign_pipe on client close..........4
----handle_sign_pipe on client close..........3
[09:45:26:255] camera_connected_to_app connected:1
Pentax preview stage get-frame returned 0x2001 (20655 bytes)
----handle_sign_pipe on client close..........3
[09:45:36:741] camera_connected_to_app connected:1
```

The repeated `camera_connected_to_app connected:1` messages with `handle_sign_pipe on client close` countdowns between them show the preview connection repeatedly dropping and re-establishing.

---

## Root Cause Hypothesis

The camera's PTP property set is not being applied reliably on the first attempt after a liveview session starts. The `-2110` error suggests a PTP operation failure (likely device busy or invalid state during liveview). The shutter speed reading back as 0 despite `SP_SET_SHUTTER OK` indicates the value isn't actually reaching the camera or is being rejected silently.

All three exposure parameters exhibit the same pattern:

| Parameter | First attempt | Second attempt | Sticks? |
|-----------|--------------|----------------|---------|
| Aperture (fNum) | ret -2110 FAIL | ret 0 OK | Yes (f/11) |
| Shutter speed (s:12) | ret 0 OK | reads back as 0 | **No** |
| ISO (iso:2→iso:6) | ret -2110 FAIL | ret 0 OK | Yes (6400) |

---

## Files

All logs saved under `docs/evidence/v104-k1ii-liveview-garbled-20261110/`:

| File | Size | Description |
|------|------|-------------|
| `meta.txt` | 810 bytes | Device identity, provenance, processes, mounts |
| `Mlog.txt` | 9,736 bytes | Current Mlog (first pull) |
| `Clog.txt` | 2,635 bytes | Current Clog (first pull) |
| `Mlog-current.txt` | 15,917 bytes | Fresh Mlog after shutter/F-stop changes |
| `Clog-current.txt` | 29,361 bytes | Fresh Clog after shutter/F-stop changes |
| `Mlog-current-2.txt` | 15,917 bytes | Fresh Mlog after shutter/F-stop changes (2nd pull) |
| `Clog-current-2.txt` | 29,605 bytes | Fresh Clog after shutter/F-stop changes (2nd pull) |
| `Mlog-current-3.txt` | 34,385 bytes | Fresh Mlog after ISO change |
| `Clog-current-3.txt` | 65,301 bytes | Fresh Clog after ISO change |
| `Mlog_000377.log` | 1,841,909 bytes | Rotated SD Mlog (Nov 10 05:32) |
| `Mlog_000378.log` | 272,476 bytes | Rotated SD Mlog (Nov 10 09:20) |
| `Mlog_000379.log` | 328,354 bytes | Rotated SD Mlog (Nov 10 09:37) |
| `Clog_000377.log` | 1,835,939 bytes | Rotated SD Clog (Nov 10 05:32) |
| `Clog_000378.log` | 27,812 bytes | Rotated SD Clog (Nov 10 09:20) |
| `Clog_000379.log` | 13,646 bytes | Rotated SD Clog (Nov 10 09:37) |
| `error_000378.log` | 524 bytes | Rotated SD error log |
| `error_000379.log` | 70 bytes | Rotated SD error log |
| `sd-root-listing.txt` | 2,395 bytes | SD card root directory listing |

---

## Steps to Reproduce

1. Connect K1 II to Polaris running v104 (FwVer:6.0.0.54.104)
2. Open liveview in Benro Connect
3. Change shutter speed → observe liveview cutting out, shutter reads back as 0
4. Change ISO → observe first attempt fails with -2110/SP_SET_ISO FAIL, liveview cuts out
5. Change aperture → observe first attempt fails with -2110/SP_SET_FNUM FAIL, retry succeeds

## Expected Behavior

- Parameter changes apply on first attempt
- Shutter speed reads back the value that was set
- Liveview remains stable during parameter changes

## Actual Behavior

- First parameter change after connecting often fails with -2110
- Liveview repeatedly drops and reconnects (`camera_connected_to_app connected:1` loop)
- Shutter speed reads back as 0 despite `SP_SET_SHUTTER OK`

---

**Note:** This is v104 test evidence. The device is running build_id=v104, display_fwver=6.0.0.54.104, libgphoto2 commit=806c3bda62d6c0c23ca7a3091fb42f3d7894172b, patcher commit=1e88637cf61d152f94e23f6e139adec4b9fa80c2.