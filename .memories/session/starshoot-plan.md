=== #158 Orion StarShoot — session plan ===
Measured: VID:PID 16c0:29a0; USB class 255 (vendor-specific, NOT UVC); bulk+isochronous endpoints; no kernel driver.
Path: vendor-protocol (QHY5L-II/INDI family) -> libusb backend -> Polaris adapter (per #151 ownership layer).
Remaining: confirm model/protocol; validate libusb; define adapter contract; prove on Hi3559V200.
Next: identify QHY5L-II SDK / INDI protocol version for 16c0:29a0
#158 Orion StarShoot (16c0:29a0): adapter skeleton present (stage2_ipolar_adapter.c is iPolar; starshoot adapter MISSING — subagent only produced iPolar). Vendor-protocol libusb backend + QHY5L-II protocol identification still required. Source: existing LibGphoto2/libgphoto2 repo (no new clone). Pentax mods preserved (POLARIS_CAMLIBS=ptp2,pentax).
#151 ownership layer: vendor-protocol requires separate libusb adapter (not produced by subagent)
Next: complete link + confirm model/protocol before FwPkt --build
