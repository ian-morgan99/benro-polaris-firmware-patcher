# o-v12o direct-capture A/B candidate — 2026-09-24

## Purpose

Restore `gp_camera_capture` to the exact resolved libgphoto2 core target. The
Stage-2 capture wrapper was introduced after o-v9p, the last broad repeated
K-3 III capture PASS. On o-v12j, o-v12k and o-v12n, capture entered that wrapper
and then faulted at an invalid low program counter before the core returned.

## Direct camera discriminator

K-3 III firmware 2.20 was attached directly as USB `25fb:0189`. A clean build
of the exact o-v12n libgphoto2 SHA, `ab0de090c`, passed:

- five valid preview JPEGs;
- shutter `1/20 -> 1/8000 -> 1/20` with read-back and restoration;
- two consecutive RAW captures twice, producing four complete, distinct DNG
  payloads (`IMGP3605` through `IMGP3608`).

After a physical USB detach/re-attach, Linux created a new USB generation but
the camera retained a vendor-mode owner. CloseSession, libusb reset, direct
reopen, a new PTP session id, vendor disable and the standard PTP USB reset
request could not recover it: OpenSession/GetDeviceInfo passed, while every
`0x9001` vendor transition returned `0x2002`. This separate direct defect is
tracked in libgphoto2 issue #83. IMAGE Transmitter evidence requires fail-closed
handling for a failed vendor transition; no guessed recovery opcode was added.

## Source and review

- Patcher commit: `073f471` (PR #138)
- Registry commit: `b4d2300`
- libgphoto2: `ab0de090c63e707afccc6d425c1c596799952341`
- Build id: `6.0.0.54.24-o-v12o-direct-capture`

All five runnable Stage-2 host tests pass. The host lacked
`arm-linux-gnueabi-gcc`; the canonical container build subsequently compiled
the ARM loader and passed its architecture/ABI/symbol gates.

## Artifact and gates

- Registry id: `o-v12o-direct-capture-20260924`
- PrivateResearch commit: `9f44f54`
- zip MD5: `ec140c6041a939555fe562a238084721`
- zip SHA-256:
  `3b5ba628ef6e4a48b37958462aee512c51342e698df4b79e16d5746d87d3b5cd`
- appfs MD5: `ab13820a561201500ef7b8162e782afc`

The clean matched-stack build passed ARM ABI, glibc ceiling, symbol resolution,
wrapper, appfs content, six-entry firmware manifest and package-layout gates.
The pre-release gate reported 3 PASS, 0 FAIL, 1 stock-path SKIP; the skipped
manifest prerequisite was independently passed by the build and private-upload
re-verification.

## Deployment status

Installation in progress. At 2026-09-24 the registered extracted `FwPkt` tree
was being tar-streamed to the empty `/app/sd/FwPkt` target while the 9090
keepalive remained active. Independent remote `du` checks showed monotonic
growth (`14.0M`, `18.8M`, `26.3M`, `32.9M`); there was no SSH or tar error.
Do not reboot until that stream completes and the six payload MD5s match the
on-card `firmwareInfo`, including appfs
`ab13820a561201500ef7b8162e782afc`.

The working wake handoff starts NetworkManager's
saved-profile association first, then sends the bare GATT connect while that
association is already pending. This produced `ServicesResolved: yes` and the
Wi-Fi activation completed even though BlueZ later reported no BR/EDR profile.
Identity was then proven independently:

- SSID `polaris_d13e86`, BSSID `48:E7:DA:D4:B5:73`, interface `wlp8s0`;
- `192.168.0.1 dev wlp8s0 src 192.168.0.4`;
- installed FwVer `6.0.0.54.23-o-v12n-companion-ownership`;
- installed provenance `ab0de090c` / patcher `7bcbc39`;
- one polestar PID and one pgphoto PID; listeners 22/8080/9090 present.

This corrects the earlier failed sequencing: beginning Wi-Fi association eight
seconds after the short wake connection was too late. No characteristic write
or BLE pairing was required.

Next: let the active stage finish, verify on-card manifest MD5s, reboot through
the normal watcher, and prove runtime hashes/maps before camera attachment.

## Required physical matrix

1. JPEG-only: three captures.
2. RAW-only: three captures.
3. RAW+JPEG: two captures, both objects per exposure.
4. Pixel Shift RAW+JPEG: four physical actuations, one DNG/JPEG composite pair,
   followed by another valid shutter.
5. Preview demand/stop/restore, stable pgphoto PID/session and stable USB.
6. Camera power-generation recovery with capture-mode restoration.
7. Surprise USB detach: invalidate the old generation and fail visibly without
   restart churn; automatic vendor recovery remains blocked by libgphoto2 #83.

K-1 II and Canon R5 Mark II remain unqualified until physically rerun.
