# Pentax stability staged execution order

## Stage 0 — instrumentation/source inventory

Add structured observation and inventory all timeout/watchdog actions. No behavioural fix yet.

## Stage 1 — cheap, high-information non-destructive tests

- E4 back-to-back
- E5 candidate lifecycle
- E1 100-second boundary

## Stage 2 — concurrency

- E2 controlled foreign command
- E3 preview races
- E13 overlapping shutter

## Stage 3 — real astro timing

- E6 120/300 s normal and NR
- Pixel Shift/NR hardware characterisation
- Bulb

## Stage 4 — history and accumulation

- E12 session history
- E11 soak/resource trends

## Stage 5 — isolation controls

- E14 upper-layer/network
- E15 direct libgphoto2

## Stage 6 — destructive fault injection

Only after clean lifecycle is understood:

- E7 cancellation
- E8 pgphoto interruption
- E9 USB/power disruption

## Stage 7 — fixes and regression

Fix the earliest proven transition, add regression coverage, rerun relevant lower stages, then reintroduce OpenPolaris for E2E qualification.
