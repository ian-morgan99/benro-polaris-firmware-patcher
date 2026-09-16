# Roadmap to stability — BenroPolarisPatcher (2026-09-15)

Status legend: [ ] not started, [~] in progress, [x] done

## Phase 1 — Clean rebuild (release process fix)
- [x] 1. Commit wrapper/test changes on a dedicated branch; verify `git status` clean
      → branch `fix/release-safety-gates`, commit `5d2df7d` (7 files; unrelated pending work left untouched)
- [x] 2. Rebuild from canonical stock FwPkt with `--build-id` set (clean tree, no `--allow-dirty-patcher`)
      → built via detached clean worktree `/tmp/bpp-clean-build` at `5d2df7d`; build_id `6.0.0.54.5`; all gates incl. new post-repack wrapper-export assertion passed
- [x] 3. Verify packaged wrapper inside rebuilt appfs
      → extracted appfs.ubifs; `/app/bin/pgphoto` contains `STAGE2_PENTAX_PREVIEW_BACKOFF=1` / `STAGE2_PENTAX_PREVIEW_MIN_INTERVAL_SECS=2` exports; provenance records `patcher_commit=5d2df7d`, empty `patcher_dirty_diff_hash`
- [x] 4. Upload clean candidate to PrivateResearch + commit registry row
      → PrivateResearch commit `239f3b4` (`firmware-packets/o-v9n-clean-preview-throttle/`); registry row committed at `838ab60`

## Phase 2 — Qualification gates (the step o-v9m skipped)
- [x] 5. No-camera runtime canary — PASSED
      → installed via sanctioned extracted FwPkt/ SD flow; on-card appfs md5 `74b811187693cab0e792100f48cfd7c3` verified
      → post-boot provenance: `patcher_commit=5d2df7d`, `build_id=6.0.0.54.5`, clean dirty-hash
      → ~20 min soak (T0 22:10 / T1 22:19 / T2 22:30 UTC): pgphoto PID 250 stable, both listeners up, no FATAL/state:-/ret:-, app code:266 polling steady ~30s
      → init-block accumulation (34→110) = expected camera-absent scan churn, NOT a crash loop
      → o-v9m's failure signature (rapid app-reconnect churn + general outage) NOT reproduced
- [x] 5b. No-camera runtime canary for **o-v9o-capture-shim** (build_id `6.0.0.54.6`, patcher `fa10bfb`) — PASSED 2026-09-16
      → installed via sanctioned extracted FwPkt/ SD flow + `/sbin/reboot`; all 7 payloads MD5+size verified on-card against firmwareInfo before install; post-boot provenance `patcher_commit=fa10bfb…`, `build_id=6.0.0.54.6` verified; live loader carries capture-shim strings
      → ~48 min soak (T0 18:46 / T1 19:02 / T2 19:34 UTC): pgphoto PID 250 stable across all three samples, both listeners up (8080/9090), zero FATAL/state:-/ret:- in Clog at every sample, load steady ~1.0
      → init-block count churn (78→44→0) = Clog rotation, NOT a crash loop (PID 250 unchanged across the window)
- [ ] 6. K-3 III ordinary capture baseline (preview OFF): fresh USB/session, one capture through candidate/transfer/reconcile/READY — BLOCKED on camera availability
- [ ] 7. K-1 II ordinary capture baseline (preview OFF): same, second body, explicit hot-swap verification (#89) — BLOCKED on camera availability

## Phase 3 — Fix the real defects (issues #86–#90)
- [ ] 8. #86 — reproduce & fix preview empty-frame (0x2002/0 bytes) → USB loss; find first abnormal transition; add regression test
- [ ] 9. #87 — client keepalive/radio hardening; iPad vs iPhone comparison; bounded preview buffering/backpressure; prove BT/Wi-Fi survive client crash
- [ ] 10. #89 — deterministic camera_session_reset() on hot-swap: release PTP/libusb, clear cached abilities/port/candidates, rescan, fresh init. "session already open" must become a fail/reset trigger, not tolerated state
- [ ] 11. #90 — mode-aware capture liveness: instrument exposure/processing/candidate/transfer/READY separately; test short/long/NR/PixelShift/Astro/bulb; stop timeout==failure conflation
- [ ] 12. #88 — restore K-1 II ISO/aperture/shutter/EV/WB writes; reproduce on exact direct-PC libgphoto2 SHA; serialize background config polling around writes; require readback proof

## Phase 4 — Close-out
- [ ] 13. #81 — close general o-v9m-class stability regression once clean candidate passes canary + baselines with no recurrence (canary passed; awaiting camera baselines)
- [ ] 14. Full physical regression matrix (all previously-qualified cameras) against final candidate — no regressions
- [ ] 15. Update docs/TESTED.md, docs/RUN-JOURNAL.md, docs/canonical-pentax-source.md, docs/patcher-gates.md per AGENTS.md documentation obligations
- [ ] 16. Mark release stable; update README supported/qualification claims

## Current blockers
- Camera not currently attachable (user constraint, 2026-09-15) — blocks steps 6/7 and everything downstream
- ARM cross-compiler (arm-linux-gnueabi-gcc) unavailable on this host — Stage-2 loader compile gate runs inside the Docker build (passed during o-v9n build)

## Key facts to not re-derive
- o-v9l-74-77 = last known-good; was installed as restore after o-v9m outage, build_id 6.0.0.54.4
- o-v9m-preview-throttle = RELEASE BLOCKED (dirty patcher tree at build time, general runtime outage post-install, no-camera canary skipped)
- o-v9n-clean-preview-throttle = superseded on-device by o-v9o (build_id 6.0.0.54.5), zip md5 `e8715e92aaa8a62f0a26ee5f47422213`, appfs md5 `74b811187693cab0e792100f48cfd7c3`, libgphoto2 `121675124e173da1864421acebea8e20c851c827`
- o-v9o-capture-shim = CURRENTLY INSTALLED candidate (build_id 6.0.0.54.6, patcher `fa10bfb`, no-camera canary PASSED 2026-09-16), zip md5 `27cead5f8c8294bfb764ca57e9bd77cb`, appfs md5 `34c1f07580c6cc2b4a1b5c83d974416d`, libgphoto2 `121675124e173da1864421acebea8e20c851c827`; adds SHIM #6 capture-shim + 8080 ownership proof + PID-reuse-safe lock validation
- Stock FwPkt lives at BenroPolarisPatcher/firmware/FwPkt.zip (gitignored, appfs md5 47f2ae680be3a5f5d69aa20e20a2397b)
- Release gates added this session: dirty-patcher fail-closed in patch-polaris.sh, patcher_commit/patcher_dirty_diff_hash in provenance, post-repack wrapper-export assertion in container/patch.sh

## o-v9n canary verdict
PASS for no-camera stability. Ready for camera baselines (steps 6/7) as soon as the camera is attachable. Do NOT enable preview yet; do NOT run multi-shot until an ordinary capture reaches state:5 + READY.

## o-v9o canary verdict (2026-09-16)
PASS for no-camera stability (~48 min soak, T0 18:46 / T1 19:02 / T2 19:34 UTC): pgphoto PID 250 stable across all samples, both listeners up (8080/9090), zero FATAL/state:-/ret:- in Clog at every sample, load steady ~1.0; init-block churn (78→44→0) = Clog rotation, not a crash loop. o-v9o is now the installed candidate (build_id 6.0.0.54.6). Same rules as o-v9n: ready for camera baselines (steps 6/7) as soon as the camera is attachable; do NOT enable preview yet; do NOT run multi-shot until an ordinary capture reaches state:5 + READY.
