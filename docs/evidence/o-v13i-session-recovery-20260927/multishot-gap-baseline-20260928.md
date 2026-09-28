## 2026-09-28 multi-shot gap investigation + baseline lock

- Observed: Benro Connect multi-shot/lapse on o-v13i — shots complete but ~1 min gap (app interval 7 s).
- Mlog: shot 1 ~65 s (31 s dead gap before code 286 status); shots 2+ fail fast with state:-110 (GP_ERROR_CAMERA_BUSY) -> PHOTO_RECORD Fail -> u32PhotoErrorCnt>=3 stop.
- Clog: 76433 / 39587 / 30563 / 2711 'stubbed 64 slots' re-inits across rotated logs; active pgphoto PID ~19 s old -> heavy stage2 re-init churn.
- Filed issue #160 (multi-shot gap + -110 busy + re-init churn).
- Baseline locked before the fix: pre-release gate GREEN at commit df870e5 (13 container + 24 Python PASS, 0 fail/skip).
