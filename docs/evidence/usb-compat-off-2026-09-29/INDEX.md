# USB compatibility OFF failure evidence

Collected read-only from the Polaris on 2026-09-29 after the failure/reboot.
Device identity at collection: AP `polaris_d13e86`, BSSID `48:E7:DA:D4:B5:73`,
Wi-Fi route via `wlp8s0`; firmware
`6.0.0.54.34-o-v13j-crash-boundary`; uptime about 12 minutes at 11:17 UTC.

## Files

- `Clog_000169.log`, `Mlog_000169.log`, `error_000169.log`: session before
  the apparent reboot.
- `Clog_000170.log`, `Mlog_000170.log`, `error_000170.log`: session after
  reboot, including the failed capture/restart sequence and the monitored
  `SP_0137` request at 11:21:35. That request was rejected with `-110` by the
  unclaimed-transfer-candidate guard before any new InitiateCapture. The
  camera remained USB `25fb:0189`; pgphoto PID stayed `1585`; Polaris uptime
  continued. No `SP_0137` output was found.
- `dmesg-current-boot.txt`: kernel ring buffer from the current boot only.
  The previous boot's ring buffer was lost at reboot; no retained kernel panic
  or reboot-cause record was found in the checked persistent paths.
- `dmesg-after-SP0137.txt`: a second snapshot after the monitored request.
  The SSH monitor polled every five seconds for roughly two minutes. Matching
  Broadcom pool-exhaustion lines (`No more free tdata_psh_info` / `Out of
  tdata_disc_grp`) rose from 864 in the first snapshot to 1668 afterward.
  This strongly correlates with the high-frequency polling interval; causation
  is not proven, so do not treat those added messages as camera-caused. The
  monitor was stopped and no further frequent polling is planned.

The current-boot dmesg identifies Pentax `25fb:0189` during USB enumeration and
shows two subsequent xHCI resets of `usb 1-1.2`. This establishes that the
camera was present on the bus during startup and was reset by the host after
boot. It does not establish whether it remained physically connected through
the precise reboot transition, whether those resets were abnormal, or what
caused the reboot.

Device clock/host clock differ by one hour (device log files are stamped one
hour ahead of the UTC `date` output); event times above refer to device log
timestamps. Tar extraction warned that device mtimes were ahead of the host;
file contents were extracted and hashed below.

## SHA-256

```
2187c0d02d579f27f384f56f402369d2783e5418459f0e5fedcd5135cfe1b122  Clog_000169.log
e25cb9c5306270716a2a14672a59aede3c3beb41951bb8788c80e5fafa1901f7  Clog_000170.log
841ea526336ee358b2d1cf28dc19ffc661070ee7771550573815c474beedf6b7  Mlog_000169.log
38fd941120bd7dfa54afd435069142e759dd016a2b9da3e3f13834397705fbe7  Mlog_000170.log
af0d0d7e4a23c3a33511190cf8a2d2906d4bd3f40fbcd1bb732be3c33cf87917  error_000169.log
6c462be4a39148072745884aadbc678fbdbc992ef473d9698a576d8be8a324cd  error_000170.log
bc029d89615124e1165dc98ca6175cbe4439a2114dfba271fa1aa10b2eedf5cb  dmesg-current-boot.txt
df5dfa70c75a86b321276840e62693f974e8d1932a999914e915df0ec985709e  dmesg-after-SP0137.txt
```
