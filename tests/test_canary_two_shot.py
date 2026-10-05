import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "canary-two-shot.py"
SPEC = importlib.util.spec_from_file_location("canary_two_shot", SCRIPT)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class FakePolaris:
    def __init__(self, frames):
        self.frames = iter(frames)
        self.sends = []

    def send(self, *args, **kwargs):
        self.sends.append((args, kwargs))

    def frame(self, deadline):
        try:
            return next(self.frames)
        except StopIteration:
            raise TimeoutError("test exhausted")


def test_raw_jpeg_event_order_waits_for_both_outputs_and_idle():
    frames = [
        (264, "state:1;"),
        (264, "state:4;"),
        (773, "path:/app/sd/normal/SP_0085.dng;"),
        (773, "path:/app/sd/normal/SP_0085.jpg;"),
        (264, "state:0;"),
    ]
    rec = MOD.run_shot(FakePolaris(frames), 1, [], 1.0, 2,
                       "/app/sd/normal/SP_", "test-run")
    assert rec["states"] == [1, 4, 0]
    assert rec["idle_confirmed"]
    assert rec["terminal_failure"] is None
    assert MOD.shot_satisfied(rec, [], 2, "/app/sd/normal/SP_")


def test_file_after_completion_state_is_not_lost():
    frames = [
        (264, "state:4;"),
        (773, "path:/app/sd/normal/SP_0086.jpg;"),
        (264, "state:0;"),
    ]
    rec = MOD.run_shot(FakePolaris(frames), 1, [], 1.0, 1,
                       "/app/sd/normal/SP_", "test-run")
    assert MOD.shot_satisfied(rec, [], 1, "/app/sd/normal/SP_")


def test_photo_format_hint_cannot_override_explicit_raw_only_obligation():
    """Regression for #155: photoFormat:2 may coexist with one authoritative DNG."""
    frames = [
        (264, "state:4;"),
        (773, "path:/app/sd/normal/SP_RAW_ONLY.dng;"),
        (264, "state:0;"),
    ]
    rec = MOD.run_shot(FakePolaris(frames), 1, [], 1.0,
                       expected_files=1, expected_sp_prefix="/app/sd/normal/SP_",
                       run_id="test-run")
    assert MOD.shot_satisfied(rec, [], 1, "/app/sd/normal/SP_")


def test_raw_jpeg_companions_must_share_exposure_stem():
    rec = {
        "states": [1, 4, 0],
        "files": ["/x/SP_1.dng", "/x/SP_2.jpg"],
    }
    assert not MOD.shot_satisfied(rec, [], 2, "/app/sd/normal/SP_")


def test_stale_file_fails_closed():
    path = "/x/SP_1.jpg"
    frames = [(264, "state:4;"), (773, f"path:{path};"), (264, "state:0;")]
    rec = MOD.run_shot(FakePolaris(frames), 2, [path], 1.0, 1,
                       "/x/SP_", "test-run")
    assert rec["stale_candidate"] == path
    assert rec["terminal_failure"].startswith("timeout:")


def test_terminal_failure_exhausts_budget_without_retry_or_second_shutter():
    p = FakePolaris([(264, "state:1;"), (264, "state:-1005;")])
    ok, records, paths = MOD.run_sequence(
        p, 2, 1.0, 1, "/app/sd/normal/SP_", "test-run")
    capture_sends = [call for call in p.sends if call[0][0] == 264]
    assert not ok
    assert len(records) == 1
    assert records[0]["terminal_failure"] == "state:-1005"
    assert paths == []
    assert len(capture_sends) == 1


def test_timeout_exhausts_budget_without_retry_or_second_shutter():
    p = FakePolaris([])
    ok, records, paths = MOD.run_sequence(
        p, 2, 1.0, 1, "/app/sd/normal/SP_", "test-run")
    capture_sends = [call for call in p.sends if call[0][0] == 264]
    assert not ok
    assert len(records) == 1
    assert records[0]["terminal_failure"].startswith("timeout:")
    assert paths == []
    assert len(capture_sends) == 1


def test_wrong_sp_target_invalidates_capture_result():
    rec = {
        "states": [1, 4, 0],
        "files": ["/app/sd/astro/SP_0123.jpg"],
    }
    assert not MOD.shot_satisfied(rec, [], 1, "/app/sd/normal/SP_")


def good_shot(shot_no: int) -> list[tuple[int, str]]:
    return [
        (264, "state:1;"),
        (264, "state:4;"),
        (773, f"path:/app/sd/normal/SP_02{shot_no:02d}.jpg;"),
        (264, "state:0;"),
    ]


def test_sequence_runs_every_requested_shot_in_one_session():
    """The #175 acceptance shape: N captures, no reconnect between them."""
    frames = [frame for shot in (1, 2, 3, 4, 5) for frame in good_shot(shot)]
    p = FakePolaris(frames)
    ok, records, paths = MOD.run_sequence(
        p, shot_count=5, shot_timeout=1.0, expected_files=1,
        expected_sp_prefix="/app/sd/normal/SP_", run_id="orphan-accept")
    assert ok
    assert len(records) == 5
    assert len(paths) == 5
    # One session means one socket: every capture is issued to the same handle,
    # so a latch that only appears on the second request cannot hide.
    assert sum(1 for args, _ in p.sends if args and args[0] == 264) == 5


def test_sequence_stops_at_the_shot_that_latches():
    """A -1005 on the third shot must fail the run, not be retried away."""
    frames = [
        *good_shot(1),
        *good_shot(2),
        (264, "state:1;"),
        (264, "state:-1005;"),
    ]
    p = FakePolaris(frames)
    ok, records, paths = MOD.run_sequence(
        p, shot_count=5, shot_timeout=1.0, expected_files=1,
        expected_sp_prefix="/app/sd/normal/SP_", run_id="orphan-latch")
    assert not ok
    assert len(records) == 3
    assert records[2]["terminal_failure"] == "state:-1005"
    assert len(paths) == 2
    # Fail-closed: no fourth shutter is issued after the latch.
    assert sum(1 for args, _ in p.sends if args and args[0] == 264) == 3


def test_a_repeated_path_is_a_stale_candidate_not_a_new_output():
    """The orphan signature: the camera reports the previous shot's file."""
    first = "/app/sd/normal/SP_0201.jpg"
    frames = [
        *good_shot(1),
        (264, "state:1;"),
        (264, "state:4;"),
        (773, f"path:{first};"),
        (264, "state:0;"),
    ]
    p = FakePolaris(frames)
    ok, records, paths = MOD.run_sequence(
        p, shot_count=2, shot_timeout=1.0, expected_files=1,
        expected_sp_prefix="/app/sd/normal/SP_", run_id="orphan-stale")
    assert not ok
    assert records[1]["stale_candidate"] == first
    assert len(paths) == 1
