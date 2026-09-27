# o-v13i session-recovery candidate

Status: **installed; runtime verified; camera canary pending because the camera is not enumerated**.

## Failure isolated on v13g

Benro Connect completed an exposure, then lost its camera session about 30 seconds later. The Pentax remained electrically present on USB at that time. A replacement `pgphoto` process failed to open the retained PTP session with response `0x02fa`; the existing USB-control reset retry did not recover it.

The owning fix is libgphoto2 commit `e6cc1f8c8eeb95e4a9cb1652e804b9488167c4a4`: on the first two Pentax open-session failures `0x02fa`, `0x02fd`, or `0x02ff`, perform the established ordered close-session, port reset, delay, and reopen sequence. The third failure is returned without another reset. Generic-camera recovery is unchanged.

## Provenance

- Build ID: `6.0.0.54.33-o-v13i-session-recovery`
- Patcher source: `0746ed3562f39317eb312be9356fc01e60e46595`
- libgphoto2 source: `e6cc1f8c8eeb95e4a9cb1652e804b9488167c4a4`
- Harness source: `0355f6f643ae7c154ea42a2f751d14fa1dbcb135`
- ZIP MD5: `eaa35290f26a1533c874e8f047de957c`
- ZIP SHA-256: `9c80bbd27d4f968dd4f38b62ceb608bc27cc0ac58416ed1478451515c8a79609`
- appfs MD5: `2f86289a7130bf4f5deb6d440b03ceba`
- Private artifact commit: `2816285d4`

## Verification

- Four focused libgphoto2 Pentax tests: PASS.
- Patcher deterministic tests: 13 PASS.
- Python integration/contract tests: 24 PASS.
- Package structure and `firmwareInfo`: PASS.
- Install and `/app/FwVer`: PASS.
- Runtime matched-core hashes: `/app/lib/stage2/libgphoto2.so.6` equals `/app/lib/libgphoto2.so.6` (`390194dd561de4bde4eb7ed701401507`).
- Runtime matched-ptp2 hashes: Stage-2 equals stock lookup path (`25ad3be49f7b5aa169281236f0d901ae`).
- Camera-on canary: SKIP. After the firmware reboot, `lsusb` did not list Pentax `25fb:0189`; therefore no shutter was sent.

## Remaining physical acceptance

With the camera powered and enumerated, run one Benro Connect still capture, wait beyond the prior 30-second failure point, and run a second capture. Acceptance requires both files to publish and the session to remain usable. Capture logs must show either uninterrupted ownership or the new bounded close/reset/reopen recovery.
