# o-v13c canary terminal -108 — 2026-09-26

- Branch: `release/o-v13d-review-convergence-20260926` (commit `03286f0`)
- Installed runtime: `6.0.0.54.27-o-v13c-boundary-trace`, libgphoto2 `4868d3649`
- Camera: Pentax K-3 III, RAW-only (`photoFormat:2`), storage 2

## Capture sequence (canary-shot.txt, UTC)

- 08:41:47Z probe: camera state 1, `photoFormat:2`; Preview stop acknowledged.
- 08:41:49Z shutter command 264 sent; lifecycle `[1]`.
- 08:41:52Z state 4 (exposure complete); lifecycle `[1, 4]`.
- 08:41:54Z state -108; `TERMINAL-FAILURE`; `DONE states=[1, 4, -108] files=[]`.

The updated fail-closed gate stopped after exactly one shutter command: no
retry, no second shutter. This is the first physical observation of the
negative-state stop path on a real body (the deterministic fixtures in
`tests/test_canary_two_shot.py` cover it offline).

## Interpretation

- The late `-108` notification matches the known Benro behaviour recorded in
  `o-v12h-recoverylog-2026-09-23/SUMMARY.md`: after a completed capture the
  daemon publishes a late negative state. It is a notification, not a new
  exposure; the gate must treat it as terminal for that operation.
- After -108 the camera returned to idle `state:0` and kept publishing mode
  and IMU frames; no second shutter was issued by the client.

## Log windows (local time, UTC+1)

- `Mlog-capture-window.txt` (09:42:58–09:43:04) starts ~60 s after the capture
  finished and contains only idle `state:0` pushes; it does not cover the
  capture states themselves.
- `Clog-capture-window.txt` (09:43:00–09:43:04) shows eight full Stage-2
  re-initialization blocks (mmap, dlopen of core/port, 64/64 slot fill) within
  four seconds. The camera-side process is cycling through reinitialization in
  this window; whether that is normal post-capture behaviour or a symptom of
  the -108 path is not yet established.

## Status

- Confirms: fail-closed single-shutter stop on a real body; late -108 after a
  completed RAW capture; camera back to idle afterwards.
- Still owed: physical recovery (next shutter after -108), Preview recovery,
  and post-failure idle qualification. Do not treat this run as a pass.
