# o-v13i session-recovery candidate

Status: **installed; runtime verified; stale-session rebind observed working; capture canary FAILED**.

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

## 2026-09-28 physical result

After a fresh camera battery was fitted, the K-3 III enumerated as `25fb:0189` on bus 1 device 3. The supervisor encountered the retained-session condition, rebound the camera, and code 286 reached camera-ready state 1. This qualifies only the observed stale-session/rebind path; it does not qualify the provisional `0x02fd`/`0x02ff` classifications.

One bounded RAW+JPEG canary was then issued. Preview was stopped and confirmed state 0, and code 264 accepted exactly one shutter command at 22:58:29Z. No lifecycle state 4 or code-773 file event followed. The operation timed out at 23:01:29Z; the fail-closed client sent no second shutter.

The Pentax remained electrically present as the same `25fb:0189`, bus 1 device 3 throughout. However, the active camera service changed from PID 8264 to PID 9342 during the operation. Kernel evidence records USB resets without a disconnect/re-enumeration. The replacement process recovered to code-286 state 1 and the matched runtime hashes remained intact.

This separates two defects: v13i recovers the replacement process from the stale Pentax session, but it does not prevent the original capture owner from being terminated/replaced after an operation that fails to complete. The next investigation boundary is the pgphoto/polestar watchdog decision and the first blocked/failed production operation before replacement. Do not add another USB retry or claim the capture fixed.

## v13j diagnostic canary result

The installed crash-boundary diagnostic build `6.0.0.54.34-o-v13j-crash-boundary` then completed two consecutive direct bounded RAW+JPEG operations: `SP_0114.dng/.jpg` and `SP_0115.dng/.jpg`, both with lifecycle `[1,4,0]`. The K-3 III remained `25fb:0189` on the same USB identity, the active `pgphoto` PID remained `29865` across the second operation and the >40-second post-first-shot observation, and `/app/stage2-crash.log` was absent. This does not close the Benro Connect failure: it proves the exact lower-level direct path can complete and remain owned, so the next reproduction must include Benro Connect's concurrent session/Live View/mode traffic. No libgphoto2 behaviour was changed by v13j; it only preserved crash evidence.

## Remaining physical acceptance

After the active-owner failure is corrected, run one Benro Connect still capture, wait beyond the prior watchdog boundary, and run a second capture. Acceptance requires both files to publish and the session to remain usable without replacement of the active pgphoto owner. Capture logs must show either uninterrupted ownership or an explicitly safe generation transition; recovery after killing a blocked operation is not capture success.
