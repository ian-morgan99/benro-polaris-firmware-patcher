# K-1 II on v118 — evidence bundle and overnight fix plan

Rig `d13e86`, firmware `astro-v118-stage2-gate-wedge-fix-20261126` / display `6.0.0.54.118`,
patcher `858edfd87be3681d26cbfee4810dff2c25c8696f`, libgphoto2 pin `f48a05e0` (unchanged from v117).
Camera: Pentax K-1 II. Captured 2026-11-26 before the body was powered off.

## Contents

- `sanitized/` — 40 log files (`Clog_000016..000035`, `Mlog_000015..000034`) pulled from
  `/app/sd/system/log/`, **credential-redacted**. Read these, not the device.

### Why sanitized and nothing else exists here

The raw logs contain base64 account credentials in cleartext-adjacent form:

```text
msgToApp success;type[2],code[790],val[step:1;password:[REDACTED-B64];securityQ:3;securityA:[REDACTED-B64]
```

`password:` decodes to a 4-digit PIN and `securityA:` to a security-question answer (both are plain
base64, trivially reversible). These appear in most Clog files. The raw copies and the original
`device-logs.tgz` were **deleted** rather than committed; only the redacted set is here, with `password:` /
`securityA:` values replaced by `[REDACTED-B64]`.

### This is not a new problem — it is already published

While writing this up I checked the whole tree, not just my own files. **8 credential-bearing evidence files
are already on `origin/main`, and the repo is PUBLIC.** They have been there since at least 2026-09-29:

```text
docs/evidence/benro-connect-crash-20261010/raw/Mlog_000276.txt
docs/evidence/issue-297-k3iii-stale-restart-lock/api-link-opcodes.json
docs/evidence/liveview-crash-camera-offbus-20261103/raw/Mlog_000356.clean.txt
docs/evidence/o-v13t-preinstall-state-20260929-132320/Mlog_000169.txt   (+ 000170, 000171)
docs/evidence/v104-k1ii-android-20261110/Mlog-android-baseline.txt
docs/evidence/v104-k1ii-liveview-garbled-20261110/Mlog-post-reboot-camera-not-detected.txt
```

Anyone can read these today. Removing the files from HEAD does not fix it — they remain in git history and
in any clone or fork made since September. Treat the PIN and security answer as **compromised**: rotate them
on the Benro account, then decide separately whether history rewriting is worth the disruption (it invalidates
every commit SHA after the rewrite point, including the release/registry references this project depends on).

**Do this before any camera work.** It is the only item here with an external blast radius.

**Standing rule this implies:** any device log bundle must be redacted before it touches git. `code:790` is
the account flow and it logs credentials on every session. Add a CI guard that fails on credential-shaped
patterns in committed evidence — prose that *names* the fields is fine, but never quote their values.

Redaction used:

```bash
sed -E 's/(password:)[A-Za-z0-9=+\/]*/\1[REDACTED-B64]/g; s/(securityA:)[A-Za-z0-9=+\/]*/\1[REDACTED-B64]/g'
```

## Install state — verified, not assumed

| Check | Result |
|---|---|
| `verify-installed-build.sh` | **PASS** — `build_id=astro-v118-stage2-gate-wedge-fix-20261126`, `display_fwver=6.0.0.54.118` |
| `/app/lib/stage2/libpolaris_stage2.so` | `222a09f049a80b69b6d015d3df0f8f3f` — byte-identical to the loader built for this candidate and to the copy extracted from the shipped `appfs.ubifs`. Replaced v117's `765e9528b8d2dddaeb0d25f6ed54e977`. |
| `/app/lib/stage2/pgphoto.stage2ondisk` | `79d4454fe2a674b32127698d0ee7aac1` — unchanged from v117, as expected (no pgphoto machine-code change in this release) |
| Astro kit | `build_id=astro-v118-stage2-gate-wedge-fix-20261126`, 714 files verified byte-for-byte, **port 8090 serving**, boot hook present |

The kit needed a second pass. The flash exited at step `[5/6]` when the AP flapped during the 900 s wait,
so step `[7/7]` never ran and the rig booted with the **v117** kit stamped on SD while running `.118`.
`verify-installed-build.sh` returned PASS anyway — it had nothing to compare, because the kit is not part
of appfs. Fixed in `791ab779`: the verifier now compares kit `build_id` and fails closed on mismatch or
absence. Kit re-installed and confirmed (`installed-verified`, receipt appended).

## Gate: fixed, measured

`stress-config-gate.py --clients 8 --rounds 4` (read-only by construction):

```text
160 reads: ok=160 sentinel(-1)=0 empty=0 timeouts=0 closed=0
latency p50=0.05s p95=3.64s max=3.64s mean=0.33s   throughput 4.4 reads/s
camera session seen by handshake: pentax k-1 mark ii state=1 x8
```

The v117 wedge signature was 71 refusals in one window, **all** `generation=1` — the gate wound once and
never released. On v118 every refusal recovers, `stolen=0`, depth bounded at 1.

