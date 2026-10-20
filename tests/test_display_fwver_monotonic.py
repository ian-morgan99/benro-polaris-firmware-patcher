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

# Commit identities used to exercise the version <-> commit-set binding.
LIBG_A = "a" * 40
LIBG_B = "b" * 40
PATCHER_A = "c" * 40
PATCHER_B = "d" * 40


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
         "--state", str(state), "--record",
         "--libgphoto2-commit", LIBG_A, "--patcher-commit", PATCHER_A],
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, out.stdout + out.stderr
    assert MOD.read_last_display_fwver(state) == (6, 0, 0, 54, 55)
    assert (6, 0, 0, 54, 55) in MOD.read_consumed_display_fwvers(state)
    assert MOD.read_version_commit_bindings(state) == {
        (6, 0, 0, 54, 55): (LIBG_A, PATCHER_A)
    }


# --- One version, one set of commits ----------------------------------------
#
# The consumed registry makes a version unique, which is only half of what the
# release needs. A version is a claim about a build, so uniqueness has to hold
# in both directions:
#
#   version    -> commit set   the same number never describes two builds
#   commit set -> version      the same build is never re-issued as new
#
# The second direction is the one that breaks silently: rebuilding an unchanged
# tree to "try again" would mint a fresh version for identical commits, and Benro
# Connect would report two firmwares that cannot behave differently. These tests
# pin both directions and the fail-closed behaviour around them.

STATE_WITH_BINDING = """\
```text
last_display_fwver=6.0.0.54.53
```

```text
consumed_display_fwver=6.0.0.54.53
consumed_display_fwver=6.0.0.54.54
version_commit_binding=6.0.0.54.54|libgphoto2=%s|patcher=%s
```
""" % (LIBG_A, PATCHER_A)


def test_binding_round_trips(tmp_path):
    bindings = MOD.read_version_commit_bindings(write_state(tmp_path, STATE_WITH_BINDING))
    assert bindings == {(6, 0, 0, 54, 54): (LIBG_A, PATCHER_A)}


def test_unbound_history_is_absent_rather_than_guessed(tmp_path):
    """A pre-binding version must not be invented into a commit set."""
    bindings = MOD.read_version_commit_bindings(write_state(tmp_path))
    assert bindings == {}


def test_malformed_binding_fails_closed(tmp_path):
    state = write_state(
        tmp_path,
        "consumed_display_fwver=6.0.0.54.53\n"
        "version_commit_binding=6.0.0.54.53|libgphoto2=abc\n",
    )
    with pytest.raises(ValueError, match="version_commit_binding"):
        MOD.read_version_commit_bindings(state)


def test_a_bound_version_cannot_describe_different_commits(tmp_path):
    state = write_state(tmp_path, STATE_WITH_BINDING)
    bindings = MOD.read_version_commit_bindings(state)
    with pytest.raises(ValueError, match="already bound"):
        MOD.validate_commit_set("6.0.0.54.54", (LIBG_B, PATCHER_A), bindings)


def test_the_same_commits_cannot_take_a_second_version(tmp_path):
    """The direction that breaks silently: a no-op rebuild must not consume one."""
    state = write_state(tmp_path, STATE_WITH_BINDING)
    bindings = MOD.read_version_commit_bindings(state)
    with pytest.raises(ValueError, match=r"already issued as 6\.0\.0\.54\.54"):
        MOD.validate_commit_set("6.0.0.54.55", (LIBG_A, PATCHER_A), bindings)


def test_rebinding_identical_commits_is_idempotent(tmp_path):
    """Re-validating an existing candidate must not be reported as a conflict."""
    state = write_state(tmp_path, STATE_WITH_BINDING)
    bindings = MOD.read_version_commit_bindings(state)
    MOD.validate_commit_set("6.0.0.54.54", (LIBG_A, PATCHER_A), bindings)


def test_different_commits_are_a_new_version(tmp_path):
    state = write_state(tmp_path, STATE_WITH_BINDING)
    bindings = MOD.read_version_commit_bindings(state)
    MOD.validate_commit_set("6.0.0.54.55", (LIBG_B, PATCHER_A), bindings)


def test_an_unknown_commit_cannot_be_bound(tmp_path):
    with pytest.raises(ValueError, match="unknown commit"):
        MOD.validate_commit_set("6.0.0.54.55", (LIBG_A, "unknown"), {})


def test_record_without_a_commit_set_is_refused(tmp_path):
    """A claim with no commit set would record a version that proves nothing."""
    state = write_state(tmp_path)
    import subprocess
    import sys

    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--candidate", "6.0.0.54.55",
         "--state", str(state), "--record"],
        capture_output=True,
        text=True,
    )
    assert out.returncode != 0
    assert "requires the commit set" in out.stderr
    assert (6, 0, 0, 54, 55) not in MOD.read_consumed_display_fwvers(state)


