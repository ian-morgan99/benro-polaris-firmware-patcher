# o-v7 field-test evidence — K-1 II / K-3 III / K-01 (2026-09-10)

Build under test: **o-v7-preview-shims** (zip MD5 `9e2addfc…`, appfs `66cb2604…`,
libgphoto2 `38780d88b`, patcher `de98a23`). Installed via the proven remote SSH
staging route + boot-watcher. Provenance on device confirmed (`git_commit=38780d88b`),
#51 dual-path core+port MD5s match, single pgphoto owner.

Logs pulled: `polaris-logs/Clog_00000{7,8}.log`, `Mlog_00000{7,8}.log`.

## Headline finding — the preview shims were SILENTLY INACTIVE (root cause of "much worse than v3/4")

`stage2_model_uses_pentax_keep_lv()` gated on `strncmp(model,"Pentax:",7)`, but the
**runtime** abilities string pgphoto sets uses a **SPACE**, not a colon:

```
('Pentax K-01 (PTP Mode)')...
('Pentax K-1 Mark II (PTP mode)')...
('Pentax K-3 Mark III (MTP mode)')   [from earlier o-v7 Clog]
```

So Shims #4 (keep-live-view) and #5 (preview backoff) **never activated** on any of
these bodies — no `[stage2] keep-lv:` line ever logged. The per-frame PC-LV teardown +
NoUpdateImage warmup churn continued exactly as pre-shim.

- Fix: case-insensitive brand substring match (`pentax`/`ricoh`, plus `gx10`/`gx-10`
  token only) — commit **`0953dde`** (patcher main), unit test expanded to cover the
  space form, all capitalisations, Ricoh, GX10-only + negatives. All pass.
- Not yet on a flashed build: needs an o-v8 rebuild + re-flash to prove the shims now
  fire (`[stage2] keep-lv:` line must appear in Clog).

## Symptom → issue map (all cross-referenced, no duplicates)

| Observed today | Evidence | Issue |
|---|---|---|
| K-1 II capture fails `-6` on Polaris | `Clog_000008`: `ARG_CAPTURE_IMAGE -6`, `captureImage ret -6`; **1808×** `get_single_config … failed: -2` storm in the same session | fork **#48** (K-1 II capture -6) — supplemented |
| K-1 II "reads aperture, can't write; no other controls work" | `Clog_000008`: repeated `get_single_config … failed: -2` for whitebalance/shutterspeed/imageformat/imagequality → app `ret:-1` | fork **#49** (WB/aperture false-failure) — supplemented |
| K-01 "detected, controls do nothing" in MTP mode | `Clog_000007`: repeated `get_single_config … failed: -2`; model string `Pentax K-01 (PTP Mode)` | fork **#50** (K-01 MTP empty config tree) — supplemented; now also seen on the **patched** o-v7 build, not just stock 2.5.27.1 |
| Preview "spams the shutter" / one image every 4–5 s then black | per-frame PC-LV teardown churn (shims inactive); `get-frame returned 0xa008` + `restore-after-frame 0x2001` loops in Clog | patcher **#36** (K-3 III preview 0xa008) — supplemented with the model-gate root cause |
| K-1 II "dead to Polaris" after USB-compat toggle / reconnect | `Clog_000008` session; detection flaps, then config storm | patcher **#50** (K-1 II fails to connect under o-v5b) — supplemented as continuation on o-v7 |
| **OpenPolaris sends preview stream to port 9090 (control), not 8080** | `Mlog_000008`: `unkown msg:GET /?action=stream HTTP/1.1 … Host: 192.168.0.1:9090`, `User-Agent: OpenPolaris/0.1` — Polaris logs it as an unknown control message | **NEW** OpenPolaris issue (created) — corroborates the other agent's in-flight fix |

## Error-code note (corrected 2026-09-10 per TA review of patcher #50)
Generic GP result codes live in the `0..-99` range (`gphoto2-port-result.h`);
camera-level codes begin at `-102` (`GP_ERROR_CORRUPTED_DATA`,
`gphoto2-result.h`). So:
- `-2` = **`GP_ERROR_BAD_PARAMETERS`** — returned by `gp_camera_get_single_config()`
  when the requested widget is not in the config tree. Not by itself proof of an
  "empty tree"; it means *this key* was missing/unavailable at that moment.
- `-6` = **`GP_ERROR_NOT_SUPPORTED`** — the normal constant for capture on bodies
  whose camlib path does not support `capture_image`.

K-1 II storm detail (per TA request): the distinct requested keys are
`shutterspeed`, `manualfocusdrive`, `imageformat`, `autofocusdrive` (2 misses each,
via pgphoto's `checkWidgetForName` diagnostics = 8 named misses); the 1,808
`get_single_config … failed: -2` lines are pgphoto's app-level config-poll loop
re-querying those missing widgets. These four keys are exactly the generic controls
tracked in fork #54/#57/#59 (imageformat / autofocusdrive / manualfocusdrive) +
shutterspeed — consistent with an unpopulated/absent config surface for K-1 II,
but ownership still needs the §3b direct-on-PC baseline before assignment.

## Direct-on-PC baseline (§3b) — PENDING re-attach
K-01 (`25fb:0131`) and K-3 III (`25fb:0189`) were attached to the PC, udev rule
`99-pentax-mtp-ignore.rules` intact. Native fork sample tools built at
`_build/examples/{sample-autodetect,pentax-safe-preview,pentax-safe-shutter-roundtrip}`.
Both bodies **dropped off the bus** mid-sweep (re-attach needed). `sample-autodetect`
returned "Could not detect any camera" while they were present — itself a data point to
chase (detection vs control divergence).

## Next actions for the next developer
1. Rebuild o-v8 with `0953dde`, re-flash, confirm `[stage2] keep-lv:` now logs on K-3 III/K-1 II/K-01 → proves shims active; then re-run the preview-churn + capture matrix.
2. Re-attach K-01 + K-3 III to PC; run `sample-autodetect` (why no detect?) and `pentax-safe-preview` / `pentax-safe-shutter-roundtrip` for the §3b direct baseline that fork #48/#49 require before assigning libgphoto2 ownership.
3. OpenPolaris: land + verify the 8080 preview-port fix (see new issue); confirm Polaris no longer logs `unkown msg:GET /?action=stream` on 9090.
