# K-3 III direct-PC baseline at the `.62` libgphoto2 SHA

Date: 2026-10-09. This is Layer A from the Pentax stability plan: exact libgphoto2 source SHA, K-3 III attached directly to the PC. No Polaris or Benro Connect was in the camera path.

## Provenance and setup

- Camera: Pentax K-3 III, freshly enumerated `25fb:0189`, `usb:001,011`.
- Attachment/layer: PC / A.
- libgphoto2 source: `67843d2248e7e37cfa58c15cc52e0a47bc13d952`, the source SHA recorded for installed `.62`.
- Test: `examples/pentax-safe-preview`, five frames. The harness is documented as preview-only: no shutter capture and no configuration setters.
- Build: temporary detached worktree `/tmp/lgp-direct-67843d224`; exact-SHA Meson build with `camlibs=ptp2`, `iolibs=disk,libusb1`, `debugoptimized`, and the research Pentax capture macro enabled. No install or source edit.
- Binary hashes: preview harness SHA-256 `ae91fceb99765f40c2fbe9b3b71dd670696dd5f20f4c152dea7eb99d4093da0f`; `ptp2.so` SHA-256 `cdd7d38aed0c0a485b1509ae1b343b25c78f673ecd873885c0623854edaaa091`.

## Result: PASS

All five preview frames returned PTP `0x2001` (`PTP_RC_OK`), each was a valid JPEG, each transfer completed in 11–35 ms, and `gp_camera_exit` cleanup reported `cleanup=ok`. The initial PTP open encountered `SessionAlreadyOpened`; the same exact-SHA library reported “observing camera state”, then vendor enable succeeded, and preview continued.

Raw command/result transcript: [`raw/direct-preview-5frames.txt`](raw/direct-preview-5frames.txt).

## What this establishes—and what it does not

- **Established:** the exact `.62` libgphoto2 source can initialize this directly attached K-3 III, recover from the observed pre-existing PTP session, enable Pentax vendor mode, and fetch five valid previews on the PC.
- **Comparison:** on the Polaris second camera-on event, Clog instead reported a reused Pentax session, vendor enable `0x2002`, and init `-1` / state `-1`. That is a divergence in the packaged Polaris path/session context, not evidence by itself that the libgphoto2 source is defective. By the repository ownership rule, do not change libgphoto2 for this Polaris-only difference without a direct reproducer.
- **Not established:** this preview does not reproduce Benro Connect's UI crash, does not validate capture/Bulb, and does not prove which camera/module path the Polaris used during the failed event. In the camera-off post-restart check, the daemon had Stage-2 core/port loaded, but `ptp2.so` was not mapped because the camera was absent.
- **No camera change:** no shutter or setting write was sent; the direct harness verified and exited cleanly. USB still enumerated as `25fb:0189` after the run.

## Next step

The useful next hardware comparison is a supervised Layer-B repro on Polaris with the phone already connected and the same camera state, preserving pre-replay native logs and observing the first PTP transition. Do not stage firmware or alter the camera mode based on this Layer-A PASS. A power cycle resets camera menu state, so read/confirm the intended mode before any later capture qualification.
