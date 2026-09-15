# Bounded patience

"Do not prematurely timeout" does not mean "wait forever".

For long/unknown modes, use bounded observation based on actual safe progress/health signals. Separate a generous operation envelope from transport/process failure detection. If no safe progress signal exists, that is an observability/design problem to solve explicitly rather than falling back to a short generic timeout.
