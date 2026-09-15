# Pentax stability acceptance summary

For the current K-3 III stability family, acceptance requires more than recovery:

- no reproducible initiating candidate/timing/concurrency defect remains in the covered matrix;
- multi-minute legitimate Pentax operations are not torn down due solely to fixed elapsed-time assumptions;
- output candidates are discovered/reconciled safely without guessing from Pixel Shift/NR mode;
- command ownership is deterministic;
- process/USB/session failures are distinguishable in logs;
- genuine failure can recover to fresh READY without routine Polaris reboot;
- consecutive capture and soak metrics meet the release gate;
- K-1 II is separately validated;
- OpenPolaris/Benro-facing E2E path is requalified after lower-layer fixes.
