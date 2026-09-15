# Pentax stability regression philosophy

A regression test should reproduce the **minimal initiating condition**, not merely verify that a reset eventually succeeds.

Examples:

- candidate bug: prove second shutter succeeds after a multi-output first capture and candidate ownership is terminal;
- timeout bug: prove captures on both sides of the old threshold remain healthy when camera state is legitimate;
- concurrency bug: prove unsafe command is queued/rejected and active capture remains intact;
- session cleanup bug: prove fresh lifecycle after genuine failure without stale abilities/port reuse;
- USB bug: prove real identity transition is handled without conflating unrelated ttyUSB state.

Keep recovery tests too, but do not let them replace prevention tests.
