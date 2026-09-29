# Read-only check after camera was turned on

Device-reported time: 2026-09-29 14:30 UTC. No shutter command was sent.

## Result

- Polaris identity checks passed: BSSID `48:E7:DA:D4:B5:73`, SSID
  `polaris_d13e86`, route to `192.168.0.1` via `wlp8s0`.
- Installed firmware is still `6.0.0.54.35-o-v13s-preserve-pending`; embedded
  libgphoto2 is `204c2a95a0da78135ad3c6dc244c230d5d16d2e9`, patcher is
  `d11bc748f917a1705988596aa6acf565a7131c9a`. The new candidate is not staged.
- USB enumerated Pentax `25fb:0189`. The official no-capture probe first saw
  `state=-5` while pgphoto was reinitialising; a later single probe returned
  K-3 Mark III, `state=1`, `storage=2`, `photoFormat=2`.
- During re-enumeration the USB supervisor logged identity `none -> 1-1.2` and
  restarted pgphoto (reported restart budget `4/6`). The captured Clog also has
  `sp_Gphoto_Init ret 0`, successful K-3 III model/config reads, and some
  individual unsupported/config/preview operations returning errors. These
  observations are not evidence of a shutter or output success and do not prove
  the cause of earlier capture failures.
- At the last read-only process check, pgphoto PID was `15905`; its environment
  had `STAGE2_CAPTURE_TRACE=1`. Stage-2 and stock core hashes matched each
  other, as did both port hashes and both ptp2 hashes. The core appeared in
  `/proc/15905/maps`; no `capture-enter` or `InitiateCapture` was observed.

## Evidence preservation

Complete raw `Clog.txt` and `Mlog.txt` were retrieved in one bounded SSH/tar
read. To avoid publishing the camera USB serial present in kernel diagnostics,
the raw files remain local and are ignored by this evidence folder; their
SHA-256 values are:

- Clog: `ad02f48f32124ebbe7141f40f24aee02dacb031a88715c71909cce97a53e872c`
- Mlog: `eeaaaaa6331ffe808e25ff69d9711656dfa80f97fb90f5d4eb39db818f3946be`

The installed candidate and source fixes remain unqualified. The independent
review of o-v13v is still pending. Do not send a shutter or install this
candidate until that review clears the package and the known restart-durability
gap is explicitly dispositioned.
