# o-v9q-bulb-timeout — Q test field results (2026-09-17/18)

Build: **o-v9q-bulb-timeout** (build_id 6.0.0.54.8, libgphoto2 `dacfc8986` "Bulb capture
port timeout + integer-second shutter enumeration", patcher `2b56e8d`).

## Field test results (Q test, 2026-09-17/18)

### PASS
- **Version Q installed safely** (SD FwPkt flow, clean boot; provenance verified on device:
  git_commit=dacfc8986, build_id=6.0.0.54.8).
- **Multiple shots in Astro mode work** — intervalometer multi-shot capture now succeeds
  (previously only the first shot fired; see issue #80 / o-v9o astro multishot evidence).

### NEW BUGS FOUND (Q test)

All six are tracked as GitHub issues in `ian-morgan99/benro-polaris-firmware-patcher`
(#111–#115), filed 2026-09-18. Cross-references below.

1. **Bulb option in Manual mode: image takes but app reports "shot failed"** — the exposure
   completes and the file is written, but the capture result path reports failure to the app.
   Suspect: bulb capture returns a non-zero/timeout code after the long exposure even though
   the transfer succeeded (see dacfc8986 port-timeout change; possible over-long wait budget
   or a post-capture reconcile that times out on bulb). → **issue #111**
2. **Bulb mode in Astro still shows 3 minutes for "minutes"** — the bulb time control in
   Astro mode is still capped/labelled at 3 min (180 s) instead of the full range; and it
   **waits that full period before taking the first photo** (the intervalometer delay is
   applied to shot #1 instead of firing immediately). → **issue #112**
3. **Bulb time doesn't "stick"** — once changed, the bulb duration reverts / stays at the
   last value; setting a new value does not persist across shots or mode switches. → **issue #113**
4. **EV not available in Bulb mode** — EV control missing/unavailable when shutter = Bulb. → **issue #114**
5. **Professional mode: slews to position then "shot failed"** — after the gimbal slews to
   the target position, the capture reports failure (same class as bug #1: exposure completes
   but result path reports failure). Tracked under **issue #111** (same "shot failed" class;
   Professional mode is a second repro of the same capture-result-path failure).
6. **Panorama and related modes seem not to work** — panorama (and "stuff" around it) fails;
   needs log correlation to find first abnormal transition. → **issue #115**

### STILL OPEN (pre-existing, re-confirmed in Q test)
- **ISO still max 6400** — ISO control capped at 6400 (issue #85 / libgphoto2 #77: ISO cap;
  K-3 III enumerates only part of the list).
- **Battery flat** — Polaris battery ran flat during the test (field note; not a firmware bug,
  but blocked part of the session).

### PASS notes
- Android app recompiled with the battery indicator (client-side, done).
- Astro multi-shot now works (was issue #80 first-shot-only) — needs formal re-qualification
  on K-3 III + K-1 II to close #80.

## Log correlation TODO (overnight)
- Pull Mlog/Clog from Polaris for the Q test window; correlate:
  - bulb "shot failed" → capture result code path (gp_camera_capture_image return / reconcile)
  - professional-mode slew-then-fail → same capture-result class?
  - panorama failure → first abnormal transition in Mlog
  - bulb time not sticking → set_single_config write path for shutter=Bulb duration
  - EV unavailable in Bulb → app-side or camera-side config availability
