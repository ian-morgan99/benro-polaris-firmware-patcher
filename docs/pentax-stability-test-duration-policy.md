# Test duration escalation policy

Start with the shortest exposure that can test a hypothesis. Increase duration only when needed.

For mode characterisation: 1 s -> 30 s -> boundary/long cases. For timeout causality: use the tight 95/99/100/101/105 s sweep. For real Astro qualification: 120/300 s after instrumentation/safe probes are known.

This reduces camera time and makes state differences easier to compare.
