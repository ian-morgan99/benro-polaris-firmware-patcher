# Pentax stability tooling

Initial repository tooling:

```sh
python3 tools/validate_pentax_stability_plan.py
python3 tools/check_pentax_stability_matrix.py
pytest -q tests/test_pentax_stability_trace.py tests/test_pentax_stability_scenarios.py
```

Hardware traces can be written with `tools/pentax_stability_trace.py` or the lightweight embedded `tools/pentax_trace_mark.sh`, then summarised with `tools/analyse_pentax_stability_trace.py`.

These are scaffolding. Prefer source-level structured instrumentation once the pgphoto/libgphoto2 transition points are identified.
