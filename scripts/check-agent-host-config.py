#!/usr/bin/env python3
"""Fail-closed check that agent model selection stays deterministic.

Issue #185. The workflow currently guards the experimental model picker with
``chat.experimentalModelPicker: false`` in user and workspace settings. That
is an opt-out guard: it holds only while the setting stays false. If Microsoft
adopts the picker (default true, or the opt-out key retired), model selection
silently changes under us — the utility model, plan-agent model and LM Studio
default are exactly what the picker governs.

The durable defence is explicit pinning, not the opt-out. This script asserts
the host-config contract (docs/AGENT-HOST-CONFIG.md):

  * every PINNED_KEY exists and is a non-empty string in the merged settings;
  * the repo workspace settings contain no machine-specific keys (the rule
    from the 5fdc174 review note — machine identity lives in user settings);
  * ``chat.experimentalModelPicker`` may be true OR false: the value is
    reported, and the check passes either way as long as the pins exist.

Exit codes (stable): 0 CONFIG_OK, 1 CONFIG_BAD, 77 NO_SETTINGS (non-VS Code
host; matches the repo prerequisite-skip contract).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Reuse the JSONC loader shared with the sandbox checker; both read the same
# files and must not drift on comment handling or discovery order.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_host_settings import (  # noqa: E402
    discover_user_settings,
    load_settings,
)

# Keys whose absence (or emptiness) makes model selection depend on whatever
# the picker defaults to. These are the pins that keep behaviour identical
# whether chat.experimentalModelPicker is true or false.
PINNED_KEYS = (
    "chat.byokUtilityModelDefault",
    "chat.planAgent.defaultModel",
    "lmstudio.defaultModelId",
)

# The key under observation. Reported, never required either way.
PICKER_KEY = "chat.experimentalModelPicker"

# Keys that carry machine identity and must NOT appear in tracked repo
# settings (5fdc174 review note). Matched as substrings of the key name.
MACHINE_SPECIFIC_PATTERNS = (
    "lmstudio.baseUrl",
    "lmstudio.secondaryServers",
    "lmstudio.supervision.pythonExecutable",
    "lmstudio.supervision.device",
)


def merged_settings(
    user_paths: list[Path], workspace_path: Path | None
) -> tuple[dict, list[Path], list[str]]:
    merged: dict = {}
    loaded: list[Path] = []
    errors: list[str] = []
    paths = list(user_paths)
    if workspace_path is not None:
        paths.append(workspace_path)
    for path in paths:
        if not path.is_file():
            continue
        try:
            merged.update(load_settings(path))
            loaded.append(path)
        except (OSError, ValueError) as exc:
            errors.append(f"{path}: {exc}")
    return merged, loaded, errors


def check(
    home: Path,
    workspace_settings: Path | None,
    *,
    require_user_settings: bool = True,
) -> tuple[int, list[str]]:
    user_paths = discover_user_settings(home)
    if not user_paths and require_user_settings:
        return 77, ["VERDICT=NO_SETTINGS reason=no VS Code-family user settings"]

    merged, loaded, problems = merged_settings(user_paths, workspace_settings)
    if problems:
        return 1, ["VERDICT=CONFIG_BAD reason=settings unreadable"] + problems

    picker = merged.get(PICKER_KEY, "unset")
    notes = [f"{PICKER_KEY}={picker} (accepted either way; pins below are the guard)"]

    for key in PINNED_KEYS:
        value = merged.get(key)
        if not isinstance(value, str) or not value.strip():
            problems.append(
                f"missing or empty pin: {key} — model selection would fall "
                f"back to the picker default if {PICKER_KEY} becomes true"
            )

    ws = workspace_settings if (workspace_settings and workspace_settings.is_file()) else None
    if ws is not None:
        ws_data = load_settings(ws)
        for key in ws_data:
            for pattern in MACHINE_SPECIFIC_PATTERNS:
                if pattern in key:
                    problems.append(
                        f"machine-specific key in tracked workspace settings: {key}"
                    )

    if problems:
        return 1, ["VERDICT=CONFIG_BAD"] + notes + problems
    return (
        0,
        ["VERDICT=CONFIG_OK pins=present settings=" + ",".join(str(p) for p in loaded)]
        + notes,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--workspace-settings", type=Path, default=None)
    args = parser.parse_args(argv)
    code, lines = check(args.home, args.workspace_settings)
    for line in lines:
        print(line)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
