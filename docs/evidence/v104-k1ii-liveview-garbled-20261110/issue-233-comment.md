## Additional evidence — v104 (FwVer:6.0.0.54.104, build_id=v104)

After Polaris reboot with camera already on, EV readback STILL fails:

```
[10:48:08:836] deal_camera_control_handler: command 29 info exposurecompensation ret -1
[10:48:08:836] recv_ipc_msg: code[266], val[-1]
```

EV compensation (code 260) still does not reach the camera. The widget is present in the camera config tree but readback fails with `ret -1`.

Shutter speed behavior after restart: No shutter speed change attempts were captured in these logs yet. The user reported shutter speed also doesn't work on Android after restart.

Other controls (WB, ISO, aperture) work correctly with `ret 0`.

This confirms issue #233 is still present on v104 — EV readback fails with `ret -1` on the K-1 II after restart.