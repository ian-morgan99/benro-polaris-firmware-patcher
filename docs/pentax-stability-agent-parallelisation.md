# Parallelising Pentax stability work across agents

Parallel work is useful only when agents do not mutate the same runtime behaviour independently.

Safe initial split:

- Agent A: source inventory of all capture/watchdog/retry timeouts and fill `pentax-stability-timing-inventory-template.md`.
- Agent B: locate capture/candidate lifecycle source transitions and propose structured trace insertion points; no behavioural change.
- Agent C: inspect preview/config/focus/status command entry points and build the static command-concurrency map; no behavioural change.
- Agent D: prepare/execute E4/E5 physical-camera baseline once instrumentation is available.
- Agent E: review pgphoto process/reset/session lifecycle for what state survives in-process reset vs process replacement.

One integration owner should merge instrumentation and decide when hardware tests start. Behavioural fixes should be driven by resulting evidence, not parallel speculative patches.
