# #159 iOptron iPolar (1233:1455) — UVC Backend Plan

Status: genuine UVC camera (class 14) — see #159 issue body. The attached
device's measured streaming format is packed YUYV 4:2:2, not Y16.
Measured descriptor (attached device):
- VID:PID 1233:1455; bcdUSB 2.00, bcdDevice 1.00
- Device class 239 (Miscellaneous / SubClass 2 / Protocol 1) — composite UVC function
- Interface 0: Video Control (UVC 1.00, clock 15 MHz, 1 collection, camera sensor input)
- Interface 1: Video Streaming (1 format, EP1 IN, packed YUYV 4:2:2)
- Resolutions: 640x960 enumerates but is not yet frame-qualified; 1280x960 is
  the first bounded frame-qualified mode
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
3. Prove on device: /dev/video* creation, YUYV format/stride, bounded frames,
   reconnect, coexistence with PTP, packaging/provenance/rollback

Implementation status (2026-10-04): the local userspace adapter now requests
the measured 1280x960 packed-YUYV mode using libuvc's device-advertised
cadence (fps=0), and its deterministic mock exercises open/stream/frame
publication/reconnect. This does not make the adapter part of the Polaris
application: `patch.sh` only compile-checks the adapter and frame store, and
no runtime camera-source consumer calls them. No packaged or Polaris hardware
support claim is justified until the common camera-source interface is linked
and exercised on Polaris with a real iPolar.
