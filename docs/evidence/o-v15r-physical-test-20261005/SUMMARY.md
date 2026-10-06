# o-v15r physical test — 2026-10-05

Status: **#160 fix CONFIRMED on hardware. Capture retest BLOCKED — the K-3 III left
USB during the first Bulb attempt and has not returned.**

Candidate: `o-v15r-supervisor-preload-20261005`, `FwVer:6.0.0.54.55`,
md5 `7618f507fbec1793bb560d7a1ac7586e`.
Installed through the SD `FwPkt/` tree + on-boot watcher per
`.github/skills/fwpkt-update-flow/SKILL.md`. No direct NAND edits.

> **This corrects the impression given in the 2026-10-05 review.** The review was
> written on the assumption that v15r had not been physically tested. It has been,
> and the outcome is mixed: the log-flood fix works exactly as designed, but the
> Manual baseline could **not** be re-confirmed, and Bulb is worse than "duration
> ignored" — the stop edge is unreachable.

## 1. Install and provenance — PASS

| Check | Result |
| --- | --- |
| Staged tree | 8 files, `/app/sd/FwPkt` was empty first (no merge with a partial tree) |
| On-device MD5 vs on-card `firmwareInfo` | **6/6 match** (config, uImage, rootfs, appfs, polaris403, polaris413) |
| Reflash | completed, device back in ~4 min |
| `/app/FwVer` | `6.0.0.54.55` ✅ |
| `/app/openpolaris-libgphoto2-provenance.txt` | `build_id=6.0.0.54.55-o-v15r-supervisor-preload-20261005`, `patcher_commit=5fdc174af3c7280fee34b07f46c24d1e5d9a584c`, `dirty_diff_hash=` (clean), `selected_camlibs=ptp2,pentax` ✅ matches the registry row |

Staging took **19 min** for 88 MB (~60 KB/s over the USB-ethernet bridge). Worth
budgeting for in the runbook.

## 2. #160 log flood — FIXED, verified on hardware

The claim was that `camera_usb_supervisor.sh` children inherited `LD_PRELOAD` and
each re-ran the Stage-2 ELF constructor, printing a 13-line banner once per poll.

Measured on the running `.55` build:

```
child_samples=33  child_samples_with_preload=0
```

33 supervisor children sampled over 10 s (the poll loop is unchanged and still
forks), **zero of which carry `LD_PRELOAD`**. The supervisor process itself
(pid 272) reports `LD_PRELOAD_entries=0`.

`/app/Clog.txt` is **1736 bytes** after 2.4 h uptime. On `.54` the equivalent
rotation window held ~48 150 banner lines across 42 MB.

`pgphoto` still has the preload (the wrapper keeps it for the camera process), so
the fix is selective, as intended.

**#160 can be closed.**

## 3. Manual capture baseline — NOT RE-CONFIRMED (blocked, not failed)

The 11/11 v15q Manual baseline could not be re-run: by the time the capture test
was attempted the camera was no longer on USB (§5). No Manual shot was taken on
`.55`. The baseline is therefore **unverified on this build**, neither confirmed
nor regressed.

## 4. Bulb — the stop edge is unreachable (new, more serious than #173)

Operator report: *"terminate shot does work [in Manual] … bulb fails also …
terminate did not work in Bulb mode"*, with the red button spinning.

`Clog_000247.log` captures both halves.

### 4a. A stop while idle returns `-2` and never sends 0x9012

```
[11:34:34:906] recv_ipc_msg code[264],val[state:0;focus:-1000;leve:1;b:0;path:;c:0;]
[11:34:34:906] captureImage ----will captureImage status:0  focus:-1000  sPath:
[11:34:35:006] capture_image_with_Burst[3481]: ----capture_image_with_Burst  -2 continuous 0
[11:34:35:007] captureImage[1547]: ----capture burst Image ret -2
[11:34:35:008] SP_sendMsg code[264],val[state:-2;]
```

`-2` is `GP_ERROR_BAD_PARAMETERS`. It returns in ~100 ms and **no
`ptp_pentax_terminate_capture` (0x9012) is issued anywhere in the log**. So the
stop edge, when it is actually serviced, is a no-op against the camera.

