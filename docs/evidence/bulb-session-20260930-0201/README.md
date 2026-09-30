# Bulb-mode session evidence (2026-09-30)

- [Timestamped test ledger](SESSION-LEDGER.md): user observations and device-log
  facts kept separate.
- [Evidence analysis](ANALYSIS.md): supported findings, open questions and
  repository/issue ownership; not a substitute for direct camera reproduction.
- `raw/`: complete rotated Clog/Mlog sessions 000177–000180 plus active-log
  snapshots. Rotated logs were refreshed through about 02:20 UTC; active Clog
  was snapshotted during collection and may have continued changing on-device.
- [SHA256SUMS](SHA256SUMS): integrity hashes for every raw file.

Device: Polaris FwVer `6.0.0.54.43`; Pentax K-3 Mark III, RAW+JPEG during the
recorded capture attempts. The active `Mlog.txt` snapshot was empty; use the
rotated `Mlog_000180.log` for application-level events. The refreshed logs
include the SP_0157 timeout and a kernel USB removal event at 02:15:04 UTC.
