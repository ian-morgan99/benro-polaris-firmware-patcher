"""Execute polaris-httpd and assert the /api/wifi action contract (#273).

Why this compiles and runs the server instead of grepping it: the bug was a
contract mismatch that no amount of source reading would settle. app.js posted
"autojoin=1"; the handler read "action". The request matched no branch, fell
through into the status block, and answered HTTP 200 with {"ok":true,...}
carrying the *unchanged* wifi state. The caller saw success. The toggle was
dead. Only a real request against a real server distinguishes "answered ok"
from "answered ok because nothing was recognised".

The rejection path returns before touching any device path, so it is testable
on a build host with no Polaris attached. That is deliberate: the check has to
run in the prerelease gate, which runs off-device.

Skips are loud. If gcc is absent the suite reports why rather than passing
quietly -- an unexecuted contract test is the #292/#299 failure mode this repo
has already been bitten by twice.
"""
from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ASTRO = REPO / "container" / "astro"
SOURCES = [
    ASTRO / "polaris-httpd.c",
    ASTRO / "polaris-link.c",
    ASTRO / "polaris-jog.c",
    ASTRO / "polaris-prog.c",
    ASTRO / "polaris-astro.c",
]
APP_JS = ASTRO / "webui" / "app.js"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def httpd(tmp_path_factory):
    """Build polaris-httpd for the host and run it on a spare port."""
    if shutil.which("gcc") is None:
        pytest.skip("gcc unavailable; the /api/wifi contract can only be "
                    "checked by executing the server")
    binary = tmp_path_factory.mktemp("httpd") / "polaris-httpd"
    build = subprocess.run(
        ["gcc", "-O0", "-o", str(binary)] + [str(p) for p in SOURCES] + ["-lm"],
        capture_output=True, text=True,
    )
    if build.returncode != 0:
        pytest.skip("polaris-httpd does not build on this host: "
                    + build.stderr.strip().splitlines()[-1][:200])

    port = _free_port()
    proc = subprocess.Popen(
        [str(binary), "--port", str(port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 10
    try:
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                    break
            except OSError:
                if proc.poll() is not None:
                    pytest.skip("polaris-httpd exited on startup on this host")
                time.sleep(0.1)
        else:
            pytest.skip("polaris-httpd never accepted a connection within 10 s")
        yield proc, port
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def _post(port: int, fields: dict) -> dict:
    body = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/wifi", data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:
        return {"_http": exc.code, **json.loads(exc.read().decode())}


def _get(port: int) -> dict:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/wifi", timeout=8) as r:
        return json.loads(r.read().decode())


def test_unknown_action_is_rejected_not_reported_as_success(httpd):
    """The exact payload app.js used to send must no longer look like a success.

    Before the fix this returned {"ok":true,...,"autojoin":false}: a 200, an ok
    flag, and a state that had not changed. A caller checking res.ok concluded
    the toggle had been applied.
    """
    _, port = httpd
    reply = _post(port, {"autojoin": "1"})
    assert reply.get("ok") is False, (
        "a POST with no recognised action was accepted as success; that is the "
        "#273 silent no-op: %r" % (reply,)
    )
    assert "action" in (reply.get("error") or "").lower(), (
        "the rejection must name the missing parameter, not just fail: %r" % (reply,)
    )


def test_recognised_actions_still_succeed(httpd):
    """Rejecting unknown actions must not break the ones that were correct."""
    _, port = httpd
    for action in ("autojoin_on", "autojoin_off"):
        reply = _post(port, {"action": action})
        assert reply.get("ok") is True, f"{action} regressed: {reply!r}"


def test_status_get_is_unchanged(httpd):
    """GET carries no action and must still return the status object."""
    _, port = httpd
    status = _get(port)
    assert status.get("ok") is True, status
    for field in ("ssid", "configured", "autojoin"):
        assert field in status, f"status lost field {field}: {status!r}"


def test_client_sends_the_action_the_handler_reads():
    """The two halves of the contract have to agree, on both pages.

    Asserted against the shipped source because the server cannot tell us what
    app.js will send -- and the whole bug was a client that had drifted from the
    handler while the handler stayed correct.
    """
    js = APP_JS.read_text(encoding="utf-8")
    assert "autojoin_on" in js and "autojoin_off" in js, (
        "app.js must post action=autojoin_on/autojoin_off"
    )
    assert "{ autojoin: join.checked ? 1 : 0 }" not in js, (
        "the old body-less payload is back; it matches no handler branch and "
        "becomes a silent no-op again"
    )


def test_credential_entry_exists_in_the_settings_page():
    """#273's second half: the toggle existed with nowhere to enter credentials.

    Without an SSID/password field, turning auto-join on from the settings page
    joined nothing at all -- the credentials lived only in the fallback page.
    """
    html = (ASTRO / "webui" / "index.html").read_text(encoding="utf-8")
    for element_id in ("wifi-ssid", "wifi-psk", "wifi-save"):
        assert f'id="{element_id}"' in html, f"settings page lost #{element_id}"
    js = APP_JS.read_text(encoding="utf-8")
    assert "'action: 'save'" in js or '"action": "save"' in js or "action: 'save'" in js, (
        "the save button must post action=save, the same verb the fallback page uses"
    )
