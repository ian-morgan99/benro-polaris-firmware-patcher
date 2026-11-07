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

`audit-camera-on.txt` — **47 PASS, 2 FAIL, 3 SKIP**, exit 1.

Now confirmed with a camera attached (previously 7 camera-dependent checks were skipped):

- `connected` → `Ricoh Pentax K-1 Mark II`
- APERTURE (275) f/1.6 → f/1.4, ISO (265) 6400 → 100, WB (266) — **confirmed by read-back**
- Focus AF/MF round-trip, live view streaming at 720x480, camera-name chip shown while live

## The two failures

### SHUTTER (268) — silent drop, no refusal reported

`asked index 0, camera reports 14, badge ''`.

The real list is `["00-30","00-25",…,"13/10","00-01",…]`, so index 0 is a **timed
30-second exposure** and index 14 is `13/10`. The body kept its previous value, the
write was dropped, and **no badge appeared at all** — unlike EV, which reports
`camera refused`. A user sees the control silently revert with no explanation.

This is not #251's bulb case: index 0 here is timed 30 s, not bulb. (My first draft of
the probe assumed index 0 was bulb; the captured list disproves that.)

### EV (267) — audit says "never settled", probe shows a refusal

`probe-268-267.py` wrote index 0 and watched `S.expoPending` plus the badge:

```
t+01 pending=1 badge='EV: applying…'
t+02 pending=1 badge='EV: retry 2/3'
t+03 pending=1 badge='EV: camera refused'   <- correct behaviour
...
t+12 pending=0 badge=''                     <- badge cleared, value unchanged (idx 15)
```

So the web UI **did** retry three times and report `camera refused` — correct. The audit
reported "never settled" instead because its loop only samples once `pending == 0`, by
which point the badge has already been cleared, so the refusal text is gone and it falls
through to a timeout verdict.

**Harness bug, not a product bug.** The audit must capture the badge while pending is
still non-zero. Until fixed it will keep mis-reporting camera refusals as timeouts —
which matters, because #146/#147 triage depends on distinguishing "camera said no" from
"we never got a reply".

## Not done, deliberately

Shutter (268) was **not** re-pressed by the probe. #251 states an untimed-B exposure
cannot be physically cancelled on this body, so writing the shutter wheel unattended is
unsafe. Any bulb-path test needs supervised hardware and a lens cap.

## Files

| File | Contents |
|---|---|
| `audit-camera-on.txt` | Full audit output |
| `probe-268-267.py` | Read-only 268 probe + safe 267 write with badge timeline |
| `shots-camera.py` | Screenshot script |
| `01..05-*.png` | Manual screenshots taken with the camera attached |
