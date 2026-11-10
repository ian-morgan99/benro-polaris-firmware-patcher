# GitHub Issue: v104 — Camera not detected after Polaris reboot when camera already on

**Title:** [v104] Camera not detected after Polaris reboot when camera already on

**Labels:** bug, v104, k1-ii, k3-iii, pentax, camera-session, reboot

**Device:** Benro Polaris, FwVer:6.0.0.54.104, date:2026.11.10, build_id=v104  
**Camera:** Pentax K-1 II / K-3 Mark III  
**Client:** Android phone (Benro Connect app)  
**Logs:** `docs/evidence/v104-k1ii-liveview-garbled-20261110/`

---

## Summary

On v104, when the Polaris reboots with the camera already powered on and connected, the camera is not detected after reboot. The camera state remains `-110` (not connected) with `manufacturer:none;model:none`.

This is a significant regression — we had worked on this historically (issue #146 covers camera session lifecycle — startup, disconnect, body/battery swap, rebind and recovery without Polaris restart).

## Observed Behavior

From `Mlog-post-reboot-camera-not-detected.txt` / `Clog-post-reboot-camera-not-detected.txt`:

```
code[286],val[manufacturer:none;model:none;state:-110;storage:0;photoFormat:0;]
```

State `-110` means camera not connected. No manufacturer, no model detected.

The Clog shows repeated `camera_connected_to_app connected:1` messages with `handle_sign_pipe on client close` countdowns, indicating the app keeps trying to connect but the camera is not detected.

## Expected Behavior

- After Polaris reboot with camera already on, the camera should be detected and connected
- Camera state should show `state:1` with manufacturer and model populated
- PTP session should establish successfully

## Actual Behavior

- Camera state remains `state:-110` with `manufacturer:none;model:none`
- Camera is not detected after reboot
- App keeps retrying connection but fails

## Steps to Reproduce

1. Power on the camera (K1 II or K3 III) and connect it to the Polaris
2. Reboot the Polaris (while camera remains on)
3. After reboot, check camera state — it remains `-110` (not connected)
4. Camera is not detected in Benro Connect

## Expected Behavior

- Camera should be detected and connected after reboot
- Camera state should show `state:1` with manufacturer and model

## Actual Behavior

- Camera state remains `-110` (not connected)
- Camera is not detected

---

## Files

All logs saved under `docs/evidence/v104-k1ii-liveview-garbled-20261110/`:

| File | Size | Description |
|------|------|-------------|
| `Mlog-post-reboot-camera-not-detected.txt` | 9,877 bytes | Mlog after reboot with camera already on |
| `Clog-post-reboot-camera-not-detected.txt` | 401 bytes | Clog after reboot with camera already on |

Key log lines:
- `Mlog-post-reboot-camera-not-detected.txt`: `code[286],val[manufacturer:none;model:none;state:-110;storage:0;photoFormat:0;]`
- `Clog-post-reboot-camera-not-detected.txt`: Repeated `camera_connected_to_app connected:1` with `handle_sign_pipe on client close` countdowns

---

## Related Issues

- #146: CANONICAL: camera session lifecycle — startup, disconnect, body/battery swap, rebind and recovery without Polaris restart
- #119: Camera-USB supervisor churn/quarantine

---

**Note:** This is v104 test evidence. The device is running build_id=v104, display_fwver=6.0.0.54.104, libgphoto2 commit=806c3bda62d6c0c23ca7a3091fb42f3d7894172b, patcher commit=1e88637cf61d152f94e23f6e139adec4b9fa80c2.