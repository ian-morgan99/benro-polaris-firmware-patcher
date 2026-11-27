# K-1 II issue plan — v118 findings mapped to existing issues, serial execution order

Base: `astro-v118-stage2-gate-wedge-fix-20261126` (`6.0.0.54.118`), rig `d13e86`, K-1 II.
Evidence: `docs/evidence/k1ii-overnight-20261126/` (redacted logs + HANDOFF.md).
Repo: `ian-morgan99/benro-polaris-firmware-patcher`.

## Framing for the next run (operator, 2026-11-26)

**None of these failures are new, and that is the point.** They have been failing across v104–v117. What is
different now is that we are materially closer to solving them than we have ever been: for the first time the
gate recovers instead of wedging, the refusal diagnostics name the holding site with `held_ms`, the config-read
cost is quantified (#389), and the AF failure has been decoupled from contention. The v118 evidence in
`docs/evidence/k1ii-overnight-20261126/` is therefore **critical input for the next run** — it is the first
dataset where each symptom is measurable rather than just observable. Treat it as the working baseline, not
as another log dump.

Corollary: do not re-litigate whether these defects predate v118. They do, they are tracked, and that is
settled. Spend the run on the narrowed causes above.

## Read this first: most of it is already tracked

I checked every symptom against the issue tracker before planning anything. The important result is that
**the K-1 II symptoms are not new** — they have open issues with prior evidence, and v118 mostly adds
confirmation rather than new defects. Planning "fix 5 new bugs" would have duplicated work and ignored
existing acceptance criteria.

Two findings genuinely change what should be done first:

1. **#389 explains the live view flicker.** A single `gp_camera_get_config` for ONE widget on a live K-1 II
   costs **7.85 s / ~62 PTP round-trips** because devprop caching is flushed and all 30 descriptors are
   refetched per call. That is almost certainly what holds the gate for seconds — my `held_ms=1276..4557`
   observations are downstream *symptoms* of #389, not a gate defect. **Do not tune the gate lease/budget
   to chase the flicker.** Fix the config-read cost and the flicker should collapse with it.
2. **#359 already covers AF**, including the exact `sp_Gphoto_Init → updateCameraAutoFocus → -1` chain, with
   v104 evidence. My contribution is that it still fails on v118 with **zero successes ever** across every
   log on the rig, and that it fails in a file with **zero gate refusals** — which retires the contention
   hypothesis #359 leaves open.

   **Correction to my own triage here.** I wrote that AF is "vendor `polestar_app`, not our code" because
   those symbols are absent from our repos. That inference is invalid and the claim is withdrawn: pgphoto
   was already decompiled on this workstation, and its `updateCameraAutoFocus` resolves a libgphoto2 widget
   by name and calls `gp_camera_set_config` — a widget our camlib owns. Four branches in that function can
   return `-1`, and one of them returns success having done nothing at all. Task 8 below ("prove/disprove
   our opcode-311 kit path") does **not** settle ownership either way; it only tells us whether a workaround
   exists. Run `scripts/find-authoritative-source.py updateCameraAutoFocus` before re-triaging #359.

## Triage: symptom → existing issue → what v118 adds

| Symptom | Issue | Status | What v118 evidence adds |
|---|---|---|---|
| LV flickers off/on every 3–4 s | **#389** (+ #369) | open | `held_ms` 1276–4557 ms on `0x100540` = `STAGE2_CONFIG_WAIT_RETURN`. Confirms the 7.85 s config cost is now *bounded and recovering* instead of wedging. Symptom, not cause. |
| AF "trying but not working" | **#359** (+ #146/#147) | **root-caused, fix shipped in v119; runtime unqualified** | Fails on v118 too. `ret:-1` in **every** log file containing an attempt, 0 successes ever. Fails with **0 refusals** in the same file (`Clog_000033`) → contention ruled out. ~~Vendor `polestar_app`, not our code~~ **withdrawn**: pgphoto's `updateCameraAutoFocus` is a generic libgphoto2 widget call (see `docs/evidence/k1ii-overnight-20261126/HANDOFF.md`). **Root cause found:** `_get_Pentax_AutofocusDrive` returned `NOT_SUPPORTED` unless the model was in the PC-live-view table, which removed the widget from the tree entirely — so pgphoto's `_find_widget_by_name("autofocusdrive")` failed and AF reported `-1` with no diagnostic. Only K-3 III and K-3 III Monochrome carry `supports_pc_live_view = 1`, which is exactly why AF worked there and nowhere else. Fixed in libgphoto2 `089ae66c7`; shipped in v119 (`ptp2.so` md5 `84c724e2…`). **Still unproven on hardware:** no camera was attached when v119 was installed (`lsusb` shows hubs only), so the qualification round could not run. |
| Focus peaking garbles lower half | **#363** (+ #383) | open | #363 already records K-1 II **>50%** vs K-3 III ~20 px. Confirms it survives to v118. No device-side log evidence exists — needs live repro. |
| RAW+JPEG shown as RAW (#362) | **#362** | open | Detection works (`companions=1` on every dual-format capture, fresh boot included). `gp_camera_get_extra_capture_files` still has **no consumer**. |
| Negative capture durations | **#315** | open | #315 already logs `capture end -14660 ms`. v118 adds scale: **32 negative, 0 positive** across every log ever written on this rig — it is *every* capture, not one instance, and persists to v118. |
| Shutter says "processing" before actuation | **#315** | open | #315's title is literally "shutter release timing wrong". The K-1 II vs K-3 III **ordering difference** is the only part not captured — comment on #315 rather than filing new. |
| Old iPad crashes Benro Connect | client app | out of scope | No device-side crash text at all. iPhone/Android fine. Not Stage-2. |
| Clients dropping out | **#360** (+ new) | partial | `SP_ClientCtxDel:not find this is id[N]` × **307**, open+close in the same millisecond. Vendor socket bookkeeping race — not tracked as its own defect. |

### Blast radius of the #359 fix (v119) — which bodies need AF re-testing

`supports_pc_live_view = 1` is set for exactly two entries in
`pentax_model_capabilities[]` (`camlibs/ptp2/pentax-utils.c:1042,1064`). Because the
old AF getter required it, `autofocusdrive` existed on **only** those bodies. Removing
the requirement exposes the widget on every supported Pentax model, so this is not a
K-1 II-only change and cannot be qualified by testing one body.

| Body | `autofocusdrive` before v119 | After v119 | AF runtime status |
|---|---|---|---|
| K-3 III | present | present (unchanged) | was the only body where AF worked — re-test to prove no regression |
| K-3 III Monochrome | present | present (unchanged) | untested, no hardware |
| **K-1 II** | **absent → `-1`** | present | **the #359 case; untested, no camera attached** |
| K-1 | absent → `-1` | present | untested, no hardware |
| K-P, K-70, K-3, GR III, 645D, 645Z, KF | absent → `-1` | present | untested, no hardware |

The set path is gated on `conditions.af_mode != 0`, matching IT2's own `CamAutoFocus()`
precondition, and returns a clear error rather than sending `PTP_OC 0x9011` when the
body is in MF. It keeps `_pentax_readiness_preflight` and never deletes a transfer
candidate. So a body that genuinely cannot drive AF should fail cleanly instead of
misbehaving — but "should" is not evidence, and none of these bodies has been driven
since the change.

Verify statically with `scripts/check-af-fix.py <config.c>`: it passes on `089ae66c7`
and fails on the parent commit, checking the getter, the `af_mode` gate, the retained
preflight and the no-delete rule by function scope. It cannot substitute for a body on
the bench.

## Genuinely new — but read N1 first

### N1. SECURITY: account password and security answer are logged in base64 — **already published publicly**

`code:790` (the account flow) writes credentials to the rotating camera log on **every session**, as plain
base64:

```text
msgToApp success;type[2],code[790],val[step:1;password:[REDACTED-B64];securityQ:3;securityA:[REDACTED-B64]]
```

The logs live on the SD card at `/app/sd/system/log/`, readable by anyone with the card or with storage
access, and eight credential-bearing evidence files are on `origin/main` of a **PUBLIC** repo dating to at
least 2026-09-29 (list in HANDOFF.md).

**Severity, corrected after decoding the values.** The logged PIN is a trivial well-known four-digit default,
so there is probably nothing to rotate and this is *not* the "do it before anything else" item I first called
it. Two caveats keep it worth fixing:

- The **security answer** decodes to 16 characters that look like a genuine answer (a personal name), not a
  default. That field pairs with the PIN to defeat account recovery and is the one actually worth caring about.
- Whether the logged PIN is this account's live value is knowable only to the operator. If it was never
  changed there is nothing to rotate; if the real PIN differs, the logged value is stale and harmless.

So the durable defect is the **logging behaviour**, not these particular values: `code:790` writes account
material into a world-readable rotating log on every session, which will keep happening for any account that
uses a non-default PIN. Fix that, redact the eight files at HEAD, and add a CI guard failing on
credential-shaped patterns in evidence. A history rewrite is not worth it here — it invalidates every SHA
after the rewrite point, including the release/registry references this project depends on, for a default PIN.

**Do not file this as a public issue.** An issue naming the affected paths would advertise exactly where to
look. Track it privately until the files are redacted.

Related but distinct: **#290** covers a Wi-Fi password in *process arguments*. This is credential material in
*persisted logs*, which is a wider exposure.

### N2. `SP_ClientCtxDel:not find this is id[N]` — **withdrawn as filed; my own probing**

I originally proposed this as a vendor socket-lifecycle race and called it the best device-side candidate for
the client dropouts. That was wrong. The pairs in the K-3 III bundle come from **192.168.0.4 — this
workstation**, i.e. my own one-shot `printf | nc -q1` probes:

```text
SOCKET_ACCEPT(201) [id=96 192.168.0.4:39950] s_u32ClientNum[4]
SOCKET_CLOSE(201)  [id=96] s_u32ClientNum[3]
ERROR SP_ClientCtxDel[392]: not find this is id[96]
```

Open and close within the same millisecond is exactly what a one-shot probe does, so the 307 occurrences in
the K-1 II bundle are largely self-inflicted — that session involved heavy probing. Do not file this until it
is re-counted with no probes running and confirmed from genuine client IPs (phone/tablet). See
`k3iii-v118-20261126/FINDINGS.md`.

Separately, the "clients dropping out" report is **not** explained by this. When the K-3 III was attached-but-
invisible, Benro Connect toasted as if reconnecting every ~30 s while pgphoto's PID stayed constant, `dmesg`
line count never moved, and USB presence never flickered — nothing was actually flapping. The toasts tracked
the app's own 30 s `code:286` poll returning `model:none;state:-5`. Absence reported on a timer looks like
churn; it is not instability.

### N3. Shutter state ordering differs between K-1 II and K-3 III — **comment on #315, do not file**
Red → *image processing* → actuation on K-1 II; previously red → actuate → processing. #315 already covers
"shutter release timing wrong" with the same negative-duration arithmetic, so this is a comment there, not
a new issue. Hypothesis only: negative durations may let a caller treat a capture as instantly complete.
`ptp=0x2001` on both preconditions and initiate, so the vendor ops succeeded. **Needs the K-3 III
comparison before it is called a regression.**

### N4. Release-process gaps found while verifying this install (already fixed here)
Worth issues so the fixes get reviewed rather than landing silently:
- Kit identity was never verified: rig ran `.118` with the **v117** kit stamped and `verify-installed-build.sh`
  returned PASS. Fixed in `791ab779` (fails closed on mismatch/absence, 4 synthetic cases).
- Both rig tools grepped `/app/Clog.txt`, which does not exist on `.115+`, so they reported **0 refusals**
  against an actual 61. Fixed in `17d093aa` (unknown now reports UNKNOWN, never 0).
- `release-fwpkt.sh` exits at `[5/6]` when the AP flaps during the 900 s wait, silently skipping `[7/7]`
  kit install even though the reflash succeeded. **Not fixed** — this is the one that actually bit us.

## Serial execution order for the overnight run

`#375` mandates strictly serial, single-agent, one branch/PR at a time, checkpoint after each task. This
order follows its queue and puts the highest-leverage fix first.

| # | Task | Issue | Why here | Needs rig? |
|---|---|---|---|---|
| 0 | Redact the eight published evidence files at HEAD + CI guard on credential-shaped patterns | N1 (private) | The *logging defect* is the durable problem. The leaked PIN turned out to be a trivial default, so this is no longer an emergency — but close it before more evidence accumulates. | no |
| 0b | Record baseline: v118 identity, loader MD5 `222a09f0…`, kit stamp, archived packet `d078695cf` | #361/#375 task 00 | Already done this session; paste into #375 checkpoint. | no |
| 1 | Credential redaction at the vendor write site (never log `password:`/`securityA:`) | N1 (private) | Independent of camera work, no hardware risk. | no |
| 2 | Instrument config-read cost on v118 **via direct-PC `gp_camera_get_config`** | #389/#369 (task 03) | Protocol-level probe is fast with 0 refusals, but that is a different code path — it does NOT close #389. Needs the PC-to-camera USB link. | **yes** |
| 3 | Cache `GetDevicePropDesc` per session; build widget tree once | #389 (task 04) | The dominant K-1 II latency source. Expected to collapse LV flicker *and* p95=3.64 s. | partial |
| 4 | Batch `GetAllConditions` | #369 | Cheap only after step 3, per #389's own note. | partial |
| 5 | RAW+JPEG: wire a consumer for `gp_camera_get_extra_capture_files` | #362 (task 11) | Detection already proven on v118; the gap is consumption, not discovery. | **yes** |
| 6 | ~~Bulb end-to-end~~ **VERIFIED on v118** — see `k1ii-v118-bulb-verified-20261126/` | #145/#251/#317 | States `1→4→0` twice, two JPEGs delivered, storage accounting correct. Remaining: cancellation, and `duration:0` vs a *timed* bulb (#315). | **yes** |
| 7 | LV frame corruption: characterise peaking repro | #363/#359 (task 08) | Needs live capture; cannot be diagnosed from logs. | **yes** |
| 8 | AF: prove/disprove our opcode-311 kit path works independently of vendor AF | #359/#146 | Determines whether this is upstream-report-only or ours to route. | **yes** |
| 9 | Capture-duration arithmetic + ordering comparison | #315 | Fix the negative durations (every capture, not one case), then re-test ordering on both bodies and post the K-1 II/K-3 III difference as a comment on #315. | **yes** |
| 10 | Re-count `SP_ClientCtxDel` with no probes running; only file if genuine clients trigger it | N2 (withdrawn) | My own `nc` probes produced most of the 307. Verify before filing. | no |
| 11 | `release-fwpkt.sh`: run kit install even after a lost connection | N4 | Prevents a repeat of the stale-kit install. | no |

Steps 2, 5–9 need the rig. Steps 1, 4(partial), 10, 11 are offline — do those if the rig goes dark.

## What the K-3 III session must capture (do this before any code)

The gate regression hit **every** model on `.115`–`.117`; only the K-1 II has been exercised on v118. Until
the K-3 III passes, v118 is not cross-model qualified — that is the single biggest gap in its status.

```bash
# 1. identity + kit first, always (kit check now fails closed)
./scripts/verify-installed-build.sh out/astro-v118-stage2-gate-wedge-fix-20261126

# 2. gate under load — refusal counts are honest now, read them
python3 scripts/stress-config-gate.py --ssh-host 192.168.0.1 --ipolar-host 192.168.0.1 \
    --clients 8 --rounds 4

# 3. config-read cost: is #389 still ~62 PTP ops / ~7.85 s on this body?
ssh root@192.168.0.1 'ls -t /app/sd/system/log/Clog_*.log | head -1 | xargs sed "s/\x1b\[[0-9;]*m//g" \
  | grep -acE "GetDevicePropDesc|GetAllConditions"'

# 4. AF: does the vendor path fail identically on K-3 III?
ssh root@192.168.0.1 'ls -t /app/sd/system/log/Clog_*.log | head -1 | xargs sed "s/\x1b\[[0-9;]*m//g" \
  | grep -aE "updateCameraAutoFocus|change focus mode" | tail -20'

# 5. capture ordering + duration sign (the #315/N3 comparison)
ssh root@192.168.0.1 'ls -t /app/sd/system/log/Clog_*.log | head -1 | xargs sed "s/\x1b\[[0-9;]*m//g" \
  | grep -aE "capture=|capture end|get file to buffer" | tail -20'

# 6. peaking corruption extent on this body (compare to K-1 II >50%)
```

Then **redact before committing** — same command as HANDOFF.md.

## Guardrails

- **Do not tune the gate lease or budget to fix the flicker.** #389 is the cause; the gate is now behaving
  correctly (recovers, `stolen=0`, depth bounded at 1).
- **Do not attribute the flicker, peaking corruption, AF failure, or negative durations to v118.** All four
  predate it in this rig's own logs.
- **Redact every device log bundle before commit.** No exceptions — credentials are already public precisely
  because this was never enforced (N1).
- **Never quote credential values**, not in prose, not in issues, not inside a redaction example. Name the
  field, never the value. (This plan deliberately does not reproduce them, even though they are already public.)
- **Serial only** per #375: one branch, one task, checkpoint in #375 after each.
- v118 is archived (`d078695cf`, MD5 `b0e59b08…` verified byte-identical) and v117 remains the fallback
  (`8719db93f`). Rollback is available before any of this starts.

## Not verified — do not record as fixed

Bulb end-to-end; RAW+JPEG delivery; LV frame delivery as a measured rate; cross-model qualification;
whether our kit AF path works at all.
