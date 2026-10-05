"""Data-driven offline regression coverage for the Bulb capture matrix.

These tests exercise the same lifecycle and output-obligation code used by the
live canary scripts.  They do not claim that a camera physically captured an
image: every matrix row remains a live qualification precondition.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CANARY = _load("bulb_variations_canary", "scripts/canary-two-shot.py")
ASTRO = _load("bulb_variations_astro", "scripts/test-astro-multishot.py")
PROBE = _load("bulb_variations_probe", "scripts/canary-probe.py")


def _matrix() -> dict[str, Any]:
    return json.loads(
        (ROOT / "tests/pentax_bulb_variation_matrix.json").read_text(
            encoding="utf-8"
        )
    )


def _cases() -> list[dict[str, Any]]:
    matrix = _matrix()
    cases: list[dict[str, Any]] = []
    for camera in matrix["cameras"]:
        for mode in matrix["modes"]:
            for fmt in matrix["formats"]:
                for shots in mode["shot_counts"]:
                    for seconds in matrix["bulb_seconds"]:
                        cases.append(
                            {
                                "camera": camera,
                                "mode": mode["id"],
                                "prefix": mode["output_prefix"],
                                "runner": mode["runner"],
                                "format": fmt["id"],
                                "expected_files": fmt["expected_files"],
                                "suffixes": fmt["suffixes"],
                                "shots": shots,
                                "seconds": seconds,
                            }
                        )
    return cases


class FakePolaris:
    def __init__(self, frames):
        self.frames = iter(frames)
        self.sends: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def send(self, *args, **kwargs):
        self.sends.append((args, kwargs))

    def frame(self, _deadline):
        try:
            return next(self.frames)
        except StopIteration as exc:
            raise TimeoutError("test exhausted") from exc

    def wait_code(self, wanted, _timeout):
        code, payload = self.frame(0)
        assert code == wanted
        return payload


def _frames(case: dict[str, Any]):
    frames = []
    for shot in range(1, case["shots"] + 1):
        stem = f"{case['prefix']}BULB_{shot:04d}"
        frames.extend(
            [
                (264, "state:1;"),
                (264, "state:4;"),
            ]
        )
        for suffix in case["suffixes"]:
            frames.append((773, f"path:{stem}{suffix};"))
        frames.append((264, "state:0;"))
    return frames


def _case_id(case: dict[str, Any]) -> str:
    return (
        f"{case['camera']}-{case['mode']}-{case['format']}-"
        f"{case['shots']}shot-{case['seconds']}s"
    )


def test_matrix_is_complete_and_explicit():
    matrix = _matrix()
    assert matrix["physical_status"].startswith("contract-only:")
    assert set(matrix["cameras"]) == {"K-3 III", "K-1 II"}
    assert {mode["id"] for mode in matrix["modes"]} == {"manual", "astro"}
    assert {fmt["id"] for fmt in matrix["formats"]} == {
        "raw",
        "jpeg",
        "raw+jpeg",
    }
    assert {fmt["expected_files"] for fmt in matrix["formats"]} == {1, 2}
    assert set(matrix["bulb_seconds"]) == {4, 60, 70}
    for mode in matrix["modes"]:
        assert mode["output_prefix"].endswith("/SP_")
        assert mode["shot_counts"]
        assert mode["runner"] in {"canary-two-shot", "test-astro-multishot"}

    # 2 cameras x 2 modes x 3 output contracts x (2+3) sequence lengths
    # x 3 durations.  This fails if a variation is silently dropped.
    assert len(_cases()) == 90


@pytest.mark.parametrize("case", _cases(), ids=_case_id)
def test_each_bulb_variation_has_a_fail_closed_lifecycle(case):
    """Exercise RAW, JPEG, RAW+JPEG, Manual, Astro, and sequence lengths."""
    device = FakePolaris(_frames(case))
    seen: set[str] = set()

    if case["runner"] == "canary-two-shot":
        if case["shots"] == 1:
            record = CANARY.run_shot(
                device,
                1,
                [],
                1.0,
                case["expected_files"],
                case["prefix"],
                "matrix",
                bulb_seconds=case["seconds"],
            )
            assert CANARY.shot_satisfied(
                record, [], case["expected_files"], case["prefix"]
            )
            assert not record["terminal_failure"]
        else:
            ok, records, paths = CANARY.run_sequence(
                device,
                case["shots"],
                1.0,
                case["expected_files"],
                case["prefix"],
                "matrix",
                bulb_seconds=case["seconds"],
            )
            assert ok
            assert len(records) == case["shots"]
            seen.update(paths)
    else:
        for shot in range(1, case["shots"] + 1):
            files = ASTRO.capture(
                device,
                shot,
                1.0,
                expected_files=case["expected_files"],
                seen_paths=seen,
                bulb_seconds=case["seconds"],
            )
            assert len(files) == case["expected_files"]
            assert all(path.startswith(case["prefix"]) for path in files)

    capture_sends = [
        call for call in device.sends
        if call[0] and call[0][0] == 264
    ]
    assert len(capture_sends) == case["shots"]
    assert all(
        call[1]["payload"] == f"state:1;bulb:{case['seconds']};c:-1;"
        for call in capture_sends
    )


def test_bulb_selection_is_a_separate_required_wire_step():
    """Shutter selection is command 261 `s:<index>;`, verified by a 268 readback.

    277 is `camera_set_aperture`; sending the shutter there is what made every
    earlier Bulb canary time out.  See docs/evidence/bulb-root-cause-20261005.
    """
    device = FakePolaris([
        (261, "s:5;ret:0;"),
        (268, "V:5;R:1/8000,1/1000,1/60,1/4,00-03,00-08,00-30;"),
    ])
    PROBE.set_shutter(device, 5)
    assert device.sends == [
        ((261,), {"payload": "s:5;"}),
        ((268,), {}),
    ]


def test_matrix_distinguishes_single_file_formats_from_raw_plus_jpeg():
    formats = {item["id"]: item for item in _matrix()["formats"]}
    assert formats["raw"]["expected_files"] == 1
    assert formats["jpeg"]["expected_files"] == 1
    assert formats["raw+jpeg"]["expected_files"] == 2
    assert formats["raw+jpeg"]["suffixes"] == [".dng", ".jpg"]
