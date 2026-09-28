# #159 iOptron iPolar (1233:1455) — UVC Backend Plan

Status: genuine UVC camera (class 14) — see #159 issue body.
Measured descriptor (attached device):
- VID:PID 1233:1455; bcdUSB 2.00, bcdDevice 1.00
- Device class 239 (Miscellaneous / SubClass 2 / Protocol 1) — composite UVC function
- Interface 0: Video Control (UVC 1.00, clock 15 MHz, 1 collection, camera sensor input)
- Interface 1: Video Streaming (1 format, EP1 IN, uncompressed Y16)
- Resolutions: 640x960 (~1.8 fps) and 1280x960 (~0.9 fps)
- String descriptors: "iOptron iPolar"

Host evidence:
- Kernel binds both interfaces to uvcvideo (/sys/bus/usb/devices/1-5:1.0/driver -> uvcvideo)
- Exposes /dev/video0 and /dev/video1 (name "iOptron iPolar: iOptron iPolar")
- OpenCV capture on /dev/video1 succeeds (~960x640 BGR888, ~18 fps observed)

Path (per #151 ownership layer):
UVC -> kernel uvcvideo/V4L2 (preferred if module available on Hi3559V200)
OR UVC -> userspace libuvc -> Polaris adapter -> OpenPolaris

Open items (separate from #158):
1. Confirm uvcvideo/videodev module on Polaris kernel (or package libuvc userspace)
2. Add device entry to uvc-devices.c (only if UVC camlib included; current 2.5.34 source has no uvc/ — requires newer source or userspace path per #151)
3. Prove on device: /dev/video* creation, Y16 format, bounded frames, reconnect, coexistence with PTP, packaging/provenance/rollback
