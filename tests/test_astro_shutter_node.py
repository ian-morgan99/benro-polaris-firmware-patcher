"""Run the Astro WebUI shutter dispatch tests under node (#309).

Why this exists as a pytest wrapper rather than only as a .js file: the
prerelease gate and `python -m pytest` are what actually run on every candidate.
A test file nothing invokes is the exact failure mode of #292 -- a check that
existed but was never called, so astro-v102 shipped without it.

The skip is deliberately loud. If node is missing the suite reports a skip with
the reason, and scripts/build-doctor.sh checks for node separately so a host that
cannot run these tests is visible at preflight rather than silently green.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
JS_TESTS = REPO / "tests" / "test_astro_shutter.js"
SHUTTER_MODULE = REPO / "container" / "astro" / "webui" / "shutter.js"


def test_shutter_module_exists_and_is_shipped():
    """The WebUI must actually load the module the tests cover.

    A pure-JS test suite can pass while the page never references the file, which
    would make the whole thing decorative. index.html is the only script tag list
    that matters here.
    """
    assert SHUTTER_MODULE.is_file(), f"missing {SHUTTER_MODULE}"
    html = (REPO / "container" / "astro" / "webui" / "index.html").read_text(
        encoding="utf-8")
    assert "shutter.js" in html, (
        "shutter.js exists but index.html never loads it, so the tested code is "
        "dead and app.js still contains the old inline dispatch")


def test_app_js_no_longer_sends_the_continuation_trigger():
    """app.js must not carry a hardcoded c:0 shutter payload.

    This is the specific defect #309 reports. Asserting it here, in Python, means
    the rule holds even on a host with no node -- the JS tests cover behaviour,
    this covers that the old call site stayed gone.
    """
    app = (REPO / "container" / "astro" / "webui" / "app.js").read_text(
        encoding="utf-8")
    assert "state:1;bulb:0;c:0;" not in app, (
        "app.js still sends the continuation-shooting trigger on an ordinary "
        "capture; dispatch belongs in shutter.js (#309)")


@pytest.mark.skipif(shutil.which("node") is None,
                    reason="node not on PATH -- run scripts/build-doctor.sh")
def test_astro_shutter_dispatch_under_node():
    """Execute the real acceptance tests against the real module."""
    proc = subprocess.run(
        ["node", str(JS_TESTS)], capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, (
        f"shutter dispatch tests failed\n{proc.stdout}\n{proc.stderr}")
    assert "ok " in proc.stdout, f"unexpected output: {proc.stdout!r}"
