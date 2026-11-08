# K-1 II web UI evidence — camera attached, 2026-11-07

Device: Benro Polaris Astro. Camera: Ricoh Pentax K-1 Mark II (`25fb:0183`).

## What is actually installed (provenance)

Two components, from different builds, and the display version describes only one of them:

| Component | Hash | Which build |
|---|---|---|
| `/app/bin/polestar_app` | `a5e58ffd…` | **astro-v97** — matches v97's `install-manifest.json` exactly |
| `/app/lib/stage2/pgphoto.stage2ondisk` | `f167e668…` | **astro-v97** |
| `/app/lib/stage2/libpolaris_stage2.so` | `70b316c1…` | **astro-v97** |
| `/app/astro/polaris-httpd` | `b7c5fec2…` | **astro-v99** (`f8e602b`) |

`/app/FwVer` reads `FwVer:6.0.0.54.97;date:2026.11.06;`.

So the camera stack — `polestar_app`, stage2, libgphoto2 — **is v97**, verified by
hash against the published manifest, not by the displayed string. The astro bundle
contains no `stage2`, `polestar_app`, `FwVer` or `libgphoto2` file at all (43 files,
none of them camera payload), and `git diff 5dbd19d..f8e602b` touches no
`stage2|libgphoto|pentax|pgphoto|camlib` path.

**Consequence for #146/#147/#251:** those reports describe camera behaviour, and the
camera code they exercised is v97. The "version 97, actually version 99" description is
half right — the *web UI* is v99, the *camera stack* is genuinely v97. Findings about
shutter semantics, session lifecycle or preview belong against v97's camera payload.

## Audit result

Two runs, same build, camera attached:

| Run | Harness | Result |
|---|---|---|
| `audit-camera-on.txt` | before the badge fix | 47 PASS, **2 FAIL**, 3 SKIP |
| `audit-camera-on-fixed.txt` | after the badge fix | 47 PASS, **1 FAIL**, 4 SKIP |

The difference is entirely the harness bug below — no product code changed between runs.

Now confirmed with a camera attached (previously 7 camera-dependent checks were skipped):

- `connected` → `Ricoh Pentax K-1 Mark II`
- APERTURE (275) f/1.6 → f/1.4, ISO (265) 6400 → 100, WB (266) — **confirmed by read-back**
- Focus AF/MF round-trip, live view streaming at 720x480, camera-name chip shown while live

## The two failures — and a correction to this file's first version

**My first draft of this README was wrong about SHUTTER (268), and the reason matters.**
It claimed "asked index 0, camera reports 14, badge ''" proved a *silent drop* with no
explanation shown. That reading came from the harness bug described below: it sampled the
badge only after `pending` cleared, by which point the badge had already been wiped. The
badge was in fact present and correct.

Re-running with the fixed harness (`audit-camera-on-fixed.txt`) gives **47 PASS, 1 FAIL,
4 SKIP**, and the two controls turn out to be *different* failure classes:

### SHUTTER (268) — correct behaviour, not a defect

Now reported as SKIP: `camera refused the write (body mode locks it); webui retried 3x
and reported it correctly`. The body declined because of its dial mode; the app retried
three times and said so. Nothing to fix here. This matches the manual's guidance that
"camera refused" is usually the camera, not the page.

### EV (267) — bounded correctly. My "unbounded" claim here was WRONG; retracted.

The badge timeline:

```
t+01..t+24  'EV: applying…'      (24 consecutive samples)
t+25..t+30  'EV: not applied'    (6 consecutive samples)
harness window ended at t+30
```

I published that as "`S.expoPending` never clears — nothing bounds it". It is bounded, and
**my own captured data proves it**. From `container/astro/webui/app.js` on main:

| Constant | Line | Effect |
|---|---|---|
| `EXPO_SET_TIMEOUT_MS = 25000` | 715 | `now - sentAt > 25000` → `state = 'timeout'` → paints `not applied` |
| `EXPO_MESSAGE_MS = 8000` | 718 | `endedAt + 8000` → `delete S.expoPending[key]` |

