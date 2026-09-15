# Pentax stability experiment principles

1. **Measure before modelling.** Pixel Shift/NR timing and candidate semantics come from hardware observations.
2. **One variable at a time.** Use A/B/A where practical.
3. **Repeat.** Intermittent failure requires a rate, not an anecdote.
4. **Find the first divergence.** Recovery symptoms are downstream evidence.
5. **Use the production-relevant lower path.** Polaris pgphoto + staged libgphoto2 first; direct gphoto2 is a control; OpenPolaris is later E2E qualification.
6. **Protect data and hardware.** Non-destructive tests first; do not purge unknown DNG candidates.
7. **Separate time, state and transport.** None alone is a complete liveness model.
8. **Prove READY with the next operation.** A saved first image is not enough.
9. **Automate reproducible mechanics.** Runtime decisions remain deterministic; agents analyse results, not control session state.
10. **Promote every real failure recipe into regression coverage.**
