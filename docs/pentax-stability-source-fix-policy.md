# Source fix policy

When evidence identifies a first divergence:

1. locate exact source path/function;
2. explain why current behaviour violates the capture/session contract;
3. add a failing deterministic regression where practical;
4. make the smallest fix that restores the invariant;
5. avoid broad timeout/retry/recovery changes unless the evidence requires them;
6. rerun the causal reproducer and adjacent baselines;
7. deliver through reproducible FwPkt path for product qualification.

Prefer a small proven fix over a large "stability hardening" patch that changes several variables at once.
