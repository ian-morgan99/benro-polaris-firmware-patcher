import json
import os
import stat
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WATCH = ROOT / "ondisk" / "polaris-frame-watch.sh"


def _jpeg(path: Path, payload: bytes = b"frame"):
    path.write_bytes(b"\xff\xd8" + payload * 8 + b"\xff\xd9")


def _wait_for(predicate, timeout=4.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    assert predicate()


def test_frame_watch_admits_only_new_or_changed_jpegs(tmp_path):
    capture = tmp_path / "normal"
    capture.mkdir()
    old = capture / "old.jpg"
    _jpeg(old, b"old")

    astro = tmp_path / "astro"
    astro.mkdir()
    align = astro / "polaris-align.sh"
    align.write_text(
        '#!/bin/sh\n'
        'printf \'{"solved":true,"ra_deg":1,"dec_deg":2,"matched_count":20,"rms_px":1.0,"rotation_deg":3}\\n\'\n'
    )
    align.chmod(align.stat().st_mode | stat.S_IXUSR)

    mode = tmp_path / "mode"
    mode.write_text("0\n")
    log = tmp_path / "watch.log"
    history = tmp_path / "history.jsonl"
    state = tmp_path / "state.tsv"
    admission = tmp_path / "admission.tsv"
    frame_state = tmp_path / "last.json"

    env = os.environ.copy()
    env.update(
        {
            "ASTRO": str(astro),
            "CAPTURE_DIR": str(capture),
            "CAPTURE_GLOB_EXTRA": str(tmp_path / "not-a-capture-dir"),
            "MODE_FILE": str(mode),
            "LOG": str(log),
            "HISTORY": str(history),
            "STATE": str(state),
            "ADMISSION": str(admission),
            "FRAME_STATE": str(frame_state),
            "SOLVER_BIN": "native-test",
            "FRAME_WATCH_POLL": "0.05",
            "FRAME_STABLE_WAIT": "0",
            "FRAME_MIN_BYTES": "1",
            "MIN_MATCHES": "12",
            "MAX_SOLVE_RMS_PX": "3",
        }
    )
    proc = subprocess.Popen(["sh", str(WATCH)], env=env)
    try:
        time.sleep(0.15)
        mode.write_text("8\n")
        time.sleep(0.15)

        # Existing gallery content is admitted as the session baseline.
        assert not history.exists() or not history.read_text().strip()

        new = capture / "new.jpeg"
        _jpeg(new, b"new")
        _wait_for(lambda: "new.jpeg" in log.read_text())

        # A later write reusing an existing path has a new size/key and is not
        # silently discarded by the old path-only deduplication.
        _jpeg(old, b"changed-and-larger")
        _wait_for(lambda: log.read_text().count("old.jpg") >= 1)
        assert history.exists()
        assert len(history.read_text().splitlines()) == 2
        assert admission.exists()
        assert json.loads(history.read_text().splitlines()[0].split("\t", 1)[1])["solved"]
    finally:
        proc.terminate()
        proc.wait(timeout=3)
