# Bulb trace evidence — consolidated summary (2026-10-12)

Cross-reference of every bulb-related trace and finding to date, for issue #186
(K-3 III timed-Bulb qualification) and the related #187 crash work. This is a
summary index; each entry links to the authoritative raw evidence.

## 1. o-v16b (.61) — the camera never fires (2026-10-08)

Source: [`o-v16b-bulb-trace-20261008/SUMMARY.md`](o-v16b-bulb-trace-20261008/SUMMARY.md),
raw extracts `capture-trace.txt`, `capture-264-lifecycle.txt`.

- Two capture attempts through the Stage-2 hook both returned **`ret=-10`
  (GP_ERROR_TIMEOUT)**; the app's own `ret 0` discards the gphoto result.
- The 66 s gap is the driver's `PENTAX_CAPTURE_TIMEOUT_MS_BASE` (60 s) wait,
  not an exposure.
- Operator observation (canary **and** Benro Connect): no shutter actuation,
  only a reflex twitch; no file created. This is a **trigger failure**, not a
  transfer loss (#181's premise corrected).
- Not yet ruled out at the time: electronic/silent shutter or drive mode that
  ignores PTP capture; whether the K-3 III accepts `CaptureImage` while live
  view is active.

## 2. o-v16f (.64) — branch audit, diagnostic only (2026-10-10)

Source: [`o-v16f-bulb-branch-audit-20261010/SUMMARY.md`](o-v16f-bulb-branch-audit-20261010/SUMMARY.md).

- **DO NOT STAGE.** Omits the retired zero-`bulb_ms` polestar_app patch and
  verifies the original app branch is intact, but does not connect the request
  to a held-Bulb action. No physical Bulb qualification.

## 3. o-v16g (.65) — timed-Bulb dispatch installed; Layer B pending (2026-10-10/11)

Source: [`o-v16g-k3iii-timed-bulb-20261010/SUMMARY.md`](o-v16g-k3iii-timed-bulb-20261010/SUMMARY.md).

- Positive-`bTime`, status 0, Pentax + K-3 III capture requests now route to
  `capture_image_with_Bulb(Status, time_ms, newFiles)` (bulb=1 → wait ms →
  bulb=0 → finalize/transfer). Zero-duration and other-model paths unchanged.
- Installed 2026-10-11; runtime provenance verified (`6.0.0.54.65`, libgphoto2
  `2cde4485b`, patcher `9d0efe0`).
- **Layer B qualification still pending**: one bounded positive-duration Bulb
  capture with trace proof of exactly one PTP start/stop, elapsed-vs-requested
  duration, file publication, and idle recovery.

## 4. #187 crash-window analysis on .65 (2026-10-10 evening)

Source: [`benro-connect-crash-20261010/SUMMARY.md`](benro-connect-crash-20261010/SUMMARY.md)
(boot 276, Mlog/Clog pull `polaris-logs-20261011-004459.tar.gz`,
SHA-256 `a9edd667…`).

Key findings relevant to Bulb:

1. **The o-v16g timed-Bulb path was NOT exercised** — every `code:264` in the
   session carried `bulb:0` (zero duration), so the positive-duration dispatch
   never ran. The session is a canary-pending observation, not Layer B proof.
2. **USB flapping** (7+ connect/disconnect cycles in ~13 min) with pgphoto
   restart lock contention kept re-initialising the camera session.
3. **`SP_SET_SHUTTER FAIL` ×4** — shutter-speed widget `get_current_shutter`
   returns `s:00:00` after each re-init; F-number and ISO recover faster. This
   is the gimbal-side symptom of the degenerate camera state that crashes Benro
   Connect (#187 root cause: degenerate camera-state burst pushed while the PTP
   property store is still initialising — shutter 268 collapsed to `00:00`, EV
   267 collapsed to `0`, fNum 275 reversed, ISO 265 extended).
4. Fix direction for #187 is a polestar_app state-machine guard (gate the
   camera-state burst on the property store being initialised), **not** a
   pgphoto/timed-Bulb change.

## 5. o-v17a (.66) — shutter-fallback shim, staged 2026-10-12

Source: uncommitted working-tree changes in `container/` (SHIM #6 in
`stage2_loader.c`, wrapper env export, `build_ptp2.sh` CFLAGS). Staged package:
`out/staged/o-v17a-shutter-fallback-off-20261012/FwPkt.zip`
(MD5 `da6fbce4…`, SHA-256 `8fb21a68…`, appfs MD5 `6cd24351…`, FwVer `.66`).

- Adds a `gp_camera_get_single_config` wrapper (SHIM #6): on failure for the
  `shutterspeed` widget it can synthesize a minimal TEXT widget so pgphoto's
  `updateCameraViewFinder` does not see `ret:-1` and trigger a restart loop.
- **Fail-closed by default**: synthesis only happens when
  `STAGE2_SHUTTER_FALLBACK=1`; the shipped wrapper exports `0`. This targets the
  #187 shutter-widget failure mode (finding 3 above) without masking genuine
  camera/session errors until the A/B test and K-1 II regression check pass.
- Not yet installed. **Offline validation complete 2026-10-12** (device access unavailable): pre-release gate GREEN 9/9, static diff vs o-v16g confirms the behavioral delta is confined to SHIM #6 + the new `gp_camera_get_single_config` trampoline + the wrapper env export (camlib .so files are a toolchain-only rebuild from identical libgphoto2 source `2cde4485b`), provenance registry row added, `.66` recorded as consumed. See [`o-v17a-offline-validation-20261012/SUMMARY.md`](o-v17a-offline-validation-20261012/SUMMARY.md).

## Open items (in order)

1. ~~Run the pre-release gate on the staged o-v17a FwPkt; add its provenance
   registry row~~ — **done 2026-10-12** (gate GREEN 9/9; registry rows in
   `docs/FWPKT-PROVENANCE-CONTRACT.md` and `docs/RELEASE-VERSION-STATE.md`;
   record: [`o-v17a-offline-validation-20261012/SUMMARY.md`](o-v17a-offline-validation-20261012/SUMMARY.md)).
2. Wake the Polaris (BT pulse / AP poll), stage o-v17a to `/app/sd/FwPkt`,
   reboot via the on-boot watcher, verify `FwVer 6.0.0.54.66` + provenance.
   **Blocked 2026-10-12:** host has no BT adapter (`/dev/hci0` absent, no USB
   BT device, `bluetoothd` not running) and the AP is unreachable; needs a
   reconnected dongle or a manual power-cycle of the gimbal.
3. **Layer B for #186** (o-v16g or o-v17a): one bounded positive-duration Bulb
   capture with K-3 III attached and Benro Connect absent; trace exactly one
   PTP start/stop, compare elapsed vs requested duration, verify file
   publication and idle recovery, then a Manual control capture. Any ambiguous
   start/stop or missing output is `OUTCOME UNKNOWN` — do not retry shutter
   commands. Keep K-3 III Monochrome blocked.
4. **#187**: with o-v17a installed, A/B test `STAGE2_SHUTTER_FALLBACK=0` vs `1`
   on the K-3 III connect burst; confirm the id-churn crash loop stops or is
   reduced; then run the K-1 II regression check before enabling by default.
