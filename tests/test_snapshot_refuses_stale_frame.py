"""Execute polaris-httpd and prove /api/snapshot cannot serve a stale frame.

The defect: serve_snapshot() called liveview_grab() and threw away the result,
then opened SNAP_JPG unconditionally. liveview_grab() only writes the file when
it has a complete SOI..EOI frame (polaris-httpd.c:1004-1012) and returns 0 on
timeout, so when the grab fails the path still holds whatever an earlier success
left there. The fopen then succeeded and the endpoint answered

    200 OK, Content-Type: image/jpeg

with a frame from hours ago. polaris-httpd.c:890 already documents the intended
contract -- "on timeout we return 0 and the caller serves its usual 'no frame'
response" -- so this is the caller not honouring it.

Measured on the live head (192.168.68.25, K-1 II absent from USB):
    GET /api/snapshot -> http=200 time=6.31s bytes=28691
    GET /api/snapshot -> http=200 time=6.40s bytes=28691
and /tmp/polaris-snap.jpg was dated Nov 18 00:45 while the device clock read
07:51 -- 7h06m old, byte-identical across both responses. The overlay in app.js
polls this endpoint once a second (setPeak -> setInterval(peakTick, 1000)), so
the user watched a frozen image that looked like a stalled camera rather than a
missing one, and each poll blocked the single select() thread for the full
6-second SO_RCVTIMEO.

These tests run the real binary rather than grepping it, for the same reason
test_webui_serves_and_stays_serving.py does: "answered 200" and "answered 200
with a frame that is actually current" are different claims, and only a live
request separates them. Skips are loud -- an unexecuted gate test is the #292/
#299 failure mode this repo has been bitten by twice.
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ASTRO = REPO / "container" / "astro"
EMBED = ASTRO / "embed_webui.py"
WEBUI = ASTRO / "webui"
SOURCES = [
    ASTRO / "polaris-httpd.c",
    ASTRO / "polaris-link.c",
    ASTRO / "polaris-jog.c",
    ASTRO / "polaris-prog.c",
    ASTRO / "polaris-astro.c",
]

# A minimal but structurally valid JPEG. serve_snapshot() does not parse it --
# it streams the bytes -- so only its size and non-zero length matter here.
FAKE_JPEG = b"\xff\xd8\xff\xe0" + b"\x00\x10JFIF\x00\x01\x01\x00\x00\x01" \
    + b"\x00\x01\x00\x00" + b"\x11" * 64 + b"\xff\xd9"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _build(work: Path) -> tuple[Path, str | None]:
    """Return (binary_path, skip_reason). Never raises: the caller turns a
    reason into a skip so the gate says why rather than going quiet."""
    if shutil.which("gcc") is None:
        return work / "polaris-httpd", "gcc unavailable"

    embed = subprocess.run(
        [sys.executable, str(EMBED), str(WEBUI), str(work / "webui.h")],
        capture_output=True, text=True,
    )
    if embed.returncode != 0 or not (work / "webui.h").exists():
        return work / "polaris-httpd", "could not generate webui.h: " + \
            (embed.stderr or embed.stdout).strip()[-200:]

    binary = work / "polaris-httpd"
    build = subprocess.run(
        ["gcc", "-O0", "-I", str(work), "-o", str(binary)]
        + [str(p) for p in SOURCES] + ["-lm"],
        capture_output=True, text=True,
    )
    if build.returncode != 0:
        return binary, "polaris-httpd does not build on this host: " + \
            (build.stderr.strip().splitlines()[-1][:200] if build.stderr else "")
    return binary, None


def _start(binary: Path, port: int, work: Path, snap_jpg: Path):
    astro = work / "astro"
    astro.mkdir(exist_ok=True)
    # --mount-host 127.0.0.1 with nothing listening on 8080 makes every
    # liveview_grab() fail fast on connect() rather than burning the full
    # SO_RCVTIMEO, so the test is quick and deterministic.
    proc = subprocess.Popen(
        [str(binary), "--port", str(port), "--lat", "55.95", "--lon", "-3.19",
         "--astro", str(astro), "--mount-host", "127.0.0.1",
         "--snap-jpg", str(snap_jpg)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return proc
        except OSError:
            if proc.poll() is not None:
                raise RuntimeError("polaris-httpd exited on startup")
            time.sleep(0.1)
    proc.terminate()
    raise RuntimeError("polaris-httpd never accepted a connection within 10 s")


@pytest.fixture()
def server(tmp_path):
    binary, reason = _build(tmp_path)
    if reason:
        pytest.skip(f"cannot execute polaris-httpd here, so the stale-frame "
                    f"defect cannot be checked: {reason}")
    snap = tmp_path / "snap.jpg"
    port = _free_port()
    proc = _start(binary, port, tmp_path, snap)
    try:
        yield port, snap
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def _get(port: int, path: str, timeout: float = 12.0):
    """GET and return (status, body). Returns (int, bytes) for HTTP errors too."""
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_stale_frame_is_not_served_as_live(server):
    """The core regression: a leftover file must not be answered with 200.

    Pre-fix this returned (200, b"<the old frame>") because serve_snapshot()
    ignored liveview_grab()'s return value and opened the path regardless.
    """
    port, snap = server
    snap.write_bytes(FAKE_JPEG)
    # Backdate it so "stale" is unambiguous even if something did write.
    old = time.time() - 7200
    os.utime(snap, (old, old))

    status, body = _get(port, "/api/snapshot")

    assert status == 502, (
        f"/api/snapshot answered {status} with {len(body)} bytes while the only "
        f"frame on disk was two hours old and no camera was reachable. A stale "
        f"frame served as 200 image/jpeg is indistinguishable from a live one "
        f"over HTTP -- there is no Last-Modified or age field."
    )
    assert body != FAKE_JPEG, "the stale frame was handed to the client verbatim"


def test_no_frame_at_all_is_still_502(server):
    """The pre-existing failure path must keep working."""
    port, snap = server
    assert not snap.exists()
    status, body = _get(port, "/api/snapshot")
    assert status == 502
    assert b"no live-view frame" in body


def test_other_endpoints_still_serve(server):
    """The fix must not take the whole server down with it."""
    port, snap = server
    snap.write_bytes(FAKE_JPEG)
    status, body = _get(port, "/api/state")
    assert status == 200, "a failed snapshot grab must not break /api/state"
    assert b"status" in body


def test_default_snap_path_is_unchanged():
    """The override must not move the file on a real install.

    polaris-httpd writes SNAP_JPG and the on-device live-view path reads it; a
    changed default would break live view on every install while every test here
    still passed, because each test passes --snap-jpg explicitly.
    """
    src = (ASTRO / "polaris-httpd.c").read_text()
    assert '#define SNAP_JPG_DEFAULT "/tmp/polaris-snap.jpg"' in src, (
        "the default snapshot path changed; on-device live view and any caller "
        "reading /tmp/polaris-snap.jpg would silently stop working"
    )
    assert "static const char *g_snap_jpg = SNAP_JPG_DEFAULT;" in src
