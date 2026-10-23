# Pentax historical-capability retention matrix

**Purpose:** prevent a previously hardware-proven capability from silently falling out of the release gate. This document is an evidence-backed comparison, **not** a declaration that current firmware regressed.

## Baselines

| Capability | Physical proof | Historical source | .68 source check | Current physical status |
| --- | --- | --- | --- | --- |
| K-3 III two consecutive RAW+JPEG captures | [v13g evidence](evidence/o-v13g-linked-publication-20260927/SUMMARY.md): distinct DNG+JPG pairs, publication, safe next-shot admission | libgphoto2 `8601460b3`; patcher `93e1898` | `pentax-publication.c/.h` still in Automake; publication clearing and reconciliation code present | **UNRUN on .68**: its three-shot stability gate was RAW-only |
| Preview ON → suspend → RAW+JPEG → restore ON | [v13g evidence](evidence/o-v13g-linked-publication-20260927/SUMMARY.md) | same v13g source | Historical source is an ancestor of .68, but behavioural equivalence unproven | **UNRUN on .68** |
| Direct-owner repeated RAW+JPEG with stable pgphoto | [v13i/v13j evidence](evidence/o-v13i-session-recovery-20260927/SUMMARY.md): v13j two operations, same PID | libgphoto2 `e6cc1f8c8` | Same commit is ancestor of .68; source has extensive later capture changes | **UNRUN in comparable mode** |
| Stale-session rebind after previous owner death | [v13i evidence](evidence/o-v13i-session-recovery-20260927/SUMMARY.md): code 286 recovered ready | `e6cc1f8c8` | `pentax_session_error_needs_close_reset` and ordered close/reset/retry still present | **PARTIAL historical PASS; #182 wedge remains unresolved** |
| Bulb duration budget, label fidelity, abort safety | [v15g log](CURRENT-STATE.md) and [Bulb regression evidence](evidence/polaris-bulb-regression-20261002-last-test/SUMMARY.md) | libgphoto2 `e8f0a839` | Ancestor of .68; Bulb lifecycle tests and mode gate remain | **Timed 10s Bulb+NR passed; held/untimed and Bulb→Manual unqualified** |
| K-3 III three short RAW shots | [.68 stability evidence](evidence/o-v17c-stability-20261019/SUMMARY.md) | libgphoto2 `8e06d39ae`; patcher `36d72ae` | Exact installed candidate verified | **PASS**, NR off / Pixel Shift off only |
| Named colour temperature and six CI controls | [.68 physical qualification](evidence/o-v17c-physical-20261019/SUMMARY.md) | same .68 source | Verified exact installed binaries and controls | **PASS** on K-3 III; other bodies unqualified |

## Required release regression contracts

1. **RAW+JPEG two-shot:** camera K-3 III, both files per shutter, same stem, unique stems between shots, nonzero/credible file sizes, `264 [1,4,0]`, expected `773` file publications, no duplicate/stale publication, no second shutter before first fully reconciled, unchanged pgphoto PID and USB identity where uninterrupted ownership is required. Capture logs and output inventory; fail closed on partial pairs.
2. **Preview transition:** verify Preview ON, suspend and confirm OFF, take one RAW+JPEG shot, verify both files and terminal state, restore and verify ON. Do not infer sustained preview JPEG delivery from this gate.
3. **Production path separation:** run direct libgphoto2, packaged pgphoto/9090 and Benro Connect separately. Passing one layer must not qualify another.
4. **Stale-session recovery:** deliberately reproduce only under controlled hardware conditions; record PTP open-session response, actual owner PID, watchdog decisions, `/proc/<pid>/maps`, USB identity, reset and reopen, and code-286 ready. Distinguish a retained-session *new owner* from a wedged *active owner* (#182). Never add unlimited retries or replay an ambiguous shutter.
5. **Bulb:** timed and untimed modes separately; duration requested/read back and EXIF/file timing; NR on/off; safe cancellation and terminal cleanup; transition Bulb→Manual. A single timed success cannot qualify the matrix.
6. **Build integrity:** fail on unresolved internal `pentax_*` symbols; prove `pentax-publication.c` is linked in the actual packaged camlib; check loaded core/port/ptp2/usb1 paths and hashes rather than assuming stage2 paths.
7. **Release reporting:** for each capability mark `PASS`, `FAIL`, `BLOCKED` or `UNRUN`, with exact build ID, source SHAs, body firmware, camera mode, NR/Pixel Shift settings, evidence path, and owner. **Do not change an UNRUN to FAIL.**

Keep physical shutter count bounded: normally **three captures per scenario**, not 50. Reuse a two-shot gate when sufficient to reproduce the historical contract. Camera-side NR and Pixel Shift changes require explicit operator confirmation if software cannot control them safely.

## Ownership and execution

- [Benro #149](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/149): cross-layer programme and regression acceptance.
- [Benro #147](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/147): Preview transition.
- [Benro #180](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/180): physical scenario matrix.
- [Benro #182](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/182): session wedge.
- [libgphoto2 #113](https://github.com/ian-morgan99/libgphoto2/issues/113): protocol and implementation research.

### Source audit, 23 October 2026

GitHub compares confirm that .68 `8e06d39ae` descends from v13g (53 commits), v13i (52), v15g (30). `camlibs/ptp2/Makefile-files` still lists `pentax-publication.c/.h`; `library.c` still includes publication lifecycle calls and bounded session recovery; `tests/test-pentax-reconcile.c` and `tests/test-pentax-bulb-lifecycle.c` remain. These are **source inspections only**. No source change, build, hardware retest or firmware flash occurred in this audit.

Do not revert to v13g/v13i/v15g wholesale: each had independent known defects. First prove a present-day failure, identify the first failing layer, and forward-port only a justified fix with a regression test.
