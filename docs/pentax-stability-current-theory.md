# Current evidence-weighted Pentax stability theory

This is a working theory, not a conclusion.

## High-confidence defects already evidenced

1. A multi-output Pentax capture can leave a transfer candidate pending and block the next shutter in the related libgphoto2 hardware evidence.
2. In-process reset/reinitialisation can preserve stale camera selection/explicit USB port/application-session state after removal/body change rather than constructing a truly fresh lifecycle.

## Strong architectural concern requiring direct proof

A fixed capture timeout around 100 seconds exists in the relevant libgphoto2 source. Legitimate Pentax astro operations can exceed this substantially due to requested shutter, long-exposure NR, Pixel Shift, processing and Bulb. The experiment programme must determine whether this or another timer actually initiates any field failure; source existence alone is not proof.

## Plausible compounding mechanisms

- preview/config/focus/status traffic collides with an active capture lifecycle;
- preview retry loops create PTP/radio pressure;
- pgphoto process/runtime state survives or accumulates across operations;
- recovery observes/reuses an already-open Pentax session instead of proving fresh ownership;
- upper-layer/network effects obscure the underlying camera failure.

## Critical distinction

A stale session can be both a real recovery defect **and** an aftermath of a different initiating defect. The campaign is designed to identify both without confusing them.
