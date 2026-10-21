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

## Correction: there are 2 real failures, not 34

An earlier draft of this note counted 34 negative `capture end` values as timeouts. That was
wrong: **every** `capture end` line is negative, including the successful 10 s shot at 17:13:33
(`capture end -23398 ms`, which produced `SP_0365.dng`). The sign is a pgphoto logging defect,
not a failure indicator.

Filtering on the actual failure marker (`ERROR: Could not capture image`) across all 20 archived
logs gives **2 failures in 34 captures**:

| Log | Time | Requested | Gave up at | Budget `(b+1)+30` |
|---|---|---|---|---|
| `Clog_000282` | 14:54:12 | 70 s bulb | 107.4 s | 101 s |
| `Clog_000295` | 17:15:01 | 40 s bulb | 71.6 s | 71 s |

Both are budget-bound. The 6 s overshoot on the 70 s case is expected: the code deliberately
performs up to three default-timeout conditions reads before raising the long-read timeout
(`library.c:7233`), so the give-up lands slightly after the nominal budget.

## The 70 s question is already answered — and needs no hardware

The 14:54:12 entry is a 70 s bulb request that failed at 107.4 s. Its outcome is determined by
arithmetic, not observation:

- **NR ON** needs ≈ 70 s exposure + ≈ 70 s dark frame + transfer ≈ **143–146 s**, against a
  **101 s** budget → cannot fit, at any margin.
- **NR OFF** needs ≈ 70 s + transfer ≈ 75 s < 101 s → would have passed.

It failed, so the per-frame overhead was of the order of the exposure itself. The failure is
therefore only explicable with noise reduction enabled — the outcome proves the cause without a
controlled A/B.

## Generalised model

The true requirement is

```
budget = frames x (exposure + dark_frame_if_NR) + compositing + transfer
```

The current formula is `frames x exposure + 30 s`, which is wrong in two independent ways:

1. **No dark frame.** `PENTAX_CAPTURE_PROCESSING_MARGIN_MS` is a flat 30 s and
   `grep -c noise|nr_|long_exp` over `pentax-utils.c` returns **0** — NR is not modelled at
   all, and the conditions blob exposes no NR flag.
2. **The margin does not scale with frame count.** Pixel shift budgets `4 x exposure` correctly
   (`PENTAX_PIXEL_SHIFT_MULTIPLIER`) but still adds one flat 30 s for four frames' worth of
   processing. A 70 s pixel-shift capture budgets `(70+1) x 4 + 30 = 314 s` against a real need
   of ≈ 4 x (70 + 70) = 560 s when NR is on.

The same gap applies to a **non-bulb** long exposure: `PentaxConditions` has no shutter-speed
field (only `bulb_timer_seconds`), so an M-mode 30 s exposure budgets the 60 s base while
needing 30 + 30 + processing. `pentax_parse_shutter_duration()` already exists
(`pentax-utils.h:406`) but is not wired into the conditions parse.

## Decided design — filed as `ian-morgan99/libgphoto2#106`

The earlier `frames x 2 x exposure` sketch in this file is **superseded**. The chosen approach is
not a bigger guessed budget but a change in what the deadline measures.

The camera already reports, in every conditions read, whether it is still exposing
(`PENTAX_CONDITION_ACTIVITY_SHOOTING`) or still processing (`_PROCESSING`). The polling loop
already reads both into `last_activity_flags` (`library.c:7352`) and then uses them only to
describe, after the fact, which kind of timeout occurred (`:7369-7384`). The loop condition
itself (`:7358`) is purely wall-clock.

**Rule:** keep polling while the camera asserts busy, and give up only once it has been busy for
longer than a mode-aware ceiling:

| Mode | Ceiling |
|---|---|
| Pixel shift (multi-capture) | `4 x exposure + margin` |
| Everything else | `2 x exposure + margin` |

Two deliberate simplifications:

