#!/usr/bin/env python3
"""Issue #321: a plate-solve that times out must leave a duration in the log.

Before this, solve_frame() invoked the solver three ways and recorded nothing about
how long any of them took. "Slow but eventually fine", "burned the whole cpulimit"
and "failed in milliseconds" were indistinguishable, which is exactly the ambiguity
the issue reports.

These tests execute the REAL functions extracted from container/astro/ondisk/polaris-
autosolve.sh against stubbed polaris-extract / polaris-align.sh. They are not source
greps: the assertions run against log output produced by running the shipped code.

Extraction is by function name rather than line number so the tests do not break when
unrelated lines shift.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
AUTOSOLVE = os.path.join(ROOT, "container", "astro", "ondisk", "polaris-autosolve.sh")


def extract_function(name: str) -> str:
    """Return the verbatim POSIX-sh definition of `name` from the shipped script."""
    with open(AUTOSOLVE, "r", encoding="utf-8", errors="replace") as handle:
        lines = handle.read().splitlines()
    start = None
    for i, line in enumerate(lines):
        if re.match(rf"^{re.escape(name)}\(\)\s*{{", line):
            start = i
            break
    if start is None:
        raise AssertionError(f"{name}() not found in {AUTOSOLVE}")
    # Brace counting: the script uses no nested braces inside these two functions,
    # and a column-0 '}' is the terminator in this file's style.
    for j in range(start + 1, len(lines)):
        if lines[j] == "}":
            return "\n".join(lines[start:j + 1])
    raise AssertionError(f"unterminated {name}() in {AUTOSOLVE}")


def build_sandbox(tmp_path, align_stdout: str, align_rc: int = 0) -> dict:
    """A fake $ASTRO with stubbed extract/align, plus the extracted functions."""
    astro = tmp_path / "astro"
    astro.mkdir()

    extract = astro / "polaris-extract"
    extract.write_text(
        "#!/bin/sh\n"
        "printf '# polaris-extract: img.jpg\\n'\n"
        "printf '# full resolution 4000 x 2664\\n'\n"
        "printf '# y-origin: top\\n'\n"
        "printf '10 10 10\\n'\n"
    )
    extract.chmod(0o755)

    align = astro / "polaris-align.sh"
    align.write_text(
        "#!/bin/sh\n"
        f"cat <<'JSON'\n{align_stdout}\nJSON\n"
        f"exit {align_rc}\n"
    )
    align.chmod(0o755)

    frame = tmp_path / "frame.jpg"
    frame.write_text("not a real jpeg, only its size matters\n")

    log_file = tmp_path / "autosolve.log"
    dims_file = tmp_path / "frame-dims"

    harness = tmp_path / "harness.sh"
    harness.write_text(
        "#!/bin/sh\n"
        f"ASTRO={astro}\n"
        f"LOG={log_file}\n"
        f"FRAME_DIMS_FILE={dims_file}\n"
        "FOCAL=50\n"
        ": > \"$LOG\"\n"
        "log() { echo \"12:00:00 $*\" >> \"$LOG\"; }\n"
        "\n"
        + extract_function("pick_downsample")
        + "\n\n"
        + extract_function("solve_frame")
        + "\n\n"
        + 'solve_frame "$1" "$2" "$3" >/dev/null 2>&1\n'
    )
    harness.chmod(0o755)
    return {"harness": str(harness), "log": str(log_file), "frame": str(frame)}


def run_harness(sb, hint_ra: str = "", hint_dec: str = "") -> str:
    proc = subprocess.run(
        ["sh", sb["harness"], sb["frame"], hint_ra, hint_dec],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, f"harness failed: {proc.stderr}"
    with open(sb["log"], "r", encoding="utf-8") as handle:
        return handle.read()


SOLVED = '{"solved":true,"logodds":9.1,"nmatch":42}'
UNSOLVED = '{"solved":false,"logodds":0.2,"nmatch":3}'


def test_pick_downsample_records_dimensions(tmp_path):
    """The dims must land in the side-channel file, and stdout must stay numeric.

    stdout has to remain just the number: keep_failed_frame() calls this as
    $(pick_downsample ...) inside a polaris-extract argument list, so anything extra
    on stdout would corrupt that invocation.
    """
    sb = build_sandbox(tmp_path, SOLVED)
    dims_file = sb["log"].replace("autosolve.log", "frame-dims")

    proc = subprocess.run(
        ["sh", "-c",
         f'. {sb["harness"]} >/dev/null 2>&1 || true'],
        capture_output=True, text=True, timeout=60,
    )
    assert proc is not None  # harness runs solve_frame on its own; ignore here

    # Call the function directly so we can see stdout and the side file separately.
    probe = tmp_path / "probe.sh"
    probe.write_text(
        "#!/bin/sh\n"
        + extract_function("pick_downsample")
        + "\n"
        + f'ASTRO={tmp_path}/astro\nFRAME_DIMS_FILE={dims_file}\n'
        + f'pick_downsample {sb["frame"]}\n'
    )
    probe.chmod(0o755)
    out = subprocess.run(["sh", str(probe)], capture_output=True, text=True, timeout=60)
    assert out.stdout.strip() == "2", (
        f"stdout must stay a bare downsample number, got {out.stdout!r} "
        f"(stderr: {out.stderr[:120]})"
    )
    with open(dims_file, "r", encoding="utf-8") as handle:
        assert handle.read().strip() == "4000 x 2664", (
            "pick_downsample must record 'W x H' for the solve log line"
        )


def test_hinted_solve_logs_duration_and_context(tmp_path):
    """The core of #321: a successful hinted solve reports how long it took."""
    sb = build_sandbox(tmp_path, SOLVED)
    log = run_harness(sb, hint_ra="12.5", hint_dec="-3.2")
    assert re.search(r"solve: hinted ok\s+\d+s", log), (
        f"no duration logged for a successful hinted solve:\n{log}"
    )
    assert "frame=4000 x 2664" in log, (
        f"frame size missing -- a duration is not comparable without it "
        f"(the project's historical 361 s figure was full-res):\n{log}"
    )
    assert "downsample=" in log and "radius=" in log, (
        f"downsample and hint radius must be on the same line:\n{log}"
    )


