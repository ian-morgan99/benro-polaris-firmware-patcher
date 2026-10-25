# 40 s exposure with noise reduction on `6.0.0.54.69` — live hardware session, 2026-10-25

Rig awake (`FwVer:6.0.0.54.69;date:2026.10.23;`), K-3 III `25fb:0189` attached, RAW
(`photoFormat=2`). Clog polled host-side every 3 s so truncation could not destroy evidence
(#213). Protocol keepalive on 9090 every 30 s.

## Result 1 — the timed 40 s path PASSES, and the driver budget is not the limiter

```
07:33:06  CAPTURE state=1
07:34:29  captureImageEvent:0 Path:IMGP3976.DNG
07:34:29  capture end   -83196 ms        <- 83.2 s for a 40 s exposure
07:34:29  FILE /app/sd/normal/SP_0429.dng
07:34:29  PASS lifecycle=[1, 4, 0]       wall=87s
```

Reproduces the earlier 83.3 s / 87 s measurements exactly. The exposure plus its dark frame
needs ~83-87 s, and it succeeds.

`.69`'s driver budget for this case is **112 000 ms**, proven by `tests/test-pentax-utils.c:742-746`
built and run against `.69`'s bound sha (`731d7fbd5`), which exits 0:

```c
/* A long timed shutter is scaled exactly as a bulb would be, because it is
 * the same field: 41s + 41s + 30s. */
conditions.bulb_timer_seconds = 40;
conditions.bulb_timer_denominator = 1;
CHECK (pentax_capture_timeout_ms (&conditions) == 112000);
```

**This refutes the root cause written into #230's body.** Offset 272/276 is the live shutter
speed in *every* mode, not a bulb-only field — commit `731d7fbd5` exists precisely to pin that,
and it is already in `.69`. A timed 40 s exposure therefore gets the dark-frame allowance and
does not fall through to the un-margined 60 s base. Correction posted on #230; the proposed
fix there must not be implemented.

## Result 2 — #205 reproduced again, with fresh logs

`scripts/repro-app-bulb-request.py 40` (the app's exact frame `state:1;bulb:40;c:-1;`):

```
+  1.34s 264 state=1
+  1.38s 264 state=-6      <- terminal, 1.4 s after the request
```

Clog for that capture (`key-lines.txt`):

```
---bulb11 40000   --- /app/sd/normal/SP_0428.jpg
Camera-timed Bulb is active; use normal timed capture instead of the start/stop action.
Failed to set new configuration value 1 for configuration entry bulb.
capture_image_with_Bulb[3222]: CAPTURE bulb start  -6
```

Command 268 returned the full 57-entry list (`V:14`), so the dial was on a timed slot.

## Result 3 — scope of the failure is dial-position dependent (corrected against prior evidence)

Across every captured log in `docs/evidence/`, `CAPTURE bulb start` appears only as `-6` (4x) or
`-1` (1x). That on its own would suggest the held-shutter path never works — **but that reading is
wrong**, and prior evidence settles it:

Commit `ff39696` (2026-10-21, on `.68`) records **five consecutive in-B successes at 5/8/40/90/5 s**,
durations honoured to the millisecond, files on card, and states the app is mode-aware:

> `captureImage[1485]->captureBulbImage` (camera-timed, -6) versus
> `captureImage[1521]->capture_image_with_Bulb` (held-shutter, **works**)

So the held-shutter path does succeed — in B mode. The successful runs' Clogs were not preserved
(#213 truncation), which is why my grep found only failures.

My repro went through `captureImage[1521] -> capture_image_with_Bulb` — the *same* path that works
in B — and still got `-6`, with the dial on a timed slot. The refusal at `library.c:7104-7114` is
gated on `capability_flags & PENTAX_CONDITION_BULB_TIMER` (offset 504).

**Why this bit cannot be a pure capability flag:** if it were permanently set on the K-3 III, the
second check would refuse in B mode too, contradicting `ff39696`'s 5/5. So it must be
state-dependent — set when the camera reports a camera-timed bulb as active. My earlier capability
hypothesis is therefore refuted by that evidence and should not be pursued.

**Open question:** with the dial on a timed slot, why does the camera report camera-timed bulb
active at all? Candidates: a previous `bulb:N` request left the timer armed, or the bit tracks a
non-zero bulb-timer value rather than live exposure. Distinguishing them needs offset 504 read with
the dial on B versus on a timed slot. `/app/bin/gphoto2` cannot claim the interface while pgphoto
holds it (`Could not claim interface 0 (Device or resource busy)`), so this needs either a
pgphoto-free session or the app-side run below.

## Still needed to close #230's real cause

The evidence file `docs/evidence/bulb40s-20261023/SUMMARY.md:160-186` already points at a timer
**above pgphoto** — `polestar_app` appearing to declare "shot failed" at roughly the *requested*
duration while the body needs ~2x that for its dark frame — and labels it "Not proven". Settling
it needs one run that cannot be produced from a timed slot:

1. Dial physically on **B**.
2. One long exposure from Benro Connect (30 s or 40 s, noise reduction ON).
3. Record the elapsed time at which "shot failed" is emitted versus when code 773 delivers the
   file.

If it fails near the requested duration while the file lands ~2x later, the fault is an app-side
timer and no libgphoto2 change can address it.

## K-1 II

Not attached this session (only `25fb:0189`). #232/#233/#234/#235 cannot be reproduced or fixed
without a `25fb:0183` body.
