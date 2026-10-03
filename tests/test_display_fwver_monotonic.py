from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "verify_display_fwver_monotonic.py"
SPEC = importlib.util.spec_from_file_location("verify_display_fwver_monotonic", SCRIPT)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


BASELINE = (6, 0, 0, 54, 52)


def test_next_display_version_is_accepted():
    assert MOD.validate_monotonic("6.0.0.54.53", BASELINE) == (6, 0, 0, 54, 53)


@pytest.mark.parametrize(
    "candidate",
    [
        "6.0.0.54.52",  # reusing the installed version
        "6.0.0.54.51",  # going backwards
        "6.0.0.53.53",  # changing the firmware family
        "6.0.0.54",  # silently dropping the build component
        "6.0.0.54.053",  # non-canonical spelling
        "6.0.0.54.53-extra",  # build metadata must not reach code 780
    ],
)
def test_bad_display_versions_are_rejected(candidate):
    with pytest.raises(ValueError):
        MOD.validate_monotonic(candidate, BASELINE)


def test_state_file_is_read_from_the_committed_release_baseline(tmp_path):
    state = tmp_path / "state.md"
    state.write_text("last_display_fwver=6.0.0.54.52\n", encoding="utf-8")
    assert MOD.read_last_display_fwver(state) == BASELINE


def test_malformed_state_fails_closed(tmp_path):
    state = tmp_path / "state.md"
    state.write_text("last_display_fwver=8.0.0.76\n", encoding="utf-8")
    with pytest.raises(ValueError):
        MOD.read_last_display_fwver(state)
