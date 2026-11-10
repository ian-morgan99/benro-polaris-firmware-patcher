# GitHub Issue: v104 K3 III — Bulb mode capture actuates but reports transaction failed, no image file saved

**Title:** [v104] K-3 III: Bulb mode capture actuates but reports transaction failed, no image file saved

**Labels:** bug, v104, k3-iii, pentax, bulb

**Device:** Benro Polaris, FwVer:6.0.0.54.104, date:2026.11.10, build_id=v104  
**Camera:** Pentax K-3 Mark III  
**Client:** Android phone (Benro Connect app)  
**Logs:** `docs/evidence/v104-k3iii-20261110/`

---

## Summary

On v104 with a K3 III, Bulb mode capture actuates (shutter fires) but reports "transaction failed" and no image file is saved to the SD card. The user suspects this may be related to RAW+JPG vs RAW-only format checking.

## Observed Behavior

### Bulb capture — actuates but fails

From `Mlog-k3iii-bulb.txt` / `Clog-k3iii-bulb.txt`:

```
[10:28:08:009] capture_image_with_Bulb[3321]:----blub timeout
[10:28:08:020] send_ipc_msg_retry[80]:------SP_sendMsg success; id[98307] type[1],code[264],val[state:-1;/app/sd/normal/SP_0587.jpg]
[10:28:08:020] ERROR: SP_MsgFromCameraProc[1343]:PHOTO_RECORD Fail
[10:28:08:021] captureBulbImage[1458]:----captureBulbImage ret -1  p:   ;
```

### No file saved

SP_0587.jpg does NOT exist on the SD card. The last file is SP_0586.jpg from 10:11.

### Preview continues after failure

```
Pentax preview stage get-frame returned 0x2001 (62107 bytes, 1 attempts, 15 ms).
Pentax preview stage get-frame returned 0x2001 (61942 bytes, 1 attempts, 15 ms).
...
[stage2] preview: unknown error class (ret=-112) -- surfacing the original code without relabelling as CAMERA_BUSY and without arming the transient backoff (issue #127)
```

### User hypothesis

The user suspects this may be related to RAW+JPG vs RAW-only format checking — the capture may be failing because the image format setting doesn't match what the Bulb path expects.

---

## Pattern Summary

| Aspect | Result |
|--------|--------|
| Shutter actuation | ✅ Fires (bulb timeout reached) |
| Image file saved | ❌ No file (SP_0587.jpg missing) |
| App reports | ❌ "transaction failed" / state:-1 |
| Preview after capture | ✅ Continues normally |

---

## Files

All logs saved under `docs/evidence/v104-k3iii-20261110/`:

| File | Size | Description |
|------|------|-------------|
| `Mlog-k3iii-bulb.txt` | 1,059 bytes | Mlog with Bulb capture failure |
| `Clog-k3iii-bulb.txt` | 2,111 bytes | Clog with Bulb capture failure |

Key log lines:
- `Mlog-k3iii-bulb.txt` line 3: `state:-1;/app/sd/normal/SP_0587.jpg` — capture failed
- `Mlog-k3iii-bulb.txt` line 4: `PHOTO_RECORD Fail`
- `Clog-k3iii-bulb.txt` line 1: `blub timeout` — Bulb timeout occurred
- `Clog-k3iii-bulb.txt` line 3: `captureBulbImage ret -1` — capture returned -1

---

## Steps to Reproduce (Android)

1. Connect K3 III to Polaris running v104 (FwVer:6.0.0.54.104)
2. Set camera to Manual mode with Bulb 'wheel' setting
3. Initiate a Bulb capture
4. Observe: shutter actuates but app reports "transaction failed"
5. Observe: no image file is saved to the SD card

## Expected Behavior

- Bulb capture completes and saves an image file
- App reports success

## Actual Behavior

- Bulb capture actuates but no file is saved
- App reports "transaction failed"

---

**Note:** This is v104 test evidence from K3 III Bulb testing. The device is running build_id=v104, display_fwver=6.0.0.54.104, libgphoto2 commit=806c3bda62d6c0c23ca7a3091fb42f3d7894172b, patcher commit=1e88637cf61d152f94e23f6e139adec4b9fa80c2.