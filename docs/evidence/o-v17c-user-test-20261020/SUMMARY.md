# o-v17c (.68) user test 2026-10-20 — long-exposure wait budget too small when noise reduction is ON

Bundle: `/tmp/polaris-logs-20261020-172244/polaris-logs-20261020-162244.tar.gz` (5.9 MB,
25 newest `Mlog_*`/`Clog_*` archives). Firmware `6.0.0.54.68`. Device clock matched the
workstation at pull time (3 s), so Mlog timestamps are directly usable.

Scope is the operator's session only: boot at 17:12 through 17:18. Everything from 17:20
onward is OpenPolaris testing and is excluded.

## Timeline (Mlog code 264 + Clog `[pentax]` markers, correlated)

| Time | Capture | Result |
|---|---|---|
| 17:13:09 | `capture=1`, 10 s bulb | `state:1` → `state:4` 17:13:33, `SP_0365.dng` 34 172 056 B. **PASS** (~24 s) |
| 17:13:50 | `capture=2`, 40 s bulb | `initiate-return ptp=0x2001`, then **`capture end -71634 ms`**, `ERROR: Could not capture image.` **FAIL** |
| 17:16:05 | `capture=3` | `camlib-enter recovery=1 output_pending=1`; refused `state:-110` → **`state:-1005`** |
| 17:16:07 | `capture=4` | same, **`state:-1005`** |
| 17:17:18 | `capture=1` (new process) | `state:4` 17:17:32, `SP_0366.dng` 32 479 210 B. **PASS** |

Files on the card afterwards: `SP_0365.dng` 17:13, `SP_0366.dng` 17:17, then `SP_0367`/
`SP_0368` at 17:25/17:28 (OpenPolaris). **The 40 s exposure has no file — the image was
lost, not merely reported as an error.**

## Root cause

The wait budget for a bulb exposure is sized from the camera's own bulb timer plus a fixed
processing margin:

```c
#define PENTAX_CAPTURE_TIMEOUT_MS_BASE          (60 * 1000)   /* pentax-utils.h:143 */
#define PENTAX_CAPTURE_PROCESSING_MARGIN_MS     (30 * 1000)   /* pentax-utils.h:146 */
/* pentax_capture_timeout_ms(): bulb_ms = (bulb_timer_seconds + 1) * 1000 + margin */
```

- 10 s bulb → `(10+1) + 30 = 41 s`, clamped up to the 60 s floor. Observed completion 24 s. **Fits.**
- 40 s bulb → `(40+1) + 30 = 71 s`. Observed give-up **71.634 s**. **Matches to within 0.6 s.**

The camera needed longer than 71 s because noise reduction was ON: the body captures a dark
frame of roughly the exposure length after the shutter closes, so a 40 s NR exposure needs
≈80 s plus RAW conversion before the candidate is published. The margin budgets post-exposure
*processing*, not a second exposure.

**Noise reduction is not modelled anywhere in this path.** `grep` for any noise/long-exposure
term in `camlibs/ptp2/pentax-utils.c` returns zero, and the conditions blob exposes no NR
flag — so the budget cannot know NR is enabled even in principle.

## Relation to #172 — the guard behaved correctly

This refutes the "spurious latch" reading and confirms the fail-closed design:

```
capture=3 boundary=camlib-enter transfer=0 recovery=1 output_pending=1
RECOVER capture=3 path=recovery-probe reason=transfer-candidate-available
        field32=0x00000001 field36=0x00000001 field104=0x00000000
        action=recover-output-with-ownership;preserve-candidate; never-delete-or-shoot-over-it
```

`field36=1` means the camera genuinely still held the un-transferred 40 s candidate, so
`OUTPUT_UNRESOLVED` was the correct refusal — the obligation-release path correctly declined
to forget an obligation the camera still owed. Per
`docs/pentax-capture-stability-experiments.md:288`, the two `-1005` results are **aftermath**;
the first abnormal event is the 71.6 s timeout.

So #172's remaining cause is not a latch bug. It is a **wait budget that does not account for
long-exposure noise reduction**, and the resulting loss of a real exposure.

## Prediction for the 70 s test

Budget for 70 s = `(70+1) + 30 = 101 s`.

- **NR ON:** ≈70 s exposure + ≈70 s dark frame + RAW write ≈ 145 s > 101 s → **expected to
  fail identically**, followed by `-1005` refusals until the candidate is recovered.
- **NR OFF:** ≈70 s + write ≈ 75 s < 101 s → **expected to pass.**

Test both if practical; the NR ON/OFF contrast is the controlled experiment that isolates this
cause from every other candidate.

## Candidate fixes (not yet implemented)

1. Budget the dark frame: when a long exposure is requested, size the post-exposure phase at
   ≈1× the exposure again rather than a flat 30 s. Safe and self-contained, but over-budgets
   when NR is off.
2. Discover the NR setting. It is not in the conditions blob; it may be reachable via a Pentax
   property (the same `GetAllProps` route that produced the `0xd103`/`0xd104` findings). Needs
   a device probe before it can be designed.
3. Recover rather than lose: on this timeout the image is still on the camera. The
   `recover-output-with-ownership` path exists in the guard but has no owner-level publisher
   (see `docs/PENTAX-CAPTURE-RECOVERY.md`, "Recovery limitation").

Option 1 is the smallest change that stops losing photographs; 2 and 3 are the correct long-term
answers.
