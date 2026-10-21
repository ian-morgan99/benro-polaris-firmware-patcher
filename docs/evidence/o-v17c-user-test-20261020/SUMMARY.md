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

~~The same gap applies to a non-bulb long exposure: `PentaxConditions` has no shutter-speed field
(only `bulb_timer_seconds`), so an M-mode 30 s exposure budgets the 60 s base while needing
30 + 30 + processing.~~ **Withdrawn.** `bulb_timer_seconds` *is* the shutter-speed field — offset 272
is the current Tv numerator in every mode, with 276 as its denominator — so a non-bulb long exposure
was never unmodelled. The reasoning here was led astray by the field's name; see the final section.

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
3. ~~Non-bulb shutter speed.~~ **Superseded** — the offset is not missing; 272/276 already carries
   the set shutter speed in every mode and is already parsed. See *The non-bulb shutter-speed offset
   is already known* at the end of this file. What remains is a field-name correction, not a
   discovery.

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

~~The one item that genuinely needs hardware is the **non-bulb** case: finding the conditions-blob
offset that carries the set shutter speed.~~ **That was wrong, and the run below is what disproves
it** — the offset is 272/276, already parsed, and the 40 s non-bulb request proves the field is
populated in a timed mode. See *The non-bulb shutter-speed offset is already known*.

## Live reproduction on hardware, 2026-10-21 — confirms the model, and refutes my "residual gap"

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

**71 s elapsed.** ~~the `PENTAX_CAPTURE_TIMEOUT_MS_BASE` floor exactly~~ — that reading was wrong and
is corrected below and at the end of this file. 71 s is *not* the 60 s base: under the `.68` code the
only branch that yields 71 s is the bulb one, `(40+1)×1000 + 30 000`. So offset 272 held **40** even
though this request carried no bulb field. The exposure plus its NR dark frame needs ≈80 s, so it was
cut off mid-processing either way.

**The image was destroyed, not delayed.** Checked four hours later: card count unchanged at 539,
newest file still `SP_0376.dng` from 02:09. No late publication, no orphan. This is the direct
evidence for the "lose vs recover" question: giving up at the budget **discards a photograph that
would otherwise have completed**.

### Why this is a post-fix reproduction, not a contradiction of the fix

`libgphoto2` `23008c229` ("ptp2: budget the dark frame in the Pentax capture wait") is on `main`
and implements the scaled allowance — `pentax_processing_allowance_ms()` returns
`known_exposure_ms + margin` when a duration is known, `margin` alone otherwise. It covers bulb,
astro-shift and astro-tracer.

This run does not exercise the fix, for one reason:

1. `.68` was built 2026-10-19, the fix committed 2026-10-20 — the installed library predates it.

~~2. More importantly, the run went through the non-bulb path, where `known_exposure_ms` is still 0
and the committed fix therefore still yields the flat base.~~ **Withdrawn.** I had assumed a non-bulb
request leaves `bulb_timer_seconds` at 0; the 71 s give-up proves it was 40, because no other branch
produces that number. The field carries the set shutter speed in every mode (see the final section),
so `23008c229` *does* cover this case — for the same input the current code budgets
`(40+1) + (40+1) + 30 = 112 s`.

So what this run confirms on hardware is narrower than I first wrote, and more useful: **the old
flat-margin budget destroyed a real photograph, and the committed fix would have allowed it.** It is
not evidence of a residual gap in the fix.

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

**The dial position was not established, and the evidence points the other way.** My first reading
claimed the dial was on B because the conditions blob showed `exposure-mode-raw=9`
(`PSLR_EXPOSURE_MODE_B`, `camlibs/pentax/pslr.h:85`). That reading is withdrawn: the value came
from a `print_widget` dump in an **archived** `Clog` at 00:42, and those dumps are event-driven,
not periodic — across the four newest archives the string appears 0, 2, 0 and 5 times, all
clustered at boot or a mode change. It is not a live reading, and the 01:03 request was ~20 minutes
later.

