"""Tests for scripts/qualification-verdict.py (#203).

These exist because the previous runner's verdict was assembled by grepping
strings and could print DONE after failures. The decision logic is now code, so
the ways a round can be wrongly called qualified are pinned here.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "qualification-verdict.py"


def load():
    spec = importlib.util.spec_from_file_location("qual_verdict", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = load()


def case(name="timed6s", **over):
    base = {
        "case": name,
        "status": "pass",
        "rc": 0,
        "expected_files": 1,
        "files": ["/app/sd/normal/SP_0001.dng"],
        "mode_before": "1",
        "mode_after": "1",
    }
    base.update(over)
    return base


# --- happy path -------------------------------------------------------------

def test_clean_round_qualifies():
    code, problems, _ = mod.evaluate([case(), case("bulb40s")])
    assert code == 0 and problems == []


def test_empty_round_is_blocked_not_green():
    code, problems, _ = mod.evaluate([])
    assert code == 1
    assert any("BLOCKED" in p for p in problems)


# --- exit-code enforcement --------------------------------------------------

def test_pass_with_nonzero_rc_is_a_failure():
    code, problems, _ = mod.evaluate([case(rc=1)])
    assert code == 1
    assert any("exited 1" in p for p in problems)


def test_pass_without_rc_is_a_failure():
    code, problems, _ = mod.evaluate([case(rc=None)])
    assert code == 1
    assert any("without a probe exit code" in p for p in problems)


# --- output obligation ------------------------------------------------------

def test_pass_below_output_obligation_fails():
    code, problems, _ = mod.evaluate([case(expected_files=2, files=["a.dng"])])
    assert code == 1
    assert any("1 correlated file" in p for p in problems)


def test_missing_obligation_fails():
    code, problems, _ = mod.evaluate([case(expected_files=None)])
    assert code == 1
    assert any("photoFormat is not authoritative" in p for p in problems)


def test_unattributed_card_file_fails():
    # The card gained a file the probe never reported. The round cannot claim to
    # know what produced it, so it is not qualification evidence (#203).
    code, problems, _ = mod.evaluate(
        [case(unattributed_files=["/app/sd/normal/SP_0002.dng"])])
    assert code == 1
    assert any("not attributed" in p for p in problems)
    assert any("SP_0002.dng" in p for p in problems)


def test_no_unattributed_files_is_clean():
    code, problems, _ = mod.evaluate([case(unattributed_files=[])])
    assert code == 0 and problems == []


# --- exposure claim ---------------------------------------------------------

def test_exposure_claim_without_exif_is_unsupported():
    code, problems, _ = mod.evaluate([case(expected_exposure_s=6.0)])
    assert code == 1
    assert any("unsupported" in p for p in problems)


def test_exposure_claim_mismatch_fails():
    code, problems, _ = mod.evaluate(
        [case(expected_exposure_s=6.0, actual_exposure_s=8.0)])
    assert code == 1
    assert any("EXIF says 8s" in p for p in problems)


def test_exposure_within_tolerance_passes():
    code, problems, _ = mod.evaluate(
        [case(expected_exposure_s=6.0, actual_exposure_s=6.02)])
    assert code == 0 and problems == []


# --- mode verification ------------------------------------------------------

def test_pass_without_verified_mode_fails():
    code, problems, _ = mod.evaluate([case(mode_before=None)])
    assert code == 1
    assert any("exposure mode" in p for p in problems)


def test_mode_drift_is_noted_not_fatal():
    code, _, notes = mod.evaluate([case(mode_after="9")])
    assert code == 0
    assert any("drifted" in n for n in notes)


# --- skips ------------------------------------------------------------------

def test_skip_with_reason_qualifies_with_gaps():
    code, problems, notes = mod.evaluate([case(), case("bulb40s", status="skip",
                                                     reason="no 00-40 slot")])
    assert code == 2 and problems == []
    # evaluate() reports the gap per case; the round-level "WITH GAPS" summary
    # line belongs to main(), asserted by test_cli_exit_two_on_gaps.
    assert any("SKIP bulb40s: no 00-40 slot" in n for n in notes)


def test_cli_summary_distinguishes_gaps_from_clean():
    clean = run_cli([case()])
    gaps = run_cli([case(), case("x", status="skip", reason="slot absent")])
    assert "QUALIFIED —" in clean.stdout and "GAPS" not in clean.stdout
    assert "QUALIFIED WITH GAPS" in gaps.stdout
    assert "the skipped cases are NOT qualified" in gaps.stdout


def test_skip_without_reason_is_a_problem():
    code, problems, _ = mod.evaluate([case("bulb40s", status="skip")])
    assert code == 1
    assert any("machine-evaluated reason" in p for p in problems)


def test_all_skipped_is_blocked():
    code, problems, _ = mod.evaluate(
        [case("a", status="skip", reason="x"), case("b", status="skip", reason="y")])
    assert code == 1
    assert any("BLOCKED" in p for p in problems)


# --- failures ---------------------------------------------------------------

def test_fail_and_error_are_fatal():
    code, problems, _ = mod.evaluate([
        case(),
        case("timed40s", status="fail", verdict="no-file"),
        case("bulb90s", status="error", reason="probe crashed"),
    ])
    assert code == 1
    assert any("no-file" in p for p in problems)
    assert any("probe crashed" in p for p in problems)


def test_duplicate_case_is_rejected():
    code, problems, _ = mod.evaluate([case(), case()])
    assert code == 1
    assert any("recorded twice" in p for p in problems)


def test_unrecognised_status_is_fatal():
    code, problems, _ = mod.evaluate([case(status="maybe")])
    assert code == 1
    assert any("unrecognised status" in p for p in problems)


# --- CLI contract -----------------------------------------------------------

def run_cli(lines):
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input="\n".join(json.dumps(x) for x in lines),
        capture_output=True, text=True,
    )


def test_cli_exit_zero_on_clean_round():
    proc = run_cli([case()])
    assert proc.returncode == 0, proc.stdout
    assert "QUALIFIED —" in proc.stdout


def test_cli_exit_one_when_a_case_failed():
    proc = run_cli([case(), case("bulb40s", status="fail", verdict="no-file")])
    assert proc.returncode == 1
    assert "NOT QUALIFIED" in proc.stdout


def test_cli_exit_two_on_gaps():
    proc = run_cli([case(), case("x", status="skip", reason="slot absent")])
    assert proc.returncode == 2
    assert "QUALIFIED WITH GAPS" in proc.stdout


def test_cli_rejects_unparseable_line():
    proc = subprocess.run([sys.executable, str(SCRIPT)], input="not json\n",
                          capture_output=True, text=True)
    assert proc.returncode == 1
    assert "unparseable" in proc.stdout
