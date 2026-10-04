# o-v15q Manual capture regression — 2026-10-04

Status: **REPRODUCED, root cause narrowed, not yet fixed.**
Tracked at [#172](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/172).

## Scope

Operator report after installing `o-v15q` (`6.0.0.54.54`):

> General stability is back, but the shot capture lifecycle is broken again.
> Shooting with Manual says 'Shot failed'.

Both halves confirmed. General stability is fixed (8 h uptime, code 780 clean,
no crash on interaction). Capture is not.

## Reproduced on demand

Camera enumerated as `25fb:0189`; code 286 reports
`pentax k-3 mark iii;state:1;storage:2;photoFormat:2`, so this is not a
presence problem.

```
TX 1&264&4&state:1;bulb:0;c:-1;#
RX 264@state:1#            <-- accepted
RX 264@state:-1005#        <-- terminal, ~0.3 s later
TERMINAL-FAILURE state=-1005
DONE states=[1, -1005] files=[]
```

No exposure, no state 4/0 completion, no code-773 publication, no file.
Newest file on the gimbal SD is `SP_0176.dng` dated **Oct 2 16:14** — nothing
has landed since.

## Where the refusal happens

`camera_pentax_capture_internal()` ordering in libgphoto2 `ee301fefe`:

```
6480  boundary=camlib-enter
6519  pentax_admission_block_reason(...)          <- strict +32/+36/+104 gate
6610  boundary=preconditions-enter
6634  baseline_reason = pentax_admission_block_reason(...)
6639  if (baseline_reason != PENTAX_ADMISSION_BLOCK_NONE)  -> refuse here
6758  boundary=initiate-enter                     <- never reached
```

A 0.3 s terminal means we bail at **6639**, before `InitiateCapture`. The reason
string is computed at 6554/6645 and written to stderr, but is not currently
captured: the live process runs with `STAGE2_CAPTURE_TRACE=0`.

Leading hypothesis: `PENTAX_ADMISSION_BLOCK_OUTPUT_UNRESOLVED` (line 6638) — an
unresolved/orphaned candidate holding the guard closed, i.e. the
`pending-candidate` row of `docs/PENTAX-CAPTURE-RECOVERY.md`.

## Capture-path deltas in the window

| Build | libgphoto2 commit | Capture qualified? |
|---|---|---|
| o-v15i (Oct 2) | `697907059` | **No** — camera absent, "no capture or Bulb canary was attempted" |
| o-v15n (Oct 3) | `e0e513502` | No |
| o-v15q (installed) | `ee301fefe` | No — fails as above |

`git log 697907059..ee301fef` is three commits; two touch capture:

* `e0e513502` — block unsafe K-3 III held-shutter action (release mode 2).
* `52196d9f1` — restore explicit timed capture route; candidate ownership changes
  from fail-closed to name-matching.

Because o-v15i was never capture-qualified, this cannot be called a proven
regression against a passing baseline. What is proven: no build since Oct 2 has
produced a file, and the capture path changed in exactly this window.

## Independent finding: preview dead + library re-init per request

```
Pentax preview stage get-frame returned 0xa008 (0 bytes, 30 attempts, 1230 ms).
Pentax preview stage restore-after-frame returned 0x2001.
[stage2] preview-backoff: 140 consecutive transient failures (last ret=-10) -- backing off 30s
```

Decoded: `0xa008` = Pentax **NoUpdateImage** (`pentax-utils.c:325`); `0x2001` =
`PTP_RC_OK` (the restore succeeded); `ret=-10` = `GP_ERROR_TIMEOUT`.
**140 consecutive** — preview has not produced a single frame.

The Stage-2 loader re-initialises the whole library per preview request inside
one process:

```
pgphoto pid = 250   (unchanged, starttime 211, uptime 6333 s)
restart_gphoto invocations = 0
"resolved 64/64" full dlopen cycles = 30   <-- one per preview request
```

Not the supervisor (no restarts). Something in the preview-backoff path tears
down and re-`dlopen`s core + port + 64 shims per attempt.

## Observability gaps

1. `STAGE2_CAPTURE_TRACE=0` in the live environment — the boundary markers the
   recovery map depends on are off.
2. `Mlog` rotates in ~50 s and only ever logs `type:2` traffic (`284`, `517`,
   `778`, `525`). It never records the `type:4` capture command, so it
   structurally cannot show the capture lifecycle.
3. A `stage2` SIGSEGV at 21:10 (`pc=0x00500046`, `si_addr=0x00500046`,
   `last checkpoint reached: slots filled`) — see `stage2-crash-device2110.log`.

## Not the cause

* Not the code-780 version patch (different binary; the version probe passes in
  the same session).
* Not camera presence — enumerated and identified correctly.
* Not the WiFi driver issue (#171) — stock `dhd` behaviour, independent path.
* Not a crash — `polestar_app` 249 and `pgphoto` 250 both survived.

## Next steps

1. Set `STAGE2_CAPTURE_TRACE=1`, re-run one Manual shot, capture the refusal
   reason from stderr.
2. Identify the unresolved output; decide whether an owner path is required or
   the guard is correctly blocking.
3. Stop the per-request library re-init, or prove it is intentional.
4. Only then re-attempt Bulb — after `52196d9f1` it shares
   `PENTAX_CAPTURE_TIMED`, so it will fail identically until Manual passes.

## Files in this directory

Filenames carry the **device-local** timestamp (the device clock is +3596 s,
≈1 h, ahead of the host) matching the times visible inside the logs.

| File | Contents |
|---|---|
| `Mlog-device2226.txt` | Mlog pulled before the controlled shot |
| `Clog-device2226.txt` | Clog pulled before the controlled shot |
| `Mlog-postshot-device2233.txt` | Mlog pulled immediately after the failed shot |
| `stage2-crash-device2110.log` | 21:10 SIGSEGV with full process maps |

Note: Mlog rotates in roughly 50 seconds and does not record `type:4` capture
traffic, so the post-shot pull does **not** contain the failed request. That gap
is itself finding 3 above.
