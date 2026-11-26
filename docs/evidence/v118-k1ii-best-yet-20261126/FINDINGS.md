# v118 on Pentax K-1 II: best K-1 II build observed so far, with named open defects

Candidate `astro-v118-stage2-gate-wedge-fix-20261126`, display `6.0.0.54.118`, patcher
`858edfd87be3681d26cbfee4810dff2c25c8696f`, libgphoto2 pin `f48a05e08b54d6d433a556c2df512987a51ce742`
(unchanged from v117 — there are no driver commits after it, so this release ships no driver change).

Recorded at operator request as the best build to date for the K-1 II. That claim is stated below with
its evidence and its limits, not as a blanket pass.

## Verdict

**Best K-1 II build observed so far.** The gate wedge that made `.115`–`.117` unusable on this body is
gone under the same load that produced it before. Four defects remain open and are listed with evidence
below; none of them returns the failure mode v117 had.

## Before / after on the same rig, same body

Baseline is `docs/evidence/v117-k1ii-regression-20261125/FINDINGS.md`, the symptom set reported against
the release that was installed until today.

| Reported on `.117` (K-1 II) | On `.118` | Evidence |
|---|---|---|
| "keeps periodically saying 'connect the camera'" | not observed in this session | operator report; 0 refusals inside the stress window |
| "liveview works for a moment, then goes black then shows reconnecting" | live view stays up; flickers ~3–4 s (see defect A) | operator report + refusal `held_ms` distribution |
| "changing parameter values do not stick" | reads all valid under 8 concurrent clients | `stress-config-gate.py`: 160/160 ok, 0 sentinel, 0 empty, 0 timeouts |
| "5 s bulb … countdown but shot failed" | not re-tested to completion this session | **not verified** — do not claim fixed |
| K-1 II fails faster than K-3 III, both fail | K-1 II holding under load | `pentax k-1 mark ii state=1 x8` across all 8 clients |

## Measured on the device (`.118`, K-1 II)

Identity and payload:

- `scripts/verify-installed-build.sh` → `INSTALLED BUILD IDENTITY: PASS`,
  `build_id=astro-v118-stage2-gate-wedge-fix-20261126`, `display_fwver=6.0.0.54.118`.
- Live loader `/app/lib/stage2/libpolaris_stage2.so` = `222a09f049a80b69b6d015d3df0f8f3f`, byte-identical
  to the loader built for this candidate and to the copy extracted out of the shipped `appfs.ubifs`. The
  v117 loader it replaced was `765e9528b8d2dddaeb0d25f6ed54e977`. So the fix is demonstrably what is
  running, not merely what was built.
- `pgphoto.stage2ondisk` = `79d4454fe2a674b32127698d0ee7aac1`, unchanged from v117 as expected — no
  pgphoto machine-code patch changed in this release.

Gate under load (`scripts/stress-config-gate.py --clients 8 --rounds 4`):

```text
load: 8 clients x 4 rounds x 5 codes = 160 reads
refusals before: 0
wall: 36.6s  throughput: 4.4 reads/s
latency p50=0.05s p95=3.64s max=3.64s mean=0.33s
outcomes: ok=160 sentinel(-1)=0 empty=0 timeouts=0 closed=0
admission refusals in window: 0
camera session seen by handshake: pentax k-1 mark ii state=1 x8
VERDICT: clean under load -- 160 reads all valid, p95=3.64s
```

The wedge signature on `.117` was 71 refusals in one window, **all** reading `generation=1`, i.e. the
gate wound up once and never released. On `.118` the same class of concurrent read load produces zero
refusals in-window and every read returns a valid value.

## Open defects on `.118`

### A. Live view flickers off/on every ~3–4 s (new symptom, mechanism identified)

Operator: "liveview goes on and off every 3-4 seconds. It's not dropping out, but just odd."

The refusal log now carries per-claim detail added in this release, and it matches the reported cadence
exactly:

```text
site=100540 kind=2 owner_site=100540 last_owner_kind=3 generation=1 camera_present=1 budget=500
  tid=1192 owner_tid=649 depth=1 held_ms=4080 stolen=0
site=102ff0 kind=0 owner_site=100540 last_owner_kind=2 ... held_ms=2517 stolen=0
```

`held_ms` ranges 1276–4458 ms. Site map from `container/test_stage2_native_admission.c`:
`0x100540 = STAGE2_CONFIG_WAIT_RETURN`, `0x102ba0 = STAGE2_PREVIEW_WAIT_RETURN`. So a config-path claim
is being held for seconds at a time, and preview/config waits are refusing each other while it is held.

This is **not** the v117 wedge: `stolen=0`, depth is bounded at 1, and every refusal recovers — which is
the intended behaviour of the lease. The remaining question is why a config read holds the camera for
~4 s at all. That is a pgphoto-side question, not a gate-logic question; the gate is now reporting it
instead of silently dying.

Attribution: refusals exist across `Clog_000015`–`Clog_000034`, i.e. **before** v118 as well. What is new
in v118 is the visibility (`tid/owner_tid/depth/held_ms/stolen`) and the recovery. Do not describe the
flicker as introduced by v118 without a pre-v118 measurement of the same cadence.

### B. Focus peaking garbles the lower half of live view (new, reproducible)

Operator: on iPhone "liveview looked really good, until I turned on focus peaking, when the screen
became garbled for the bottom half. Turning it off recovers full view."

