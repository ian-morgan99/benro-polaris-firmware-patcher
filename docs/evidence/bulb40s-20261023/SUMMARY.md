# 40 s Bulb "shot failed" on `6.0.0.54.69` — log pull + reproduction

Date: 2026-10-23. Device `FwVer:6.0.0.54.69`, K-3 III attached, RAW mode.

## Your evidence was destroyed before I could read it

- `/app/Clog.txt` was **0 bytes** when I first looked (mtime 19:04). It is truncated
  every time the watchdog replaces pgphoto — documented at
  `container/stage2_loader.c:1358`: *"The stock launcher truncates /app/Clog.txt when
  its watchdog replaces a …"*.
- `/app/Mlog.txt` rotates in ~2 minutes (27,234 bytes at 19:05 → 3,618 at 19:07).
- **No rotated archives exist**: `ls /app | grep -c '^Clog_'` → `0`.

So the 40 s failure you saw is not recoverable. Everything below is my own
reproduction plus what I could capture live.

## The fix is installed and verified on the device

| check | result |
|---|---|
| `ptp2.so` candidate vs installed | `748b00f698aa` == `748b00f698aa` |
| dark-frame commit | libgphoto2 `23008c229` — `camlibs/ptp2/pentax-utils.c` |

The fix is in **libgphoto2**, not the patcher repo — which is why grepping
`container/*.c` for "dark" returns nothing. `.68`→`.69` spans 3 libgphoto2 commits:

```
731d7fbd5 tests: pin that offsets 272/276 are the shutter speed in every mode
23008c229 ptp2: budget the dark frame in the Pentax capture wait
4a8fe7ff1 docs(agents): add two-agent working agreement for this repo
```

`23008c229` names your exact case verbatim: *"a 70 s bulb gave up at 107.4 s against a
101 s budget, and a **40 s bulb at 71.6 s against 71 s**, while the exposure plus its
long-exposure noise-reduction dark frame needs roughly twice the exposure."*

Old budget: `frames x exposure + flat 30 s`. New: `exposure + (exposure + 30 s)`, i.e.
one dark frame per known exposure.

## Measured on this body: the dark frame really does double the wall time

`--timed-seconds` exercises the normal `gp_camera_capture()` path, which is what the
budget governs:

| request | state 1 → state 4 | wall | old budget (exp+30) | new budget | result |
|---|---|---|---|---|---|
| 40 s (`00-40`) | 18:29:37 → 18:30:59 | **82.4 s** | **71 s — too short** | ~112 s | PASS `SP_0410.dng` |
| 50 s (`00-50`) | 18:31:36 → 18:33:18 | **102.6 s** | **80 s — too short** | ~140 s | PASS `SP_0411.dng` |

Clog independently confirms it: `capture_image[3164]:----capture end -83117 ms` for
the 40 s shot. So a 40 s exposure genuinely occupies ~83 s, and the pre-`.69` budget
of 71 s was shorter than the work — exactly the arithmetic failure the commit
describes. **The fix is correct and it is live.**

## What I could not reproduce, and why

**Your app-side 40 s Bulb.** My probe cannot reach that path:

```
BULB shutter_index=14 shutter_label='00-40' requested_seconds=40.0
CAPTURE state=1 lifecycle=[1]
CAPTURE state=-6 lifecycle=[1, -6]
TERMINAL-FAILURE state=-6
```

Clog gives the reason:

```
capture_image_with_Bulb[3213]:----capture with bulb 40000 ms
Camera-timed Bulb is active; use normal timed capture instead of the start/stop action.
Failed to set new configuration value 1 for configuration entry bulb.
capture_image_with_Bulb[3222]:----CAPTURE bulb start  -6
```

`library.c:7104-7113` refuses the *start/stop* Bulb action whenever
`PENTAX_CONDITION_BULB_TIMER` is set, returning `GP_ERROR_NOT_SUPPORTED`. This is
**pre-existing, not a `.69` regression** — `git merge-base --is-ancestor` confirms
`697907059` ("add research Pentax Bulb start/stop action") is already in `.68`. It
refuses for *any* duration: `--bulb-seconds 2` fails identically at once, so it is
mode-dependent, not duration-dependent.

## The open question — your failure was at ~40 s, not at a budget boundary

Your report says the failure appeared *"after around 40s"*. Neither budget explains
that:

- old ptp2 budget for 40 s = **71 s** (would fail at ~71 s, matching the historical
  71.6 s measurement)
