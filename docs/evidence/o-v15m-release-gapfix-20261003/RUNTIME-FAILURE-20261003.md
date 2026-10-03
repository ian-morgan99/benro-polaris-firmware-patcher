# o-v15m runtime failure and rollback

## Failure reproduced

The installed 15m runtime was:

`6.0.0.54.52-o-v15m-release-gapfix`

With no camera attached, `polestar_app` was initially running and TCP 9090
was listening. The exact canary probe then requested protocol code 780, the
firmware-version query used by Benro Connect:

`1&780&2&-100#`

Mlog recorded `mFwVer[6.0.0.54.52]`, but no code-780 response was returned.
Immediately afterwards `polestar_app` had exited and TCP 9090 was no longer
listening. The device itself remained booted and SSH-accessible.

The failure was repeatable after a normal reboot. This means the 15m exact
version patch passes static/package checks but is unsafe in the live
`polestar_app` code-780 path. It is rejected for testing and must not be
staged again.

## Recovery

The provenance-verified, previously installed 15i artifact was staged through
the sanctioned extracted `FwPkt/` path and rebooted:

- Candidate: `o-v15i-pentax-bulb-matched-20261002`
- ZIP MD5: `4ddbe3754fc7832750f0ee6b895fe616`
- ZIP SHA-256: `d4623510357125e25c2e9a7c512bae238a686e1e5eab3db47d66956f0bfb0e75`
- appfs MD5: `e10d206ce758f6d534677f881557cd6c`

Post-rollback verification showed:

- `/app/FwVer`: `6.0.0.54.52;date:2026.10.02;`
- build ID: `6.0.0.54.52-o-v15i-pentax-bulb-matched`
- `polestar_app` running
- TCP 9090 and 8080 listening
- code 780 returned `sw:8.0.0.76`
- `polestar_app` remained running after the code-780 query

The camera was not attached, so this is a recovery/runtime result, not a
physical capture qualification.
