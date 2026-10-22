"""Tests for scripts/capture-outcomes.py (#218).

The classifier exists because pgphoto logs every capture duration as negative, so a
sign-based reading reports successes as failures. These tests pin it to a real archived
log whose counts are independently known, and to synthetic fixtures for the cases that
log does not contain.
"""

import importlib.util
import os
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def load():
    path = ROOT / "scripts" / "capture-outcomes.py"
    spec = importlib.util.spec_from_file_location("capture_outcomes", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Independently counted with grep over the archived bundle: 8 `capture end` lines and
# 7 `ERROR: Could not capture image.` markers.
REAL_LOG = ROOT / "docs" / "evidence" / "bulb-session-20260930-0201" / "raw" / \
    "Clog_000180.log"


def test_real_log_matches_independently_counted_markers():
    mod = load()
    if not REAL_LOG.exists():
        # The archived bundle is not in every checkout; the synthetic tests below
        # still cover the logic, so this is a skip rather than a failure.
        return
    _records, summary = mod.classify([str(REAL_LOG)])
    assert summary["capture_end_lines"] == 8, summary
    assert summary["outcomes"]["FAIL"] + summary["outcomes"]["FAIL-UNMATCHED"] == 7, \
        summary
    # Every duration in this log is negative; a sign-based reading would call all
    # eight captures failures.
    assert summary["negative_logged_durations"] == 8, summary
    assert summary["outcomes"]["PASS"] == 5, summary


def test_negative_duration_alone_is_not_a_failure():
    mod = load()
    body = ("[01:00:00:000 INFO-]:capture_image[3164]:----capture end   -23398 ms\n"
            "[01:00:00:100 INFO-]:state:0;\n")
    with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as fh:
        fh.write(body)
        path = fh.name
    try:
        records, summary = mod.classify([path])
    finally:
        os.unlink(path)
    assert len(records) == 1
    assert records[0]["outcome"] == "PASS", records
    assert records[0]["logged_ms"] == -23398
    assert summary["outcomes"]["FAIL"] == 0


def test_failure_marker_before_capture_end_is_correlated():
    """The marker precedes its `capture end` line by ~135-160 lines on device.

    A forward-only window misses it entirely and every failure reads as a pass --
    the bug this script originally had when run over docs/evidence.
    """
    mod = load()
    body = ("[02:00:00:000 ERROR-]:ERROR: Could not capture image.\n"
            + "\n".join(f"[02:00:00:000 INFO-]:filler {i}" for i in range(200))
            + "\n[02:01:43:899 INFO-]:capture_image[3164]:----capture end   -66429 ms\n")
    with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as fh:
        fh.write(body)
        path = fh.name
    try:
        records, summary = mod.classify([path])
    finally:
        os.unlink(path)
    ends = [r for r in records if r["logged_ms"] is not None]
    assert len(ends) == 1
    assert ends[0]["outcome"] == "FAIL", ends
    assert summary["failures_total"] == 1, summary


def test_failure_marker_far_from_any_capture_end_is_not_dropped():
    mod = load()
    body = ("[02:00:00:000 ERROR-]:ERROR: Could not capture image.\n"
            + "\n".join(f"[02:00:00:000 INFO-]:filler {i}"
                        for i in range(mod.FAILURE_LOOKBACK_LINES + 50))
            + "\n[02:10:00:000 INFO-]:capture_image[3164]:----capture end   -100 ms\n")
    with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as fh:
        fh.write(body)
        path = fh.name
    try:
        records, summary = mod.classify([path])
    finally:
        os.unlink(path)
    # The distant marker is reported rather than silently discarded.
    assert summary["outcomes"]["FAIL-UNMATCHED"] == 1, summary
    assert summary["failures_total"] == 1, summary


def test_each_failure_marker_is_claimed_by_at_most_one_capture():
    mod = load()
    body = ("[02:00:00:000 ERROR-]:ERROR: Could not capture image.\n"
            "[02:00:01:000 INFO-]:capture_image[3164]:----capture end   -1000 ms\n"
            "[02:00:02:000 INFO-]:capture_image[3164]:----capture end   -2000 ms\n")
    with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as fh:
        fh.write(body)
        path = fh.name
    try:
        records, summary = mod.classify([path])
    finally:
        os.unlink(path)
    ends = [r for r in records if r["logged_ms"] is not None]
    assert [r["outcome"] for r in ends] == ["FAIL", "UNKNOWN"], ends
    assert summary["failures_total"] == 1, summary


def test_contradictory_evidence_is_surfaced_not_resolved():
    mod = load()
    body = ("[02:00:00:000 ERROR-]:ERROR: Could not capture image.\n"
            "[02:00:01:000 INFO-]:capture_image[3164]:----capture end   -66429 ms\n"
            "[02:00:01:100 INFO-]:SP_0151.jpg\n")
    with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as fh:
        fh.write(body)
        path = fh.name
    try:
        records, summary = mod.classify([path])
    finally:
        os.unlink(path)
    ends = [r for r in records if r["logged_ms"] is not None]
    assert ends[0]["outcome"] == "FAIL"
    assert ends[0]["file_produced"] == "SP_0151.jpg"
    assert ends[0]["contradictory_evidence"] is True
    assert summary["contradictory_failures"] == 1, summary


def test_markdown_summaries_are_not_parsed_as_logs():
    """docs/evidence is full of SUMMARY.md files quoting log lines as evidence."""
    mod = load()
    assert mod._looks_like_a_log("Clog_000180.log") is True
    assert mod._looks_like_a_log("Mlog_000178.log") is True
    assert mod._looks_like_a_log("SUMMARY.md") is False
    assert mod._looks_like_a_log("PRIOR-NOTES.md") is False


def test_over_report_factor_is_computed_against_real_failures():
    mod = load()
    body = ("[01:00:00:000 INFO-]:capture_image[3164]:----capture end   -100 ms\n"
            "[01:00:00:100 INFO-]:state:0;\n"
            "[01:00:01:000 ERROR-]:ERROR: Could not capture image.\n"
            "[01:00:02:000 INFO-]:capture_image[3164]:----capture end   -200 ms\n")
    with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as fh:
        fh.write(body)
        path = fh.name
    try:
        _records, summary = mod.classify([path])
    finally:
        os.unlink(path)
    assert summary["negative_logged_durations"] == 2
    assert summary["failures_total"] == 1
    assert summary["naive_sign_based_failure_count"] == 2
    assert summary["over_report_factor"] == 2.0, summary
