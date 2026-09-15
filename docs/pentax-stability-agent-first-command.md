# First agent action

Do **not** start by changing timeout/recovery values.

First:

```sh
python3 tools/validate_pentax_stability_plan.py
python3 tools/check_pentax_stability_matrix.py
```

Then complete the static timeout/command/session inventories and identify source-level structured trace insertion points. Once observability is ready, run `tests/pentax_stability_minimum_first_run.csv` against the physical K-3 III/Polaris environment.
