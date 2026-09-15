# Prevent -> detect -> contain -> recover

Pentax stability engineering should cover all four stages:

**Prevent** — correct candidate finalisation, mode-aware operation semantics, deterministic command serialization.

**Detect** — first-divergence observability; distinguish legitimate busy state from real transport/process/session failure.

**Contain** — reject/queue conflicting commands; stop retry/restart storms; preserve user data and active capture ownership.

**Recover** — clean session/process/USB escalation after genuine failure, ending in provably fresh READY.

The project should not over-invest in the final stage while prevent/detect defects remain unidentified.
