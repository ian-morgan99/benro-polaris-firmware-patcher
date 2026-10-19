# `.68` stability run — 2026-10-19

Candidate under test: `o-v17c-colortemp-formless` → `6.0.0.54.68;date:2026.10.19;`
libgphoto2 `8e06d39ae`, patcher `36d72ae`. Body: PENTAX K-3 Mark III (`25fb:0189`),
firmware 2.20, RAW to `/app/sd/normal/`.

This run exists because "stability" was previously unmeasured for this candidate:
`tests/pentax_stability_*` is design-only (every row `TO_MEASURE`, evidence
register empty, no runner), and the `.68` qualification summary covered
crash-freedom during a CLI session rather than repeat captures. The bar used here
is the one #180 already defines: three consecutive captures, each recorded
separately, because first-shot behaviour is diagnostic. It is deliberately not an
endurance test.

## Result: 3/3 PASS, no health regression

| shot | result | lifecycle | file |
|---|---|---|---|
| #1 | **PASS** | `[1, 4, 0]` | `SP_0357.dng` |
| #2 | **PASS** | `[1, 4, 0]` | `SP_0358.dng` |
| #3 | **PASS** | `[1, 4, 0]` | `SP_0359.dng` |

No first-shot divergence: shot #1 behaved identically to #2 and #3. Each capture
produced exactly one file, correct `expected-sw`, and a clean `state:0` close.

### Device health, before vs after

| metric | before (15:48:24Z) | after (15:49:57Z) | verdict |
|---|---|---|---|
| `polestar_app` pid 249 | rss 11288 kB, 18 fds, 27 threads | rss 11312 kB, 18 fds, 27 threads | stable (+24 kB) |
| `pgphoto.stage2ondisk` pid 27532 | rss 12144 kB, 11 fds, 7 threads | rss 12392 kB, 11 fds, 7 threads | stable (+248 kB over 3 captures) |
| pids | 249 / 27532 | 249 / 27532 | **unchanged — no restart** |
| kernel faults (segfault/OOM/panic) | 0 | 0 | none |
| camera on USB | present | present | no drop |
| uptime | 3732 s | 3825 s | monotonic, one boot |

`memfree` fell 1354636 → 1260384 kB, which is the three ~28 MB DNGs landing in
page cache, not a leak; process RSS moved by hundreds of bytes.

Transcripts: `shots.txt` (full protocol traces), `health.txt` (both samples).
Runner: `scripts/stability-3shot.sh`.

## Also observed: `823` is unanswered, and always has been

Replaying Benro Connect's own startup burst (`scripts/app-burst.py --group all`)
answers 17 of 18 queries and never answers `823` — `NO_REPLY` after 3 s, on four
consecutive runs.

This is **not** a `.68` regression. Across every archived Mlog, `823` was
requested 475 times and answered **0** times; the daemon logs
`SP_sendMsg Fail; key[1001],type[2],code[823],val[-1]` for each. The neighbouring
`824` was answered 160 times in the same logs, so the path works and `823`
specifically is unhandled. It is a long-standing gap in the stock protocol
surface, not something this candidate introduced, and the app evidently tolerates
it — Benro Connect connects today exactly as it always has. Worth a look at what
the app expects there, but it does not bear on `.68`.

## Not covered by this run

- **Manual dial.** Immediately after this run, at 17:52, the operator took a
  10 s bulb capture with noise reduction ON — that **succeeded** (`SP_0360.dng`,
  28393553 B, mtime 17:52:12) — then switched the camera to **Manual** and took
  one shot, which **failed**: `264` returned `state:-1005` and no file was
  written (`SP_0360.dng` stayed the newest; the next sequence number was never
  allocated). That is #172 reproduced, and the ordering is the useful part: the
  same daemon, same session, same camera served bulb+NR successfully seconds
  before refusing the manual request, so this is not a generally broken capture
  path. It is pre-existing and unrelated to anything in `.68`, but it means the
  capture path is qualified for the canary and bulb paths **only**.
- The full #180 six-scenario matrix (JPEG+RAW / RAW-only × short / long × NR /
  Pixel Shift). This run is one scenario: RAW, short exposure, NR off, Pixel
  Shift off. The other five need camera-side setting changes and are not
  reachable from the current tooling without extending it.
- K-1 II behaviour of the relaxed `_pentax_prop_get` branch — still untested,
  unchanged from the qualification's caveat.
- Long-duration soak. Three captures is the documented release gate, not an
  endurance result; the ~94 s of activity here would not surface a slow leak.

## Verdict

`.68` is stable on the K-3 III for the canary capture path under the project's
own release bar: three consecutive captures, no first-shot divergence, no daemon
restart, no memory or fd growth, no kernel fault. Combined with the qualification
in `../o-v17c-physical-20261019/SUMMARY.md` (acceptance PASS, blast radius
proven to be one control, install verified 10/10), it is a solid installed
candidate **for the paths tested**.

Two things sit outside that verdict and are not `.68` regressions: Manual-dial
capture is refused with `state:-1005` (#172, reproduced same evening), and a
PTP session can wedge with the camera still on USB until the camera is power
cycled (#182, reproduced same evening — the supervisor took no action). Both are
pre-existing. Neither is a reason to move off `.68`; both are reasons not to
call the capture path finished.