What the wire shows instead is the opposite. Per #205, a B-mode dial collapses the 268 shutter
list to a single entry; a timed dial returns the full list. Immediately before the refusals the
list was **full** — 56 entries at 01:03, and `RD:0;V:3;R:00-01,00-02,…` at 22:09:51, two seconds
before the `b:1000` request. So on every sample I actually have, **the dial was on a timed mode
while a bulb capture was requested** — which is precisely the mis-routing #205 describes.

That reframes this section rather than weakening it. The finding is no longer "the correctly-routed
Bulb path fails" but "**a bulb request made outside B mode is routed to `captureBulbImage` and
refused**", which is #205's stated defect reproduced on `.68`. The genuinely-in-B case remains
untested: it needs the dial physically on B with the list shape confirmed at the moment of the
request, which is the measurement to make next time the camera is connected.

What is still established about these refusals: the camera was idle (`shooting=no; processing=no`),
and non-bulb captures from the same daemon succeeded — at 22:09:58, five seconds after the
`b:1000` refusal, and again at 02:08:58 after the three attempts here. Each probe opens its own
socket to 9090, but the `pgphoto` process and therefore its libgphoto2 session were unchanged
throughout, which is the session #164's rebind theory concerns. So this is not a busy camera and
not session state; the `bulb:` field is the differentiator, and the dial position is now a live
variable rather than a controlled one.

**Where `-6` comes from — corrected after review.** My first reading was that `-6` is not a
libgphoto2 code and therefore must be app-generated. That was wrong: I checked `gphoto2-result.h`
and missed the port header. `GP_ERROR_NOT_SUPPORTED` **is** `-6`
(`libgphoto2_port/gphoto2/gphoto2-port-result.h:61`; `GP_ERROR_TIMEOUT` is `-10` at `:73`), and
`camlibs/ptp2/library.c` returns it from the Bulb-action guards at `:7099` and `:7112` and from the
unqualified-model gate at `:7758`. The number alone therefore cannot distinguish an app-generated
refusal from a library error forwarded by the app.

What the logs *do* establish, from the 22:09:53 request:

```
[22:09:53:650] rcv msg from App: type:2;code:264;val:state:1;bulb:1;c:-1;
[22:09:53:652] captureImage[1485]:----will captureImage status:1 focus:-1000 sPath:SP_0370.jpg
[22:09:53:695] captureBulbImage[1458]:----captureBulbImage ret -6  p:   ;
[22:09:53:695] ERROR: PHOTO_RECORD Fail
[22:09:53:695] code[264],val[state:-6;/app/sd/normal/SP_0370.jpg]
```

`captureBulbImage` is the helper #205's trampoline routes to, so **the routing is live on `.68` and
that helper is what returns `-6`**, with an empty path (`p:`) — nothing was ever produced. That is
the substantive finding and it does not depend on which layer minted the code.

The library's Bulb-action path is also demonstrably live on this device: `Clog` carries its refusal
string *"Pentax Bulb stop has no matching active start; refusing to send another shutter command."*
That is the state machine the helper drives, which makes a forwarded `GP_ERROR_NOT_SUPPORTED` at
least as likely as an app-generated value.

**Unresolved, and the single test that settles it:** does `captureBulbImage` call the library's
Bulb start/stop action and forward its return, or refuse on its own? Trace the call/return
provenance of the `state:-6` emission against the installed `.68` artifact hashes. Until then the
defensible statement is: *the app's Bulb helper refuses; the layer that produced the code is not
established.*

One further observation, recorded as non-attributable: a `bulb:5` request at 10:38 did **not**
produce an instant `-6` — the probe's socket timed out, and `Clog` shows a capture that reached
`initiate-return ptp=0x2001`. Because `Clog`'s `[pentax]` markers carry no timestamps (#213), that
capture cannot be tied to the request with certainty, so it is not evidence that the refusal is
intermittent — only that the behaviour may not be as uniform as the four `-6` samples suggest, and
that #213 is what prevents saying so either way.

### Why the behaviour changed since #173 was written

#173 documented the opposite symptom: `bulb:N` was **accepted**, exposed for the camera's own
2.0 s setting, and reported success. That was the effect of `--polestar-bulb-patch`, which zeroed
`bulb_ms` and made the app's Bulb branch unreachable, routing every bulb request down the
plain-capture path.

