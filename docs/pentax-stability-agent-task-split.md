# Initial agent task split

See `tests/pentax_stability_agent_tasks.csv`.

Source-audit agents should not make speculative behavioural changes. The first behavioural mutation should follow instrumentation plus a reproduced first divergence. This avoids several agents independently 'fixing' timeouts/recovery and destroying the experimental baseline.