- new ptp2 budget for 40 s = **~112 s**
- your observed failure = **~40 s**

A ~40 s failure is roughly *the exposure itself*, i.e. something declared failure as
soon as the shutter closed and the dark frame began. That points at a timer **above**
ptp2 — most likely `polestar_app`'s own assumption that wall time ≈ exposure, which
this project does not patch. **This is a hypothesis, not a finding.** The ptp2 fix
cannot address it, because it only governs pgphoto's capture wait.

## Corrected note on the shutter list

Docs state the K-3 III tops out at `00-30` (`canary-probe.py:528`, `:831`). The live
list now runs to `20-00` and includes `00-40`/`00-50`:

```
SHUTTER_OPTIONS current=9 options=['00-01',...,'00-30','00-40','00-50','01-00',...,'20-00']
```

That is why `--timed-seconds 40/50` resolved to real slots. The doc claim is stale for
this body/firmware and should not be relied on when choosing a test duration.

## Update — the 30 s repeat, and my own tests broke the reproduction

The user then reported **the same failure at 30 s**. That is the decisive clue: the
deadline tracks the *requested* duration, not a fixed budget.

I reproduced the app's exact wire request (`out/bulb40s-20261023/app-bulb-repro.py`,
sending `1&264&4&state:1;bulb:N;c:-1;#` verbatim as seen in Mlog):

| bulb | result | elapsed |
|---|---|---|
| 2 s | `state:-6` | 1.3 s |
| 5 s | `state:-6` | 1.3 s |
| 10 s | `state:-6` | 1.4 s |
| 30 s | `state:-6` | 1.4 s |

An **instant refusal**, not the ~duration-then-fail the user sees. Clog:

```
capture_image_with_Bulb[3213]:----capture with bulb 40000 ms
Failed to set new configuration value 1 for configuration entry bulb.
capture_image_with_Bulb[3222]:----CAPTURE bulb start  -6
```

**Why I cannot reproduce it: my own tests moved the dial off B.** `--list-shutters`
now reports `current_index: 13`, `bulb_slot_list: false`, a full timed list — because
my `--timed-seconds 40/50/30` runs each wrote a shutter index through command 261,
which takes the body off the B dial. The app's bulb path needs the dial on B; with a
camera-timed shutter active it refuses immediately. I restored index 9 (10 s), which
is still a timed slot, not B — **the dial must be returned to B physically** before
this path can be exercised again. That is a hand action; there is no Bulb entry in the
261 list to write.

## Duration-match evidence (still a hypothesis, but now quantitatively supported)

Measured wall time for these exposures on this body, including the dark frame:

| requested | measured wall (state 1 → 4) | user's reported failure time |
|---|---|---|
| 30 s | **63.5 s** | ~30 s |
| 40 s | **82.4 s** | ~40 s |

The user's failures land at almost exactly the **requested** duration, while the
camera actually needs roughly **twice** that. Neither ptp2 budget explains it (old
`exp+30` = 60/71 s; new `2*exp+30` = 90/110 s). The match with the requested value
points at a timer above pgphoto — most plausibly `polestar_app` treating wall time as
≈ exposure, so it declares "shot failed" while the camera is still in its noise-
reduction dark frame. That also fits "it did recover soon after": the file lands once
the dark frame finishes, after the app has already given up.

**Not proven.** It needs one captured app-side run with the dial on B to confirm which
component emits the failure and at what elapsed time.

## Next step needed from you

1. **Put the dial back on B.** My timed tests moved it to a timed slot, which is why
every bulb request now returns `state:-6` in ~1.3 s instead of reproducing your
   failure.
2. Then run a 30 s Bulb from Benro Connect once. Live capture is running again
   (`out/bulb40s-20261023/{Clog,Mlog}-live2.txt`, polling every 4 s, appending
   host-side so Clog truncation cannot destroy evidence).

I need the app-side request and the elapsed time at which it declares failure. If it
fails at ~30 s while the camera needs ~63 s, the fault is a timer above pgphoto and
the `.69` dark-frame fix cannot address it — the fix would have to go where that timer
lives.

## Artifacts

- `Mlog-live.txt`, `Clog-live.txt` — 19:16–19:31 window (my tests; your run predates it)
- `shot40.json`, `shot40b.json` — bulb path, `state:-6`
- `timed40.json`, `timed50.json` — timed path, both PASS
