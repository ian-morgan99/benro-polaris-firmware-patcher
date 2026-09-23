# o-v12g second-shot failure — 2026-09-23

Identity was re-proven against BSSID `48:e7:da:d4:b5:73`, the Wi-Fi route, and
installed provenance (`6.0.0.54.17-o-v12g-recoverydiag`, libgphoto2
`252b98d57`, patcher `769b54b`). Persistent `Clog_000132.log` and
`Mlog_000132.log` were pulled locally before further work.

At 11:04:34 the first request was accepted. The camera exposed
`IMGP3586.JPG`, pgphoto returned capture success, and the app received state 4.
At 11:04:39 the second request was accepted by the protocol layer, but at
11:04:40 libgphoto2 refused it before exposure with `GP_ERROR_CAMERA_BUSY
(-110)` because the prior capture's fail-closed `recovery_required` probe did
not pass. Polestar mapped this to app `state:-1005` ("shot failed").

The o-v12g `GP_LOG_E` raw-field diagnostic was compiled in but did not reach
Clog because that libgphoto2 logging channel is not connected to the appliance
log sink. A bounded same-session direct CLI attempt was made after stopping the
daemon, but the camera was by then absent from USB and returned `-105`; the
packaged daemon was restored successfully. No shutter was triggered by that
attempt.

The next diagnostic must surface PTP result, payload length, and fields
+32/+36/+104 through stderr/context, which are captured by Clog. The recovery
predicate must remain unchanged until those values identify the stale field.