### 4b. A stop during an in-flight capture is never even dequeued

```
[11:35:44:020] recv 264 state:1;...;path:/app/sd/normal/SP_0203.jpg;c:-1   <- start
[11:35:44:037] current_shutter  configInfo:s:00:01;  ret:0  sValue 00:01
[11:35:44:037] updateCaptureInfo ----shutter speed  0.000000
[11:35:44:044] numOfCaptureImage ----numOfCaptureImage  2                  <- RAW+JPEG
[11:35:44:074] capture_image ---- will CAPTURE_IMAGE
[libgphoto2] gp_camera_capture: enter camera=0x3abce8 type=0
[pentax] capture=1 boundary=camlib-enter transfer=0 recovery=1 output_pending=0
[pentax] capture=1 boundary=preconditions-return ptp=0x2001 size=576
[pentax] capture=1 boundary=initiate-enter focus=2 companions=1
[pentax] capture=1 boundary=initiate-return ptp=0x2001
   ... 45 s: nothing but camera_connected_to_app heartbeats ...
```

**IPC commands handled between 11:35:44 and 11:36:29: 1** — the start itself.

`captureImage()` is called synchronously from the `ipc_msg_loop` handler, so the
whole candidate-wait loop blocks the only thread that reads the command queue.
The app's stop is written to the queue and sits there. This is the mechanism
behind the spinning button, and it explains why terminate "works" in Manual: a
Manual exposure finishes before the user can press stop, so the stop is serviced
against an idle (already-finished) capture.

### 4c. The camera then left USB

```
[11:36:28] [camera-usb] stable identity change: 1-1.2|25fb:0189|1:3 -> none; restarting pgphoto
[restart_gphoto] stopping pgphoto (PID 21831)
[11:36:31] SP_sendMsg code[286],val[manufacturer:none;model:none;state:-5;...]
```

`lsusb` now shows no `25fb:0189`. `286` reports `state:-5` and `model:none`
~2.4 h later. This is the same signature as the 2026-10-04 pgphoto-restart
disconnects (#146), reached here via a long in-flight Bulb instead.

### 4d. Why the library cannot help

`pentax_bulb_action_model_supported()` (`camlibs/ptp2/pentax-utils.c:84`) returns
false for the K-3 III by design:

> *The K-3 III probe on 2026-09-06 accepted vendor mode but rejected the
> held-shutter release=2 edge with 0x2002, followed by USB disappearance.*

so `ptp2_pentax_bulb_action()` returns `GP_ERROR_NOT_SUPPORTED` and the
`Pentax Bulb` widget is never exposed. `grep -c pentax-bulb` over the recent log
set is **0** — the generic action was never entered. The only Bulb path available
on this body is the camera-timed one, and that path has **no stop at all**.

## 5. Consequences for the plan

1. **#173 is understated.** There is no working stop, and the attempt cost us the
   camera on USB. (Corrected after the TA review: this line originally also
   asserted "duration ignored" was *still true*. It is not a property of the
   K-3 III — the camera honours a 261 shutter write, applying it asynchronously.
   What is true is that the *stock app path never issues* that write, and that
   our own canary appeared to fail because it verified with a single immediate
   readback. See `pgphoto-dies-mid-capture-20261005/SUMMARY.md` §12/§12b.)
2. **A real fix needs the stop to be reachable.** Either the wait loop must poll
   a cancellation the wrapper can raise from outside, or the 264 handler must run
   off the queue-reading thread. Until then no Bulb design is testable from the
   app.
3. **Do not judge Manual on `.55` yet.** Re-confirmation needs the camera back on
   USB; a power cycle is the known-good recovery.
4. Agrees with the review: **no speculative capture changes**. The two safe items
   it asked for (#169 tooling, `.vscode/settings.json` hygiene) touch no capture
   code and were done separately.

## Files

- `supervisor-preload-evidence.txt` — the 33/0 child sample and Clog size
- `bulb-stop-trace.txt` — the 4a/4b/4c log extracts