def test_a_partial_commit_set_is_refused(tmp_path):
    """Half a commit set cannot prove uniqueness in either direction."""
    state = write_state(tmp_path)
    import subprocess
    import sys

    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--candidate", "6.0.0.54.55",
         "--state", str(state), "--record", "--libgphoto2-commit", LIBG_A],
        capture_output=True,
        text=True,
    )
    assert out.returncode != 0
    assert "both --libgphoto2-commit and --patcher-commit" in out.stderr


def test_cli_refuses_to_reissue_the_same_commits(tmp_path):
    state = write_state(tmp_path, STATE_WITH_BINDING)
    import subprocess
    import sys

    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--candidate", "6.0.0.54.55",
         "--state", str(state), "--record",
         "--libgphoto2-commit", LIBG_A, "--patcher-commit", PATCHER_A],
        capture_output=True,
        text=True,
    )
    assert out.returncode != 0
    assert "already issued as 6.0.0.54.54" in out.stderr
    assert (6, 0, 0, 54, 55) not in MOD.read_consumed_display_fwvers(state)


def test_binding_is_appended_after_the_registry(tmp_path):
    state = write_state(tmp_path, STATE_WITH_BINDING)
    MOD.bind_display_fwver(state, "6.0.0.54.55", (LIBG_B, PATCHER_A))
    lines = state.read_text().splitlines()
    order = [i for i, line in enumerate(lines)
             if line.startswith("consumed_display_fwver=")
             or line.startswith("version_commit_binding=")]
    consumed_last = max(i for i, line in enumerate(lines)
                       if line.startswith("consumed_display_fwver="))
    assert all(i > consumed_last for i in order
               if lines[i].startswith("version_commit_binding="))
    assert MOD.read_version_commit_bindings(state) == {
        (6, 0, 0, 54, 54): (LIBG_A, PATCHER_A),
        (6, 0, 0, 54, 55): (LIBG_B, PATCHER_A),
    }


def test_binding_a_second_commit_set_to_one_version_is_refused(tmp_path):
    state = write_state(tmp_path, STATE_WITH_BINDING)
    with pytest.raises(ValueError, match="already bound"):
        MOD.bind_display_fwver(state, "6.0.0.54.54", (LIBG_B, PATCHER_B))


def test_rebinding_the_same_value_is_a_no_op(tmp_path):
    state = write_state(tmp_path, STATE_WITH_BINDING)
    before = state.read_text()
    MOD.bind_display_fwver(state, "6.0.0.54.54", (LIBG_A, PATCHER_A))
    assert state.read_text() == before


def test_malformed_binding_block_fails_the_whole_read(tmp_path):
    """A half-parsed binding must not let a duplicate version through."""
    state = write_state(
        tmp_path,
        "last_display_fwver=6.0.0.54.53\n"
        "consumed_display_fwver=6.0.0.54.53\n"
        "version_commit_binding=6.0.0.54.53|libgphoto2=zzz|patcher=%s\n" % PATCHER_A,
    )
    with pytest.raises(ValueError, match="version_commit_binding"):
        MOD.read_version_commit_bindings(state)


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


def test_committed_bindings_are_consistent_and_unique():
    """A binding in the shipped state must be readable and one-to-one.

    This is the gate for the invariant itself: one version may describe only one
    commit set, and one commit set may carry only one version. Both directions
    are checked against the real file, because a duplicate here means two builds
    would report the same version in Benro Connect, or an unchanged build would
    be re-issued as new.
    """
    repo_state = Path(__file__).parents[1] / "docs" / "RELEASE-VERSION-STATE.md"
    consumed = MOD.read_consumed_display_fwvers(repo_state)
    bindings = MOD.read_version_commit_bindings(repo_state)

    # A bound version must also be in the consumed registry; a binding alone
    # would let a number be re-used by the version check.
    for version in bindings:
        assert version in consumed, (
            f"bound version {'.'.join(map(str, version))} is not recorded as consumed"
        )

    # commit set -> version must be a function, not a one-to-many relation.
    seen: dict[tuple[str, str], tuple[int, ...]] = {}
    for version, commit_set in bindings.items():
        assert "unknown" not in commit_set, "a bound version may not cite unknown commits"
        prior = seen.get(commit_set)
        assert prior is None, (
            f"commit set {commit_set} is issued as both "
            f"{'.'.join(map(str, prior))} and {'.'.join(map(str, version))}"
        )
        seen[commit_set] = version
