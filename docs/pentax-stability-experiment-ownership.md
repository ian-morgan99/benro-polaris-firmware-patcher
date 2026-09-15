# Experiment ownership

One integration owner should control the physical-camera baseline and behavioural changes while source-audit agents can work in parallel.

Reason: if several agents independently change timeouts, locks, recovery and candidate handling, an improvement/regression cannot be attributed to one variable and the hardware campaign loses value.

Parallelise observation/source mapping; serialise behavioural experiments and fixes.
