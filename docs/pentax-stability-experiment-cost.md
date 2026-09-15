# Pentax stability experiment cost/risk guidance

Prefer experiments by information gained per camera minute and risk.

**Cheap/high value:** 1 s DNG+JPEG back-to-back, candidate enumeration, command injection with preview initially off, source timeout inventory.

**Moderate:** 30 s concurrency/preview races, 95-105 s timeout sweep, short Pixel Shift/NR characterisation.

**Expensive:** repeated 120/300 s NR/Pixel Shift/Bulb, long soak.

**Risky/destructive:** aborts, pgphoto kill mid-capture, USB/power interruption. Run these only after clean lifecycle is understood and evidence collection is ready.

If a cheap experiment yields a deterministic failure, reduce and fix it before running the entire expensive matrix.
