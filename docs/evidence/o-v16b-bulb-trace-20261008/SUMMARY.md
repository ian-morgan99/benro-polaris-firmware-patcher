# o-v16b (.61) bulb trace — the camera never fires (#186)

Device `6.0.0.54.61` (`o-v16b-empty-path-capture-20261008`), K-3 III `25fb:0189`,
boot 266, 2026-10-08 16:37 local. Diagnostic only: `STAGE2_CAPTURE_TRACE=1` set
in `/app/bin/pgphoto` for the run and restored to `0` afterwards. Raw extracts:
`capture-trace.txt`, `capture-264-lifecycle.txt`.

## What the trace shows

Two capture attempts, both through the Stage-2 hook:

```
[stage2-trace] capture-enter  seq=1 pid=251 type=0
[stage2-trace] capture-return seq=1 ret=-10      # GP_ERROR_TIMEOUT
[stage2-trace] capture-enter  seq=2 pid=251 type=0
[stage2-trace] capture-return seq=2 ret=-10
```

Each is followed in Clog by `captureImage[1579]:----captureImage ret 0  p:` and in
Mlog by the full success lifecycle `264 state:2 -> state:5 -> state:0`.

Consequences:

1. libgphoto2 returned **-10**, not `GP_OK`. The app's `ret 0` is its own
   variable; it discards the gphoto result. #183's premise ("GP_OK with an empty
   path") does not hold, and the `.61` empty-path conversion is inert — it never
   logged `capture-outcome=empty-path` across three failures with
   `STAGE2_CAPTURE_EMPTY_PATH_CHECK=1` confirmed in `/proc/<pid>/environ`.
2. The wrapper is installed and on the call path (the trace proves it); it simply
   never sees a `GP_OK` to rewrite.
3. The 66 s gap is our own wait, not an exposure:
   `PENTAX_CAPTURE_TIMEOUT_MS_BASE` is 60 s (`camlibs/ptp2/pentax-utils.h:145`),
   so the driver waits a minute for a candidate that never arrives.

## The camera never actuated

Operator observation, both the canary path and **Benro Connect itself**:

- no shutter sound or actuation at all, only a brief reflex twitch;
- Benro Connect bulb: live view stayed active ~9 s, no exposure, app stuck on the
  red button;
- no file created — newest on card remains `SP_0279` from 2026-10-07 21:48.

So #181's "the camera fires, the transfer is lost" is wrong: this is a **trigger
failure**, and it is not specific to our client.

## Not yet ruled out

- Camera state: electronic/silent shutter or a drive mode in which PTP capture is
  ignored would produce exactly this. Cheapest check, do it first.
- Whether the K-3 III accepts PTP `CaptureImage` while live view is active. The
  app path keeps LV running; the canary path that passes 16/16 forces preview off.
- The 268 list exposes no `Bulb` entry (stops at `00-30`); what the closed app
  writes before `264 state:1;bulb:N` is unknown.

Tracked in #186. `.61` remains the running build; its empty-path check is a
harmless no-op for this failure mode.
