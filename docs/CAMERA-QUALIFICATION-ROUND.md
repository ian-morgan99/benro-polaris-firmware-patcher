# Camera qualification round — one session for #293 Phase 4

`scripts/camera-qualification-round.py` runs WBS-04.1 through WBS-04.7 against a real
camera in one pass, so the K-1 II / K-3 III qualification needs one physical session
instead of seven separate probes. It was written because the camera issues (#275 preview,
#276 shutter, #277 ISO, #278 AF, #279 capture, #251 Bulb, #285 crash, #274 busy) each
accumulated their own probe and none of them kept the bytes behind their verdict.

**Nothing here qualifies a camera by itself.** `DEVICE_VERIFIED` means the device answered
that case. #293 still requires independent review, and code-only tests never qualify a
camera.

## Before you start

1. Join the gimbal's own AP (`polaris_*`, BSSID prefix `48:E7:DA`). `root@192.168.0.1` is
   also your home router — the script checks identity, but join the right network first.
2. Confirm the camera is awake and attached (`25fb:0183` for the K-1 II) and the battery is
   charged. #285 lists a depleted battery as a crash candidate; do not start a round you
   cannot finish.
3. **Do not run this on the SD card reported in #284.** That card returns continuous FAT
   metadata errors, so captured logs may be incomplete and the harness will say so rather
   than silently producing partial evidence.

## Run it

```sh
# what it would do, touches nothing
python3 scripts/camera-qualification-round.py --plan

# the round
python3 scripts/camera-qualification-round.py --host 192.168.0.1 \
    --outdir /tmp/polaris-camera-qualification
```

Bulb cases are gated behind two flags, because #293 forbids unattended Bulb tests and
cancellation is a safety release blocker:

```sh
python3 scripts/camera-qualification-round.py --with-bulb --i-am-present
```

`--i-am-present` asserts you can physically interrupt the shutter. Exposure length is capped
by `canary_probe.MAX_TEST_EXPOSURE_SECONDS` (45 s), inherited rather than re-declared so the
two tools cannot disagree.

## What each case does, and what it cannot tell you

| Case | Issues | Method | Honest limit |
|---|---|---|---|
| WBS-04.1 | #285 #253 | pgphoto pids, single `:1F90` listener, 9090 reachability, crash signatures in logs | cannot attribute the exit-139 to a frame; needs PC/LR from the loader's signal handler |
| WBS-04.2 | #275 #274 | requests liveview off via 291/292, then counts new `get-frame` lines in Clog over 5 s | proves frames stopped arriving; does not prove the scheduler released the camera |
| WBS-04.3 | #147 #146 | reports what it can reach | frame integrity must be hashed at camera→pgphoto→transport→iOS and the iPad crash reproduced separately — not automatable from a PC |
| WBS-04.4 | #276 #277 #233 #232 | writes ISO, EV, then shutter; polls for physical readback instead of trusting `ret:0` | ISO/EV first so a shutter failure is not masked by earlier retries leaving the body busy |
| WBS-04.4b | #276 #277 #233 | reads every control, writes **one**, reads them all again | a re-applied identical value is invisible from readback alone; confirm with Clog showing multiple `SP_SET_*` per one request |
| WBS-04.5 | #278 | reports AF job state | **needs you watching the lens.** No automated proxy can prove lens movement |
| WBS-04.6 | #279 | fires one capture, follows 264 states, compares produced files | distinguishes queued-command success from a real file; does not test RAW/JPEG matrix or recovery |
| WBS-04.7 | #251 | refuses to run without both flags | cancellation must be exercised manually with `canary-probe.py`; see #251 |

## Reading the output

Statuses follow #293's vocabulary — `DEVICE_VERIFIED`, `OFFLINE_VERIFIED`,
`CODE_COMPLETE_UNVERIFIED`, `UNKNOWN`, `BLOCKED`, `FAIL`. They are not interchangeable:

- **BLOCKED** — could not reach the device. Never a pass. An unreachable camera yields
  BLOCKED for all eight cases and zero passes; that is asserted in
  `tests/test_camera_qualification_round.py` and mutation-tested.
- **UNKNOWN** — ran, but the result cannot be attributed. WBS-04.4b returns this when no
  unrequested control moved, because that does not disprove re-apply.
- **CODE_COMPLETE_UNVERIFIED** — the check exists but needs a human or hardware observation
  (AF lens movement, iOS frame integrity).

A bundle is written even when every case fails:

```
camera-qualification-<UTC>.tar.gz
  transcript.txt   every TX/RX and decision with timestamps
  cases.json       one record per WBS item, with status and evidence
  logs-before/     every Mlog/Clog, sha256'd, captured first
  logs-after/      captured again after the round
```

Re-score saved bytes without a device:

```sh
python3 scripts/camera-qualification-round.py --analyze-only <bundle>.tar.gz
```

## Two things this exists to prevent

**Evidence loss.** #275, #276 and #277 all quote `ret:-2110` lines dated 2026-11-08. That
literal appears **zero times** in `docs/evidence` (131 bundles) and those logs are not on
disk anywhere — the session was never pulled. The most quoted evidence for the control
failures cannot be re-examined, which is why #293 asks for retained raw bytes before
quoting rates. Logs are snapshotted before and after so a verdict always has its evidence.

**Wrong markers.** Aperture emits `SP_SET_FNUM`; there is no `SP_SET_APERTURE`. Grepping the
latter returns nothing, which is how aperture came to be reported as never exercised when
eight successful writes are archived. Measured with the correct names:

| control | OK | FAIL |
|---|---|---|
| ISO | 8 | 0 |
| EV | 4 | 0 |
| aperture (`FNUM`) | 8 | 1 |
| shutter | 8 | 14 |
| WB | 0 | 1 |

Failures concentrate on shutter, not evenly across configTypes as earlier summaries suggested.

## After the round

Attach the bundle to each owning issue and record status per #293 rule 3 — agent, date,
commit, proof link, offline/device status, reviewer. Leave partial tasks unchecked. A
`FAIL` that reproduces a known bug is a good outcome: it means the failure mode is real and
now has bytes behind it.