**Correction to a number quoted earlier today:** an earlier run printed `admission refusals in window: 0`.
That was wrong. Both rig tools grepped `/app/Clog.txt`, which does not exist on `.115+` — the daemon writes
rotating logs under `/app/sd/system/log/`. An empty grep was indistinguishable from a healthy gate. The
newest Clog actually held 61 refusal lines at that moment. Fixed in `17d093aa`; unknown now reports as
UNKNOWN instead of 0. The read-outcome numbers above are unaffected — they come from the socket, not the log.

## Open defects, ranked by how actionable they are

### 1. Autofocus never succeeds — vendor code, decoupled from the gate (NEW evidence)

Operator: "autofocus appears to be trying to do something on the k1ii but it doesn't seem to be quite working."

Every single attempt fails, both directions:

```text
[17:30:39] updateCameraAutoFocus 1
[17:30:42] updateCameraAutoFocus 0
[17:30:47] updateCameraAutoFocus enable:0  ret:-1
[17:30:47] camera_autoFocus_enable  0
[17:30:47] camera_autoFocus_enable  1
[17:30:51] updateCameraAutoFocus enable:1  ret:-1
```

Counts across the whole bundle: `ret:-1` in **every** log file that contains an AF attempt, and **zero**
successes ever. Per-file failure rate is 100%.

Two things narrow the cause sharply:

- **It is not gate contention.** `Clog_000033.log` contains an AF attempt with **zero** admission refusals
  in the same file, and that attempt still returned `ret:-1`. Correlation across files is also weak
  (`Clog_000028`: 2 failures / 8 refusals; `Clog_000034`: 25 / 93). The near-match between the ~4.3 s AF
  block and the ~4.5 s gate holds is a coincidence, not a cause — do not chase it.
- **It is not our code.** `updateCameraAutoFocus`, `camera_autoFocus_enable` and `sp_Gphoto_Init` appear in
  no source file in this repo. They are vendor `polestar_app`. The sequence `change focus mode ret 0`
  succeeds immediately before the failure, so the mode change works and the AF enable itself times out at a
  consistent ~4.3–4.4 s — a timeout signature, most likely a PTP/vendor-PTP reply that never arrives on
  this body.

Our kit's own focus path is separate and unaffected by this: `autofocus.sh` drives the focuser
**relatively via opcode 311** through the already-registered control channel, and scores frames by median
HFR from `polaris-extract --focus-metric`. Tunables `AF_STEPS AF_ADJ AF_SETTLE AF_BACKLASH DOWNSAMPLE`,
progress in `AF_JSON`.

Overnight: confirm whether the kit path works independently of the vendor path. If opcode 311 works, the
vendor `updateCameraAutoFocus` failure is a Benro/Pentax issue to report upstream, not something we can
patch — and the app's AF button should probably route to our path instead.

### 2. Live view flickers off/on every ~3–4 s

Operator: "goes on and off every 3-4 seconds. It's not dropping out, but just odd."

Matches the new per-claim diagnostics exactly — `held_ms` ranges 1276–4557 ms:

```text
site=100540 kind=2 owner_site=100540 last_owner_kind=3 budget=500 tid=1192 owner_tid=649 depth=1 held_ms=4080 stolen=0
site=102ff0 kind=0 owner_site=100540 ... held_ms=2517 stolen=0
```

Site map (`container/test_stage2_native_admission.c`): `0x100540 = STAGE2_CONFIG_WAIT_RETURN`,
`0x102ba0 = STAGE2_PREVIEW_WAIT_RETURN`. So a **config-path** claim holds the camera for seconds and
preview/config waits refuse each other while it is held. Histogram in the newest Clog:
`37× site=100540 kind=2`, `6× 102cd4 kind=0`, `5× 100540 kind=3`, `3× 102ff0 kind=0`.

Refusals exist across `Clog_000016`–`000035`, i.e. before v118 too. What is new in v118 is the visibility
and the recovery — **do not describe the flicker as introduced by v118** without a pre-v118 cadence
measurement. The actionable question is why a config read holds the camera ~4 s at all; that is pgphoto/vendor
behaviour, and the gate is now reporting it instead of silently dying.

### 3. Focus peaking garbles the lower half of live view (iPhone)

Operator: "liveview looked really good, until I turned on focus peaking, when the screen became garbled for
the bottom half. Turning it off recovers full view."

**No device-side log evidence exists for this.** `Pentax Focus Peaking Descriptor` is logged as a readonly
TEXT widget with no value, and there is no peaking/mjpeg/decode marker anywhere in the bundle. Geometry at
the time: `area=720x480; active=720x480; caf-active=576x320; caf-spot=48x48`. A 576×320 region nested in a
720×480 frame is where a line-stride or offset error would corrupt exactly the lower half. Needs a live
repro with frame capture to characterise — cannot be diagnosed from these logs.

### 4. Shutter reports "image processing" before actuation (K-1 II; K-3 III differed)

