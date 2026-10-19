# o-v17b (`.67`) install — VERIFIED 2026-10-19 09:30 local

Candidate: `o-v17b-ci-colortemp-20261018` → `6.0.0.54.67;date:2026.10.18;`
Artifact: `out/o-v17b-ci-colortemp-20261018/FwPkt.zip`
sha256 `bed0ef63c4e6554fae257fb2a2a2df4bc4086218087947584a2329efccda9efd`,
md5 `537e42dce2c84fd67e542d19878c3a62`, size 68390567.
Provenance: libgphoto2 `6c6142625` (PR #103), patcher `8a7f2bf5`,
camlibs `ptp2,pentax`, build_id `6.0.0.54.67-o-v17b-ci-colortemp-20261018`.

## Verdict: VERIFIED
`o-v17a-autonomous-install.sh --verify-only` at 09:31:40:
- `/app/FwVer = FwVer:6.0.0.54.67;date:2026.10.18;` (target match)
- on-device `build_id: 6.0.0.54.67-o-v17b-ci-colortemp-20261018`
- all 10 mandatory files match `install-manifest.json` (SHA-256 + size)

## What actually happened (the two traps)
1. **Zip-only staging is ignored by the on-boot watcher (issue #58).** The first
   attempt staged `FwPkt.zip` and rebooted; the device came back on `.66` with
   the zip untouched and `--verify-only` returned `not-installed`. The watcher
   consumes the extracted `FwPkt/` **tree** at `/app/sd/FwPkt/`, not the zip.
2. **The device never actually rebooted on the first several attempts.** Mlog was
   live (fresh 09:25 entries) and Clog empty, with **zero** FwPkt/upgrade/
   SYS_REBOOT lines, and `/proc/uptime` kept climbing (27k+ s, continuous since
   the 01:44 boot). Every "went dark" was an AP-link flap, not a boot —
   `/sbin/reboot` was killed mid-flap before it ran, and the `812` frame was not
   acted on (K-3 III connected, `state:1`).

## Fix applied
- **Tree path without a re-transfer:** the AP link was flapping hard (single
  tar/`cat` transfers kept dying at 0 bytes), so the already-staged
  `/app/sd/FwPkt.zip` was **extracted on-device** (`unzip` present; zip digest
  `bed0ef63…` confirmed). All 6 `firmwareInfo` MD5s matched on-device:
  config `1905e2d0…`, uImage `5f6a0c18…`, rootfs `778b27bc…`,
  appfs `9e91562c…`, polaris403 `4facafa7…`, polaris413 `c0299d06…`.
  Stray `FwPkt.zip`/`.part` removed.
- **Detached reboot that survives the SSH drop:**
  `setsid sh -c "sleep 2; sync; /sbin/reboot" &` fired at 09:29:02.
  Success judged by **uptime reset** (27872 → 17), not by the link going dark.
  Device up on `.67` at 09:30:18.

## Outstanding
Physical qualification on a K-3 III: confirm `0xd018` and `0xd021`–`0xd029`
write and round-trip (the read-back verification makes this honest), and confirm
`0xd024`'s descriptor enumerates the 255 sentinel. `.55` remains the last
*physically* tested rollback target.

**RESOLVED 2026-10-19** — see `../o-v17b-physical-20261019/SUMMARY.md`.
`0xd021`/`0xd022` round-trip with an independent raw read-back; `0xd024`–`0xd026`
enumerate nothing (there is no 255 sentinel) and stay withheld as designed;
`0xd018` is rejected by the `PTP_DPFF_None` guard while the raw property reads
and writes fine — libgphoto2 #104.
