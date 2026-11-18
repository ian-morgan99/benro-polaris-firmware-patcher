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
HTTPD = ASTRO / "polaris-httpd.c"
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


# ---------------------------------------------------------------------------
# #370: the accept thread must not block on every poll.
#
# app.js setPeak() polls /api/snapshot once a second. The head's MJPEG source
# (pgphoto Stage-2, measured on 192.168.68.25 with a K-1 II attached) emits one
# frame every ~10.3 s -- first frame ~5.25 s after the stream opens, then gaps of
# 10.69/10.30/10.05/10.28 s. So the poll rate is ten times the source rate, and
# every poll that misses a frame blocks the single-threaded select() server for
# the full SO_RCVTIMEO. Measured on the device: /api/state was 22 ms alone and
# 5.74 s while a snapshot was in flight -- a 260x degradation of every other
# endpoint, caused by one overlay image.
#
# The fix serves a frame that is already fresh enough without touching the
# network, and backs off after a failure instead of re-paying the timeout on
# every poll. Verified against the real head stream: over 15 polls at 1 s
# intervals, 12 were served from cache in ~0.2 ms, 1 blocked (cold cache), 2 were
# refused -- matching the 10.3 s cadence rather than blocking 15 times.
# ---------------------------------------------------------------------------

def _get_headers(port: int, path: str, timeout: float = 12.0):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def test_recent_frame_is_served_without_a_fresh_grab(server):
    """A frame younger than the freshness window is served even though no camera
    is reachable here.

    Pre-fix this returned 502: serve_snapshot() always called liveview_grab()
    first and failed the request when it returned 0, regardless of what was
    already on disk. That is correct for staleness but wrong for latency -- the
    file is as recent as the source can make it, so blocking to ask again buys
    nothing and starves every other endpoint for the duration.
    """
    port, snap = server
    snap.write_bytes(FAKE_JPEG)          # mtime == now, so age ~0 s

    status, hdrs, body = _get_headers(port, "/api/snapshot")

    assert status == 200, (
        f"a frame written moments ago was refused ({status}) even though the "
        f"source cannot produce anything newer; the poll should be answered from "
        f"the existing frame instead of blocking on a grab that will time out"
    )
    assert body == FAKE_JPEG, "served something other than the cached frame"


def test_response_declares_frame_age(server):
    """A served frame must say how old it is.

    This is what made #368 invisible: a seven-hour-old image was returned as
    200 image/jpeg with nothing in the response to distinguish it from a live
    one. The overlay polls faster than the source produces frames, so most
    responses legitimately carry a frame a few seconds old -- the client needs
    to be able to show that rather than silently display a freeze.
    """
    port, snap = server
    snap.write_bytes(FAKE_JPEG)
    old = time.time() - 3
    os.utime(snap, (old, old))

    status, hdrs, _ = _get_headers(port, "/api/snapshot")
    assert status == 200, f"expected the cached frame to be served, got {status}"

    age_hdr = hdrs.get("X-Polaris-Frame-Age-Sec")
    assert age_hdr is not None, (
        "no frame-age header: a client cannot tell a live frame from an old one, "
        "which is the failure mode #368 shipped with"
    )
    assert 3 <= int(age_hdr) <= 60, (
        f"frame age reported as {age_hdr}s for a file backdated 3s -- the value "
        f"must reflect the file's real mtime or it is worse than no header"
    )


def test_no_store_on_live_frames(server):
    """Live-view frames must not be cached by intermediaries."""
    port, snap = server
    snap.write_bytes(FAKE_JPEG)
    status, hdrs, _ = _get_headers(port, "/api/snapshot")
    assert status == 200
    cc = (hdrs.get("Cache-Control") or "").lower()
    assert "no-store" in cc, (
        f"Cache-Control is {cc!r}; a cached snapshot would be replayed as if it "
        f"were current, reintroducing #368 from the client side"
    )


def test_stale_frame_is_still_refused(server):
    """The freshness window must not become a way to serve hour-old frames."""
    port, snap = server
    snap.write_bytes(FAKE_JPEG)
    os.utime(snap, (time.time() - 7200, time.time() - 7200))

    status, _, _ = _get_headers(port, "/api/snapshot")
    assert status == 502, (
        f"a two-hour-old frame was served with {status}: the freshness window is "
        f"meant to avoid redundant grabs, not to resurrect #368"
    )


def test_freshness_window_is_configurable(server):
    """The window has to be tunable: it must exceed one source cadence (10.3 s)
    or it defeats itself, and a different camera may need a different value."""
    src = HTTPD.read_text()
    assert "POLARIS_SNAP_FRESH_SEC" in src, (
        "no knob for the freshness window; it must be at least one full frame "
        "interval of the source or every poll still blocks on a grab"
    )
    assert "POLARIS_SNAP_RETRY_SEC" in src, (
        "no knob for failure backoff; without it a head with no camera re-grabs "
        "on every poll and the accept thread is never free"
    )
