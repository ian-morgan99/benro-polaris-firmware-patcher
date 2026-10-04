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


def test_next_version_is_derived_from_the_baseline(tmp_path):
    """The release path must be able to bump without a human typing a number."""
    state = tmp_path / "state.md"
    state.write_text("last_display_fwver=6.0.0.54.52\n", encoding="utf-8")
    derived = MOD.next_display_fwver(MOD.read_last_display_fwver(state))
    assert derived == (6, 0, 0, 54, 53)
    # A derived value is by construction acceptable to the validator.
    assert MOD.validate_monotonic(".".join(map(str, derived)), BASELINE) == derived


def test_recording_advances_the_baseline_so_versions_cannot_be_reused(tmp_path):
    """Recording is what stops two candidates reporting the same version."""
    state = tmp_path / "state.md"
    state.write_text(
        "prose above\n\n```text\nlast_display_fwver=6.0.0.54.52\n```\n\nprose below\n",
        encoding="utf-8",
    )
    MOD.record_display_fwver(state, "6.0.0.54.53")
    text = state.read_text(encoding="utf-8")
    assert "last_display_fwver=6.0.0.54.53" in text
    # Surrounding documentation is preserved, not rewritten.
    assert "prose above" in text and "prose below" in text
    # Re-offering the now-recorded version is rejected, as is the old one.
    with pytest.raises(ValueError):
        MOD.validate_monotonic("6.0.0.54.53", MOD.read_last_display_fwver(state))


def test_record_requires_an_existing_baseline_entry(tmp_path):
    state = tmp_path / "state.md"
    state.write_text("# no baseline here\n", encoding="utf-8")
    with pytest.raises(ValueError):
        MOD.record_display_fwver(state, "6.0.0.54.53")


def test_cli_next_prints_the_derived_version(tmp_path):
    import subprocess
    import sys

    state = tmp_path / "state.md"
    state.write_text("last_display_fwver=6.0.0.54.52\n", encoding="utf-8")
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--next", "--state", str(state)],
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, out.stdout + out.stderr
    assert out.stdout.strip() == "6.0.0.54.53"
    # --next must not mutate the baseline; only --record claims a version.
    assert MOD.read_last_display_fwver(state) == BASELINE
