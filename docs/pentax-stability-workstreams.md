# Pentax stability workstreams

## WS1 — Capture finalisation and candidates

Experiments E4/E5. Owns consecutive-shot poisoning, multi-output candidate classification and reconciliation. Strong current candidate for a real initiating defect.

## WS2 — Mode-aware long operation / timeout audit

Experiments E1/E6. Inventory every timer/watchdog/retry around capture command 264 and prove whether it can fire during legitimate Pentax exposure/NR/Pixel Shift/processing.

## WS3 — Camera command arbitration

Experiments E2/E3/E13. Establish and encode safe command-by-phase matrix. Prevent preview/config/focus/status from racing capture.

## WS4 — pgphoto/process/session lifecycle

Experiments E8/E11/E12. Separate process failure from camera/PTP failure and prove fresh-process vs in-process reset semantics.

## WS5 — USB/physical transport

Experiment E9 plus known hub-flapping evidence. Keep true physical USB transitions separate from in-place PTP contamination.

## WS6 — Upper layer/network isolation

Experiment E14. Reintroduce preview/Benro/OpenPolaris only after lower-level baselines are known.

## WS7 — Driver/integration control

Experiment E15. Same camera/settings/library SHA via direct libgphoto2 control to distinguish Pentax driver defects from embedded pgphoto/runtime integration.

## WS8 — Recovery safety net

Implement/verify deterministic teardown only after causal evidence is captured. Recovery must preserve legitimate long exposures and user DNG data.

Each workstream should create focused issues for proven defects; #82 remains the umbrella.
