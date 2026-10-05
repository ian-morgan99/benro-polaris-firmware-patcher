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


# --- Issue #169: the consumed-version registry -------------------------------
#
# A monotonic baseline alone cannot detect a duplicate, because "this version
# was already issued" is information the baseline does not hold. When o-v15q was
# installed the baseline was left at `.53`, so `--next` re-offered `.54` - a
# version already running on hardware. These tests pin the registry as the
# primary defence and the baseline as a secondary one.

STATE_WITH_REGISTRY = """\
```text
last_display_fwver=6.0.0.54.53
```

```text
consumed_display_fwver=6.0.0.54.53
consumed_display_fwver=6.0.0.54.54
```
"""


def write_state(tmp_path, text=STATE_WITH_REGISTRY):
    state = tmp_path / "state.md"
    state.write_text(text, encoding="utf-8")
    return state


def test_registry_lists_every_issued_version(tmp_path):
    consumed = MOD.read_consumed_display_fwvers(write_state(tmp_path))
    assert consumed == {(6, 0, 0, 54, 53), (6, 0, 0, 54, 54)}


def test_malformed_registry_entry_fails_closed(tmp_path):
    state = write_state(tmp_path, "consumed_display_fwver=6.0.0.54\n")
    with pytest.raises(ValueError):
        MOD.read_consumed_display_fwvers(state)


def test_next_skips_consumed_versions_even_with_a_stale_baseline(tmp_path):
    """The exact #169 scenario: baseline `.53`, `.54` already on the device."""
    state = write_state(tmp_path)
    last = MOD.read_last_display_fwver(state)
    consumed = MOD.read_consumed_display_fwvers(state)
    assert last == (6, 0, 0, 54, 53)
    # Old behaviour returned `.54`, i.e. a duplicate of a live install.
    assert MOD.next_display_fwver(last, consumed) == (6, 0, 0, 54, 55)


def test_next_without_a_registry_still_bumps_the_baseline():
    assert MOD.next_display_fwver((6, 0, 0, 54, 52)) == (6, 0, 0, 54, 53)


def test_next_derives_from_the_registry_when_it_is_ahead_of_the_baseline(tmp_path):
    """A stale baseline must not pull the derived value back below the registry."""
    state = write_state(
        tmp_path,
        "last_display_fwver=6.0.0.54.50\n"
        "consumed_display_fwver=6.0.0.54.53\n"
        "consumed_display_fwver=6.0.0.54.54\n",
    )
    last = MOD.read_last_display_fwver(state)
    consumed = MOD.read_consumed_display_fwvers(state)
    assert MOD.next_display_fwver(last, consumed) == (6, 0, 0, 54, 55)


def test_next_rejects_a_registry_spanning_two_families(tmp_path):
    state = write_state(
        tmp_path,
        "last_display_fwver=6.0.0.54.50\nconsumed_display_fwver=6.0.0.55.51\n",
    )
    last = MOD.read_last_display_fwver(state)
    consumed = MOD.read_consumed_display_fwvers(state)
    with pytest.raises(ValueError):
        MOD.next_display_fwver(last, consumed)


def test_validator_refuses_a_consumed_version_the_baseline_does_not_know_about(
    tmp_path,
):
    """The registry check must be independent of the baseline comparison."""
    state = write_state(tmp_path, "last_display_fwver=6.0.0.54.50\n"
                                  "consumed_display_fwver=6.0.0.54.53\n")
    last = MOD.read_last_display_fwver(state)
    consumed = MOD.read_consumed_display_fwvers(state)
    # `.53` is above the stale baseline, so only the registry can reject it.
    assert MOD.validate_monotonic("6.0.0.54.53", last) == (6, 0, 0, 54, 53)
    with pytest.raises(ValueError):
        MOD.validate_monotonic("6.0.0.54.53", last, consumed)
    # An unissued version above the baseline is still accepted.
    assert MOD.validate_monotonic("6.0.0.54.54", last, consumed) == (6, 0, 0, 54, 54)


def test_claim_appends_to_the_registry_and_refuses_reuse(tmp_path):
    state = write_state(tmp_path)
    MOD.claim_display_fwver(state, "6.0.0.54.55")
    text = state.read_text(encoding="utf-8")
    assert "consumed_display_fwver=6.0.0.54.55" in text
    # Append-only: earlier entries survive.
    assert "consumed_display_fwver=6.0.0.54.53" in text
    assert "consumed_display_fwver=6.0.0.54.54" in text
    with pytest.raises(ValueError):
        MOD.claim_display_fwver(state, "6.0.0.54.55")


def test_claim_requires_a_registry_block(tmp_path):
    state = write_state(tmp_path, "last_display_fwver=6.0.0.54.52\n")
    with pytest.raises(ValueError):
        MOD.claim_display_fwver(state, "6.0.0.54.53")


def test_record_advances_baseline_and_registry_together(tmp_path):
    """A release must not be able to update one and forget the other."""
    state = write_state(tmp_path)
    import subprocess
    import sys

    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--candidate", "6.0.0.54.55",
         "--state", str(state), "--record"],
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, out.stdout + out.stderr
    assert MOD.read_last_display_fwver(state) == (6, 0, 0, 54, 55)
    assert (6, 0, 0, 54, 55) in MOD.read_consumed_display_fwvers(state)


def test_cli_next_honours_the_registry(tmp_path):
    import subprocess
    import sys

    state = write_state(tmp_path)
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--next", "--state", str(state)],
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, out.stdout + out.stderr
    assert out.stdout.strip() == "6.0.0.54.55"
    # --next still must not mutate anything.
    assert MOD.read_last_display_fwver(state) == (6, 0, 0, 54, 53)
    assert (6, 0, 0, 54, 55) not in MOD.read_consumed_display_fwvers(state)


def test_committed_state_file_is_self_consistent():
    """The shipped registry must cover the shipped baseline."""
    repo_state = Path(__file__).parents[1] / "docs" / "RELEASE-VERSION-STATE.md"
    last = MOD.read_last_display_fwver(repo_state)
    consumed = MOD.read_consumed_display_fwvers(repo_state)
    assert last in consumed, "baseline version must be recorded as consumed"
    derived = MOD.next_display_fwver(last, consumed)
    assert derived not in consumed
    assert derived > last
