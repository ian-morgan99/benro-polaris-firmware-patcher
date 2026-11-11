# Rig salvage — 2026-11-11

Logs pulled off the Polaris microSD card on 2026-11-11 while the card was failing.
Nothing here was reconstructed from memory or inferred; every byte was read off the
card over SSH before it became unreadable.

## Why this exists

The card had **709 `FAT-fs` errors in one boot** (`fat_bmap_cluster: request beyond
EOF`). Reads were intermittently returning garbage or nothing at all, so these files
were copied out in small pieces and verified, rather than trusting a single pass.

`wifi-watch.log` could not be recovered at all — `dd` returned 0 bytes, which is a
failure on the underlying blocks rather than in FAT metadata. It is present here as a
0-byte file to record that the read failed, not that the log was empty.

Afterwards the card was repaired with `chkdsk` on a PC and reinserted. On the next
boot the rig reported **1 `FAT-fs` error instead of 709**, and small writes succeeded
normally. That is a real improvement but not proof the media is trustworthy: `chkdsk`
repairs FAT metadata, and the `wifi-watch.log` failure was a block-level read error
that no filesystem check repairs. The kit also mounts with `errors=continue` (#284),
so the kernel keeps going after I/O errors and a clean-looking FAT can still silently
lose writes mid-session.

## What each file is

| file | size | what it proves |
|---|---|---|
| `solve.log` | 5,780 | **The evidence behind the #321 timeout fix.** Contains a real timeout logged as `no match` — see below. |
| `camera-roll.log` | 475,136 | Timelapse frame cadence and per-frame timing on the K-3 III. |
| `stage2-crash-20261008.log` | 28,999 | Stage2 crash trace cited in issue evidence for v104. |
| `stage2-crash-190-repro-20261009.log` | 9,585 | Reproduction of the #190 stage2 crash. |
| `polaris-autosolve.log` | 1,077 | Autosolve cycle output; correlates with `solve.log`. |
| `wifi-watch.log` | 0 | **Unrecoverable.** Read failed at block level; recorded as evidence of the failure. |

## The finding in `solve.log`

`solve_finish()` in `container/astro/ondisk/polaris-align.sh` classified only
`polaris-solve.c`'s timeout vocabulary (`"error":"timeout"`). The solver actually in
use on this rig, `polaris-solve-independent-search`, reports timeouts as
`"failure_reason":"timeout"` with exit code 7. That string was not matched, so a
genuine timeout fell through to `"solved":false` and was logged as "no match":

```
2026-11-10 23:03:48 solve start: bin=polaris-solve-independent-search img=SP_0001.jpg fullres=6192x4128 ds=4 stars=200 focal=--focal-mm 70.0
2026-11-10 23:03:48 solve no match: 50.37s rc=7 stars=200 bin=polaris-solve-independent-search --focal-mm 70.0000 --sensor-mm 23.333333
2026-11-10 23:03:48   solver said: {"solved":false,"failure_reason":"timeout","attempts":5,"search_mode":"all-sky-triangle-index"}
```

A 50-second search that hit its bound was recorded as "the sky has no match for this
frame" — the opposite diagnosis, pointing a reader at star count or focus when the
answer is a longer timeout. Fixed in `76b2eb1`; the regression tests execute the real
`solve_finish()` and are mutation-tested.

It happened twice in this log, on two different focal lengths:

```
2026-11-10 23:03:48 solve no match: 50.37s rc=7 stars=200 bin=polaris-solve-independent-search --focal-mm 70.0000 ...
2026-11-10 23:15:07 solve no match: 45.66s rc=7 stars=200 bin=polaris-solve-independent-search --focal-mm 50.0000 ...
```

Both carried `"failure_reason":"timeout","attempts":5`.

## The same label, correctly applied in a different case

The log also contains a genuine "no match", worth keeping beside the two above because it
shows the classification is not wrong everywhere — only for this one vocabulary:

```
2026-11-10 23:01:38 extract: upload-1794187168-943-regression-...jpeg fullres=1920x1280 downsample=4 stars=6 (max 200) camera='none' focal_exif=none
2026-11-10 23:01:39 solve no match: 0.56s rc=3 stars=6 bin=polaris-solve --scale-low 38.047978 --scale-high 277.973928
2026-11-10 23:01:39   solver said: {"solved":false,"nfield":6,"solve_seconds":0.060}
```

That frame did **not** solve. It is an uploaded test image with no camera EXIF, only 6
stars detected, and `polaris-solve` returned in 0.56 s with `nfield:6` — a real
"found nothing", correctly labelled. The contrast is the useful part: 0.56 s / rc=3 /
`nfield` is a genuine no-match, while 50 s / rc=7 / `failure_reason:timeout` is budget
exhaustion wearing the same label.

## Related

- Fix and tests: `76b2eb1 fix(#321): classify independent-search timeouts as TIMEOUT, not "no match"`
- Tests: `tests/test_solve_timeout_classification.py`
- The original copies remain at `~/rig-salvage-20261111/` on the workstation.