- **2x for all non-pixel-shift captures**, rather than 2x with NR and 1x without. NR is not
  reported in the conditions blob, so a rule depending on it needs a separate discovery exercise.
  Because the loop exits the moment the candidate appears, the ceiling is a give-up deadline and
  a generous one costs nothing on a successful capture — it only lengthens the wait on an
  already-wedged camera.
- **30 s margin, not the initially proposed 10 s.** A *successful* 10 s bulb capture measured
  here took 24 s end to end: 10 s exposure plus **14 s** of post-exposure work. A 10 s margin
  would have cut that capture short. `PENTAX_CAPTURE_PROCESSING_MARGIN_MS` is already 30 s and is
  validated by the successful captures in these logs.

Two edge cases that must not regress: a floor is still required when the blob is unreadable or
the camera never asserts busy, and a non-bulb long exposure has no duration to multiply
(`PentaxConditions` exposes `bulb_timer_seconds` only), so it keeps the current base + margin.

**Observability is part of the fix.** The diagnostic that would have named this cause is a
`GP_LOG_E`, and `GP_LOG_E` never reaches `Clog`: across 20 archived bundles the `GP_LOG_E` string
`recovery-probe:` appears 0 times while the `fprintf`-based `[pentax-recovery]` marker appears in
the same files. Converting those lines is required for the change to be verifiable on device.

## Follow-on work (explicitly out of scope of `#106`)

1. **Discover the NR setting.** Not in the conditions blob; possibly reachable via a Pentax
   property (the same `GetAllProps` route that produced the `0xd103`/`0xd104` findings). Only
   needed to *predict* a wait — the chosen rule *observes* it instead.
2. **Recover rather than lose.** Immediately after a give-up the camera can still hold the
   candidate — observed directly at 17:16:05, where `field36=0x00000001` proved the body still owed
   the 40 s image. The `recover-output-with-ownership` path exists in the guard but has no
   owner-level publisher (see `docs/PENTAX-CAPTURE-RECOVERY.md`, "Recovery limitation").
   **That window does not stay open on its own.** In the 01:35:40 reproduction no file was ever
   published for the exposure — re-checked four hours later, the card still held 539 files with
   `SP_0376.dng` newest. Nothing recovered it later, so recovery has to claim the candidate at the
   timeout itself rather than rely on a subsequent request noticing it. (Whether that run also
   consumed a frame number was not checked; the 22:09:53 refusal shows a consumed number is possible,
   but it is not established here.)
3. **Non-bulb shutter speed.** Wire `pentax_parse_shutter_duration()` into the conditions parse so
   an M-mode long exposure gets a real ceiling instead of the 60 s base.

## The 40 s timing run: setup notes

`libgphoto2#106` set its ceiling from reasoning; the number that would confirm it is **when the
image actually appears on the card** for a 40 s exposure with NR on. That run was attempted on
2026-10-20 and abandoned on a usage error, then **succeeded on 2026-10-21** — see *Live
reproduction on hardware* below. The setup notes are kept because they cost real time to learn.

Two things to know before running it, both learned the hard way:

1. **`canary-probe.py --shot` requires `--expected-files` explicitly** — `photoFormat` is not
   treated as authoritative by the script, so omitting it exits `2` on a usage error *before any
   shutter is pressed*. Recent captures on this body publish a single `.dng`, so `1` is correct:

   ```bash
   # from the patcher repo, with the Polaris up and the camera on its USB in MTP (25fb:0189)
   python3 scripts/canary-probe.py --shot --expected-files 1 --bulb-seconds 40
   ```

   On `.68` and later the `--bulb-seconds` form is refused before any exposure (see *The bulb path
   now refuses outright*); use the non-bulb equivalent, which is what the successful run used:

   ```bash
   python3 scripts/canary-probe.py --shot --expected-files 1 --shutter-index 14 --shot-timeout 300
   ```

   The probe's own shot timeout is `bulb_seconds + 90`, so it will observe the natural outcome
   rather than cut it short.
