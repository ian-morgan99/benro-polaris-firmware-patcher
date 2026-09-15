# Runtime control principle

> Don't ask an LLM to control things that deterministic software can guarantee.

For Pentax stability this means camera command ownership, lifecycle transitions, candidate reconciliation, timeout semantics, liveness checks and recovery escalation are deterministic code with explicit tests.

Agents/LLMs are valuable for source review, hypothesis generation, experiment orchestration, log correlation and patch review. They are not part of the live camera-control decision loop.
