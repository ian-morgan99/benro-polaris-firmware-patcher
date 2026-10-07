# App-path long-exposure USB drops — consolidated evidence (2026-10-07)

Companion to `exposure-ladder.log` and issue #181. All device times are
Clog/Mlog local (UTC+0 in file; BST local = +1h).

## Incidents (app path, 30 s shutter, camera 25fb:0189)

| # | Time | Shot | What the logs show | Outcome |
|---|------|------|--------------------|---------|
| 1 | 13:04 | 30 s app shot | `264 state:1` accepted, no `state:4`, camera identity `1:4 -> none`, supervisor restart 3/6 | Camera dropped mid-exposure; no file produced (no orphan for this shot) |
| 2 | 14:10:30 | SP_0273, 30 s, EV idx 30 | `264 state:1` at 14:10:30, widget readback `Current: 00:30`; identity `1:5 -> none` ~3–4 s later (user-observed), restart 5/6 | Camera dropped ~3–4 s into exposure; **file later recovered**: `[pentax-recovery] capture=1 path=orphan-recovery outcome=cleared recovered=1 names=IMGP3834.DNG ... wrote=/app/sd/normal/IMGP3834-orphan-1.DNG` at 14:13 (34.7 MB DNG on disk) |
| 3 | 14:13:33 | SP_0274, 30 s, LV ON (291 state:1 at 14:13:27), EV still idx 30 | Full lifecycle `state:1 → 4 (IMGP3835.JPG) → 2 → 3 (jpg+dng) → 0` in 42 s | **PASS** — same settings that dropped at 14:10 succeeded at 14:13 |

App symptom during incidents: read-back icon locked/spinning, slide-to-cancel
unresponsive — consistent with the app waiting for the `264 state:0` completion
that never arrives after the drop.

## What is ruled out

- **EV -5 "out of range": NO.** The live 267 list is ±5 EV in 1/3-stop steps
  (31 entries, idx 0 = +5 … idx 30 = -5). The app set `ev:30` (= -5) at
  14:09:01 with `ret:0` (accepted by camera). -5 is in range.
- **30 s shutter alone: NO.** Canary ladder 5/10/20/30 s: 4/4 PASS
  (`exposure-ladder.log`). And incident 3 above is a 30 s app shot that passed.
- **30 s + EV -5 + LV together: NO.** Incident 3 had all three and passed.
- **Gimbal instability/reboot: NO.** Uptime continuous; every identity change
  was the *camera* leaving/rejoining USB, caught correctly by
  `camera_usb_supervisor.sh` each time.
- **Firmware `.60` capture guard: NO.** Guard ON throughout; pgphoto never
  crashed; 21+ clean captures on the canary path same day.

## What is confirmed

1. The drop is **intermittent, not deterministic** — identical settings passed
   3 minutes after failing.
2. It correlates with the **app capture path** (plain `264 bulb:0`, camera-set
   shutter, app polling/preview traffic). The canary path (`264 bulb:N` +
   explicit 261 write, LV off, no concurrent traffic) has 21+ passes including
   the full ladder.
3. The camera sometimes **completes the photo anyway** after dropping off USB
   (incident 2 → orphan recovery preserved IMGP3834.DNG). The user's principle
   held: no photo lost, no human intervention needed for the file — but the
   app session was left hanging.
4. The stuck "read icon" is the app never receiving completion; the daemon
   side behaved correctly (it had nothing to report — the camera was gone).

## Current device state (14:2x)

- Camera present (`25fb:0189`), session healthy, EV idx 24 (-3) after the app
  re-set it at 14:14:25, shutter still 00-30 on the body.
- **Supervisor restart budget exhausted (6/6).** The next identity change may
  NOT auto-restart pgphoto. A gimbal reboot is required before further
  long-exposure testing.

## Discriminating test (next session, after gimbal reboot)

1. Reset camera: EV 0, shutter 1/125. App shot with LV on → expect PASS.
2. EV -5, shutter 30 s, LV on, app shot ×3 → does it raise drop probability?
3. Repeat 2 with the app backgrounded (no preview polling) → isolates
   concurrent-app-traffic vs camera-side exposure behaviour.
4. If drops persist only with app traffic: instrument the drop window in
   pgphoto (log PTP transaction in flight when libusb reports detach).

## Verdict so far

Honest status: **cause not proven.** Ruled out: EV range, shutter length,
firmware build, gimbal-side instability. Leading hypothesis: a race between
app-path concurrent PTP traffic (preview/option polling) and the camera's
long-exposure capture handling, causing the K-3 III to reset its USB
interface; intermittent by nature. Orphan recovery is working as designed and
saved the one photo that mattered.