2. **A poller running with no shot in flight looks exactly like a failed capture.** The attempt on
   2026-10-20 ~23:19 polled `/app/sd/normal` for four minutes and saw no new file — because the
   probe had already exited on the usage error above, not because a 40 s exposure failed. Confirm
   the probe actually fired before interpreting an empty poll.

Baseline at the point the run was abandoned: 537 files in `/app/sd/normal`, newest `SP_0371.dng`.
The camera then powered off (flat battery); the daemon reported `model:none;state:-5` and no `25fb`
device was present on the Polaris USB.

## High-ISO capture, 22:09–22:10 — clean pass, plus a known `-6` reproduction

`SP_0371.dng` (28 363 321 B) published 22:10:04: `state:1` → `state:2` → `state:3` → file added,
5.6 s end to end, no `-1005`/`-110`. First high-ISO pass on record here.

Eleven seconds earlier a **bulb-flagged** request (`b:1000`, `SP_0370.jpg`) returned `state:1` →
`state:-6` in 43 ms and consumed frame number `0370` with no file on the card; the successful
request five seconds later carried `b:0`. That is the signature already recorded on patcher#164
(K-3 III M↔Bulb session rebind, still open) — now reproduced on `.68`, which #164's evidence
predates. Note for anyone scripting qualification runs: **file count on the card is not a reliable
success counter**, because a refused request still consumes a frame number.

## Verification performed for this analysis

- `ninja -C _build test` — 15/17 pass. The two failures (`test-gphoto2`, `test-gp-port`) are the
  runbook §3.4 `ltdl` symlink step not having been run, not regressions; all six Pentax-specific
  tests pass.
- `pentax_capture_timeout_ms()` and `pentax_capture_timeout_state()` are pure functions with
  exact-value assertions in `tests/test-pentax-utils.c:644-690` and `:747-753`, so the ceiling
  arithmetic in `#106` is verifiable offline without hardware or Docker.

The one item that genuinely needs hardware is the **non-bulb** case: finding the conditions-blob
offset that carries the set shutter speed, so `frames x 2 x exposure` can be computed when
`bulb_timer_seconds` is zero. Until then a non-bulb long exposure keeps the 60 s base.

## Live reproduction on hardware, 2026-10-21 — confirms the model and the residual gap

Run on the same device (`6.0.0.54.68`, K-3 III) with a fresh battery, after the analysis above.
The timing measurement had to be taken through the **non-bulb** path, because the bulb path is now
refused before any exposure — recorded in the following section.

### The 40 s exposure was lost again, at exactly the predicted 71 s

`--shutter-index 14` (the 40 s shutter) with a plain capture request:

```
01:35:40  TX 1&261&2&s:14;#          RX 261@s:14;ret:0;#      <- shutter set to 40 s, accepted
01:35:41  RX 264@state:1#                                      <- capture accepted
01:36:52  RX 264@state:0;#                                     <- 71 s later, no state:4, no 773
```

**71 s elapsed — the `PENTAX_CAPTURE_TIMEOUT_MS_BASE` floor exactly**, because with
`bulb_timer_seconds == 0` the budget function has no duration to scale and returns the base. The
exposure plus its NR dark frame needs ≈80 s, so it was cut off mid-processing.

**The image was destroyed, not delayed.** Checked four hours later: card count unchanged at 539,
newest file still `SP_0376.dng` from 02:09. No late publication, no orphan. This is the direct
evidence for the "lose vs recover" question: giving up at the budget **discards a photograph that
would otherwise have completed**.

### Why this is a post-fix reproduction, not a contradiction of the fix

`libgphoto2` `23008c229` ("ptp2: budget the dark frame in the Pentax capture wait") is on `main`
and implements the scaled allowance — `pentax_processing_allowance_ms()` returns
`known_exposure_ms + margin` when a duration is known, `margin` alone otherwise. It covers bulb,
astro-shift and astro-tracer.

This run does not exercise it, for two independent reasons:

1. `.68` was built 2026-10-19, the fix committed 2026-10-20 — the installed library predates it.
2. More importantly, the run went through the **non-bulb** path, where `known_exposure_ms` is
   still 0 and the committed fix therefore still yields the flat base. The measured 71 s is
   precisely what the current code produces for this case.

