# Static source audits before behavioural changes

Three machine-readable templates should be completed by source-review agents before speculative fixes:

- `tests/pentax_timeout_inventory.csv` — every relevant timer/watchdog and its semantics/expiry action;
- `tests/pentax_command_entrypoints.csv` — every path capable of issuing camera/PTP work and current serialization;
- `tests/pentax_session_state_inventory.csv` — state that survives in-process reset, pgphoto restart and USB reconnect.

These audits complement, but do not replace, physical hardware experiments.
