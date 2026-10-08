"""Regression tests for scripts/check-agent-sandbox.py (issue #184).

The bug being guarded: the agent sandbox was enabled but every sandboxed
command failed to start (network.proxy requires slirp4netns, which was
missing), and the assistant silently degraded to running OUTSIDE the
sandbox. The checker must fail on BOTH shapes of that failure:

  * enabled + missing prerequisite  -> exit 2 BROKEN
  * policy disabled                -> exit 1 POLICY_DISABLED

and must not false-positive on a host with no VS Code settings (exit 77).
All cases run against fixture homes; nothing here depends on the host.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "check-agent-sandbox.py"
SPEC = importlib.util.spec_from_file_location("check_agent_sandbox", SCRIPT)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

SETTINGS_RELPATH = Path(".config/Code - Insiders/User/settings.json")


def make_home(tmp_path: Path, settings: dict | None) -> Path:
    home = tmp_path / "home"
    if settings is not None:
        target = home / SETTINGS_RELPATH
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(settings), encoding="utf-8")
    else:
        home.mkdir(parents=True, exist_ok=True)
    return home


def fake_which(present: tuple[str, ...]):
    return lambda name, *a, **k: f"/usr/bin/{name}" if name in present else None


@pytest.fixture()
def ok_sysctl(tmp_path: Path) -> Path:
    path = tmp_path / "userns"
    path.write_text("1\n", encoding="utf-8")
    return path


def test_enabled_with_all_prerequisites_is_ok(tmp_path, ok_sysctl):
    home = make_home(tmp_path, {"chat.agent.sandbox.enabled": "on"})
    code, line = MOD.verdict(
        home,
        None,
        which=fake_which(("bwrap", "slirp4netns")),
        sysctl_path=ok_sysctl,
    )
    assert code == 0
    assert "SANDBOX_OK" in line


def test_enabled_but_slirp4netns_missing_is_broken(tmp_path, ok_sysctl):
    """The exact 2026-10-07/08 regression: enabled, but no slirp4netns."""
    home = make_home(tmp_path, {"chat.agent.sandbox.enabled": "on"})
    code, line = MOD.verdict(
        home,
        None,
        which=fake_which(("bwrap",)),  # slirp4netns missing
        sysctl_path=ok_sysctl,
    )
    assert code == 2
    assert "BROKEN" in line
    assert "missing=slirp4netns" in line


def test_enabled_but_bwrap_missing_is_broken(tmp_path, ok_sysctl):
    home = make_home(tmp_path, {"chat.agent.sandbox.enabled": True})
    code, line = MOD.verdict(
        home,
        None,
        which=fake_which(("slirp4netns",)),
        sysctl_path=ok_sysctl,
    )
    assert code == 2
    assert "missing=bwrap" in line


def test_disabled_policy_is_flagged_not_silent(tmp_path, ok_sysctl):
    """Running everything outside the sandbox must be a verdict, not green."""
    home = make_home(tmp_path, {"chat.agent.sandbox.enabled": "off"})
    code, line = MOD.verdict(
        home,
        None,
        which=fake_which(("bwrap", "slirp4netns")),
        sysctl_path=ok_sysctl,
    )
    assert code == 1
    assert "POLICY_DISABLED" in line


def test_missing_key_counts_as_disabled(tmp_path, ok_sysctl):
    home = make_home(tmp_path, {"workbench.colorTheme": "Dark"})
    code, line = MOD.verdict(
        home,
        None,
        which=fake_which(("bwrap", "slirp4netns")),
        sysctl_path=ok_sysctl,
    )
    assert code == 1
    assert "POLICY_DISABLED" in line


def test_userns_disabled_is_broken(tmp_path):
    home = make_home(tmp_path, {"chat.agent.sandbox.enabled": "on"})
    sysctl = tmp_path / "userns"
    sysctl.write_text("0\n", encoding="utf-8")
    code, line = MOD.verdict(
        home,
        None,
        which=fake_which(("bwrap", "slirp4netns")),
        sysctl_path=sysctl,
    )
    assert code == 2
    assert "unprivileged_userns_clone=0" in line


def test_absent_sysctl_is_not_a_failure(tmp_path):
    """Modern kernels have no knob; userns is on. Do not false-positive."""
    home = make_home(tmp_path, {"chat.agent.sandbox.enabled": "on"})
    code, line = MOD.verdict(
        home,
        None,
        which=fake_which(("bwrap", "slirp4netns")),
        sysctl_path=tmp_path / "does-not-exist",
    )
    assert code == 0


def test_no_settings_is_prerequisite_skip(tmp_path):
    home = make_home(tmp_path, None)
    code, line = MOD.verdict(
        home,
        None,
        which=fake_which(("bwrap", "slirp4netns")),
        sysctl_path=tmp_path / "does-not-exist",
    )
    assert code == 77
    assert "NO_SETTINGS" in line


def test_workspace_settings_override_user(tmp_path, ok_sysctl):
    """Merge order matters: the workspace file is the last one applied."""
    home = make_home(tmp_path, {"chat.agent.sandbox.enabled": "on"})
    workspace = tmp_path / "ws" / ".vscode" / "settings.json"
    workspace.parent.mkdir(parents=True)
    workspace.write_text(
        json.dumps({"chat.agent.sandbox.enabled": "off"}), encoding="utf-8"
    )
    code, line = MOD.verdict(
        home,
        workspace,
        which=fake_which(("bwrap", "slirp4netns")),
        sysctl_path=ok_sysctl,
    )
    assert code == 1
    assert "POLICY_DISABLED" in line


def test_jsonc_comments_and_trailing_commas_are_tolerated(tmp_path, ok_sysctl):
    home = make_home(tmp_path, None)
    target = home / SETTINGS_RELPATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        """
        {
            // sandbox policy (Bubblewrap + network.proxy)
            "chat.agent.sandbox.enabled": "on", /* keep on */
            "unrelated": {"a": 1,},
        }
        """,
        encoding="utf-8",
    )
    code, line = MOD.verdict(
        home,
        None,
        which=fake_which(("bwrap", "slirp4netns")),
        sysctl_path=ok_sysctl,
    )
    assert code == 0
    assert "SANDBOX_OK" in line
