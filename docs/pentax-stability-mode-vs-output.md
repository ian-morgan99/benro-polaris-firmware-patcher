# Capture mode does not define output count

The host should not use a lookup such as `Pixel Shift -> 4/5 candidates` or `NR -> 2 candidates`.

Capture mode describes camera behaviour. Candidate enumeration describes what the camera actually exposes to the tether lifecycle after/while processing. These are separate domains.

Use mode for expectation/diagnostics and actual candidate descriptors for transfer/reconciliation.
