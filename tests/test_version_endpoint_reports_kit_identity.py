"""Execute polaris-httpd and prove /api/version reports kit identity honestly.

WHY THIS EXISTS. The only version a human could read on the Polaris was
/app/FwVer -- the appfs/firmware version. An SD-kit-only release never touches it,
so after astro-v112 shipped the head still displayed 6.0.0.54.110 and nothing on
the device could say which kit was installed. Confirming a deploy meant SSH plus a
manual sha256 of polaris-httpd. A *successful* install was indistinguishable from a
failed one, which is the #312/#58 blindness pointed the other way.

The fix stamps build_id and the firmware version the kit was built against into
polaris-astro/VERSION at build time, and /api/version reports that beside the live
/app/FwVer so alignment is checkable in one request.

These tests run the real binary rather than grepping it, for the same reason
test_snapshot_refuses_stale_frame.py does: "the endpoint exists" and "the endpoint
reports the right thing when the kit and firmware disagree" are different claims,
and only a live request separates them. In particular the aligned/mismatch branch
is pure comparison logic -- a grep cannot show it picks the correct branch.

Skips are loud: an unexecuted gate test is the #292/#299 failure mode this repo has
been bitten by twice.
"""
from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import time
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


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _build(work: Path) -> tuple[Path, str | None]:
    """Return (binary_path, skip_reason). Never raises: the caller turns a reason
    into a skip so the gate says why rather than going quiet."""
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


def _start(binary: Path, port: int, astro: Path, fwver_file: Path):
    proc = subprocess.Popen(
        [str(binary), "--port", str(port), "--lat", "55.95", "--lon", "-3.19",
         "--astro", str(astro), "--mount-host", "127.0.0.1",
         "--fwver-file", str(fwver_file)],
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


def _get_json(port: int, path: str) -> dict:
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def _serve(tmp_path: Path, version_text: str | None, fwver_text: str | None):
    """Start httpd against a kit dir and a stand-in /app/FwVer.

    Returns (port, cleanup). version_text=None means no VERSION file at all, which
    is the pre-stamp case and must not be reported as aligned.
    """
    binary, reason = _build(tmp_path)
    if reason:
        pytest.skip(
            "cannot execute polaris-httpd here, so kit identity reporting cannot "
            f"be checked: {reason}")

    astro = tmp_path / "astro"
    astro.mkdir(exist_ok=True)
    if version_text is not None:
        (astro / "VERSION").write_text(version_text)

    fw = tmp_path / "FwVer"
    fw.write_text(fwver_text if fwver_text is not None else "")

    port = _free_port()
    proc = _start(binary, port, astro, fw)

    def cleanup():
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    return port, cleanup


STAMPED = (
    "build_id=astro-v113-snapshot-stall-20261118\n"
    "firmware_version=6.0.0.54.111\n"
    "firmware_version_source=explicit\n"
    "patcher_commit=0123456789abcdef0123456789abcdef01234567\n"
    "built_utc=2026-11-18T15:00:00Z\n"
)

# The stock updater writes exactly this shape on the head.
FWVER_111 = "FwVer:6.0.0.54.111;date:2026.11.18;\n"
FWVER_110 = "FwVer:6.0.0.54.110;date:2026.11.17;\n"


def test_reports_build_id_and_both_firmware_versions(tmp_path):
    """One request must answer both halves of the question: which kit is installed,
    and which firmware is it running beside."""
    port, stop = _serve(tmp_path, STAMPED, FWVER_111)
    try:
        d = _get_json(port, "/api/version")
        assert d["ok"] is True
        assert d["build_id"] == "astro-v113-snapshot-stall-20261118"
        assert d["firmware_version_expected"] == "6.0.0.54.111"
        assert d["firmware_version_actual"] == "6.0.0.54.111"
        assert d["aligned"] is True
    finally:
        stop()


def test_mismatch_is_reported_not_swallowed(tmp_path):
    """The whole point of stamping: a kit deployed against a different appfs than
    the one running must be visible immediately, not discovered when it misbehaves.

    This is the exact situation astro-v112 was in -- kit newer than firmware -- and
    nothing on the device could express it.
    """
    port, stop = _serve(tmp_path, STAMPED, FWVER_110)
    try:
        d = _get_json(port, "/api/version")
        assert d["aligned"] is False, (
            "a kit stamped for .111 running on a .110 head must not read as aligned"
        )
        assert d["firmware_version_expected"] == "6.0.0.54.111"
        assert d["firmware_version_actual"] == "6.0.0.54.110"
    finally:
        stop()


def test_absent_version_file_is_unknown_and_never_aligned(tmp_path):
    """A pre-stamp kit has no VERSION file. Reporting aligned there would be a lie
    that passes an alignment check, which is worse than reporting nothing."""
    port, stop = _serve(tmp_path, None, FWVER_111)
    try:
        d = _get_json(port, "/api/version")
        assert d["build_id"] == "unknown"
        assert d["firmware_version_expected"] == "unknown"
        assert d["aligned"] is False
    finally:
        stop()


def test_missing_fwver_file_is_unknown_not_aligned(tmp_path):
    """Empty/absent /app/FwVer must not compare equal to an empty expectation."""
    port, stop = _serve(tmp_path, STAMPED, "")
    try:
        d = _get_json(port, "/api/version")
        assert d["firmware_version_actual"] == "unknown"
        assert d["aligned"] is False
    finally:
        stop()


def test_unknown_stamp_source_is_never_treated_as_aligned(tmp_path):
    """A kit built without --fwver records firmware_version=unknown. It must not
    match a real head version, otherwise the stamp silently certifies nothing."""
    text = (
        "build_id=astro-dev-20261118\n"
        "firmware_version=unknown\n"
        "firmware_version_source=not-supplied\n"
        "patcher_commit=deadbeef\n"
    )
    port, stop = _serve(tmp_path, text, FWVER_111)
    try:
        d = _get_json(port, "/api/version")
        assert d["firmware_version_expected"] == "unknown"
        assert d["firmware_version_source"] == "not-supplied"
        assert d["aligned"] is False
    finally:
        stop()


def test_fwver_parsing_stops_at_semicolon(tmp_path):
    """/app/FwVer is "FwVer:6.0.0.54.111;date:...". Taking the whole line would
    compare a version against a version+date and always mismatch."""
    port, stop = _serve(tmp_path, STAMPED, FWVER_111)
    try:
        d = _get_json(port, "/api/version")
        assert d["firmware_version_actual"] == "6.0.0.54.111"
        assert "date" not in d["firmware_version_actual"]
    finally:
        stop()
