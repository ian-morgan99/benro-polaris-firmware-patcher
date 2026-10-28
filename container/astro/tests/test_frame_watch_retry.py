import json
import os
import stat
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WATCH = ROOT / "ondisk" / "polaris-frame-watch.sh"


def _jpeg(path: Path):
    path.write_bytes(b"\xff\xd8" + b"stars" * 12 + b"\xff\xd9")


def _wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.03)
    assert predicate()


def test_failed_frame_is_retried_and_preserved(tmp_path):
    capture = tmp_path / "normal"
    capture.mkdir()
    frame = capture / "retry.jpg"

    astro = tmp_path / "astro"
    astro.mkdir()
    attempts = tmp_path / "attempts"
    align = astro / "polaris-align.sh"
    align.write_text(
        "#!/bin/sh\n"
        "n=0; [ -r '$COUNT' ] && n=$(cat '$COUNT'); n=$((n+1)); echo $n > '$COUNT'\n"
        "if [ $n -lt 3 ]; then printf '{\"solved\":false,\"failure_reason\":\"weak\"}\\n'; else printf '{\"solved\":true,\"ra_deg\":1,\"dec_deg\":2,\"matched_count\":20,\"rms_px\":1.0,\"rotation_deg\":3}\\n'; fi\n".replace("$COUNT", str(attempts)))
    align.chmod(align.stat().st_mode | stat.S_IXUSR)

    mode = tmp_path / "mode"
    mode.write_text("8\n")
    env = os.environ.copy()
    env.update(
        {
            "ASTRO": str(astro),
            "CAPTURE_DIR": str(capture),
            "CAPTURE_GLOB_EXTRA": str(tmp_path / "none"),
            "MODE_FILE": str(mode),
            "LOG": str(tmp_path / "watch.log"),
            "HISTORY": str(tmp_path / "history.jsonl"),
            "STATE": str(tmp_path / "state.tsv"),
            "ADMISSION": str(tmp_path / "admission.tsv"),
            "FRAME_STATE": str(tmp_path / "last.json"),
            "FRAME_TELEMETRY": str(tmp_path / "telemetry.jsonl"),
            "SESSION_FILE": str(tmp_path / "session-id"),
            "TARGET_FILE": str(tmp_path / "target.json"),
            "FRAME_FAILED_DIR": str(tmp_path / "failed"),
            "FRAME_LOCK_DIR": str(tmp_path / "lock"),
            "SOLVER_BIN": "native-test",
            "FRAME_WATCH_POLL": "0.03",
            "FRAME_STABLE_WAIT": "0",
            "FRAME_MIN_BYTES": "1",
            "FRAME_REQUIRE_CAPTURE_EVENT": "0",
            "FRAME_MAX_SOLVE_ATTEMPTS": "3",
            "FRAME_RETRY_DELAY": "0",
            "MIN_MATCHES": "12",
            "MAX_SOLVE_RMS_PX": "3",
        }
    )
    proc = subprocess.Popen(["sh", str(WATCH)], env=env)
    try:
        _wait_for(lambda: (tmp_path / "session-id").exists())
        _jpeg(frame)
        _wait_for(lambda: attempts.exists() and attempts.read_text().strip() == "3")
        history = tmp_path / "history.jsonl"
        _wait_for(lambda: history.exists() and len(history.read_text().splitlines()) == 3)
        rows = [json.loads(line.split("\t", 1)[1]) for line in history.read_text().splitlines()]
        assert [row["solved"] for row in rows] == [False, False, True]
        assert list((tmp_path / "failed").glob("*.jpg"))
        state = (tmp_path / "state.tsv").read_text()
        assert "\taccepted\t3\t0" in state
    finally:
        proc.terminate()
        proc.wait(timeout=3)
