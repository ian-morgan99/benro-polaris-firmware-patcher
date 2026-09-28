=== #159 iPolar — session plan ===
Measured: VID:PID 1233:1455; UVC 1.00 (class 14); Video Control + Streaming; Y16 uncompressed; 640x960 / 1280x960.
Host: binds to uvcvideo (/dev/video0, video1); OpenCV capture works.
Path: UVC -> kernel uvcvideo/V4L2 OR userspace libuvc -> Polaris adapter -> OpenPolaris (per #151).
Remaining: confirm uvcvideo module on Hi3559V200 (or package libuvc); add device entry; prove bounded frames/reconnect/coexistence.
Next: verify uvcvideo module availability on Hi3559V200