def test_blind_solve_logs_duration(tmp_path):
    """No hint supplied -> still timed. This is the path that historically took 361 s."""
    sb = build_sandbox(tmp_path, SOLVED)
    log = run_harness(sb, hint_ra="", hint_dec="")
    assert re.search(r"solve: blind\s+\d+s", log), (
        f"no duration logged for a blind solve:\n{log}"
    )
    assert "frame=4000 x 2664" in log, log


def test_hint_miss_then_blind_reports_both_timings(tmp_path):
    """A hinted failure must say how long it burned before retrying blind.

    This is the case the issue describes: a too-narrow hint fails slowly (measured at
    120 s against the simulator), and without a duration the operator cannot tell a
    slow miss from an instant one.
    """
    sb = build_sandbox(tmp_path, UNSOLVED)
    log = run_harness(sb, hint_ra="12.5", hint_dec="-3.2")
    assert re.search(r"hinted solve failed after \d+s", log), (
        f"the hint-miss path must report elapsed time before retrying:\n{log}"
    )
    assert "retrying blind" in log, log
    assert re.search(r"solve: blind \(after hint miss\) \d+s", log), (
        f"the blind retry must also be timed:\n{log}"
    )


def test_functions_parse_under_posix_sh(tmp_path):
    """These run on the Polaris under /bin/sh (busybox/dash), not bash.

    polaris-autosolve.sh declares #!/bin/sh, so a bashism here is a real defect --
    unlike the bash-declaring scripts, which must be parsed with bash.
    """
    for name in ("pick_downsample", "solve_frame"):
        body = extract_function(name)
        probe = tmp_path / f"{name}.sh"
        probe.write_text("#!/bin/sh\nlog() { :; }\n" + body + "\n")
        probe.chmod(0o755)
        proc = subprocess.run(["sh", "-n", str(probe)], capture_output=True, text=True)
        assert proc.returncode == 0, f"{name} is not POSIX-sh clean: {proc.stderr}"


def test_shipped_script_is_executable_in_git():
    """The build preserves git's mode, so a lost exec bit ships broken (issue #292)."""
    proc = subprocess.run(
        ["git", "ls-files", "-s", "container/astro/ondisk/polaris-autosolve.sh"],
        capture_output=True, text=True, cwd=ROOT,
    )
    mode = proc.stdout.split()[0] if proc.stdout.split() else ""
    assert mode == "100755", f"expected 100755 in git, got {mode!r}"
