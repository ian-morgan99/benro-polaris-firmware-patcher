# Experiment stop rule

Do not blindly execute the entire matrix once a high-information failure is found.

If a scenario produces a repeatable first-divergence fingerprint:

1. stop broader/longer/riskier variants in that family;
2. reduce it to the smallest reproducer;
3. run the discriminating A/B control;
4. locate source ownership;
5. create regression test/focused issue;
6. fix and re-run adjacent cases;
7. resume the broader matrix only if needed.

This keeps camera time focused on causal information rather than generating redundant crash logs.
