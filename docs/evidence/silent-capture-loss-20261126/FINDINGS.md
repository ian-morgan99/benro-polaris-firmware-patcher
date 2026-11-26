# A capture reported success and told the client it was done; no file exists anywhere on the device

2026-11-26, K-1 II rig (v118, `o-v18a`), first capture after a reboot. This is a **silent data-loss / false
success** path, and it is distinct from the wedge investigated earlier today.

## The sequence

```text
[20:43:35:556] will captureImage status:1  sPath:/app/sd/normal/SP_0050.jpg
[pentax] capture=1 boundary=camlib-enter transfer=0 recovery=1 output_pending=0
[pentax] capture=1 boundary=preconditions-return ptp=0x2001 size=576
[pentax] capture=1 boundary=initiate-enter focus=2 companions=1
[pentax] capture=1 boundary=initiate-return ptp=0x200c
[pentax-recovery] capture=1 path=initiate reason=initiate-not-confirmed ptp=0x200c gp=-8 output_pending=0
                   action=do-not-replay-initiate; resolve-ambiguous-output-before-next-request
[20:43:41:960] captureImage ret 0            <-- success
```

`PTP 0x200c` is DeviceBusy. Our camlib did the right thing: it refused to replay, kept `output_pending=0`,
and returned an error (`gp=-8`) via `goto out` — `library.c` ends the capture path with `return ret`, so the
error is propagated by us.

**polestar_app then logged `captureImage ret 0`.**

## What the client was told

Every 264 frame sent for SP_0050, complete:

```text
val[state:1;focus:-1000;leve:1;b:0;path:/app/sd/normal/SP_0050.jpg;c:-1]
val[state:1;/app/sd/normal/SP_0050.jpg]
val[state:2;/app/sd/normal/SP_0050.jpg]
val[state:5; ]
```

No error frame. A client watching this believes the capture completed.

## The missing state:4 is the tell

Comparing with the last successful capture (SP_0049, same rig, 20:04):

```text
GOOD: state:1 -> state:4;K1II8836.JPG -> ret 0 -> state:2 -> state:3 -> state:5 -> state:1 -> state:1;ret:0
BAD:  state:1 ->                (no state:4) -> ret 0 -> state:2 -> state:5
```

`state:4` carries the camera's own filename and is the only frame proving an exposure actually produced an
object. It is emitted by **all 37** successful captures and by **none** of this one. Across all logs on the
rig there are **38 `captureImage ret 0` lines and only 37 `state:4` frames** — exactly one mismatch, which is
this event.

## The file does not exist

```text
$ find /app /tmp /var -name "SP_0050*"      -> (nothing)
$ ls /app/sd/normal/ | tail -1              -> SP_0049.jpg  (20:04, from the previous boot)
$ ls /app/sd/normal/SP_0050.jpg             -> No such file or directory
```

So: shutter never fired, no object on the camera, nothing downloaded, and both the app's return code and the
client-visible protocol say success.

## Where it is *not* our bug

Checked and ruled out:

- **Our camlib** returns the error correctly (`return ret` at the end of the capture path; `ret != GP_OK`
  branches preserve the candidate rather than clearing state).
- **Our stage2 shim** contains a false-success guard for exactly this class — issue #183, empty returned path
  — and passes `ret` through unchanged otherwise. It is on by default (`STAGE2_CAPTURE_EMPTY_PATH_CHECK`
  unset means enabled) and the code is present in the deployed binary:
  ```text
  $ strings /app/lib/stage2/libpolaris_stage2.so | grep -c "capture-outcome=empty-path"   -> 1
  ```

**Whether that guard is actually installed at runtime on v118 is not observable, and I initially overstated
this.** `stage2_capture_slot_target()` installs the wrapper silently:

```c
if (name && strcmp(name, "gp_camera_capture") == 0) {
    if (stage2_capture_trace_enabled() || stage2_capture_guard_enabled() ||
        stage2_capture_empty_path_check_enabled()) {
        g_real_gp_camera_capture = (stage2_gp_camera_capture_fn)resolved;
        return (void *)&stage2_guarded_gp_camera_capture;
    }
}
```

Unlike every other slot it has **no `fprintf`** — the boot log prints `storage: gp_camera_init slot -> shim`,
`capturetarget: gp_camera_set_config slot -> shim`, `shutter-fallback: ... slot -> shim (issue #187)`,
`preview-backoff: gp_camera_capture_preview slot -> shim`, and nothing for `gp_camera_capture`. So the
`0 hits` for `capture-outcome=empty-path` cannot distinguish "installed but not triggered" from "never
installed at all". My earlier wording — that it was skipped because `ret != 0` — is an inference from the
source, not an observation.

Settles in one capture: set `STAGE2_CAPTURE_TRACE=1` and take a shot. `[stage2-trace] capture-enter/return`
lines prove interception; their absence proves the slot was never wrapped, which would mean the #183 fix is
compiled in but inert on this build.

**The conversion point is not visible in this capture**: `STAGE2_CAPTURE_TRACE=0` on the deployed rig, so no
`[stage2-trace] capture-return seq=N ret=-8` line exists to show what the shim handed back. Enabling that
trace and reproducing would pin whether the loss is in pgphoto's error mapping or in polestar_app's handling
of it. I am not claiming which, because I have not observed it.

## Why this matters more than the wedge

A wedge is loud: every later capture returns `-1005` and the operator knows something is wrong. This path is
silent — one capture vanishes, the app says it succeeded, the client says it finished, and the user has no
photo and no error. For astrophotography sequences that means a missing frame in a stack with nothing to
indicate it.

## Relationship to #181

#181 ("First capture after a session re-establishment can be accepted then silently lost (no shutter, no
files)") matches the symptom and the trigger exactly — this is the first capture after a reboot, with
`[camera-usb] supervisor ready; identity=none` preceding it. What this occurrence adds is the mechanism
evidence: the camlib *explicitly reports* `initiate-not-confirmed ptp=0x200c gp=-8`, so the loss happens
above the camlib, and the `state:4`-absence test gives a cheap way to detect it.

## Detection already exists -- and already caught this

My first draft of this file proposed pairing `captureImage ret 0` against `state:4` as a new detector. That was
wrong: **`scripts/capture-outcomes.py` already implements exactly this** and classified the event correctly on
the first run, with no changes:

```text
classified PASS        : 37
classified FAIL        : 1
  rig_all.txt 20:43:41:956 FAIL    logged=-6249ms file=SP_0050.jpg states=[2, 5]
naive sign-based count : 38 -> over-reports by 2.71x
```

It reports SP_0050 as **FAIL** despite `ret 0`, precisely because `states=[2, 5]` contains no `4`. Its
docstring already warns against trusting the sign at all (issue #218: `capture end -23398 ms` is a *success*),
and notes that a naive sign-based analysis once produced "34 capture timeouts" and several failure modes that
did not exist. The 38-vs-37 counter pair in this file is therefore a cross-check on the tool, not a
replacement for it -- and the tool agrees with it.

The real gap is narrower than I first wrote: this classification exists as an **offline script** and nothing
runs it at runtime. The supervisor still reports `supervisor ready` throughout (#182), so a phantom success is
only discoverable after the fact by someone who thinks to run the analyzer over the logs.
