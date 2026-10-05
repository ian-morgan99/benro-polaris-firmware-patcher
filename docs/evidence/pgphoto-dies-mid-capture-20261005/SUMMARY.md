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
| `initiate-return ptp=0x2001` (shutter accepted) | 16 | 16:17–16:29 ×13, 18:50, 20:44, 20:45 |
| `pgphoto is exit, reboot it` (app watchdog) | 3 | 18:50:19, 20:44:30, 20:45:47 |
| pgphoto process starts | 10 | only **5** of which are supervisor-initiated |
| camera file events / files saved to album | 38 / 26 | **last one at 16:29:28** |

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
- Not the #175 fix: `path=orphan-recovery` appears **0 times** in the log. The
  latch was cleared by a process restart, not by the claim path. **The fix is
  still unexercised on hardware** — it neither worked nor failed here.
- Not OOM: 1.4 GB free, `dmesg` has no OOM/killer entries.
- Not a kernel-visible fault: no `traps`/`segfault` in `dmesg`, and
  `core_pattern=core` with `ulimit -c 0`, so no core is written either way.

## 8. Next diagnostic step

The death is silent, so it has to be caught in the act:

1. Relaunch pgphoto with `ulimit -c unlimited` and a writable cwd, reproduce one
   capture, read the core. (No `strace`/`gdb`/`ltrace` on the device.)
2. If no core is produced, the process is calling `exit()` rather than taking a
   signal — then the search is for an exit path reached from the capture
   failure handler, not a memory fault.
3. Cheaper discriminator first: does the stock `/app/sd/pgphoto.prestage2.bak`
   binary die mid-capture too? If yes, this is entirely upstream of our Stage-2
   work and belongs to the stock app + this camera; if no, it is in our stack.
   Note the caveat already recorded: restarting pgphoto has dropped the K-3 III
   off USB twice before (see #146), so each of these attempts costs a reseat.

## 9. Consequence for release qualification

Consistent with the review on #175: o-v15s is an **experimental hardware
candidate**. It cannot be qualified by repeated-shot testing on this device
until the mid-capture death is fixed, because the test's precondition — a
capture that completes — is what currently fails.
