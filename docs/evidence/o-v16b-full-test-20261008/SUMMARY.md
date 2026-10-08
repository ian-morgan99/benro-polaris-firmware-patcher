# Deep analysis: every capture cycle on `.61` (o-v16b), 2026-10-08

Device `6.0.0.54.61`, K-3 III `25fb:0189`. Raw: `raw/` — Mlog+Clog for boots
265–271 (all of today), plus `/app/stage2-crash.log` analysed below. Times are
device-local (UTC+1).

## Headline

**pgphoto crashes mid-capture on every real (camera-firing) still capture on
`.61`.** Three crashes in `/app/stage2-crash.log`, exactly matching the three
watchdog restarts (`checkGphotoTask: pgphoto is exit,reboot it`), each 12–33 s
after a `will CAPTURE_IMAGE`. The camera does fire; the file lands on the
camera; the daemon dies before the transfer completes; the app hangs on the red
circle; the orphan-recovery path later rescues the file.

The prime suspect is the **#183 guarded-capture wrapper, which `.61` installs by
default** (`STAGE2_CAPTURE_EMPTY_PATH_CHECK=1`). The loader's own comment block
(lines ~1722) records why capture deliberately stayed direct-to-core: the
historical o-v12j/k/n first-shot K-3 III crashes all died at exactly this
extra ABI boundary. `.60` ran 16/16 clean yesterday with no wrapper installed;
today on `.61`, with the wrapper on by default, every successful-path capture
crashed.

## Crash forensics (`/app/stage2-crash.log`, mtime 18:14:18)

| # | signal | pc | classification |
| --- | --- | --- | --- |
| 1 | SIGILL (4) | 0x00393a38 | inside the heap (`00312000-003ed000`) |
| 2 | SIGSEGV (11) | 0x00500046 | past the heap end |
| 3 | SIGSEGV (11) | 0x312e3338 | ASCII `"8.31"` — jumped into a string buffer |

All three: `last checkpoint reached: slots filled` (loader init completed),
`si_addr NOT in the slot region`, and identical low bits in `lr` (`…b34`) and
`sp` (`…ee8`) across all three — the same call site on the same thread, with
ASLR shifting the bases. Wild PCs in heap/string space = jump through a
corrupted function pointer, i.e. the classic signature of the capture-boundary
crashes this loader was designed to avoid.

## Per-boot timeline (all commands and reactions)

### Boot 265 (15:39–16:2x) — install boot for `.61`
- 15:39 upgrade + gimbal flash; card re-enumerated (SP_0264 listed etc.).
- 16:09:05 App[3] `264 state:1;bulb:3` (canary bulb 3 s). `264 state:1` echoed,
  `captureImage[1485] will captureImage` issued.
- 16:10:11 (66 s later) `264 state:2 → state:5 → state:0` — the false-success
  lifecycle. Clog: `captureImage ret 0 p:` (empty). No file created.
- 16:12:19 App[5] `264 state:1;bulb:0` (canary plain). Same 66 s cycle at
  16:13:26, same empty `ret 0`, no file.
- `[pentax-recovery] … reason=camera-reports-no-output … forget-abandoned-obligation`
  — the core correctly saw the camera produced nothing.
- **No crash.** Camera never actuated (operator: no sound). Camera was in
  Star AF / AstroTracer 3 at this point.

### Boot 266 (16:2x–17:0x) — trace diagnostic
- `STAGE2_CAPTURE_TRACE=1` set; wrapper replaced by trace wrapper.
- 16:37:19 capture: `[stage2-trace] capture-enter seq=1` → 66 s →
  `capture-return ret=-10` (GP_ERROR_TIMEOUT). App still logged `ret 0` +
  success lifecycle. **Disproved #183's GP_OK premise.**
- 16:39 second trace pair, same `-10`. No crash, no actuation.

### Boot 267 (17:05–17:13) — OpenPolaris manual shot
- 17:05:21 first `pgphoto is exit` (startup race at boot; no capture pending).
- 17:11:04 App[8] `264 state:1;bulb:0` → `will captureImage SP_0280.jpg`.
- **17:11:16 `pgphoto is exit,reboot it` — crash #1, 12 s into the capture.**
- No `state:2/5` completion ever; log ends at the user's power-cycle. No file.

