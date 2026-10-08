# Agent host-config contract

Machine-level contract for the VS Code agent environment used on this
project's workstations. Two Microsoft-side changes in 2026 made this
necessary; both were silent regressions (issue #184):

1. **Sandbox policy change (#184).** With `chat.agent.sandbox.enabled: "on"`,
   networked sandboxed commands now require Bubblewrap **and** `slirp4netns`
   on PATH. When `slirp4netns` was missing here, every sandboxed command
   failed to start and the assistant silently degraded to running *outside*
   the sandbox — work kept "succeeding" with no isolation.
## The contract

Checked by `scripts/check-agent-sandbox.py` (fail-closed; exit 77 = no VS
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

## Where this is enforced

The fixture suite `tests/test_agent_sandbox_check.py` runs in the offline
pre-release gate, and the gate additionally runs the checker against the
live host so a broken or disabled sandbox turns the gate red instead of
degrading silently.
