# `.75` installed and verified — 2026-10-27

Candidate `o-v18e-fail-closed-bulb-shutter` -> `FwVer:6.0.0.54.75;date:2026.10.27;`
libgphoto2 `e7d0cf1dd`, patcher `116872d`. zip md5 `61ecc8e9c0e6090d1688aa6d1fd84d1c`.

## Install verification

| check | result |
|---|---|
| pre-release gate | GREEN — 14 passed, 0 failed, 1 skipped (transcript attached) |
| reboot proof | uptime `3267s -> 665s` |
| build identity | `INSTALLED BUILD IDENTITY: PASS`, `FwVer:6.0.0.54.75;date:2026.10.27;` read back from the device |
| Mlog | `SP_EVENT_UPGRADE_SUCCESS` then `SP_DelUpgradeFiles: remove /app/sd/FwPkt` |
| installed `ptp2.so` | `/app/lib/stage2/libgphoto2/2.5.34/ptp2.so`, sha256 `be2c0e7aa337029ece48e4a745b123872e8a6d16782d50b3f51a57f158c243b7`, size 1190668 — **matches the install manifest exactly** |
| distinct from `.74` | `.74`'s `ptp2.so` is `931e31cd1a8aae9b…`; the device now carries `.75`'s, not `.74`'s |

## A verification mistake worth recording

My first attempt to confirm the fixes grepped `/app/lib/ptp2/ptp2.so`, which does
not exist, then `/app/lib/libgphoto2/2.5.27.1/ptp2.so`, which **does** exist and
**does** contain the strings — but is a *different, older* copy that is not what
the manifest installs. The authoritative path is
`/app/lib/stage2/libgphoto2/2.5.34/ptp2.so`. Grepping the wrong copy would have
"confirmed" a fix on a binary pgphoto may not even load. The hash comparison
against the manifest is the only sound check, and that is what is recorded above.

## Status: installed, canary pending

**No camera is attached.** `canary-probe.py --probe` reports
`model=none state=-5 photoFormat=0`, i.e. no body present. So:

- `.74` remains the last **operator-confirmed working** build.
- `.75` is **"installed, canary pending"** — not qualified.
- The two behavioural risks introduced by `.75` over `.74` are untested on
  hardware: the fail-closed shutter write may now refuse a capture `.74` would
  have taken, and the K-3 III model gate may withhold a list `.74` synthesised.

Rollback: `./scripts/release/release-fwpkt.sh out/o-v18d-shutter-list-always-populated`
(md5 `307d8bd4ca4264973a16df0d0586de48`). See `ROLLBACK.md`.

## Blocked on

Attaching a camera body to the rig. Until then no canary, no two-shot, and no
hardware regression of #241/#243/#239 is possible.
