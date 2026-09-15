# Pentax capture command ownership policy

This is a **provisional safe policy** pending E2/E3 hardware characterisation.

## Principle

Only one operation owns the camera capture lifecycle at a time.

Until a command is proven safe in a phase, do not issue it concurrently merely because an app, preview consumer or watchdog requests it.

## Provisional behaviour

- READY: normal command dispatch.
- REQUESTED/CAMERA_ACTIVE/EXPOSING/NR/PIXEL_SHIFT_INTERNAL/PROCESSING: reject or queue a second capture; gate preview/focus/config writes; observe only via operations proven safe.
- CANDIDATE_DISCOVERY/TRANSFER/RECONCILE: preserve capture ownership until candidate lifecycle is terminal; do not declare READY because the first file was saved.
- FAILED: block new work while deterministic recovery owns the session.

`tests/pentax_safe_command_matrix.csv` starts all uncertain cells as `UNKNOWN`. E2/E3 evidence should change those cells to explicit `ALLOW`, `QUEUE`, or `REJECT`; never guess them from convenience.

Watchdog/status code is not exempt from ownership rules. A health check that itself disrupts a legitimate exposure is a defect.
