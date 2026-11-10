# GitHub Issue: v104 K3 III — shutter speed changes fail with ret -6, only integer values visible

**Title:** [v104] K-3 III: shutter speed changes fail with ret -6, only integer shutter values visible (no 1/8000 etc)

**Labels:** bug, v104, k3-iii, pentax, shutter

**Device:** Benro Polaris, FwVer:6.0.0.54.104, date:2026.11.10, build_id=v104  
**Camera:** Pentax K-3 Mark III  
**Client:** Android phone (Benro Connect app)  
**Logs:** `docs/evidence/v104-k3iii-20261110/`

---

## Summary

On v104 with a K3 III, shutter speed changes fail with PTP error `-6` on every attempt. Aperture, ISO, EV, and WB all work correctly. Additionally, the app only shows integer shutter values (e.g. `s:3`, `s:11`, `s:8`) rather than the full shutter speed range (e.g. `1/8000`, `1/4000`, `1/250`, etc.).

## Observed Behavior

### Shutter speed — FAILS on every attempt

From `Mlog-k3iii-current.txt` / `Clog-k3iii-current.txt`:

```
[10:24:06:489] App sends code:261 val:s:3                          <- user changes shutter to index 3
[10:24:07:441] setCameraConfig configType 3 value: 3 ret -6        <- FAILS with -6
[10:24:07:441] ERROR: SP_SET_SHUTTER FAIL

[10:24:09:953] App sends code:261 val:s:11                         <- user changes shutter to index 11
[10:24:10:794] setCameraConfig configType 3 value: 11 ret -6       <- FAILS with -6
[10:24:10:794] ERROR: SP_SET_SHUTTER FAIL

[10:24:29:025] App sends code:261 val:s:8                          <- user changes shutter to index 8
[10:24:29:168] setCameraConfig configType 3 value: 8 ret -6        <- FAILS with -6
[10:24:29:168] ERROR: SP_SET_SHUTTER FAIL
```

### Aperture — WORKS (contrast)

```
[10:24:27:126] App sends code:276 val:fNum:18
[10:24:28:562] setCameraConfig configType 7 value: 18 ret 0        <- SUCCEEDS
[10:24:28:562] SP_SET_FNUM OK
```

### Only integer shutter values visible

The user reports that the app only shows integer shutter values (e.g. `s:3`, `s:11`, `s:8`) rather than the full shutter speed range (e.g. `1/8000`, `1/4000`, `1/250`, `1/30`, etc.). This suggests the shutter speed property list is not being properly populated or displayed for the K3 III.

---

## Pattern Summary

| Parameter | First attempt | Result |
|-----------|--------------|--------|
| Aperture (fNum) | ret 0 OK | ✅ Works |
| Shutter speed (s:3) | ret -6 FAIL | ❌ Fails every time |
| Shutter speed (s:11) | ret -6 FAIL | ❌ Fails every time |
| Shutter speed (s:8) | ret -6 FAIL | ❌ Fails every time |

The `-6` error code (`GP_ERROR_IO_ERROR`) is different from the `-2110` seen on K-1 II. This suggests a different failure mode — possibly the K3 III's shutter control path has a transport-level issue, or the shutter speed property is not properly supported for this body.

---

## Files

All logs saved under `docs/evidence/v104-k3iii-20261110/`:

| File | Size | Description |
|------|------|-------------|
| `Mlog-k3iii-baseline.txt` | 7,507 bytes | Baseline Mlog before K3 III testing |
| `Clog-k3iii-baseline.txt` | 13,140 bytes | Baseline Clog before K3 III testing |
| `Mlog-k3iii-after.txt` | 3,240 bytes | Mlog after ISO/WB changes |
| `Clog-k3iii-after.txt` | 2,974 bytes | Clog after ISO/WB changes |
| `Mlog-k3iii-current.txt` | 5,026 bytes | Mlog with shutter speed failures |
| `Clog-k3iii-current.txt` | 5,324 bytes | Clog with shutter speed failures |

Key log lines:
- `Mlog-k3iii-current.txt` lines 3-7: shutter s:3 fails with ret -6, SP_SET_SHUTTER FAIL
- `Mlog-k3iii-current.txt` lines 8-12: shutter s:11 fails with ret -6, SP_SET_SHUTTER FAIL
- `Mlog-k3iii-current.txt` lines 31-35: shutter s:8 fails with ret -6, SP_SET_SHUTTER FAIL
- `Clog-k3iii-current.txt` lines 12-18: same failures from Clog perspective
- `Clog-k3iii-current.txt` lines 20-27: shutter s:11 fails
- `Clog-k3iii-current.txt` lines 44-48: shutter s:8 fails

---

## Steps to Reproduce (Android)

1. Connect K3 III to Polaris running v104 (FwVer:6.0.0.54.104)
2. Open liveview in Benro Connect on Android
3. Change shutter speed → observe every attempt fails with ret -6 / SP_SET_SHUTTER FAIL
4. Observe that only integer shutter values are visible, not the full range (1/8000, etc.)

## Expected Behavior

- Shutter speed changes apply successfully (like aperture, ISO, EV, WB)
- Full shutter speed range is visible (1/8000, 1/4000, ..., 30s, Bulb)

## Actual Behavior

- Every shutter speed change fails with ret -6
- Only integer values visible, not the full shutter speed range

---

**Note:** This is v104 test evidence from K3 III testing. The device is running build_id=v104, display_fwver=6.0.0.54.104, libgphoto2 commit=806c3bda62d6c0c23ca7a3091fb42f3d7894172b, patcher commit=1e88637cf61d152f94e23f6e139adec4b9fa80c2.