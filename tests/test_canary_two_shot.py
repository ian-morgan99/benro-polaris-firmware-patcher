import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "canary-two-shot.py"
SPEC = importlib.util.spec_from_file_location("canary_two_shot", SCRIPT)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class FakePolaris:
    def __init__(self, frames):
        self.frames = iter(frames)

    def send(self, *args, **kwargs):
        pass

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
    rec = MOD.run_shot(FakePolaris(frames), 1, [], 1.0, 2)
    assert rec["states"] == [1, 4, 0]
    assert rec["idle_confirmed"]
    assert rec["terminal_failure"] is None
    assert MOD.shot_satisfied(rec, [], 2)


def test_file_after_completion_state_is_not_lost():
    frames = [
        (264, "state:4;"),
        (773, "path:/app/sd/normal/SP_0086.jpg;"),
        (264, "state:0;"),
    ]
    rec = MOD.run_shot(FakePolaris(frames), 1, [], 1.0, 1)
    assert MOD.shot_satisfied(rec, [], 1)


def test_raw_jpeg_companions_must_share_exposure_stem():
    rec = {
        "states": [1, 4, 0],
        "files": ["/x/SP_1.dng", "/x/SP_2.jpg"],
    }
    assert not MOD.shot_satisfied(rec, [], 2)


def test_stale_file_fails_closed():
    path = "/x/SP_1.jpg"
    frames = [(264, "state:4;"), (773, f"path:{path};"), (264, "state:0;")]
    rec = MOD.run_shot(FakePolaris(frames), 2, [path], 1.0, 1)
    assert rec["stale_candidate"] == path
    assert rec["terminal_failure"].startswith("timeout:")
