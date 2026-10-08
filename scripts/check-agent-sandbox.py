#!/usr/bin/env python3
"""Fail-closed check that the VS Code agent sandbox is ENABLED and FUNCTIONAL.

Issue #184. Microsoft's changed sandbox policy (Bubblewrap + network.proxy)
requires ``slirp4netns`` on PATH whenever a sandboxed command may reach the
network. When it is missing, every sandboxed command fails to start and the
assistant silently degrades to running OUTSIDE the sandbox: work keeps
"succeeding" while the isolation guarantee is gone. Two failure shapes must
be caught, and this script fails on both:

  * enabled but broken  - bwrap or slirp4netns missing, or unprivileged user
    namespaces disabled, so no sandboxed command can start at all;
  * disabled entirely   - the policy is off, so everything runs unsandboxed
    and nobody notices.

Verdicts / exit codes (stable; safe to branch on):

  0  SANDBOX_OK        sandbox enabled and every prerequisite present
  1  POLICY_DISABLED   settings exist but the sandbox is off/absent
  2  BROKEN            sandbox enabled but a prerequisite is missing
  77 NO_SETTINGS       no VS Code-family settings found (non-VS Code host)

The exit-77 contract matches the repo's existing prerequisite-skip rule so
the pre-release gate can report SKIP, never silent green.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_host_settings import (  # noqa: E402
    discover_user_settings,
    load_settings,
)

SANDBOX_KEY = "chat.agent.sandbox.enabled"

# Prerequisites of the current networked sandbox policy. bwrap brings up the
# namespaces; slirp4netns is what makes the private network namespace
# reachable (network.proxy). The userns sysctl gates both on Linux hosts.
REQUIRED_TOOLS = ("bwrap", "slirp4netns")
USERNS_SYSCTL = Path("/proc/sys/kernel/unprivileged_userns_clone")


def merged_sandbox_setting(paths: list[Path]) -> tuple[str, list[str]]:
    """Return (state, errors); state is 'on' | 'off' | 'missing'."""
    state = "missing"
    errors: list[str] = []
    for path in paths:
        try:
            data = load_settings(path)
        except (OSError, ValueError) as exc:
            errors.append(f"{path}: {exc}")
            continue
        value = data.get(SANDBOX_KEY, None)
        if value is None:
            continue
        # The editor accepts "on"/"off" strings and booleans across versions.
        if value is True or (isinstance(value, str) and value.lower() == "on"):
            state = "on"
        else:
            state = "off"
    return state, errors


def check_prerequisites(
    *,
    which=shutil.which,
    sysctl_path: Path = USERNS_SYSCTL,
) -> list[str]:
    """Return the list of missing/broken prerequisites (empty = healthy)."""
    missing = [tool for tool in REQUIRED_TOOLS if which(tool) is None]
    try:
        enabled = sysctl_path.read_text(encoding="utf-8").strip() == "1"
    except OSError:
        # Sysctl absent: modern kernels have userns on unconditionally
        # (no unprivileged_userns_clone knob). Not a failure by itself.
        enabled = True
    if not enabled:
        missing.append("unprivileged_userns_clone=0")
    return missing


def verdict(
    home: Path,
    workspace_settings: Path | None,
    *,
    which=shutil.which,
    sysctl_path: Path = USERNS_SYSCTL,
) -> tuple[int, str]:
    paths = discover_user_settings(home)
    if workspace_settings is not None and workspace_settings.is_file():
        paths.append(workspace_settings)
    if not paths:
        return 77, "VERDICT=NO_SETTINGS reason=no VS Code-family settings found"
    state, errors = merged_sandbox_setting(paths)
    if errors:
        return 2, "VERDICT=BROKEN reason=settings unreadable " + "; ".join(errors)
    if state != "on":
        return 1, (
            "VERDICT=POLICY_DISABLED reason="
            f"{SANDBOX_KEY} is {state} - every agent command runs OUTSIDE "
            "the sandbox (issue #184)"
        )
    missing = check_prerequisites(which=which, sysctl_path=sysctl_path)
    if missing:
        return 2, (
            "VERDICT=BROKEN reason=sandbox enabled but host cannot start a "
            "sandboxed command missing=" + ",".join(missing)
            + " fix='install slirp4netns and bubblewrap (static binaries in "
            "~/.local/bin are fine)' or set " + SANDBOX_KEY + "=false knowingly"
        )
    return 0, "VERDICT=SANDBOX_OK sandbox=enabled prerequisites=present"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--workspace-settings", type=Path, default=None)
    args = parser.parse_args(argv)
    code, line = verdict(args.home, args.workspace_settings)
    print(line)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
