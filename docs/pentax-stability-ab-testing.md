# A/B/A testing

Use `tests/pentax_stability_ab_controls.csv` for the key hypotheses.

Returning to A after the stressor is important: if A now fails too, B may have contaminated persistent camera/session state rather than simply exposing a transient race. That observation is itself valuable and should be recorded as session-history evidence.
