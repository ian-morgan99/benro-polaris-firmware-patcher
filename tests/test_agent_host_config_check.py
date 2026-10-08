"""Regression tests for scripts/check-agent-host-config.py (issue #185).

The contract being guarded: model selection must stay deterministic whether
chat.experimentalModelPicker is false (today's opt-out) or true (the
adopted-product scenario). The guard is explicit pinning of the utility,
plan-agent and LM Studio default models — never the opt-out itself. The
checker therefore accepts the picker key at ANY value, and fails only when
a pin is missing/empty or the tracked workspace settings carry machine
identity (the 5fdc174 review rule). All cases run against fixture homes;
nothing here depends on the host.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "check-agent-host-config.py"
SPEC = importlib.util.spec_from_file_location("check_agent_host_config", SCRIPT)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

SETTINGS_RELPATH = Path(".config/Code - Insiders/User/settings.json")

GOOD_PINS = {
    "chat.byokUtilityModelDefault": "mainAgent",
    "chat.planAgent.defaultModel": "Some Pinned Model",
    "lmstudio.defaultModelId": "some-local-model",
}


def make_home(tmp_path: Path, settings: dict | None) -> Path:
    home = tmp_path / "home"
    if settings is not None:
        target = home / SETTINGS_RELPATH
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(settings), encoding="utf-8")
    else:
        home.mkdir(parents=True, exist_ok=True)
    return home


def make_workspace(tmp_path: Path, settings: dict | None) -> Path | None:
    if settings is None:
        return None
    workspace = tmp_path / "ws" / ".vscode" / "settings.json"
    workspace.parent.mkdir(parents=True, exist_ok=True)
    workspace.write_text(json.dumps(settings), encoding="utf-8")
    return workspace


def test_picker_false_with_pins_is_ok(tmp_path):
    home = make_home(tmp_path, {**GOOD_PINS, "chat.experimentalModelPicker": False})
    code, lines = MOD.check(home, None)
    assert code == 0
    assert any("CONFIG_OK" in line for line in lines)


def test_picker_true_with_pins_is_still_ok(tmp_path):
    """The adopted-product scenario: picker default true must not break us."""
    home = make_home(tmp_path, {**GOOD_PINS, "chat.experimentalModelPicker": True})
    code, lines = MOD.check(home, None)
    assert code == 0
    assert any("CONFIG_OK" in line for line in lines)
    assert any("chat.experimentalModelPicker=True" in line for line in lines)


def test_picker_unset_with_pins_is_ok(tmp_path):
    home = make_home(tmp_path, dict(GOOD_PINS))
    code, _ = MOD.check(home, None)
    assert code == 0


@pytest.mark.parametrize("drop", sorted(GOOD_PINS))
def test_missing_pin_fails_even_with_opt_out(tmp_path, drop):
    """Opt-out alone is not the guard: a dropped pin fails with picker false."""
    pins = {k: v for k, v in GOOD_PINS.items() if k != drop}
    home = make_home(tmp_path, {**pins, "chat.experimentalModelPicker": False})
    code, lines = MOD.check(home, None)
    assert code == 1
    assert any(drop in line for line in lines)


def test_empty_pin_string_fails(tmp_path):
    pins = dict(GOOD_PINS)
    pins["lmstudio.defaultModelId"] = "   "
    home = make_home(tmp_path, pins)
    code, lines = MOD.check(home, None)
    assert code == 1
    assert any("lmstudio.defaultModelId" in line for line in lines)


def test_machine_specific_key_in_workspace_settings_fails(tmp_path):
    home = make_home(tmp_path, GOOD_PINS)
    workspace = make_workspace(
        tmp_path, {"lmstudio.baseUrl": "http://localhost:8080"}
    )
    code, lines = MOD.check(home, workspace)
    assert code == 1
    assert any("machine-specific" in line for line in lines)


def test_repo_generic_workspace_settings_pass(tmp_path):
    home = make_home(tmp_path, GOOD_PINS)
    workspace = make_workspace(
        tmp_path,
        {
            "chat.experimentalModelPicker": False,
            "files.watcherExclude": {"**/.git/objects/**": True},
        },
    )
    code, _ = MOD.check(home, workspace)
    assert code == 0


def test_no_user_settings_is_prerequisite_skip(tmp_path):
    home = make_home(tmp_path, None)
    code, lines = MOD.check(home, None)
    assert code == 77
    assert any("NO_SETTINGS" in line for line in lines)


def test_workspace_pin_satisfies_the_contract(tmp_path):
    """Pins may live in either file; the merged view is what counts."""
    home = make_home(tmp_path, {"chat.byokUtilityModelDefault": "mainAgent"})
    workspace = make_workspace(
        tmp_path,
        {
            "chat.planAgent.defaultModel": "Some Pinned Model",
            "lmstudio.defaultModelId": "some-local-model",
        },
    )
    code, _ = MOD.check(home, workspace)
    assert code == 0