So the residual gap is confirmed on hardware rather than inferred: **a non-bulb long exposure is
still budget-bound at 60 s + margin**, and closing it needs the shutter-speed field in the
conditions blob, not a change to the allowance arithmetic.

### Control, same session — the fault is specific to long exposures

A default-shutter capture at 02:08:58, on the same daemon roughly half an hour after the 71 s
give-up, completed cleanly: `state:1` → `state:4` → `773` `SP_0376.dng` 33 074 966 B → `state:0`,
in 6 s. So the 71 s loss is not a general capture fault, not a wedge, and not the guard: it is the
budget, and only for exposures long enough to need a dark frame.

## The bulb path now refuses outright — retiring the polestar patch unmasked a defect

Three attempts to request a 40 s bulb (`--bulb-seconds 40`) at 01:03:20, 01:21:30 and 01:42:48
behaved identically, and identically to the 22:09:53 request above:

```
TX 1&261&2&s:14;#        RX 261@s:14;ret:0;#          <- shutter index accepted
TX 1&264&4&state:1;bulb:40;c:-1;#
                          RX 264@state:1#
                          RX 264@state:-6#             <- refused ~0.1 s later, no exposure
```

The dial was genuinely on B: the conditions blob read `exposure-mode-raw=9`, and
`PSLR_EXPOSURE_MODE_B = 9` in `camlibs/pentax/pslr.h:85` (with `_B_OFFAUTO = 12` at `:88`), so 9
is B and not, for example, M (8) at `:84`. The camera was idle (`shooting=no; processing=no`).
Non-bulb captures from the same daemon succeeded — at 22:09:58, five seconds after the `b:1000`
refusal above, and again at 02:08:58 after the three attempts here. Each probe opens its own socket
to 9090, but the `pgphoto` process and therefore its libgphoto2 session were unchanged throughout,
which is the session that #164's rebind theory concerns. So this is not a mode gate, not a busy
camera, and not session state. It is the `bulb:` field itself.

**`-6` is not a libgphoto2 error code.** The `GP_ERROR_*` enum bottoms out at `-110`
(`gphoto2-result.h`); there is no `-6`. It is generated by `polestar_app`, which is also the only
component that parses `bulb:`.

### Why the behaviour changed since #173 was written

#173 documented the opposite symptom: `bulb:N` was **accepted**, exposed for the camera's own
2.0 s setting, and reported success. That was the effect of `--polestar-bulb-patch`, which zeroed
`bulb_ms` and made the app's Bulb branch unreachable, routing every bulb request down the
plain-capture path.

`fb20128` ("fix: retire harmful polestar Bulb patch", 2026-10-10) removed it, and `.68` (built
2026-10-19) is built without the patch — `scripts/build-release-candidate.sh:72` now says so
explicitly. With the patch gone the app's real Bulb branch is live for the first time, and it
refuses.

So the patch was **masking a defect in the app's own bulb handling**, and retiring it exposed the
truth: the product path has never had a working bulb capture. The first build to ship without the
mask was `.65` (o-v16g), whose Layer B bulb qualification was recorded as *canary pending* and
never completed — #186 remains open. This run is that missing Layer B observation, and it is a
failure.

### Consequences

- #173's premise is now stale. The symptom is no longer "duration ignored, reports success" but
  "refused with `state:-6` before any exposure". The underlying cause is different and is in
  `polestar_app`, not libgphoto2.
- Any long-exposure qualification on `.68` or later must use the **non-bulb** shutter-index path
  until this is fixed; the bulb path cannot produce a frame at all. Note that this is only a
  workaround for the bulb refusal, not for the budget: the 40 s non-bulb run above still lost its
  image at the 71 s floor. Short exposures (the 6 s control) are unaffected.
- The `.68` stability verdict ("3/3 PASS") was obtained on Manual-dial captures and is unaffected,
  but it should not be read as covering bulb.
