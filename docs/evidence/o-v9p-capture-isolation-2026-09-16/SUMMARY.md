# o-v9p capture-isolation K-3 III qualification

Date: 2026-09-16 UTC

## Installed artifact

- Registry: `o-v9p-capture-isolation`
- ZIP MD5: `73a08ca492cac15124ae30e079be731d`
- ZIP SHA-256: `6c19efd728fc066e8bb5c36b0e2cd9571adfc315db0d4d22b7ccfc99ef872eb0`
- appfs MD5: `0b69ac13d3d765d37392f493f01a3885`
- libgphoto2: `121675124e173da1864421acebea8e20c851c827`
- patcher: `cddafb6f087303e3d6d16850e0ab10f962cccbf4`
- installed `build_id`: `6.0.0.54.7`

The artifact was staged only as the complete extracted `/app/sd/FwPkt/` tree.
All six payload MD5s matched `firmwareInfo` on the device before
`sync; /sbin/reboot`. SSH dropped and uptime reset from 12,289 seconds to 31
seconds. Device identity was proven by BSSID `48:E7:DA:D4:B5:73`, the
`wlp8s0` route, and `/app/FwVer`.

## Runtime proof

- K-3 III freshly enumerated as `25fb:0189` after reboot.
- Stable owners: `polestar_app` PID 249 on 9090 and
  `pgphoto.stage2ondisk` PID 250 on 8080.
- Stage-2 and stock-path core hashes matched; Stage-2 and stock-path port
  hashes matched.
- The active stock-named compatibility-path `ptp2.so` and `usb1.so` hashes
  exactly matched the extracted o-v9p appfs bytes. Pentax markers were present.
- The loader reported 64/64 slots resolved and logged both capture and preview
  shims.
- No loader, symbol, iolib, crash-loop, USB-disconnect, negative capture state,
  or capture/preview backoff activation occurred during qualification.

## K-3 III results

| Gate | Result | Evidence |
|---|---|---|
| No-camera canary | NOT RUN | Camera had to remain attached; explicitly waived as a hardware constraint. |
| Camera-attached runtime canary | PASS | Stable USB, PIDs, listeners, loader, and zero DHD errors. |
| Ordinary capture before sequence | PASS | `SP_0045.dng`, 28,367,021 bytes; 264 `1 -> 4 -> 0`, correlated 773 event; preview restored. |
| Five-shot Astro-equivalent sequence | PASS | Unique `SP_0046.dng` through `SP_0050.dng`, 28.38-28.57 MB; every shutter had 264 lifecycle plus a unique 773 file event. |
| Preview restoration | PASS | Preview was suspended to state 0 and restored to state 1 after both tests. |
| 30-second preview sample | PASS | 15 multipart frames, 15 JPEG SOI and 15 EOI markers, 69-74 KiB per frame. |
| Wi-Fi read-only counters | PASS | DHD pool-exhaustion counters stayed `0/0`; preview TX increased 1,146,850 bytes without a disconnect. |
| Post-sequence ordinary capture | PASS | `SP_0051.dng`, 28,385,516 bytes; correlated 264/773; Clog additionally proves `2 -> 3 -> 5`; preview restored. |
| Final health | PASS | K-3 III still `25fb:0189`; original PIDs/listeners retained; no established test clients remained. |

The deterministic tester was the sole shutter controller. The tested wire
sequence is preserved in `03-ordinary-shot.log`, `05-astro-five-shot.log`, and
`08-post-sequence-ordinary-shot.log`. The final Clog correlation is in
`10-capture-correlation-clog.txt`.

The `updateCameraViewFinder ... ret:-1` diagnostic still appears internally
around preview transitions, while the externally reported 291 operation is
`ret:0`, state verification succeeds, and real JPEG frames follow. It did not
cause a qualification failure in this run.

## Boundaries

- OpenPolaris capture fix `57dd1a0` exists on `origin/main` and in the
  `issue-90-capture` worktree. This run exercised the deterministic protocol
  tester, not an independently identifiable packaged OpenPolaris application
  build, so packaged-app E2E provenance is NOT RUN here.
- Direct-PC Layer A was not rerun because the camera could not be moved.
- Pentax K-1 II and Canon R5 Mark II were unavailable and are NOT RUN. No
  support claim is made for those cameras from this result.

## Bounded K-3 III focus qualification

- Initial and restored preview state: `1` (on).
- AF `1&262&1&mod:0;f:0;#`: PASS at the command/widget layer. Logs prove
  enable, successful response, disable, and `mod:0;f:0;ret:0`. Literal
  low-level `0x9011` dispatch and physical optical effect are UNKNOWN because
  normal logging does not expose the opcode and no operator observation exists.
- MF side A `1&262&1&mod:1;f:6;#`: PASS at the bounded dispatch layer; the
  device logged the Pentax manual-focus `new` path, raw `0x2001`, internal
  value `-6`, and protocol `ret:0`.
- MF side B `1&262&1&mod:1;f:2;#`: PASS at the bounded dispatch layer; the
  device logged the Pentax manual-focus `new` path, raw `0x2001`, internal
  value `6`, and protocol `ret:0`.
- Literal request opcode `0x9017`: UNKNOWN (not printed by normal logging).
  Physical Near/Far mapping and optical movement: UNKNOWN, not inferred from
  protocol-side signs.
- Preview continuity: PASS: 20 Content-Length boundaries, 20 JPEG SOIs and 20
  JPEG EOIs across 1,422,487 bytes while all three focus actions ran.
- No shutter command was sent during this bounded run. Final USB, processes,
  listeners, client count, and DHD counters remained healthy.
- Evidence: `11-focus-baseline.txt` through `17-focus-persistent-log.txt`.
