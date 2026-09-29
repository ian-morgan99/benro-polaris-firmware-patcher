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