So pending is deleted at **~33 s**. My harness polled for **30 s** — it stopped 3 s before
the delete and I read that as "never clears". The timeline matches the code exactly:
`applying…` until t+25 (the 25 s timeout), `not applied` from t+25 onward, cleared at t+33.
Nothing is stuck. #147's "bounded and cancellable" invariant **holds** on this path.

What is real, and worth keeping:

1. **The final text is `not applied`, not `refused`.** A distinct error class from 268's
   refusal: the write got no reply at all within 25 s, rather than the body actively
   saying no. The earlier harness conflated these by only matching the word "refused".
2. **`applying…` for ~24 s with no `ret:` reply** means the request went out and nothing
   came back. That is a genuine camera-side or transport-side silence, and it is the
   distinction #146/#147 triage turns on — *camera said no* versus *we never got a reply*.
3. **25 s of "applying…" is a long time to wait** before admitting nothing arrived. That
   is a UX observation, not the invariant failure I originally claimed.

### The same EV write behaved differently in two runs — do not pick one story

`probe-268-267.py` wrote index 0 to 267 from index 15 and saw:

```
t+01 'EV: applying…'  t+02 'EV: retry 2/3'  t+03..t+11 'EV: camera refused'
t+12 pending=0 badge=''
```

The fixed audit, writing the same index on the same build minutes later, saw:

```
t+01..t+24 'EV: applying…'   t+25..t+30 'EV: not applied'   pending never cleared
```

Same control, same target value, two different outcomes — **both bounded**, settling at
t+12 with `camera refused` and at ~t+33 with `not applied` respectively. I described the
second as "an unbounded stall" and "hangs forever"; both phrasings were wrong for the same
reason as above, and are retracted.

What remains genuinely open is narrower and still worth reporting: **the same write
dometimes gets a reply (`ret:` → refusal after retries) and sometimes gets no reply at all
(timeout)**. That is a real difference in what the camera does, it is state-dependent, and I
have not established what drives it — candidates are body dial mode, whether live view was
active, or how long the session had been running. It matters for #146/#147 because the two
cases surface as different text (`camera refused` vs `not applied`) and a caller cannot tell
*why* nothing landed, only that it didn't.

So the reportable finding is the **reply/no-reply ambiguity**, not an unbounded state. The
state machine itself is correct.

## Harness bug found and fixed (was corrupting these verdicts)

`tests/audit_astro_controls.py` previously sampled the badge only once `pending == 0`.
The web UI clears the badge when it gives up, so by then the refusal text is gone and any
refusal fell through to a timeout verdict. Fixed by recording every badge seen while
polling, and by splitting the verdicts into three classes — refused / not applied / no
reply at all — instead of one.

This is why the harness is now version-controlled in `tests/`. It previously existed only
in `~/astro-shots`, so a bug like this could not be reviewed or bisected, and its output
was being treated as product evidence.

**Consequence for anything triaged off the earlier run:** verdicts produced by the old
harness that say "never settled" are unreliable — they may have been refusals. Re-run
before acting on them.
## Not done, deliberately

Shutter (268) was **not** re-pressed by the probe. #251 states an untimed-B exposure
cannot be physically cancelled on this body, so writing the shutter wheel unattended is
unsafe. Any bulb-path test needs supervised hardware and a lens cap.

## Files

| File | Contents |
|---|---|
| `audit-camera-on.txt` | Audit output, pre-fix harness (verdicts for 268/267 unreliable) |
| `audit-camera-on-fixed.txt` | Audit output after the badge fix — use this one |
| `probe-268-267.py` | Read-only 268 probe + safe 267 write with badge timeline |
| `shots-camera.py` | Screenshot script |
| `01..05-*.png` | Manual screenshots taken with the camera attached |

The harness itself now lives at `tests/audit_astro_controls.py`. It previously existed
only in `~/astro-shots`, which is why its bug went unnoticed while its output was being
cited as product evidence.
