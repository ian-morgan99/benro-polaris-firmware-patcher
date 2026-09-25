#!/usr/bin/env python3
"""Offline contract tests for scripts/test-astro-multishot.py."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import unittest


SPEC = spec_from_file_location(
    "astro_multishot",
    Path(__file__).resolve().parents[1] / "scripts" / "test-astro-multishot.py",
)
assert SPEC and SPEC.loader
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FakePolaris:
    def __init__(self, frames):
        self.frames = iter(frames)
        self.sent = []

    def send(self, code, subtype=2, payload="-100"):
        self.sent.append((code, subtype, payload))

    def frame(self, _deadline):
        return next(self.frames)


class CaptureContractTest(unittest.TestCase):
    def test_requires_lifecycle_and_file(self):
        device = FakePolaris([
            (264, "state:1;bulb:0;c:-1;"),
            (264, "state:4;bulb:0;c:-1;"),
            (773, "path:/app/sd/normal/SP_0043.dng;"),
            (264, "state:0;bulb:0;c:-1;"),
        ])
        MODULE.capture(device, 1, 1)
        self.assertEqual(device.sent, [(264, 4, "state:1;bulb:0;c:-1;")])

    def test_rejects_negative_lifecycle(self):
        device = FakePolaris([(264, "state:-2;bulb:0;c:-1;")])
        with self.assertRaisesRegex(RuntimeError, "terminal failure"):
            MODULE.capture(device, 1, 1)

    def test_raw_jpeg_requires_same_stem_and_idle(self):
        device = FakePolaris([
            (264, "state:4;"),
            (773, "path:/app/sd/normal/SP_0043.dng;"),
            (773, "path:/app/sd/normal/SP_0043.jpg;"),
            (264, "state:0;"),
        ])
        self.assertEqual(
            MODULE.capture(device, 1, 1, expected_files=2),
            ["/app/sd/normal/SP_0043.dng", "/app/sd/normal/SP_0043.jpg"],
        )

    def test_rejects_two_different_exposure_stems(self):
        device = FakePolaris([
            (773, "path:/app/sd/normal/SP_0043.dng;"),
            (773, "path:/app/sd/normal/SP_0044.jpg;"),
        ])
        with self.assertRaisesRegex(RuntimeError, "exposure stem"):
            MODULE.capture(device, 1, 1, expected_files=2)

    def test_rejects_stale_file_from_prior_shot(self):
        path = "/app/sd/normal/SP_0043.dng"
        device = FakePolaris([(773, f"path:{path};")])
        with self.assertRaisesRegex(RuntimeError, "stale file"):
            MODULE.capture(device, 2, 1, seen_paths={path})


if __name__ == "__main__":
    unittest.main()
