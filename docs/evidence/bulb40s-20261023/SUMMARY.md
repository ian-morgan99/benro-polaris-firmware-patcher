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

## Next step needed from you

Live capture is running again (`out/bulb40s-20261023/{Clog,Mlog}-live2.txt`, polling
every 4 s, appending host-side so Clog truncation cannot destroy evidence). **Please
run the 40 s Bulb from Benro Connect once more.** I need the app-side request and the
exact moment it declares failure — that is the only way to tell whether the ~40 s
failure is an app-side timer or something in our stack.

## Artifacts

- `Mlog-live.txt`, `Clog-live.txt` — 19:16–19:31 window (my tests; your run predates it)
- `shot40.json`, `shot40b.json` — bulb path, `state:-6`
- `timed40.json`, `timed50.json` — timed path, both PASS
