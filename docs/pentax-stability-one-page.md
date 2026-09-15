# Pentax stability — one-page brief

## Goal
Find why healthy Pentax sessions fail, prevent those transitions, then make genuine failures recover cleanly.

## Current likely families
Candidate finalisation; mode-unaware timing; command/preview concurrency; pgphoto/session lifecycle; physical USB; upper-layer/network pressure; driver vs embedded integration.

## Pentax-specific rule
Shutter duration is not capture duration. NR, Pixel Shift, processing and Bulb can extend legitimate work. Physical exposures, files and tether candidates are separate counts.

## Primary diagnostic path
Physical K-3 III through Polaris pgphoto + staged libgphoto2, initially preview OFF and without OpenPolaris. Direct gphoto2 is a control. OpenPolaris returns for E2E replay.

## First experiments
E4/E5 candidate/back-to-back, then E1 around 100 s, then concurrency/preview and real long exposure.

## Evidence rule
Record the first abnormal transition. Treat stale session/NoUpdateImage/-1005/reset requirement as aftermath unless proven first.

## Runtime rule
Deterministic ownership/state/recovery. No LLM in live camera control.

## Done
Minimal reproducer + source owner + deterministic fix + regression + consecutive READY proof + no routine Polaris reboot + K-1 II validation + OpenPolaris/Benro E2E requalification.
