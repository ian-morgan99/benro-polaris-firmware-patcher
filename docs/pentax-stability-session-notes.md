# Session staleness: cause vs aftermath

The project has real evidence that reset/reinitialisation can preserve stale camera selection/port/session state. That recovery defect must be fixed.

However, a stale session observed after a capture failure does not establish why the healthy session failed.

For every occurrence of `session already open ... observing camera state`, correlate backwards to the last known-good state and identify whether a timeout, foreign command, candidate leak, process event, USB transition or other event occurred first.

E12 deliberately compares healthy and failed histories so we learn whether an already-open session is sometimes normal context and which additional state makes it harmful.
