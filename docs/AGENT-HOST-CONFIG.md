# Agent host-config contract

Machine-level contract for the VS Code agent environment used on this
project's workstations. Two Microsoft-side changes in 2026 made this
necessary; both were silent regressions (issues #184, #185):

1. **Sandbox policy change (#184).** With `chat.agent.sandbox.enabled: "on"`,
   networked sandboxed commands now require Bubblewrap **and** `slirp4netns`
   on PATH. When `slirp4netns` was missing here, every sandboxed command
   failed to start and the assistant silently degraded to running *outside*
   the sandbox — work kept "succeeding" with no isolation.
2. **Model picker scenario (#185).** `chat.experimentalModelPicker` is an
   opt-out that currently shields our pinned model selection. If it is
   adopted (default true / opt-out retired), model selection changes under
   us. The durable guard is **explicit pinning**, not the opt-out.

## The contract

Checked by `scripts/check-agent-sandbox.py` and
`scripts/check-agent-host-config.py` (both fail-closed; exit 77 = no VS
Code-family settings on this host = prerequisite skip, matching the gate's
SKIP convention; anything else non-zero = red).

### Sandbox (check-agent-sandbox.py)

- `chat.agent.sandbox.enabled` must be **on** in the merged user/workspace
  settings. `"off"` or absent ⇒ `POLICY_DISABLED` (exit 1): running
  everything outside the sandbox is a decision, not a default.
- `bwrap` and `slirp4netns` must both be on PATH, and unprivileged user
  namespaces must not be sysctl-disabled ⇒ otherwise `BROKEN` (exit 2).
- Fix for the 2026-10-08 host state: `sudo apt install slirp4netns`, or a
  static binary from rootless-containers releases in `~/.local/bin`
  (no sudo needed; that is what this host now runs, v1.3.1).

### Model selection (check-agent-host-config.py)

- These keys must exist and be non-empty in the merged settings (the
  **pins**): `chat.byokUtilityModelDefault`, `chat.planAgent.defaultModel`,
  `lmstudio.defaultModelId`.
- `chat.experimentalModelPicker` may be **true or false** — the checker
  reports its value and passes either way while the pins exist. Do not
  treat the opt-out as the defence; keep it only as belt-and-braces.
- Tracked repo settings (`.vscode/settings.json`) must contain **no
  machine-specific keys** (`lmstudio.baseUrl`, `lmstudio.secondaryServers`,
  `lmstudio.supervision.pythonExecutable`, `lmstudio.supervision.device`)
  — the rule from the 5fdc174 review note. Machine identity lives in the
  user profile only.

## Where this is enforced

Both fixture suites run in the offline pre-release gate
(`tests/test_agent_sandbox_check.py`, `tests/test_agent_host_config_check.py`),
and the gate additionally runs both checkers against the live host so a
broken or disabled sandbox, or a dropped model pin, turns the gate red
instead of degrading silently.
