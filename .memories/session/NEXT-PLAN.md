# Next Plan — #158 Orion StarShoot + #159 iPolar (post-adapter verification)

Verified state (from adapter protocol check):
- Adapter skeleton: container/stage2_ipolar_adapter.c (692 B) — PRESENT
- libuvc: /work/src/libuvc/build/libuvc.so.0.0.8 (105312 B) — BUILT
- Full adapter link: MISSING (host config/libusb — adapter comment confirms)
- Starshoot adapter (16c0:29a0 vendor-protocol): MISSING (subagent only produced iPolar adapter)
- Source input: /libgphoto2-source-input -> existing LibGphoto2/libgphoto2 repo (no new clone)
- Pentax mods preserved: POLARIS_CAMLIBS=ptp2,pentax; camlibs/pentax/ intact
- Gate: GREEN (2 passed, 0 failed)
- 2.5.34 source: NO uvc/ camlib (userspace libuvc path per #151)

#158 Orion StarShoot (vendor-protocol 16c0:29a0) — NEXT:
1. Build starshoot adapter: container/stage2_starshoot_adapter.c (libusb backend for QHY5L-II/INDI protocol)
2. Link adapter (host config/libusb) — full link currently MISSING
3. Confirm exact StarShoot model/protocol (family spans UVC + vendor-protocol variants)
4. Build FwPkt with adapter packaged: ./patch-polaris.sh --build out/<candidate>/FwPkt
5. Register provenance row (docs/FWPKT-PROVENANCE-CONTRACT.md) — zip MD5 + SHA-256 + appfs MD5 + libgphoto2 commit + patcher commit
6. Pass gate --build + canary (camera ON -> --canary; camera OFF -> record 'canary pending')
7. Stage to SD card via fwpkt-update-flow (tar-stream FwPkt/, on-device MD5 verify, /sbin/reboot)

#159 iPolar (UVC 1233:1455) — NEXT:
1. Confirm uvcvideo/videodev module on Polaris kernel (or package libuvc userspace — already built)
2. Note: 2.5.34 source has no uvc/ camlib — userspace libuvc path is correct (#151); do NOT add synthetic camlib
3. Complete adapter link (host config/libusb) — currently MISSING
4. Build FwPkt with adapter packaged: ./patch-polaris.sh --build out/<candidate>/FwPkt
5. Register provenance row (docs/FWPKT-PROVENANCE-CONTRACT.md)
6. Pass gate --build + canary
7. Stage to SD card via fwpkt-update-flow

Both: separate commits per issue; reference #151 ownership-layer contract; do not claim libgphoto2 support until FwPkt + gate --build + canary pass.
