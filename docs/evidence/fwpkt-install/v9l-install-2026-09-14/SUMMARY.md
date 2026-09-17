# o-v9l-74-77 installation evidence — 2026-09-14

Artifact: `o-v9l-74-77` (builds/v9l-74-77)

- ZIP MD5: `e8e8768783c6f28fcdbe1ed435765af1`
- ZIP SHA-256: `e94ef943d27fe727…` (full in registry row)
- appfs MD5: `018a250438a3bea807fd691d0d24c1ea`
- libgphoto2 commit: `121675124e173da1864421acebea8e20c851c827` (clean tree)
- build_id: `6.0.0.54.4`

## Install flow (firmware-only, sanctioned /app/sd/FwPkt path)

1. Staged the full extracted `FwPkt/` tree to `/app/sd/FwPkt` on the mounted
   SD card via the documented SSH tar stream (9090 keepalive; ~180 KB/s).
   Session was interrupted after the stream completed — the staged tree was
   left in place, un-rebooted.
2. Resume (2026-09-14 21:56 UTC): verified all 8 staged files byte-identical
   to the local build (`md5sum` per-file match; card FwVer = 6.0.0.54.4),
   no stale keepalive loops, then sanctioned `sync; /sbin/reboot`.
3. Device returned ~21:58:45 UTC (uptime 0 min). Updater consumed and removed
   `/app/sd/FwPkt` (only `FwPkt.zip` remains at SD root — the watcher ignores it).

## Post-boot verification (21:59–22:00 UTC)

- `/app/openpolaris-libgphoto2-provenance.txt`: `git_commit=121675124…`,
  `build_id=6.0.0.54.4` — v9l is the running build (was v9k, 6.0.0.54.3).
- `/app/FwVer` = `4.0.0.32` (stock) — expected: v9l keeps /app/FwVer stock so
  the displayed sw: sum stays 6.0.0.54 (see docs/FWVER-SUM-BEHAVIOR.md).
- `polestar_app` (PID 249) and `pgphoto.stage2ondisk` (PID 593) running, no
  restart loop; all `/app/lib/stage2/` components dated Sep 14 19:13.
- Clog_000066: stage2 shims engaged — preview-backoff, storage, capturetarget
  set/set_single_config shims resolved (64/64 slots), no loader-race FATAL.

Camera-control qualification (K-1 II + K-3 III A/B/C matrix vs v9f baseline)
remains the separate post-install test; K-3 III re-test still gated on the
VIA-hub power flap (docs/evidence/k3iii-hub-flap-2026-09-12/).