Half-frame corruption that clears when the feature is disabled points at a frame-size or line-stride
mismatch when peaking overlays the stream, not at the gate. Live view geometry in the log at the time:
`area=720x480; active=720x480; caf-active=576x320; caf-spot=48x48`. `576x320` inside a `720x480` frame is
the kind of nesting where an offset or stride can go wrong. Not investigated further this session.

### C. Old iPad still crashes Benro Connect (pre-existing, client-side)

Operator: "liveview works ok on iPhone, but old iPad still crashes Benro Connect." Android and iPhone
both connect. No device-side crash text found (`segfault|SIGSEGV|abort|panic|oom` → no matches in the
current Clog/Mlog). This is a client-app issue on older iPads, not a Stage-2 fault.

### D. Shutter release ordering differs from K-3 III (new observation, cause not confirmed)

Operator: on K-1 II the capture button goes red and **immediately** says *image processing*, before the
shutter actuates. Previously it went red → shutter actuated → image processing.

One captured sequence shows a timing defect in pgphoto's own accounting:

```text
[pentax] capture=1 boundary=initiate-enter focus=2 companions=1
[pentax] capture=1 boundary=initiate-return ptp=0x2001
[16:25:10:722 INFO-]:capture_image[3164]:----capture end   -14374 ms
[16:25:10:740 INFO-]:capture_image[3171]:----get file to buffer   -18 ms
```

`capture end -14374 ms` and `get file to buffer -18 ms` are **negative durations**. Across every log on
the device the count is: negative = 32, positive = 0 — every capture duration ever logged on this rig is
negative, in v117-era logs (`Clog_000017`, `000027`–`000032`) as well as the v118-era one. So the
arithmetic bug is pre-existing and was **not** introduced by v118.

Whether it causes the reported ordering change is not established. A duration that reads as negative
could let a caller treat a capture as instantly complete, which would match "processing before actuation",
but that is a hypothesis: no evidence yet ties it to the UI state machine or shows a v117/v118 difference
in the ordering itself. `ptp=0x2001` on both preconditions and initiate is PTP_OK, so the vendor ops
themselves succeeded.

## Not verified this session — do not record as fixed

- Bulb capture end-to-end (the `.117` "countdown then failed" symptom).
- RAW+JPEG delivery (issue #362). Detection works — `companions=1` on every dual-format capture, including
  a fresh boot — but `gp_camera_get_extra_capture_files` still has no consumer in pgphoto or
  `libpolaris_stage2.so`.
- Live view frame delivery as a measured rate (only operator-reported quality).
- Cross-model qualification. The gate regression affected **every** model on `.115`–`.117`; only the K-1 II
  was exercised here.

## Release-process defects found while verifying this install

1. **The canonical identity check passed while the astro kit was stale.** `/app/sd/polaris-astro/VERSION`
   read `astro-v117-k3iii-late-arrival-20261125` / `6.0.0.54.117` on a rig running `.118`. The kit is not
   part of appfs, so `verify-installed-build.sh` had nothing to compare and returned PASS. A flash deletes
   `/app/astro` and its boot hook; the device then reports the correct FwVer while plate solving still
   runs the previous candidate's kit. Fixed: the verifier now compares the candidate's kit `build_id`
   against the installed one whenever the candidate carries a kit, and fails closed on both mismatch and
   absence. Verified with four synthetic cases (stale → fail, missing → fail, match → pass, camera-only
   candidate → silent).
2. **The flash exited before the kit step and nobody noticed.** `release-fwpkt.sh` gave up waiting for the
   device after 900 s (`WARN: device not back`, exit 5), so step `[7/7]` never ran. The AP flapped during
   the wait; the rig had in fact reflashed successfully. Staging and MD5 verification had already passed
   on-device, including `appfs 003c130b1c69a71c4499e519af335ea4`.
3. **`probe-config-gate.py` counts refusals from the wrong path.** It greps `/app/Clog.txt`, which does not
   exist on this device; refusals live in `/app/sd/system/log/Clog_*.log`. It therefore always reports
   `refusals already in Clog: 0` and a delta of 0 regardless of what actually happened. Its `--bind`
   default is also the workstation's IP on the rig subnet, which breaks after a Wi-Fi re-join hands out a
   different address. Not fixed yet — until it is, treat its refusal counts as unusable and read the logs
   directly.
4. **A router on the same L2 fooled the reachability check.** After the flash, `ping 192.168.0.1` answered
   while the rig was dark, because the route went `via 192.168.68.1 dev enp11s0` to the LAN router, not to
   the head. `polaris-debugging` §5 already warns about this; the lesson is to assert
   `ip route get 192.168.0.1` shows `dev wlp8s0` before believing any reachability result.

## Reproduce

```bash
# identity + kit
./scripts/verify-installed-build.sh out/astro-v118-stage2-gate-wedge-fix-20261126
# gate under concurrent read load (read-only by construction)
python3 scripts/stress-config-gate.py --ssh-host 192.168.0.1 --ipolar-host 192.168.0.1 \
    --clients 8 --rounds 4
# refusal detail, including the new per-claim fields
ssh root@192.168.0.1 'sed "s/\x1b\[[0-9;]*m//g" /app/sd/system/log/Clog_*.log \
  | grep -a "admission refused" | tail -20'
```
