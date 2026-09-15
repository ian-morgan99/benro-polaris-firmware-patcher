# Future automated hardware regression direction

Once the lower-level capture contract and safe command mechanisms are known, turn the high-value scenarios into an automated hardware regression runner that:

- applies known camera configuration safely;
- runs one scenario at a time;
- records exact provenance and structured trace;
- preserves Mlog/Clog;
- evaluates deterministic invariants (terminal reconciliation, no unexplained candidate, next shutter succeeds, no unexpected restart);
- stops on destructive/unknown failure rather than repeatedly power-cycling hardware;
- produces a machine-readable result plus human issue summary.

OpenPolaris can later drive equivalent E2E scenarios, but the lower-level runner remains useful for attribution.
