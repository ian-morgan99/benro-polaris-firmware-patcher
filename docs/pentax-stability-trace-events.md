# Canonical stability trace events

See `tests/pentax_stability_trace_events.txt`.

Source instrumentation should prefer this vocabulary where it maps cleanly. Additional events are allowed, but stable names make cross-run fingerprinting easier.

`operation_exceeded_expectation` is deliberately distinct from `ptp_error` or `first_abnormal`: elapsed-time expectation alone is telemetry, not proof of a dead session.
