# Astro autostart after the v97 flash (2026-11-06)

## What happened

Flashing `astro-v97-liveview-diag-20261106` replaced `/app`, which deleted both
`/app/network_telnetd.sh` (the Astro autostart hook) and all of `/app/astro`.
This is the trap documented in `docs/ASTRO-V97-RELEASE.md` ("the one trap that
bites every time"), and this flash reproduced it exactly:

```
ls: /app/network_telnetd.sh: No such file or directory
ls: /app/astro: No such file or directory
```

Until the v97 flash this claim rested on a prior observation plus a matching
mechanism. It is now directly observed twice, so it is treated as fact.

## Restore, and why not the plain installer

`/app` came back at 54.9 MB used of 68 MB -- 13.1 MB free. The SD Astro bundle's
`catalogue-tiles` are ~20 MB, so a plain `install_astro.sh` would have overflowed
`/app`, which is what happened on 2026-11-03.

Restored from a minimal bundle instead: binaries and scripts only, no tiles. The
solver reads tiles from the SD card regardless, so they are redundant in `/app`.

```
/app/sd/polaris-astro-min   1.9 MB, 37 files, no catalogue-tiles
SRC=/app/sd/polaris-astro-min sh /app/sd/polaris-astro/install_astro.sh
  [astro] installed -> /app/astro
  [astro] boot hook installed -> /app/network_telnetd.sh
```

Verified after: `:8090` listening, hook present at 22040 bytes.

## What network_telnetd.sh in this directory is

A 676-byte **shim** variant captured earlier the same day, before the flash. It
`exec`s the SD copy of the boot script rather than carrying the whole hook, on
the theory that `/app` had no room for the 22 KB file.

**It is not what is deployed.** The live hook is install_astro.sh's own
22040-byte version, which fits -- 13.1 MB was free after the flash. Kept here as
the fallback that would be used if `/app` ever is genuinely full, since it needs
only a few hundred bytes.

## Follow-up

The restore is manual and must be repeated after every flash. It should be part
of the release procedure rather than left to memory; see the trap note in
`docs/ASTRO-V97-RELEASE.md`.
