# K-1 II on v118 — bulb and capture verified (first time on this build)

Rig `d13e86`, `astro-v118-stage2-gate-wedge-fix-20261126` / `6.0.0.54.118`, identity re-verified **PASS** after
the camera was re-attached. Camera: Pentax K-1 II, `state:1; storage:2; photoFormat:1`. Captured 2026-11-26.

These are the first successful captures ever recorded on v118. Every prior v118 session had the camera absent
or the gate wedged, so bulb and delivery were untested assumptions until now.

## Symptom A — exposure-time list: PASS

`probe-b-list-and-held-bulb.py`, code 268, two passes:

```text
pass 1: entries=56 current index=20   (0.40s)
pass 2: entries=56 current index=20   (2.05s)
current label: '3/10' parses to 0.3
entries that do NOT parse as a duration: []
first 6: ['00-30','00-25','00-20','00-15','00-13','00-10']
last 4:  ['1/5000','1/6400','1/8000','00-00']
```

56 entries, stable across passes, **zero malformed entries**. The list is healthy on v118.

## Symptom B — held (non-timed) bulb: PASS, twice

Both attempts completed the full state machine and produced a file:

| Attempt | States observed | File | Size |
|---|---|---|---|
| 1 | `1 → 4 → 0` | `/app/sd/normal/SP_0045.jpg` | 332,750 |
| 2 | `1 → 4 → 0` | `/app/sd/normal/SP_0046.jpg` | 337,640 |

Storage accounting moved correspondingly (`freespace 54250 → 54247`, `usespace 6639 → 6642`), so the files are
real. Camera returned to `state:1` healthy after both. **Bulb works end-to-end on v118.**

## Two things worth noting, neither a v118 regression

**`duration:0` on every capture event.** Both 773 events report `duration:0`:

```text
RX 773@type:1;path:/app/sd/normal/SP_0045.jpg;size:332750;cTime:2026-11-26 18:54:11;duration:0;#
```

For a *held* bulb the duration is operator-controlled, so `0` may be correct rather than wrong. But it is the
same field #315 reports negative values for (`capture end -14660 ms`), and here it is simply never populated.
Worth checking against a **timed** bulb run before concluding anything — `duration:0` on a timed exposure would
be a genuine defect.

**`photoFormat:1` means no RAW companion was expected.** Both captures delivered JPEG only, which is consistent
with the format in force. So this session does **not** test #362 (RAW+JPEG delivery) at all — it is not a
failure of #362, just an untested path. `scripts/physical-matrix.py` documents `format: 2 = RAW+JPEG, 1 =
RAW-only`, but `docs/CURRENT-STATE.md` explicitly warns *"do not infer RAW-only vs RAW+JPEG from
`photoFormat:2`"* — and a JPEG was delivered while `photoFormat:1`. Those two statements conflict, so the
mapping is unreliable and #362 must be tested by setting the format on the body and counting delivered files,
not by reading this field.

## Config-gate probe: PASS with zero refusals

`probe-config-gate.py --rounds 3`:

```text
265 iso                    real V=0 options=13
266 white-balance          real V=0 options=19
267 exposure-compensation  real V=15 options=32
268 shutter-speed          real V=20 options=57
275 aperture               real V=2 options=23
refusals in Clog after probe: 0 (delta 0)
VERDICT: every parameter code answered with a real value list
```

Five codes answered inside one second (`18:51:26`) with **zero gate refusals**. **This does not close #389.**
These are Polaris protocol codes, plausibly served from Stage-2's cached widget tree; #389 measured a raw
`gp_camera_get_config` via the gphoto2 CLI on direct-PC at 7.85 s / ~62 PTP ops. Different code path. Closing
#389 still needs the direct-PC timing run, which needs the PC-to-camera USB link rather than this rig.

## Also observed

`1&820&2&-100#` → `ret:-1` again (the AF path, #359) — consistent with every prior session: it has never
returned anything but -1 on any build.

## What this changes for v118 status

- **Bulb is now verified working** on v118 for the first time. Previously an untested assumption and the highest
  untested risk in the plan; it is no longer a risk.
- Capture delivery (JPEG) works, storage accounting is correct, camera recovers cleanly after captures.
- #362 remains **untested**, not failing — needs RAW+JPEG set on the body.
- #389 remains **open** — the protocol-level speed result does not measure the gphoto2 path it concerns.
- Cross-model qualification is still unproven: this is all K-1 II. The K-3 III could not be attached (see
  `../k3iii-v118-20261126/FINDINGS.md`).

## Reproduce

```bash
./scripts/verify-installed-build.sh out/astro-v118-stage2-gate-wedge-fix-20261126
python3 scripts/probe-config-gate.py --host 192.168.0.1 --ssh-host 192.168.0.1 --rounds 3
python3 scripts/probe-b-list-and-held-bulb.py   # fires the shutter; no --help, it runs immediately
```

Full transcript: `/tmp/bulb-probe-v118.txt` on this workstation (not in git).
