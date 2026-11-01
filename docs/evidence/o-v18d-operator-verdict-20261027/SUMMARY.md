# `.74` operator verdict — 2026-10-27 — "working really well"

Reported by the operator (ian-morgan99) on 2026-10-27:

> v74 was working really well.

Candidate: `o-v18d-shutter-list-always-populated` -> `FwVer:6.0.0.54.74;date:2026.10.27;`
zip md5 `307d8bd4ca4264973a16df0d0586de48`, libgphoto2 `8db3785f7`, patcher `ffb2e50`.

## What this establishes

This is the first positive **hardware** result for either of `.74`'s two fixes.
Both were previously recorded as "installed, canary pending" because no camera was
attached at install time.

| fix | issue | status before | status now |
|---|---|---|---|
| timed Bulb duration from the measured hold | #243 | unqualified | **operator-confirmed working** |
| shutter list always populated (B/no-JPEG) | #241 | unqualified, cause inferred | **operator-confirmed working** |

For #241 this is materially stronger than an anecdote. The fix was derived by
inference: the empty list was *proven* specific to the B/no-JPEG state and to
precede the exits, but that it was what Benro Connect crashed on had not been
demonstrated, because the app is closed and no captured log has an app-side stack.
The operator running `.74` without a crash is the first evidence in favour of that
inference holding in practice.

## What this does NOT establish

Recorded so the verdict is not over-read:

- It is **operator feedback**, not a coded regression result. No `--canary` or
  `--two-shot` transcript was captured for `.74`, and no `ShutterSpeedValue` was
  read back from a produced file on `.74`. The duration fix rests on the operator's
  observation, not on a measured EXIF value.
- It does not say which specific scenarios were exercised. In particular it does
  not distinguish: timed Bulb at a selected second-count, non-timed B, and the
  mode-dial change (M -> B) — all three were open on #241/#243.
- It does not cover the K-1 II matrix (#217), which has never been run against any
  candidate.

So `.74` moves from "installed, canary pending" to **"operator-confirmed working,
no coded qualification transcript"**. #241 and #243 stay open until the coded
regressions exist and pass — which is what `.75` plus the new test round is for.

## Consequence for `.75`

`.75` (`o-v18e-fail-closed-bulb-shutter`) adds, on top of `.74`:
- the Bulb shutter write **fails closed** and is verified by readback before any
  capture starts (#239 review);
- the empty-list synthesis is gated to the K-3 III only (#241 review).

Because `.74` is confirmed good, `.75` must be tested as a **regression risk**, not
just an improvement: the fail-closed path can now refuse a capture that `.74` would
have taken, and the model gate can now withhold a list `.74` would have synthesised.
The test round is therefore weighted toward proving `.75` does not lose what `.74`
fixed.