`fb20128` ("fix: retire harmful polestar Bulb patch", 2026-10-10) removed it, and `.68` (built
2026-10-19) is built without the patch — `scripts/build-release-candidate.sh:72` now says so
explicitly. With the patch gone the bulb duration survives to the dispatcher for the first time,
and the request is routed to `captureBulbImage`, which refuses.

The masking mechanism is more specific than "the app's Bulb branch", and worth stating because it
is the same predicate #205 objects to. The trampoline routes on `r1` (duration) > 0. The retired
patch replaced `mul r3, r2, r3` (bulb_seconds × 1000 → `bulb_ms`) with `mov r3, #0`, so the
duration reaching the dispatcher was zero and the routing predicate was false — every bulb request
fell through to plain capture, which is exactly #173's "exposes 2.0 s and reports success". Remove
the patch, the duration is non-zero, the predicate is true, and the request goes to the helper that
returns `-6`.

**One link in that chain is inferred, not observed:** that the `bulb_ms` the patch zeroed is the
same value the trampoline tests as `r1`. It is the obvious reading of both patches and it explains
the change in symptom without any other variable, but confirming it needs the disassembly of the
264 handler → `capture_image_with_Burst` call site. Until then the supported claim is: *the symptom
changed when the patch was retired, and the refusal is emitted by `captureBulbImage`.*

What is not in doubt is the conclusion that matters: the patch was **masking** a failure rather
than fixing one, and the product path has never had a working bulb capture. The first build to ship
without the mask was `.65` (o-v16g), whose Layer B bulb qualification was recorded as *canary
pending* and never completed — #186 remains open. This run is a partial Layer B observation: it
establishes that a bulb request outside B mode is refused, and it does **not** establish the
in-B case, which is still untested.

### Consequences

- #173's premise is now stale. The symptom is no longer "duration ignored, reports success" but
  "refused with `state:-6` before any exposure", and the refusal comes from `captureBulbImage` —
  the helper #205's trampoline routes to. Which layer mints the `-6` is not established; see
  *Where `-6` comes from* above, and settle it before choosing where to fix it.
- Any long-exposure qualification on `.68` or later must use the **non-bulb** shutter-index path
  until this is fixed; the bulb path cannot produce a frame at all. Note that this is only a
  workaround for the bulb refusal, not for the budget: the 40 s non-bulb run above still lost its
  image at the 71 s floor. Short exposures (the 6 s control) are unaffected.
- The `.68` stability verdict ("3/3 PASS") was obtained on Manual-dial captures and is unaffected,
  but it should not be read as covering bulb.

## The non-bulb shutter-speed offset is already known — the "needs hardware" item is closed offline

The open item said the conditions-blob offset carrying the set shutter speed had to be *found on a
body*, so that a non-bulb long exposure could be budgeted. It does not need a body, and the offset
is not missing. **It is 272/276 — the same pair already parsed as `bulb_timer_seconds` /
`bulb_timer_denominator`.**

IT2 reads those two words as the live shutter speed in every mode, not as a bulb-only field:

```csharp
num  = BitConverter.ToUInt32(data, 272);
num2 = BitConverter.ToUInt32(data, 276);
ConvertFractionalTvValueToString(num, num2, out _TvCurrentValueText);   // the Tv display
TimeSpan timeSpan = new TimeSpan(0, 0, (int) num);                     // the same word as the bulb timer
_camBulbTimerValue = ...;
```
(`IT2_2625_decompile/RemoteAssistant/MtpDevice.cs:4777-4783`; `ConvertFractionalTvValueToString` at
`:2444` decodes `den==1 → "N″"`, `num==1 → "1/D"`, else the quotient — a shutter-speed fraction.)
Enumerating every `BitConverter.ToUInt32(data, N)` in that parser returns **no other candidate** for
the current shutter value.

Our own tree already treats it that way, in a shipped and qualified path: the shutter-verify loop
compares the *requested* shutter against these exact fields —

```c
GP_LOG_D ("Pentax shutter verification attempt %u: requested=%u/%u, conditions=%u/%u", ...
        conditions.bulb_timer_seconds, conditions.bulb_timer_denominator);
```
(`camlibs/ptp2/config.c:11726`) — and that verification works on the body.

### And today's 40 s run proves it on hardware, without meaning to

