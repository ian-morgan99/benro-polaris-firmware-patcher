# #158 Orion StarShoot All-in-One (16c0:29a0) — Adapter Contract

Status: vendor-protocol USB camera (NOT UVC — see #158 issue body).
Path: libusb backend -> Polaris adapter -> OpenPolaris (per #151 ownership layer).

Measured descriptor (attached device):
- VID:PID 16c0:29a0; USB class 255 (Vendor Specific); bcdUSB 2.00
- Single interface, 4 alt settings: bulk (alt 1) + isochronous (alt 3) endpoints
- No iManufacturer/iProduct/iSerial strings; no kernel driver bound

Open items (separate from #159):
1. Confirm exact StarShoot model/firmware (family spans UVC + vendor-protocol variants)
2. Identify QHY5L-II/INDI command protocol / SDK version for 16c0:29a0
3. Validate libusb backend on host
4. Define adapter interface (command set, stream format, reconnect behavior)
5. Prove on Hi3559V200: open, handshake, bounded frames, reconnect, packaging/provenance/rollback

Implementation status (2026-09-30): the local adapter remains a protocol
skeleton. It now reports open/claim/cleanup and short-transfer failures, and
has a deterministic libusb mock test. The proposed control request is not a
validated camera handshake. The discriminator deliberately does not issue
guessed commands or label arbitrary bulk bytes as a frame. The adapter is not
linked to a runtime consumer, so this is not installable StarShoot support.
Required before support: establish the command/stream protocol from the exact
model/SDK or controlled hardware evidence, implement still/live frame parsing,
and integrate through the common Polaris camera-source interface.

## 2026-10-04 protocol correction

Static analysis of the archived Orion `qhy5dll.dll` found no `0x41` request.
The earlier adapter's guessed `0x41` probe has been removed and the probe API
now fails closed with `LIBUSB_ERROR_NOT_SUPPORTED`. The observed request IDs
(`0x10`, `0x11`, `0x18`, `0x21`, `0x22`, `0x25`, `0x26`, `0x55`) remain static
evidence only; none is sent until the exact operating-camera transaction is
validated.

The correct immediate test is still the hash-checked volatile Orion FX2 image
from `16c0:29a0` to `16c0:29a1`, followed by QHY/INDI enumeration and a
validated frame. Host builds do not qualify Polaris, and the available ARM QHY
SDK is hard-float while the target stack is soft-float.
