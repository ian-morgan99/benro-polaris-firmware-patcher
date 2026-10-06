import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "assert-orphan-wrote.py"
SPEC = importlib.util.spec_from_file_location("assert_orphan_wrote", SCRIPT)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


# Exactly the shape camlibs/ptp2/library.c emits from pentax_recover_orphan_
# candidates (the `wrote=` suffix is conditional on a save having happened).
AUDIT_LINE = (
    "[pentax-recovery] capture=3794 path=orphan-recovery outcome=cleared "
    "recovered=1 names=IMGP3794.DNG accepted=1 "
    "action=preserve-then-delete-only-after-verified-download "
    "wrote=/app/sd/pentax-recovered/IMGP3794-orphan-3794.dng"
)


def test_parses_the_wrote_path_from_a_real_audit_line():
    assert MOD.parse_wrote_paths(AUDIT_LINE) == [
        "/app/sd/pentax-recovered/IMGP3794-orphan-3794.dng"
    ]


def test_no_wrote_suffix_is_not_a_claim():
    line = AUDIT_LINE.split(" wrote=")[0]
    assert MOD.parse_wrote_paths(line) == []


def test_multiple_claims_keep_order_and_drop_duplicates():
    a = "/app/sd/pentax-recovered/IMGP3794-orphan-3794.dng"
    b = "/app/sd/pentax-recovered/IMGP3795-orphan-3795.dng"
    text = f"x wrote={a}\ny wrote={b}\nz wrote={a}\n"
    assert MOD.parse_wrote_paths(text) == [a, b]


def test_relative_or_truncated_path_is_not_trusted_as_a_claim():
    # A truncated record can leave a fragment; only absolute paths are assertable.
    assert MOD.parse_wrote_paths("wrote=IMGP3794.dng wrote= wrote=rel/x.dng") == []


def test_a_real_nonempty_file_passes():
    expected = ["/app/sd/pentax-recovered/IMGP3794-orphan-3794.dng"]
    report = f"{expected[0]}|ok|38214400"
    assert MOD.evaluate_report(report, expected) == []


def test_a_missing_file_fails_the_assertion():
    """The #175 defect: the log claimed a write, the card has no file."""
    expected = ["/app/sd/pentax-recovered/IMGP3794-orphan-3794.dng"]
    report = f"{expected[0]}|missing|0"
    failures = MOD.evaluate_report(report, expected)
    assert len(failures) == 1 and "missing" in failures[0]


def test_a_zero_length_file_fails_the_assertion():
    """A save that returned GP_OK but wrote no bytes is the same loss."""
    expected = ["/app/sd/pentax-recovered/IMGP3794-orphan-3794.dng"]
    report = f"{expected[0]}|ok|0"
    failures = MOD.evaluate_report(report, expected)
    assert len(failures) == 1 and "zero-length" in failures[0]


def test_a_silent_device_fails_closed():
    """No report line must never be read as success."""
    expected = ["/app/sd/pentax-recovered/IMGP3794-orphan-3794.dng"]
    failures = MOD.evaluate_report("", expected)
    assert len(failures) == 1 and "no report line" in failures[0]


def test_nothing_claimed_nothing_to_assert():
    assert MOD.evaluate_report("", []) == []


def test_check_command_quotes_paths_and_reports_size():
    cmd = MOD.build_check_command(["/app/sd/it's here.dng", "/app/sd/b.dng"])
    assert "'/app/sd/it'\"'\"'s here.dng'" in cmd
    assert "/app/sd/b.dng" in cmd
    assert "-e" in cmd  # presence decides ok/missing; size is reported alongside


def test_local_report_maps_device_paths_under_root(tmp_path):
    real = tmp_path / "app" / "sd" / "pentax-recovered"
    real.mkdir(parents=True)
    (real / "IMGP3794-orphan-3794.dng").write_bytes(b"x" * 123)
    (real / "empty.dng").write_bytes(b"")
    report = MOD.local_report(str(tmp_path), [
        "/app/sd/pentax-recovered/IMGP3794-orphan-3794.dng",
        "/app/sd/pentax-recovered/empty.dng",
        "/app/sd/pentax-recovered/absent.dng",
    ])
    lines = dict(l.split("|", 1) for l in report.splitlines())
    assert lines["/app/sd/pentax-recovered/IMGP3794-orphan-3794.dng"] == "ok|123"
    # present-but-empty is reported truthfully; evaluate_report() is what fails it
    assert lines["/app/sd/pentax-recovered/empty.dng"] == "ok|0"
    assert lines["/app/sd/pentax-recovered/absent.dng"] == "missing|0"
