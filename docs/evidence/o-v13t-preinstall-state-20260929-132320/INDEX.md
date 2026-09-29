# Pre-install state preservation

Captured read-only from Polaris on 2026-09-29 before firmware staging. Device
identity was confirmed by association to BSSID `48:E7:DA:D4:B5:73`
(`polaris_d13e86`), route via `wlp8s0`, and `/app/FwVer`.

- Installed firmware: `6.0.0.54.35-o-v13s-preserve-pending`.
- Before the battery replacement, persistent Mlog recorded camera USB removal
  at `13:22:22`, followed by camera state `none` / `-5`. User then reported
  replacing the camera battery; later live Mlog showed camera configuration
  traffic again. No shutter was sent in this session.
- Captured current Clog/Mlog and persistent numbered Clog/Mlog logs for boot
  generations 169–171. They are preserved here verbatim; file hashes follow.
- Current Stage-2 and stock-path `libgphoto2.so.6` MD5s matched each other
  (`4ef64d8950eee70d9200093286fb0f3b`); both port-library MD5s matched
  (`ad50e83594397aef48b63ed2375890cc`). Runtime maps showed Stage-2 core/port.
- The attempted o-v13t SD transfer was stopped after independent review rejected
  its recovery semantics. Its incomplete `/app/sd/FwPkt/` staging tree was
  removed; the pre-existing `/app/sd/FwPkt.zip` was left untouched. No reboot
  or candidate install occurred.

SHA-256:

```
2536149791bc33c8df9ebf3b7a7745845c66444ad0166db27f4d3dde8377d576  Clog_000170.txt
38f2b96cca95782f716bb8411f5c3519f68f67092e12cb55c694002ba22e115c  Clog-current.txt
ddeb43b9fdcdeede42acd1e20ad4d5a1065f6b0b8013d5fe7b634409a032c1f5  Mlog-current.txt
11226e34ebeeb5aa1b24a3fa47df2aa8ebe8603d83058a52ef58a75867f2ca69  Clog_000171.txt
82d2ed93157a797beebbddc71fa928820550d37d4781271d1a826befd9997e5f  Mlog_000171.txt
f18e8ac7e942997221365bef958a4228a566d0398e6d31809983aee90bc8a970  Mlog_000170.txt
841ea526336ee358b2d1cf28dc19ffc661070ee7771550573815c474beedf6b7  Mlog_000169.txt
2187c0d02d579f27f384f56f402369d2783e5418459f0e5fedcd5135cfe1b122  Clog_000169.txt
```
