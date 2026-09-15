# Pentax stability roadmap

1. Instrument first-divergence observability.
2. Inventory all timers/watchdogs around capture.
3. Reproduce candidate/back-to-back failure below OpenPolaris.
4. Sweep timeout boundaries.
5. Characterise K-3 III NR/Pixel Shift/Bulb lifecycle and outputs.
6. Characterise command concurrency/preview safety.
7. Isolate pgphoto/process, USB and direct-libgphoto2 differences.
8. Fix each initiating defect with deterministic regression tests.
9. Harden recovery for genuine failures without corrupting legitimate long operations or user data.
10. Validate K-1 II separately.
11. Reintroduce OpenPolaris and Benro-facing E2E tests.
12. Require causal stability gate for release.
