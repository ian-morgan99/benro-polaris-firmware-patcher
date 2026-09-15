# Architecture intent

The plan is intentionally conservative about runtime changes: deterministic software should guarantee camera ownership, lifecycle transitions and cleanup. AI agents are used to accelerate source analysis, hardware experiment orchestration and evidence review, not to compensate at runtime for an underspecified state machine.
