# Pentax stability observability contract

A stability fix is not complete if the next field failure cannot be attributed to its first divergent layer.

## Minimum observability

Every accepted capture gets a stable capture/run ID. Logs should allow that ID to be followed through request, camera-active work, candidate discovery, transfer, reconciliation and READY.

Every automatic recovery/restart must log:

- reason;
- lifecycle phase;
- active capture/run ID;
- camera/PTP condition if safely available;
- USB fingerprint;
- old/new pgphoto PID when applicable;
- whether the trigger was elapsed-time expectation, actual I/O failure, process health, or USB identity change.

Every command rejected/queued because the camera is owned by another lifecycle phase should be observable without log flooding.

Candidate logs must include enough descriptors to distinguish JPEG/DNG/multi-output ownership without dumping image content.

## First-divergence rule

Instrumentation must preserve ordering with a monotonic clock. A later high-level symptom cannot overwrite or hide an earlier watchdog, command collision, candidate leak or process event.

## Performance rule

Observability must be cheap enough not to create the race being measured. Prefer structured single-line events and bounded detail; image data is never part of the trace.
