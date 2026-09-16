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
        ])
        MODULE.capture(device, 1, 1)
        self.assertEqual(device.sent, [(264, 4, "state:1;bulb:0;c:-1;")])

    def test_rejects_negative_lifecycle(self):
        device = FakePolaris([(264, "state:-2;bulb:0;c:-1;")])
        with self.assertRaisesRegex(RuntimeError, "terminal failure"):
            MODULE.capture(device, 1, 1)

    def test_rejects_two_different_files_for_one_shot(self):
        device = FakePolaris([
            (773, "path:/app/sd/normal/SP_0043.dng;"),
            (773, "path:/app/sd/normal/SP_0044.dng;"),
        ])
        with self.assertRaisesRegex(RuntimeError, "multiple file events"):
            MODULE.capture(device, 1, 1)


if __name__ == "__main__":
    unittest.main()