The 01:35:40 capture was a **non-bulb** request (`--shutter-index 14`, dial on a timed mode, no
`bulb:` field) and it gave up at **71 s**. Under the `.68` code the only branch that yields 71 s is
the bulb one, `(40+1)×1000 + 30 000`; the base alone is 60 s and base+margin is 90 s. So offset 272
held **40** while the camera was in a timed mode. The field carries the set shutter duration in
non-bulb modes, observed directly.

### What that means for `libgphoto2#106`

The comment I posted this morning asserted the opposite — that `known_exposure_ms` stays 0 for a
non-bulb exposure and so `23008c229` is a no-op there. That is wrong: `bulb_timer_seconds` is
non-zero for a non-bulb long exposure, so the committed scaled allowance **already covers it**. For
the same 40 s input the current code budgets `(40+1) + (40+1) + 30 = 112 s`, above the ≥85 s the
regression pack pins at `tests/test-pentax-utils.c:709`. The residual gap I described does not
exist; `.68` lost the frame because it predates the fix, not because the fix has a hole.

Direction of any residual error is safe: because the value is a fraction, a sub-second shutter
(`1/200`) reads as 1 s and `1″3` reads as 13 s, so the budget is over- rather than under-sized,
which is the cheap direction by the reasoning in `23008c229`.

### The real defect is the name

`bulb_timer_seconds` is a misleading name for a field that is the current Tv numerator in all modes,
and that name is what produced this misanalysis — mine included, twice. The useful follow-up is
therefore small and offline: rename or document the field as the shutter/Tv fraction with the bulb
timer as its bulb-mode reading, and add a regression case that sets only the Tv fields with no bulb
mode and asserts the budget scales. No hardware required.

## Follow-on hypothesis: the #122 "skip the idle wait" fast path may be dead on a real camera

Establishing the offset map had a consequence beyond budgeting. `pentax_capture_needs_idle_wait()`
gates on `conditions->bulb_timer_seconds > 0` with the comment *"Ordinary single-shot captures do not
need the wait (issue #122)"*. If offset 272 is the shutter numerator in every mode, that condition is
**not a bulb test** — it is "a shutter speed is set", which is true for essentially every real
capture. A 1/200 s exposure reports numerator 1, so the predicate is satisfied and the function
returns 1.

The chain, and exactly where it is inferred:

| Link | Status |
|---|---|
| IT2 decodes 272/276 as a fraction, `num==1 → "1/D"` | verified, `MtpDevice.cs:2444` |
| Our parser puts 272 into `bulb_timer_seconds` | verified, `pentax-utils.c:533` |
| `needs_idle_wait` returns 1 when that is > 0 | verified, `pentax-utils.c` |
| A sub-second shutter actually reports numerator 1 at 272 | **inferred** from IT2's decoder; not observed |
| Therefore the #122 fast path never runs on a real body | follows from the row above |

The existing test does not catch this: it builds `PentaxConditions` with `memset(0)` and asserts
`!pentax_capture_needs_idle_wait(&g)` — an all-zero blob, which is precisely the state a real camera
with a shutter set does not produce. The assertion is correct and the scenario is unreachable.

**Severity is low and that is why this is a hypothesis, not a defect report.** `needs_idle_wait` only
selects a *bounded* post-capture probe, and the loop returns as soon as the camera reports idle — the
6 s control capture in this session completed normally, which is consistent with either branch. The
cost is latency on ordinary captures, not lost photographs.

**The test, when a body is next attached:** take an ordinary sub-second capture and check whether the
post-capture idle-wait path is entered. If it is, the #122 fast path is dead and the correct gate is
a real bulb-mode test (exposure mode 9/12, as used elsewhere), not a non-zero numerator.

**This is also why the field rename should be a deliberate change rather than a drive-by.** Renaming
`bulb_timer_seconds` to the shutter/Tv fraction it actually is would make this gate read as a bug on
sight, and the fix depends on the observation above. Doing it before that observation lands risks
"fixing" a name while leaving a dead fast path behind — and `libgphoto2` is in upstream-submission
readiness (`#88`), where a 31-site rename across `config.c`, `library.c` and `pentax-utils.*` wants
to be its own reviewable change.
