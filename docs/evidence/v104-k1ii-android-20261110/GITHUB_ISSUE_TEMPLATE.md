# GitHub Issue: v104 K1 II — Android: exposure parameter changes fail on first attempt, shutter reads back as 0

**Title:** [v104] K1 II Android: shutter/ISO/EV changes fail on first attempt (-2110), shutter reads back as 0 despite SP_SET_SHUTTER OK

**Labels:** bug, v104, k1-ii, pentax, android

**Device:** Benro Polaris, FwVer:6.0.0.54.104, date:2026.11.10, build_id=v104  
**Camera:** Pentax K-1 II  
**Client:** Android phone (Benro Connect app)  
**Logs:** `docs/evidence/v104-k1ii-android-20261110/`

---

## Summary

On v104 with an Android client, changing exposure parameters (shutter speed, ISO, EV) causes the first attempt to fail with PTP error -2110. Retrying the same parameter change usually succeeds, but shutter speed reads back as 0 despite `SP_SET_SHUTTER OK`. Liveview works on Android (unlike iPhone where it was garbled/cutting out).

## Observed Behavior

### Liveview — WORKS on Android
- Liveview is stable on Android (contrast with iPhone where it was garbled/cutting out)

### ISO — wider range available on Android
- ISO values 100–204800 available (wider than iPhone)

### Shutter speed — first attempt fails, second succeeds but reads back as 0

From `Clog-android-after.txt` / `Mlog-android-after.txt`:

```
[09:52:47:446] App sends code:261 val:s:9                          <- user changes shutter
[09:52:48:481] setCameraConfig configType 3 value: 9 ret -2110     <- FIRST ATTEMPT FAILS
[09:52:48:481] ERROR: SP_SET_SHUTTER FAIL
[09:52:48:481] SP_sendMsg success code:261 val:s:9;ret:-2110;

[09:52:51:444] App sends code:261 val:s:9                          <- SECOND ATTEMPT
[09:52:51:865] setCameraConfig configType 3 value: 9 ret 0         <- SUCCEEDS
[09:52:51:865] SP_SET_SHUTTER OK
[09:52:51:866] SP_GetCameraShutter: u32ShutterUs 0                 <- BUT reads back as 0!
[09:52:51:866] SP_GetCameraShutter: u32ShutterIndex 9              <- index updated but value is 0
```

### ISO — first attempt fails, second succeeds

```
[09:53:19:780] App sends code:258 val:iso:4                         <- FIRST ATTEMPT FAILS
[09:53:19:780] SP_SET_ISO FAIL (ret -2110)
```

### EV — first attempt fails, second succeeds

```
[09:53:12:362] App sends code:260 val:ev:16                         <- FIRST ATTEMPT FAILS
[09:53:12:362] ERROR: SP_SET_EV FAIL (ret -2110)
[09:53:15:666] App sends code:260 val:ev:16                         <- SECOND ATTEMPT SUCCEEDS
[09:53:15:666] SP_SET_EV OK (ret 0)
```

### Aperture — works on first attempt (Android)

```
[09:52:44:728] App sends code:276 val:fNum:19
[09:52:44:728] setCameraConfig configType 7 value: 19 ret 0        <- SUCCEEDS first time
[09:52:44:729] SP_SET_FNUM OK
```

---

## Pattern Summary

| Parameter | First attempt | Second attempt | Sticks? |
|-----------|--------------|----------------|---------|
| Aperture (fNum) | ret 0 OK | N/A | Yes |
| Shutter speed (s:9) | ret -2110 FAIL | ret 0 OK, but u32ShutterUs 0 | **No** (reads as 0) |
| ISO (iso:4→iso:5) | ret -2110 FAIL | ret 0 OK | Yes |
| EV (ev:16) | ret -2110 FAIL | ret 0 OK | Yes |

**Root cause hypothesis:** The camera's PTP property set is not being applied reliably on the first attempt after a liveview session starts. The `-2110` error suggests a PTP operation failure (likely device busy or invalid state during liveview). The shutter speed reading back as 0 despite `SP_SET_SHUTTER OK` indicates the value isn't actually reaching the camera or is being rejected silently.

---

## Files

All logs saved under `docs/evidence/v104-k1ii-android-20261110/`:

| File | Size | Description |
|------|------|-------------|
| `meta.txt` | 666 bytes | Device identity, provenance, processes |
| `Mlog-android-baseline.txt` | 37,146 bytes | Baseline Mlog before Android testing |
| `Clog-android-baseline.txt` | 55,656 bytes | Baseline Clog before Android testing |
| `Mlog-android-after.txt` | 37,119 bytes | Mlog after Android testing |
| `Clog-android-after.txt` | 63,906 bytes | Clog after Android testing |

Key log lines:
- `Clog-android-after.txt` lines 126-134: shutter first attempt fails (-2110), second attempt succeeds but reads back as 0
- `Mlog-android-after.txt` lines 42-57: `SP_SET_SHUTTER FAIL` then `SP_SET_SHUTTER OK` with `u32ShutterUs 0`
- `Mlog-android-after.txt` lines 196-198: `SP_SET_EV FAIL` (ret -2110)
- `Mlog-android-after.txt` lines 228-229: ISO first attempt fails (ret -2110)

---

## Steps to Reproduce (Android)

1. Connect K1 II to Polaris running v104 (FwVer:6.0.0.54.104)
2. Open liveview in Benro Connect on Android
3. Change shutter speed → observe first attempt fails with -2110/SP_SET_SHUTTER FAIL, second attempt succeeds but reads back as 0
4. Change ISO → observe first attempt fails with -2110, second attempt succeeds
5. Change EV → observe first attempt fails with -2110/SP_SET_EV FAIL, second attempt succeeds

## Expected Behavior

- Parameter changes apply on first attempt
- Shutter speed reads back the value that was set

## Actual Behavior

- First parameter change after connecting often fails with -2110
- Shutter speed reads back as 0 despite `SP_SET_SHUTTER OK`

---

**Note:** This is v104 test evidence from Android client testing. The device is running build_id=v104, display_fwver=6.0.0.54.104, libgphoto2 commit=806c3bda62d6c0c23ca7a3091fb42f3d7894172b, patcher commit=1e88637cf61d152f94e23f6e139adec4b9fa80c2.