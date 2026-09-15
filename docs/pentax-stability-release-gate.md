# Pentax causal stability release gate

This supplements the broader Pentax regression/release gate. A build must not be called stable merely because it can recover from failures.

For K-3 III before promotion:

- baseline normal JPEG consecutive captures pass;
- DNG+JPEG consecutive captures leave no unexplained pending transfer candidate;
- 95/99/100/101/105 s boundary sweep shows no artificial failure cliff caused solely by fixed timeout;
- 120 s and 300 s captures complete without timeout-induced session teardown;
- long-exposure NR is not classified dead during legitimate dark/processing time;
- Pixel Shift output/candidate semantics have been measured and are not guessed from physical exposure count;
- unsafe overlapping capture request is deterministically rejected/queued without corrupting active operation;
- preview OFF baseline is stable;
- preview ON does not issue unsafe camera operations during protected capture phases, or is explicitly gated until safe;
- after each successful capture, a second capture proves READY/finalisation;
- soak shows no material monotonic pgphoto resource growth or increasing per-shot failure rate;
- any genuine injected failure used for qualification returns to fresh READY without Polaris reboot where the recovery contract says it should.

Any failure must be reported using `pentax-stability-results-template.md` and classified by its first abnormal event.

After K-3 III passes, validate mode/liveness assumptions separately on K-1 II before treating them as generic Pentax rules.
