# o-v9i-capturetarget-controls installation evidence — 2026-09-12

Artifact: `o-v9i-capturetarget-controls` (out/k1ii-k3iii-v9i-capturetarget-controls-20260912)

- ZIP MD5: `6fda5c228b2d02e2dda189b19bb68d31`
- ZIP SHA-256: `5aa1606997cfee6dd7ee9f3d2a69b569e1157a196b6b8ed0b5c0124ae823f51e`
- appfs MD5: `2d1f8bb793e3f8aaa84b23dde7adcdb3`
- libgphoto2 commit: `15b8f6d89cb61b1b8c66f12f7510124fd81d1a9c` (clean tree)
- build_id: `6.0.0.55.1`

## Install flow (firmware-only, sanctioned /app/sd/FwPkt path)

1. Extracted `FwPkt/` tree tarred locally (`v9i-FwPkt.tar.gz`, 68,470,943 B,
   md5 `4802fbadb5a1f196970801316ababdbe`) + per-file md5 manifest.
2. Streamed both to `/app/sd/` via SSH pipe (scp dropped twice — K-3 III VIA-hub
   flap starving the Wi-Fi radio, the known v9h issue; SSH pipe with
   ServerAliveInterval succeeded).
3. Extracted on-device to `/app/sd/FwPkt`; `md5sum -c` verified all 7 files OK
   against the manifest before reboot.
4. Sanctioned `/sbin/reboot` at 19:29:23 UTC; device returned 19:30:31 (uptime
   0 min). Updater consumed and removed `/app/sd/FwPkt`.

## Post-boot verification (19:31 UTC)

- `/app/openpolaris-libgphoto2-provenance.txt`: `git_commit=15b8f6d89…`,
  `build_id=6.0.0.55.1` — v9i is the running build (was `90736a1ac` / 6.0.0.54.1).
- `polestar_app` (PID 253) listening on TCP 9090; `pgphoto.stage2ondisk`
  (PID 254) listening on TCP 8080; sshd on 22.
- Clog: stage2 shims engaged — preview-backoff, storage, and the new
  **capturetarget** set/set_single_config shims all resolved (64/64 slots).
- `/app/lib/stage2/libgphoto2.so.6` present (133,508 B, built 17:55 = v9i build).

Camera-control qualification (K-1 II config reads now ret 0; K-3 III focus +
RAW+ dual capture) remains the separate post-install test. K-3 III re-test is
blocked on the VIA-hub power flap (see `docs/evidence/k3iii-hub-flap-2026-09-12/`).
