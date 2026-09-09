# K-3 III persistent pgphoto launch-lock failure — 2026-09-09

## Live identity and baseline

- Host route: `192.168.0.1 dev wlp8s0 src 192.168.0.4` while associated with
  `polaris_d13e86`, BSSID `48:E7:DA:D4:B5:73`.
- Device identity: `/app/FwVer` = `FwVer:4.0.0.32;date:2025.05.09;`.
- Camera on Polaris: USB `25fb:0189`, Pentax K-3 Mark III.
- Installed candidate lineage: o-v5b, embedded libgphoto2 `990281d72`.
- Stage-2 and stock cores both had MD5 `6ae6c633b0d20d7c5bcdf717605a9224`.

## Failure

At device uptime 1h38m, `polestar_app` was live on 9090 but there was no
`pgphoto.stage2ondisk` process and no 8080 listener.  The only current Clog
message was:

```text
[stage2] another pgphoto launch is already in progress; refusing duplicate
```

`/var/run/openpolaris-pgphoto.launch.lock/` existed without owner metadata and
`openpolaris-pgphoto.backoff.tmp` was zero bytes, both timestamped 20:47.  This
is consistent with the wrapper being killed after acquiring the mkdir lock and
truncating the backoff temp, but before cleanup/startup completed.

An OS reboot was then performed after proving `/app/sd` contained no staged
update.  SSH dropped, uptime reset to zero, and the same launch-lock directory
and zero-byte temp file survived.  The first post-boot watchdog launch emitted
the same duplicate-launch line; pgphoto and 8080 remained absent.  On this
image `/var/run` is persistent, so the stale lock is not self-healing even
across a cold userspace reboot.

## Source fix and focused test

`container/ondisk/pgphoto.wrapper.in` now stores its PID inside the launch-lock
directory, preserves a lock owned by a live PID, and safely reclaims a lock
whose owner is absent.  Cleanup verifies ownership before removing the lock.
`container/test_pgphoto_wrapper_lock.sh` covers both paths and passes locally.

The same candidate also includes the independently evidenced #51 matched-stack
fix: the stock core and port libraries are both replaced together.  This is
required before the rebuilt image can be used for direct on-device CLI tests.

## Archived files

`pre-reboot/` contains the device's Clog, Mlog, rotating Mlog tree, and exact
launch-lock/PID/backoff state captured before reboot.  These files are evidence,
not a release qualification result.
