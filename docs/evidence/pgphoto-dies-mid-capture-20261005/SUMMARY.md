# pgphoto dies mid-capture — the upstream cause of both the Manual and Bulb failures

Date: 2026-10-05 (device clock is UTC+1; device 20:44:17 == 19:44:17Z)
Status: **ROOT CAUSE IDENTIFIED, reproduced on demand, not fixed.**
Tracked: parent of [#172](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/172),
origin of [#175](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/175),
currently blocking [#173](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/173).

Logs analysed: `/app/sd/system/log/Clog_000249.log`, `Mlog_000249.log`
(local copies under `out/logs/device-20261005/`).

## 1. Plain answer

**Manual and Bulb now fail for the same reason, and it is not the admission
gate.** The capture process (`pgphoto`) **dies during every capture**, after the
shutter has been released and before the camera's file event arrives. The stock
app's own watchdog notices and restarts it:

```
[20:44:17:648] capture_image: ---- will CAPTURE_IMAGE
[pentax] capture=1 boundary=initiate-return ptp=0x2001     <-- shutter fired, PTP OK
                 ... 14 s of complete silence ...
[20:44:30:578] ERROR checkGphotoTask: pgphoto is exit, reboot it   <-- app watchdog
[20:44:31:514] ------/app/lib/stage2/pgphoto.stage2ondisk: version: 1.3.4 ...  <-- new process
```

The photograph is taken. The session that owed it a download is gone, so nobody
fetches it, nothing is written to `/app/sd/normal/`, and the app reports failure.
**Zero files exist between SP_0225 and SP_0232** — eight consecutive attempts,
all with the shutter actually firing.

**And the death is a signal: `SIGILL` (4), caught directly as
`wait_status=132` — see section 8.** It is not a deliberate `exit()`, and it is
not the slot-page null jump our own crash handler was written for (that handler
printed nothing).

## 2. Direct proof, not inference

A single controlled capture with the process identity sampled on both sides:

```
pgphoto PID before: 25668
  -> capture issued, no state:4, no 773, TimeoutError
pgphoto PID after:  23766
>>> PROCESS DIED DURING CAPTURE (confirmed)
```

Correlation across the whole log (device clock):

| signal | count | times |
| --- | --- | --- |
| `initiate-return ptp=0x2001` (shutter accepted) | 17 | 16:17–16:29 ×13, 18:50, 20:44, 20:45, 21:22 |
| `pgphoto is exit, reboot it` (app watchdog) | 3 | 18:50:19, 20:44:30, 20:45:47 |
| pgphoto process starts visible in the SD log | 10 | only **5** of which are supervisor-initiated |
| camera file events / files saved to album | 38 / 26 | **last one at 16:29:28** |

A fourth death at 21:23:13 is established from `/proc` rather than from a log
line (section 9c) — it is the reason the "10 starts" and "3 watchdog reboots"
figures under-count: a watchdog restart writes to `/app/Clog.txt`, not the card.

Every capture from 18:50 onward is followed within ~15 s by a process death.
The last capture that worked (16:29, `SP_0224`) shows the healthy path for
comparison — `New file is in location` → `ARG_CAPTURE_IMAGE 0` →
`gp_file_get_data_and_size ret = 0` → `savePhotoToAblum ... ret 0`, all inside
5.2 s.

Five of the ten process starts have **no supervisor restart logged at all**.
They are the app's `checkGphotoTask` watchdog resurrecting a process that died
on its own. That is why the deaths were invisible until now: the recovery looks
like normal operation.

## 3. This is not caused by the o-v15s install

`/app/lib/stage2/libgphoto2.so.6` has mtime **20:14:10** (my reversible install).
The first death is at **18:50:19** — 84 minutes earlier, on the o-v15r
libraries. The crash is present on o-v15r too, and the mechanism is upstream of
any Stage-2 library change.

## 4. This is the origin of the #175 orphan

SP_0225 — the object whose uncaptured handle latched the pre-shutter gate and
produced every `-110` since — was created by exactly this crash:

```
[18:50:02:805] SP_sendMsg code[264] path:/app/sd/normal/SP_0225.jpg
[pentax] capture=1 boundary=initiate-return ptp=0x2001     <-- camera took the shot
[18:50:19:118] ERROR checkGphotoTask: pgphoto is exit, reboot it
```

So the causal chain is:

```
pgphoto dies mid-capture
  -> photo exists on the camera, no session left to download it  (orphan candidate)
  -> new process sees a candidate it does not own
  -> pre-shutter admission gate refuses forever (-110)            [#175]
  -> app reports -1005 for every later capture                    [#172]
```

#175 fixes the **second** half. It does not touch the first half, and the
orphan it was written to recover is a symptom of this crash.

## 5. Why the canary saw an instant `-1005`

Classifying every code-264 request in `Mlog` by whether it reached gphoto:

| window | path | result |
| --- | --- | --- |
| 16:26–16:29 | forwarded to gphoto | `state:1` → file (healthy) |
| 19:53 | **refused by the app itself** | `-1002` (no camera session) |
| 20:44:20, 20:44:26, 20:44:53, 20:44:56 | **refused by the app itself** | `-1005` |
| 20:44:17, 20:45:35 | forwarded | `state:1`, shutter fires, then process dies |
| 20:45:57, 20:45:59, 20:46:01 | forwarded | `state:-1` / `state:1` then death |

`-1005` is now generated **inside the app, without reaching libgphoto2 at all**,
whenever it has no live capture session. That is why the armed five-shot run
failed in under a second on shot 1 and why no `[pentax]` line accompanied it.
It is also why `-1005` must be triaged into "guard refused" vs "no session to
ask" — the same distinction already recorded for `-1002` in
[o-v15q-manual-capture-regression](../o-v15q-manual-capture-regression-20261004/SUMMARY.md).

## 6. Bulb specifically

Bulb is not separately broken. `bulb:5` requests at 20:44:53 and 20:44:56 were
refused by the app with no session at all; at 20:45:35 the request was
forwarded, `initiate-return ptp=0x2001` succeeded, and the process died at
20:45:47 — 12 s into a 5 s exposure plus write-down, i.e. the same failure.
**The #173 EXIF/shutter verification still cannot be run**, because no capture
survives long enough to produce a file to inspect.

## 7. What is NOT the cause

- Not the pre-shutter admission gate: `path=recovery-probe` refusals stop at
  19:21, and captures after 20:44 reach `initiate-return`.
- Not the #175 fix. (This bullet was written against a 21:10 log copy and read
  "0 occurrences, still unexercised" — see section 9 for the correction. The
  claim path has since run, it did unblock the gate, and it is not what kills
  the capture.)
- Not OOM: 1.4 GB free, `dmesg` has no OOM/killer entries.
- Not OOM, and not a kernel-visible fault in `dmesg` (no `traps`/`segfault`).
  That last point is now explained rather than assumed: the death is `SIGILL`,
  which the ARM kernel does not report as a `traps` line, and the core the
  kernel did write was `/app/sd/core` at **0 bytes** because `core_pattern=core`
  is a single fixed name on a vfat mount.

## 8. THE DEATH IS A SIGNAL: `SIGILL` (4) — not `exit()`

The bullet above ("not a `SIGSEGV`/`SIGBUS`/`SIGILL` inside our stack") was
written before the probe existed and is now wrong on the signal number. The
wrapper `exec`s pgphoto, so the wait status was being discarded. Replacing that
one `exec` with a subshell + `wait` (TERM/INT/HUP forwarded, so the #33/#34
single-owner semantics are unchanged) gives it directly:

```sh
( ulimit -c unlimited; cd /app/sd; exec "$D/pgphoto.stage2ondisk" "$@" ) &
PROBE_PID=$!
probe_forward() { kill -TERM "$PROBE_PID" 2>/dev/null; exit 143; }
trap probe_forward HUP INT TERM
wait $PROBE_PID
PROBE_RC=$?
echo "[probe] pgphoto pid=$PROBE_PID wait_status=$PROBE_RC $(date)" >&2
```

Device backup of the unmodified wrapper: `/app/sd/pgphoto.wrapper.probebak`.

```
[22:15:01:548] ---- will CAPTURE_IMAGE
[pentax] capture=1 boundary=initiate-return ptp=0x2001
<nothing>
[probe] pgphoto pid=32008 wait_status=132 Mon Oct  5 22:15:05 UTC 2026
[probe] interpretation: killed by signal 4
```

`132 = 128+4` → **SIGILL**, 4 s after the shutter was accepted. So:

- it is **not** a deliberate `exit()` from a capture-failure handler;
- **Our own crash handler is not a reliable witness.** `stage2_crash_handler()`
  is installed for SIGILL at load time (`install_crash_handler()`,
  `container/stage2_loader.c:1271`) and writes `si_addr`, the PC, a PC
  classification and the last checkpoint to fd 2 before re-raising. It printed
  **nothing** for pid 32008, even though fd 2 of that process demonstrably
  reached the card — the `[pentax]` lines above and the `[probe]` line below it
  are in the same stream, and the probe line survived. So the fault is either
  raised where the handler cannot run, or the disposition is retaken after our
  constructor. A later process does report `SigCgt: 0000000188001e48`
  (bits for SIGILL/SIGBUS/SIGSEGV set) and `SigIgn: 0x6` (which decodes to
  SIGINT+SIGQUIT, *not* SIGHUP+SIGINT — corrected after re-reading the bitmask),
  but that is a *different* pid from the one that died, so it does not tell us
  what disposition pid 32008 had at the moment of the fault. Until that is
  settled, the probe's wait status is the only dependable signal record. The
  probe now also samples `SigBlk/SigIgn/SigCgt` of the child 5 s after start, so
  the next death can be attributed to a known disposition.

A second death at 22:24:20 read `wait_status=143` → **SIGTERM**, and that one
*was* deliberate: `[restart_gphoto] stopping pgphoto (PID 10238)` immediately
before it, triggered by the USB supervisor. So the probe distinguishes the two
cases cleanly, which is exactly the discrimination this issue needed.

## 8b. Next diagnostic step

Steps 1 and 2 of the original plan are done — see section 8. The death is a
signal (`SIGILL`), so the "find the `exit()` path" branch is closed. What
remains, in order of value per unit of camera risk:

1. Get the faulting instruction, not just the signal number. Re-assert
   `install_crash_handler()` at capture entry (or install it after pgphoto's own
   signal setup) so the handler is provably the disposition at fault time, then
   take one capture. If it still prints nothing, the fault is raised somewhere
   our handler cannot run, which is itself the answer.
2. Make cores readable. `core_pattern=core` plus a vfat cwd produced a 0-byte
   `/app/sd/core`; use a `%p`-suffixed pattern and a UBIFS/ext4 target so
   successive crashes do not collide. (No `strace`/`gdb`/`ltrace` on the
   device, so a core is the only way to get a stack.)
3. ~~Cheapest discriminator for ownership: does the stock
   `/app/sd/pgphoto.prestage2.bak` binary also take SIGILL mid-capture?~~
   **Invalid as written — there is no stock ELF to A/B against.**
   `/app/sd/pgphoto.prestage2.bak` is byte-identical to our own wrapper (md5
   `8509cebb…`), and the firmware-extracted `/app/bin/pgphoto` is also a shell
   script. The real discriminator is now much cheaper anyway — see section 11:
   run `pgphoto.stage2ondisk` with the Stage-2 `LD_PRELOAD` removed and take a
   *first* capture in a fresh process.
4. Make the stock watchdog report what it saw. `checkGphotoTask` logs only
   "pgphoto is exit,reboot it"; the wait status is available to it and would
   have answered this in one line months ago.

Caveat that applies to all of the above: every restart risks the camera. The
K-3 III dropped off USB again at 22:24 during this measurement
(`[camera-usb] quarantined identity none ... bounded rebind failed; remaining
degraded`) and needed a power cycle (#146).

## 9. CORRECTION — the #175 claim path HAS now run on hardware

Section 7 said `path=orphan-recovery` appears 0 times. That was measured on the
`Clog_000249.log` copy taken at 21:10. A fresh copy taken at 21:42 contains it:

```
[21:22:59:273] capture_image: ---- will CAPTURE_IMAGE
[pentax] capture=1 boundary=preconditions-return ptp=0x2001 size=576
[pentax-recovery] capture=1 path=orphan-recovery outcome=cleared recovered=1
                  names=IMGP3794.DNG accepted=1
                  action=preserve-then-delete-only-after-verified-download
[pentax] capture=1 boundary=initiate-enter focus=2 companions=1
[pentax] capture=1 boundary=initiate-return ptp=0x2001
```

So the gate **did** unblock by claiming the orphan rather than by a process
restart, and the shutter proceeded in the same call, exactly as #175 specifies.
The earlier conclusion ("still unexercised") was an artefact of analysing a
stale log copy — the same trap as section 1's clock offset.

Two things follow, both now filed:

**(a) The claimed frame is discarded, not preserved.** `IMGP3794.DNG` exists
nowhere on the SD card (`find /app/sd -name 'IMGP3794*'` → nothing). In
`camlibs/ptp2/library.c`, `pentax_reconcile_transfer_candidate()` downloads the
object into an in-memory `CameraFile` and `pentax_capture_publication_add()`
only stores a reference in `params->pentax.capture_publications[]`;
`pentax_recover_orphan_candidates()` then calls
`pentax_capture_publications_clear()`, which `gp_file_unref`s it. Nothing ever
writes the buffer to a path. The log line's own promise —
`action=preserve-then-delete-only-after-verified-download` — is only half true:
the object is deleted from the camera after a verified *download into RAM*, and
the frame is then lost. The unblocking works; the rescue does not.

**(b) The capture still failed, and the process died again.** SP_0233 shows
`state:1` at 21:22:59 and then nothing — no `state:3`, no code 773, no file.
The running pgphoto (PID 23766) started at device **21:23:13**, i.e. ~14 s
after the shutter, from `/proc/23766/stat` starttime `2008039` against
`/proc/uptime`. Same signature as sections 1–2.

**(c) The process that killed this capture left no startup trace on the card.**
There is no `checkGphotoTask` line and no `[camera-usb] stable identity change`
line anywhere near 21:23, and there is **no version banner after Clog line
17948** — the reliable process-start marker of section 2 is absent for this
start, even though the file continues to 21:23:37.

The mechanism is a log-destination split. pgphoto's own stdout/stderr goes to
`/app/Clog.txt` on UBIFS, and the stock app is what copies that onto the card:

```
strings /app/bin/polestar_app:
    cat /app/Clog.txt >> /app/sd/system/log/Clog_%06d.log
    > /app/Clog.txt
ls -l /proc/23766/fd/{1,2} -> /app/Clog.txt
/app/Clog.txt: 0 bytes, but /proc/23766/fdinfo/1 reports pos: 108830
```

So ~108 KB was written to that fd and then truncated away by the rotation step,
and the SD-side `Clog_000249.log` stopped growing at 21:24. `/app/restart_gphoto`
uses `LOG=${OPENPOLARIS_PGPHOTO_LOG:-/app/Clog.txt}`, a different destination
from the boot-time launch. The practical effect: whether a given capture's
`[pentax]` trace survives on the card depends on whether the app happened to
rotate before the process died. That is the second reason these deaths have been
invisible, and it means the single most important capture — the one that just
died — is the one we have no trace of.

## 10. Consequence for release qualification

Consistent with the review on #175: o-v15s is an **experimental hardware
candidate**. It cannot be qualified by repeated-shot testing on this device
until the mid-capture death is fixed, because the test's precondition — a
capture that completes — is what currently fails.

## 11. SECOND FINDING — the deaths are concentrated on the *first* capture of a process

Re-correlating all three log copies by capture (correcting an earlier off-by-one
in which the `[pentax-recovery]` line was attributed to the *next* capture; it
belongs to the capture that prints it, immediately before `initiate-enter`) gives
23 attempts:

| window | attempts | outcome |
|---|---|---|
| 16:17–16:29, one long-lived process, `capture=1..13` | 13 | **13 OK** |
| 18:50, first capture of a new process | 1 | DIED |
| 18:52 / 19:12 / 19:21 | 3 | fail-110 (gate, #175) |
| 20:44, 20:45, 21:22, 22:12, 22:15 — all `capture=1` | 5 | DIED / fail-1 |
| 22:23, first capture of a new process | 1 | **OK** |

Split by position in the process rather than by time:

* **first capture in a process: 2 OK, 7 not-OK**
* **second and later in the same process: 12 OK, 0 not-OK**

One-sided Fisher exact **p = 0.00031**. This is the first discriminator this
issue has had, and it is the opposite of what "the camera is flaky" predicts.

Two consequences that matter more than the statistics:

1. **The 13-shot run at 16:2x is the real baseline and it is still valid.** It
   was one process taking 13 captures in 3 minutes with a 100% success rate. The
   "Manual has regressed" reading came from comparing *first-captures* against
   that run, which is a different population.
2. **The successful 22:23 capture did not photograph anything new.** It
   downloaded and deleted `IMGP3797.DNG` — the file the *dead* 22:15 process had
   left on the camera. So the camera completed that exposure; only pgphoto's
   wait did not survive it. Every "success" must therefore be checked for
   whether the file it reports is the one it just made.

The window in which the process dies is now narrow and specific: after
`boundary=initiate-return` and before the first candidate/event, i.e. inside the
post-initiate conditions-probe and wait loop (`library.c` ~7080 onward). What
runs there on a first capture and not on a later one is the obvious thing to
look for next; the `LD_PRELOAD`-off A/B in §8b step 3 is now cheap because we
know a *first* capture is the one that reproduces it.

## 12. THIRD FINDING — #173: the Bulb duration is settable; the Bulb path never sets it

The claim "Bulb duration is ignored" was tested directly against the descriptor
(`Pentax Shutter/Bulb Descriptor`, printed by `print_widget`):

```
18:49:38  Mlog: code 261 val[s:44;] -> ret:0     (index 44 = 00-03)
18:50:02  Mlog: code 261 val[s:45;] -> ret:0     (index 45 = 00-04)
18:50:35  Clog: bulb-seconds=4/1  bulb-timer=no  <-- the camera accepted it
20:44:53  Mlog: code 264 val[state:1;bulb:5;]    <-- bulb:5 requested
20:44:47  Clog: bulb-seconds=1/4                 <-- and never changed
```

Between the `bulb:5` request and the capture there is **no command 261 write at
all** — only reads (`command 29`, `current_shutter`), which keep reporting the
pre-existing `s:1/4`. So the duration is *not* rejected by the camera; the
Bulb code path simply never issues the shutter write that a Manual capture does.
That is a narrower and much more tractable defect than "the K-3 III ignores
Bulb durations", and it is testable without a long exposure: request `bulb:5`,
assert a 261 write, assert the descriptor reads `5/1` before `InitiateCapture`.

Note `bulb-timer=no` in every sample including the accepted `4/1`. Whether the
K-3 III needs the bulb-timer property as well for a *timed* bulb is untested
and is the next question after the missing write is fixed.

### 12b. Why #173 was misdiagnosed: the 261 write applies *asynchronously*

The canary already writes the shutter before a Bulb shot (`ce94298`, 19:22), so
"the Bulb path never writes it" is only true of the stock app, not of our test.
The reason our own test still reported failure is in the verification, and the
logs show it exactly:

```
18:49:41  WRITE s:54;                       (ret:0)
18:49:42  268 V = 33        <-- still the old index, 1 s later
18:49:54  268 V = 54        <-- applied, ~13 s after the write
```

`set_shutter()` read the state back **once, immediately**, saw the old index and
raised "accepted (ret:0) but the camera reports V:33". The camera was not
refusing the duration; it was honouring it a few seconds later than the check.
That false failure is what turned "Bulb duration is ignored" into a stated
property of the K-3 III.

Fixed in `scripts/canary-probe.py`: the readback is now polled inside a bounded
budget (`SHUTTER_SETTLE_TIMEOUT_S`, default 30 s, 1 s apart) and only fails once
the budget is exhausted. Three tests in `tests/test_canary_bulb.py` cover it —
a late-apply that must now pass, a never-apply that must still fail closed, and
the existing immediate-failure case. 125 tests pass across the canary/bulb pack.

The practical consequence for #173: the acceptance test the review asked for
(requested duration -> camera readback -> captured file -> EXIF duration) is
viable, because the second step now works. It was blocked behind a harness bug.

## 13. WHAT THE USER ACTUALLY SEES — the death produces *two* different UI symptoms

Everything above answers "why does the capture fail". It does not answer "what
does the app do about it", which is the part that was actually reported from the
camera: *'Shot failed'* on one hand, and *the red button kept spinning* on the
other. Those are the same fault, and the difference between them is whether
anything tells the app the process died.

`SP_SendMsgToApp` for code 264 has **two different producers**, distinguishable
on the wire:

```
type[1],code[264],val[state:-1005]    <-- the camlib's own reply (a real refusal)
type[2],code[264],val[state:-1005;]   <-- polestar_app synthesising a failure
```

The `type` field and the trailing `;` separate them. Cross-referencing every
app-facing 264 in `Mlog_000249` against the capture table in §11:

| capture | app sees | how |
|---|---|---|
| 18:52, 19:12, 19:21 (the #175 gate) | `state:1` → `state:-1005` in 0.3 s, `type[1]` | genuine guard refusal |
| 20:44 (pgphoto dies) | `state:1` → `state:-1005` **3 s later**, `type[2]` | app noticed the process gone |
| 21:22:59 (pgphoto dies) | `state:1` → **nothing** | no terminal state, ever |

After the 21:22:59 death the app never receives another 264 for that capture —
zero occurrences in the log. `state:1` means "accepted, shooting", so the UI is
left in the shooting state with nothing to clear it. **That is the spinning red
button.** It is not a UI bug; it is a missing terminal transition.

So the honest account of the user-visible failure is:

1. The camera usually *does* take the photograph (the exposure completes; the
   file lands on the card as `IMGP379x`).
2. pgphoto dies of SIGILL during the wait, so the completion is never reported.
3. Depending on timing, the app either invents a failure (`-1005`, "Shot
   failed") or hears nothing at all (button spins forever).

Neither of those is what #172's title describes. #172 records `state:1 →
state:-1005 in 0.3s (refused before InitiateCapture)` — that is the `type[1]`
producer, and it is a real, separate defect (the #175 gate). The `type[2]` and
silent cases are #176 masquerading as #172. Any triage that reads only the state
code conflates three different faults into "Shot failed".

### The one-line discriminator to use until #176 is fixed

`-1005` arriving on **`type[2]`, seconds after `state:1`** = pgphoto died.
`-1005` arriving on **`type[1]`, within ~0.3 s** = the pre-shutter guard refused.
No reply at all after `state:1` = pgphoto died and the app did not notice.

### What this makes fixable independently of the SIGILL

Even before the crash is understood, the *silent* case is a defect in its own
right: a process that owns an accepted capture must not be able to vanish without
a terminal state. `restart_gphoto` already knows the process went away, and the
stock `checkGphotoTask` watchdog restarts it — neither publishes a failure for the
in-flight generation. That is a small, testable change in the supervisor/watchdog
path, it does not touch the Pentax capture code, and it converts "spins forever"
into an honest failure. It will not make captures succeed, but it will stop the
UI lying about them.

Feasibility caveat, checked rather than assumed: there is **no existing mechanism
in `container/ondisk/*.sh` to inject an app-facing IPC message** — nothing there
even references code 264. The `type[2]` failure the app synthesises at 20:44
comes from inside `polestar_app` itself, which we patch by byte-patch but do not
own. So "publish a terminal state" is not a shell-script change; the realistic
options are (a) find and widen the condition under which `polestar_app` already
produces the `type[2]` failure, since it demonstrably can, or (b) have the
supervisor treat "accepted capture + process gone" as a first-class event and
force the same path. Option (a) is cheaper and should be tried first.

---

## 14. FOURTH FINDING — "Bulb still fails" on v15r is a self-locking admission gate, not a Bulb fault

Reported by the user as *"Manual shooting seems ok, but bulb still fails"* on `.55`.
Reproduced live at ~01:0x UTC 2026-10-06 and read back through `Clog_000250`
(`out/logs/device-20261006/c2.log`). The two symptoms are two events in one log,
and the second has nothing to do with Bulb.

| capture | mode | outcome |
|---|---|---|
| 1–4 | Manual | reached `state:5` — "Manual seems ok" confirmed |
| 4 | Manual | `capture end -66252 ms`, `ERROR: Could not capture image`, **yet the app still received `state:2` (`SP_0240.jpg`) + `state:5`** |
| 5 | Bulb 5 s | refused pre-shutter, `path=pre-shutter reason=output-obligation-unresolved` |
| 6 | Bulb 5 s | refused again, `path=recovery-probe reason=output-obligation-unresolved` |

Both refusals carry `field32=0x00000000 field36=0x00000000`: the camera reports
nothing active and nothing pending.

### The camera passed its own readiness check; only our bookkeeping failed it

`field104=0x20000000` is **not** in `PENTAX_CONDITION_ACTIVITY_UNSAFE`
(`0x00109a03`), so `pentax_admission_block_reason(..., STRICT)` returned `NONE`.
The block was manufactured entirely by our own `capture_output_pending` flag,
which capture 4 left set when its wait timed out.

### Why it never recovers

`capture_output_pending` is set before `InitiateCapture` and cleared in exactly
two places: an explicit non-ambiguous initiate rejection, and the publication of
every expected output. A capture abandoned on the wait timeout reaches neither.

Both admission gates then promote `NONE` → `OUTPUT_UNRESOLVED` purely because the
flag is set — the preconditions gate (capture 5) and the recovery probe (capture
6). Every escape route then tests the one thing that can only be cleared by the
publication that will now never happen: `pentax_recovery_probe_can_clear`
requires `NONE && !pending`, and `pentax_orphan_candidate_claimable` deliberately
excludes `OUTPUT_UNRESOLVED` because it is derived from that same flag. So the
lock is permanent until process restart — a self-locking bug in the gate shipped
for #172/#175.

This also explains the *apparent* Bulb-specificity: Manual looks healthy until a
Manual capture times out, and whatever request comes next inherits the lock.

### Fix

`98ee8e67a`. The flag is bookkeeping, not a measurement, so only the camera is
allowed to contradict it. `pentax_output_obligation_releasable` releases it when
a readable conditions frame positively reports no active exposure and no candidate
on the body. Anything ambiguous stays fail-closed; a frame that really did land
without being downloaded still presents a candidate and is claimed as an orphan
(#175) rather than dropped. The three sites that derived the block independently
now share one helper.

Unit-tested. **Not yet physically verified** — clearing the latch with
`restart_gphoto.sh` dropped the K-3 III off USB again (#146) and needs a power
cycle. Acceptance, in order:

1. Manual capture, let it time out deliberately, then confirm the *next* request
   is admitted instead of refused with `output-obligation-unresolved`.
2. Bulb 5 s completes and produces a file whose EXIF duration matches the request.
3. Only then treat #173 as closed. A `state:5` alone is not the acceptance test.

---

## 15. o-v15t (`.57`) built, gate-passed, and staged on-device — awaiting one power cycle

**Artifact.** `out/o-v15t-admission-deadlock-and-durability-20261006/FwPkt.zip`,
md5 `d841983329a1bae74fc74a6929aef5bb`, published to PrivateResearch at
`c72b70219`. Display version `6.0.0.54.57`, derived by the allocator (not typed),
registry updated in `3e043ea`. `.56`/o-v15s is marked **superseded, do not flash** —
it was never installed and its content is a strict subset of `.57`.

**Verified in the artifact, not just in the source SHA.** `strings` on the packaged
`stage2-ondisk/libgphoto2/2.5.34/ptp2.so` finds all four fixes by their log
signatures: `path=obligation-release` (#173), `outcome=destination-unavailable`
and `no durable owner was established` (#176 review), `orphan recovery: wrote`
(#176). A provenance row naming a commit is not evidence the binary contains it.

**Staged live on the device while the camera was off USB.** Only `ptp2.so` differed
from what was already installed — `libgphoto2.so.6` and `libgphoto2_port.so.12`
matched byte for byte — so exactly one file was swapped:

- live `/app/lib/stage2/libgphoto2/2.5.34/ptp2.so` → md5 `99657b5f…` (v15t);
- previous file preserved at `/app/sd/ptp2.so.pre-v15t-4d592aad.bak`;
- scp's sftp subsystem is unavailable on this device; `cat | ssh "cat > file"` via
  `/app/sd` works and was verified by md5 on both ends.

Doing this now rather than after the power cycle matters: `restart_gphoto` is what
drops the K-3 III off USB (#146), so a camera that is *already* detached costs
nothing to restart. When the camera comes back it should attach to the fixed
library with no further restart.

**The restart loop is not the new library — A/B proved it.** After the swap pgphoto
churned (new PID every ~10 s, 8080 flapping). Restoring the previous `ptp2.so`
produced **identical** churn, so the cause is the camera being absent, matching the
existing #119 path:

```
[camera-usb] quarantined identity none stable for 9 polls but bounded rebind
             failed; remaining degraded (issue #119)
```

The new library itself loads cleanly: `dlopen core ok`, `resolved 64/64`,
`slots filled 64/64`, no symbol or version errors.

**One operational trap hit and cleared.** `/app/restart_gphoto` refused to run with
`another restart owns /var/run/openpolaris-pgphoto.restart.lock`. The lock held
`pid=18006`, dead since 00:22 — the script's `trap 'rm -rf "$LOCKDIR"' EXIT` does
not run when the process is SIGKILLed, so a killed restart leaves a lock that never
expires. Removing it by hand was safe (owner verified gone), but the script has no
staleness check on the lock owner and will re-trip the same way. Worth a small fix
separate from this thread.

**Blocked on:** one physical power cycle. Then run the §14 acceptance sequence —
deliberate Manual timeout → next request admitted → Bulb 5 s with EXIF duration
match.

## 16. FOURTH FINDING — the deaths are already recorded; we were not reading them

Prompted by re-reading the TA's three later comments (`out/ta/comments-new.md`
lines 85–233 — I had previously acted only on the first two). The wrapper records
the child's wait status (`128+N` ⇒ killed by signal N), so the fatal signal is in
the logs already. Histogram over the retained Clog set:

```
 873  wait_status=1     # ordinary exit
1251  wait_status=143   # SIGTERM — the camera-absent churn (§15)
   2  wait_status=139   # SIGSEGV
   1  wait_status=132   # SIGILL
```

The three real faults, all in `Clog_000249`:

| time | pid | signal | last line from that pid |
| --- | --- | --- | --- |
| 22:15:05 | 32008 | **SIGILL (4)** | `[pentax] capture=1 boundary=initiate-return ptp=0x2001` |
| 22:45:58 | 6556 | SIGSEGV (11) | none — last capture line ~36 000 lines earlier |
| 23:22:09 | 25903 | SIGSEGV (11) | none — context is the #119 rebind quarantine |

Two corrections to my own first reading, recorded so the error is not repeated:
the two SIGSEGVs are **not** in a capture window at all (they belong to the
camera-absent population, same as the 143s), and the single
`boundary=initiate-return ptp=0x2002` in the whole log set is at line 25545, not
adjacent to either. Adjacency was checked by line number, not by "last match
before".

So of three faults, **one** is a capture-path death — and it is a `capture=1`, a
first capture, in exactly the window the TA narrowed to in #176: after
`boundary=initiate-return`, before any candidate or event. It is a hard fault,
not a timeout and not `checkGphotoTask`.

### 16b. Why we never got the faulting PC

`install_crash_handler()` installs SIGSEGV/SIGBUS/SIGILL handlers from the ELF
constructor, and the handler writes to fd 2 — the same descriptor the `[pentax]`
boundary lines use, which do survive. Yet `*** CRASH` / `pc classify` appears
**0 times in 235 MB**. The handler never ran.

The wrapper's own sample explains it: the child's `SigCgt` is `0x188001e48`,
which decodes to SIGILL, SIGBUS, SIGSEGV **and** SIGUSR1, SIGUSR2, SIGRTMIN+3.
Our constructor installs only the first three, so the broader set is
`polestar_app`'s — installed after us, superseding us. The one datum that would
localise the death was discarded purely because of installation order.

Fixed in `4a8359f`: `stage2_reassert_crash_handler()`, called from the
`gp_camera_init` shim (the earliest point that necessarily runs after the app has
set up). Opt-in via `STAGE2_REASSERT_CRASH_HANDLER` so the shipped signal
disposition is unchanged unless a run asks for it. It deliberately does **not**
chain to the displaced handler — calling an unknown `SA_SIGINFO` handler with a
synthesised `siginfo_t` risks a second fault inside the crash path, which would
lose the record we are trying to keep. The handler still restores `SIG_DFL` and
re-raises, so the `wait_status` the wrapper records is unaffected.

Checked and ruled out as the mechanism: `gp_port_set_timeout` (the first thing the
window calls) is **not** one of the 64 slotted symbols — dumped from the device's
`libpolaris_stage2.so` — and every launch logs `resolved 64/64 / slots filled
64/64`. So there is still no mechanism, only a better instrument.

## 17. FIFTH FINDING — we ship a byte-patch whose premise our own RE falsified (#178)

`--polestar-bulb-patch` is applied unconditionally by the release builder
(`scripts/build-release-candidate.sh:62`), so it is in o-v15t. Its docstring
justifies zeroing `bulb_ms` because "the camera's own Bulb timer (set via cmd 277
shutter index) controls the actual shutter-open duration". Both halves were
disproved by `bulb-root-cause-20261005` (§1, §3): 277 is `camera_set_aperture`,
and `bulb_ms` never reaches libgphoto2 — it becomes a watchdog deadline at
`ctx+0x180`. The patch (2026-09-21, `691e034`) simply predates the RE
(2026-10-05, `ce94298`) and was never revisited.

It also does more than documented. The instruction it rewrites feeds the very next
branch:

```
4975c:  mul  r3, r2, r3      ; bulb_seconds * 1000   <-- replaced by mov r3,#0
49768:  cmp  r3, #0
4976c:  bne  497a0           ; non-zero -> the app's Bulb branch
        ; fall-through (r3 == 0) -> SP_SetPhotoRecodeState(0, 0, 1, ...) plain capture
```

With `r3` pinned to zero the `bne` is never taken, so every `state:1;bulb:N;`
request is routed down the plain-capture branch and the app's Bulb branch is
unreachable. That is consistent with the TA's #173 item 1 (no 261 write on the
product path) and with `bulb-timer=no` in every sample. It does not prove the app
*would* have issued 261 without the patch — the branch may only have set the
watchdog — which is exactly why it is the first variable to A/B rather than an
assumption to keep.

## 18. #175 assertion implemented, and it answered part of the question without a camera

`scripts/assert-orphan-wrote.py` (`4d25c29`, 11 tests) parses `wrote=<path>` out
of the `path=orphan-recovery` audit line and asserts each is a real non-empty
file. Fail-closed three ways: no report line, absent path, or zero-length file
all fail; a local log copy without `--root` reports *inconclusive* rather than
passing.

Run against the device with the camera still off USB, the Clog set contains:

```
[pentax-recovery] capture=1 path=orphan-recovery outcome=cleared recovered=1 names=IMGP3795.DNG accepted=1 action=preserve-then-delete-only-after-verified-download
[pentax-recovery] capture=1 path=orphan-recovery outcome=cleared recovered=1 names=IMGP3796.DNG accepted=1 action=preserve-then-delete-only-after-verified-download
[pentax-recovery] capture=1 path=orphan-recovery outcome=cleared recovered=1 names=IMGP3797.DNG accepted=1 action=preserve-then-delete-only-after-verified-download
```

Three claims of `recovered=1 accepted=1` with **no `wrote=` suffix on any of
them**. Those captures ran on `.55`/o-v15r, whose library is `ee301fef`;
`git merge-base --is-ancestor e0742ce03 ee301fef` is false, so that build predates
the save-before-delete fix entirely. The absent suffix is therefore exactly what
that build must emit — it confirms the *pre-fix* behaviour is observable in the
audit line, but it is **not** a test of the fix. Against the current log set the
assertion correctly returns `PASS (vacuous)`: the staged v15t library contains
`e0742ce03`, but no orphan recovery has run since it was installed.

## 19. State of play

Still blocked on one physical power cycle, which now covers four things at once:

1. #177/#173 acceptance — deliberate Manual timeout → next request admitted
   (`path=obligation-release … released=1`) → Bulb 5 s with EXIF duration match.
2. #176 first-capture reproduction **with `STAGE2_REASSERT_CRASH_HANDLER=1`**, to
   get `pc`/`lr`/slot classification instead of a bare 132/139.
3. #173 step 1 — A/B `--polestar-bulb-patch` on/off and assert on the wire
   whether a 261 write appears for `bulb:5`.
4. #175 — the positive `wrote=` assertion once a capture leaves an orphan.

The device remains a v15r appfs + v15t `ptp2.so` hybrid, so
`verify_installed_build.py` will report a mismatch until a candidate is flashed
properly.

**Flash `.58`/o-v15u, not `.57`/o-v15t** (`docs/RELEASE-VERSION-STATE.md`). It is
o-v15t's content plus `4a8359f`, built from the stock `firmware/FwPkt.zip`
(md5 `90bdad51`) and libgphoto2 `e6b55ad09`, gate GREEN with the single known
prerequisite skip. Verified to carry the diagnostic: the loader `patch.sh`
recorded (`42efee0c`) is byte-identical to the one in the candidate, and the same
`$APP` tree is what `repack_appfs.sh` writes into `appfs.ubifs`, so the flashed
image has it and not only the reversible `stage2-ondisk` copy.

Two things worth recording about how that was reached, because both were my
errors and both would have been silent:

* The first build attempt used `out/FwPkt.zip` — a leftover *candidate* output
  (`FwVer='unknown'`) — instead of the documented stock input. It failed
  fail-closed at pgphoto analysis (`ELFError: Magic number does not match`),
  which is the correct outcome; the trap is that `out/` accumulates FwPkt.zip
  files that look like inputs.
* `strings appfs.ubifs | grep <marker>` returns 0 for **every** marker, including
  ones known to be present, because the UBI image is compressed. Confirming a
  change is in a candidate means comparing the loader md5 `patch.sh` logs against
  the built artifact, not grepping the image.
