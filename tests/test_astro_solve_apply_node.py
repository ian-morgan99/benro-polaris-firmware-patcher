"""Run the Astro WebUI apply-last tests under node (#329).

Why this exists as a pytest wrapper rather than only as a .js file: the prerelease
gate and `python -m pytest` are what actually run on every candidate. A test file
nothing invokes is the exact failure mode of #292 and #299 -- a check that existed
but was never called, so a candidate shipped without it.

The skip is deliberately loud. If node is missing the suite reports a skip with
the reason, and scripts/build-doctor.sh checks for node separately so a host that
cannot run these tests is visible at preflight rather than silently green. The
Python assertions below still run on such a host: they cover the wiring, which is
the part most likely to regress without anyone noticing.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
JS_TESTS = REPO / "tests" / "test_astro_solve_apply.js"
APPLY_MODULE = REPO / "container" / "astro" / "webui" / "solve-apply.js"


def test_apply_module_exists_and_is_shipped():
    """The WebUI must actually load the module the tests cover.

    A pure-JS suite can pass while the page never references the file, which
    would make the whole thing decorative and leave app.js on the old inline
    handler. index.html is the only script-tag list that matters here.
    """
    assert APPLY_MODULE.is_file(), f"missing {APPLY_MODULE}"
    html = (REPO / "container" / "astro" / "webui" / "index.html").read_text(
        encoding="utf-8")
    assert "solve-apply.js" in html, (
        "solve-apply.js exists but index.html never loads it, so the tested code "
        "is dead and app.js still contains the old inline apply handler")
    # app.js calls into it at click time; if the tag order ever changes so that
    # app.js runs first, SOLVE_APPLY is undefined and every branch silently falls
    # back to the inline behaviour.
    assert html.index("solve-apply.js") < html.index("/app.js"), (
        "solve-apply.js must load before app.js")


def test_app_js_no_longer_posts_an_empty_apply_body():
    """The specific defect #329 reports must stay gone.

    Asserting it in Python means the rule holds even on a host with no node: the
    JS tests cover behaviour, this covers that the old call site stayed gone.
    """
    app = (REPO / "container" / "astro" / "webui" / "app.js").read_text(
        encoding="utf-8")
    assert "post('/api/apply', {})" not in app, (
        "app.js posts an empty body to /api/apply again; the apply-last decision "
        "table belongs in solve-apply.js (#329)")


@pytest.mark.skipif(shutil.which("node") is None,
                    reason="node not on PATH -- run scripts/build-doctor.sh")
def test_astro_solve_apply_under_node():
    """Execute the real acceptance tests against the real module."""
    proc = subprocess.run(
        ["node", str(JS_TESTS)], capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, (
        f"apply-last tests failed\n{proc.stdout}\n{proc.stderr}")
    assert "FAIL" not in proc.stdout, f"a group failed:\n{proc.stdout}"
    assert "assertion group(s) passed" in proc.stdout, (
        f"unexpected output: {proc.stdout!r}")