Operator: button goes red → immediately *image processing* → shutter actuates. Previously red → actuate →
processing.

One captured sequence exposes a timing defect in pgphoto's own accounting:

```text
[pentax] capture=1 boundary=preconditions-return ptp=0x2001 size=576
[pentax] capture=1 boundary=initiate-enter focus=2 companions=1
[pentax] capture=1 boundary=initiate-return ptp=0x2001
[16:25:10:722] capture_image[3164]:----capture end   -14374 ms
[16:25:10:740] capture_image[3171]:----get file to buffer   -18 ms
```

`capture end -14374 ms` and `get file to buffer -18 ms` are **negative durations**. Across every log on the
device: **32 negative, 0 positive** — every capture duration ever logged is negative, in v117-era files
(`000017`, `000027`–`000032`) as well as v118's. So the arithmetic bug is pre-existing and **not** a v118
regression.

Whether it *causes* the ordering change is unproven. A duration reading negative could let a caller treat a
capture as instantly complete, which fits the symptom, but nothing here ties it to the UI state machine or
shows a v117→v118 difference in the ordering itself. `ptp=0x2001` (PTP_OK) on both preconditions and
initiate means the vendor ops succeeded.

### 5. Old iPad still crashes Benro Connect; clients dropping out

iPhone and Android both fine. No device-side crash text anywhere (`segfault|SIGSEGV|abort|panic|oom|core
dump` → no matches). This is a client-app issue on older iPads, not Stage-2.

One real device-side fault correlates with dropouts — `SP_ClientCtxDel:not find this is id[N]`, **307
occurrences** across the Mlogs:

```text
[16:41:49:999] SOCKET_ACCEPT(201) [id=38 192.168.0.4:55860] s_u32ClientNum[2]
[16:41:50:000] SOCKET_OPEN(201)  [id=38] start
[16:41:50:000] SOCKET_CLOSE(201) [id=38] s_u32ClientNum[1]
[16:41:50:000] ERROR SP_ClientCtxDel[392]: not find this is id[38]
```

A connection opens and closes within the same millisecond and the context is already gone — a lifecycle
race in vendor `polestar_app`'s socket bookkeeping. Also one-off:
`dbus[248]: ... assertion "_dbus_check_is_valid_utf8 (*string_p)" failed` in `Mlog_000025.log`.

## Not verified — do not record as fixed

- **Bulb capture end-to-end** (the `.117` "countdown then shot failed" symptom). Never completed on v118.
- **RAW+JPEG delivery, issue #362.** Detection works — `companions=1` on every dual-format capture including
  a fresh boot — but `gp_camera_get_extra_capture_files` still has no consumer in pgphoto or the loader.
- **Live view frame delivery as a measured rate.** Only operator-reported quality so far.
- **Cross-model qualification.** The gate regression hit every model on `.115`–`.117`; only the K-1 II was
  exercised here.

## Archive status — gap still open

v118 is what is running, but it is **not yet published** to `PrivateResearch`, so the installed firmware is
not currently recoverable from the archive. Two attempts failed with `fetch-pack: unexpected disconnect`; a
retry loop cloned successfully to `/tmp/PR-publish` and is ready for the publish step. v117 remains archived
(`8719db93f`, byte-verified) as the fallback.

## For the K-3 III session (next up)

Capture the same evidence set so the two bodies are comparable:

```bash
# identity + kit first, always
./scripts/verify-installed-build.sh out/astro-v118-stage2-gate-wedge-fix-20261126
python3 scripts/stress-config-gate.py --ssh-host 192.168.0.1 --ipolar-host 192.168.0.1 \
    --clients 8 --rounds 4          # refusal counts are now honest; read them
# refusals with the new per-claim fields
ssh root@192.168.0.1 'ls -t /app/sd/system/log/Clog_*.log | head -1 | xargs sed "s/\x1b\[[0-9;]*m//g" \
  | grep -a "admission refused" | tail -30'
# AF: does the vendor path fail identically on K-3 III? (it never worked on K-1 II)
ssh root@192.168.0.1 'ls -t /app/sd/system/log/Clog_*.log | head -1 | xargs sed "s/\x1b\[[0-9;]*m//g" \
  | grep -aE "updateCameraAutoFocus|change focus mode" | tail -20'
# capture ordering + duration sign
ssh root@192.168.0.1 'ls -t /app/sd/system/log/Clog_*.log | head -1 | xargs sed "s/\x1b\[[0-9;]*m//g" \
  | grep -aE "capture=|capture end|get file to buffer" | tail -20'
```

Then **redact before committing** (see the credential note above).

## Reproduce / verify

```bash
./tests/run_prerelease_gate.sh          # GREEN after all edits: 17 passed, 0 failed, 2 skipped
python3 -m py_compile scripts/stress-config-gate.py scripts/probe-config-gate.py \
                      scripts/verify_installed_build.py
```

Commits this session: `399cc942` (v118 registered + `.118` claimed), `791ab779` (kit identity guard),
`17d093aa` (refusal path + probe bind).