### Boot 268 (17:15, ~2 min) — camera off; nothing but `state:-5`.

### Boot 269 (17:17–17:5x) — camera power-cycled in astro mode, dial on B
- Repeated `Pentax init stage vendor enable returned 0x2002` → `gp_camera_init
  ret -1` → `state:-1/-2`. **The camera refuses Pentax vendor mode (0x9001)
  in this state.** Benro Connect crash-loops (#187).
- 17:45 dial moved off B + replug: `vendor enable succeeded; gp_camera_init
  ret 0` within seconds. Camera then dropped off the bus at 17:49:51.
- App socket churn continues with no camera attached (client-side crash loop).

### Boot 270 (17:5x, ~2 min) — brief boot, no activity.

### Boot 271 (17:51–now) — dial in Av, clean init, two real captures, two crashes
- 18:09:35 clean init: `state:1`, model reported, vendor enable OK.
- 18:11:44 App[7] (user, Benro Connect) `264 state:1;bulb:0` →
  `will captureImage SP_0280.jpg`; app's own log shows shutter `00:20`.
  Core boundaries: `preconditions-return ptp=0x2001 size=576`,
  `initiate-return ptp=0x2001` — **capture accepted, camera firing** (operator
  heard the exposure).
- **18:12:17 `pgphoto is exit` — crash #2, 33 s into the capture.**
  Watchdog restarts (PID 13781); init re-succeeds 18:12:35.
- 18:13:56 App[8] (canary plain capture) `264 state:1` → `will captureImage
  SP_0281.jpg` → boundaries OK again →
  `[pentax-recovery] path=orphan-recovery recovered=1 names=IMGP3847.DNG
  wrote=/app/sd/normal/IMGP3847-orphan-1.DNG` — **the previous capture's file,
  rescued from the camera after the restart**.
- **~18:14:18 crash #3** (crash-log mtime; second capture, ~22 s in).
  Watchdog restarts (PID 15948, current, healthy `state:1`).
- The app stayed on the red circle throughout — it is talking to a daemon that
  died under it.

## What this resolves

1. **The red-circle hang is a daemon crash, not a protocol wedge.** Every
   manual capture kills pgphoto 12–33 s in; the watchdog restarts it; the app
   never gets `state:2/5`.
2. **The camera fires on the normal-mode path.** The 13–20 s exposure really
   happened (operator heard it; `IMGP3847` exists on the card). The earlier
   "never fires" failures were all in Star AF / AstroTracer 3 / dial-B state.
3. **Dial-B / astro-state vendor refusal (0x2002) is real and reproducible**
   in one direction (off-B init succeeds twice, on-B refused twice). The
   reverse A/B (back to B → refusal returns) is still pending.
4. **#183's premise stays disproved** (boot 266 trace: `-10`, not `GP_OK`),
   and its fix is now implicated in something worse: see 5.
5. **New, most-likely root cause for the crashes:** `.61` is the first build
   that installs the guarded capture wrapper by default. `.60` (no wrapper)
   completed 16/16 identical canary captures yesterday. The crash signature
   (wild PC, same call site, mid-capture) matches the historical o-v12j/k/n
   capture-boundary crashes the loader comment says must not be reintroduced.

## Decisive next test (cheap)

Set `STAGE2_CAPTURE_EMPTY_PATH_CHECK=0` in `/app/bin/pgphoto` (wrapper stays
installed only if the guard is set; otherwise capture goes direct-to-core as on
`.60`), restart, take one plain capture in Av.
- Completes with `state:2/5` + file → the wrapper is the crash cause; revert
  #183 to default-off or fix the wrapper ABI; the empty-path check is useless
  anyway (the app ignores return codes).
- Still crashes → the wrapper is exonerated; suspect the core's
  candidate/download path on the success branch and re-instrument there.

## Side findings

- The app's shutter for the "manual" shot was `00:20` per the daemon's own
  `current_shutter` readback, while the camera UI showed ~13 s and the phone
  showed 15 s — three different values for one setting; worth a look at how
  the app maps its slider to command 261 indices.
- `checkGphotoTask` restarts the daemon but the app is never told the session
  died; hence the indefinite red circle.
