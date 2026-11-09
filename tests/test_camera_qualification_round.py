"""Tests for scripts/camera-qualification-round.py (issue #293 Phase 4).

The harness exists because the camera issues in #293 (#275 preview, #276 shutter, #277
ISO, #278 AF, #279 capture, #251 Bulb, #285 crash) each accumulated their own probe and
none of them preserved the bytes behind their verdict. Measured over docs/evidence before
writing it: #275/#276/#277 all quote `ret:-2110` lines dated 2026-11-08, and that literal
appears **zero** times in the archive -- the session was never pulled, so the most quoted
evidence for the control failures cannot be re-examined.

These tests do not need a camera. They pin the properties that make the harness safe to
run against real hardware:

  * an unreachable device yields BLOCKED for every case, never a silent pass;
  * Bulb cases refuse to run without --i-am-present, because #293 forbids unattended
    Bulb tests and cancellation is a safety release blocker;
  * the log parser counts the markers pgphoto actually emits. Aperture is SP_SET_FNUM --
    searching for SP_SET_APERTURE returns nothing and reads as "aperture was never
    exercised", which is exactly how an earlier survey misreported it;
  * the analyzer is non-vacuous on real archived bytes, so a parser bug cannot report
    "no evidence" when evidence exists.

The last two groups run against docs/evidence, which is committed, so they need no device
and no network.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPT = os.path.join(ROOT, "scripts", "camera-qualification-round.py")
EVIDENCE = os.path.join(ROOT, "docs", "evidence")


def _load():
    spec = importlib.util.spec_from_file_location("camqual", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["camqual"] = module
    spec.loader.exec_module(module)
    return module


camqual = _load()


def run(*args, timeout=300):
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True,
                          text=True, timeout=timeout)


# ── safety gates ────────────────────────────────────────────────────────────────────

def test_plan_touches_no_device():
    """--plan must enumerate every WBS-04 item without contacting anything."""
    proc = run("--plan")
    assert proc.returncode == 0, proc.stderr
    for wbs in ("WBS-04.1", "WBS-04.2", "WBS-04.3", "WBS-04.4", "WBS-04.4b",
                "WBS-04.5", "WBS-04.6", "WBS-04.7"):
        assert wbs in proc.stdout, f"{wbs} missing from plan"


def test_bulb_refuses_without_human_presence():
    """#293: 'No unattended Bulb tests.' --with-bulb alone must not fire one."""
    with tempfile.TemporaryDirectory() as tmp:
        proc = run("--host", "203.0.113.198", "--ssh-host", "root@203.0.113.198",
                   "--outdir", tmp, "--with-bulb")
    assert proc.returncode == 0, proc.stderr
    assert "without --i-am-present" in proc.stdout, (
        "Bulb case ran without asserting a human can interrupt the shutter")


def test_bulb_skipped_without_flag():
    with tempfile.TemporaryDirectory() as tmp:
        proc = run("--host", "203.0.113.198", "--ssh-host", "root@203.0.113.198",
                   "--outdir", tmp)
    assert "Bulb requires --with-bulb" in proc.stdout


def test_exposure_cap_is_inherited_not_reinvented():
    """The cap must come from canary-probe so the two tools cannot disagree."""
    with tempfile.TemporaryDirectory() as tmp:
        proc = run("--plan", "--outdir", tmp)
    assert "exposure cap" in proc.stdout
    assert str(camqual.cp.MAX_TEST_EXPOSURE_SECONDS) in proc.stdout


def test_device_output_dir_matches_canary_probe_default():
    """#305: WBS-04.6 baselined /tmp, where the device writes nothing.

    A check pointed at a directory the body never writes to reports "no new file"
    for a capture that succeeded -- a false FAIL attributed to the camera. The two
    tools must agree on the path the same way they agree on the exposure cap.
    """
    assert camqual.DEVICE_OUTPUT_DIR == "/app/sd/normal"
    probe = os.path.join(ROOT, "scripts", "canary-probe.py")
    src = open(probe, encoding="utf-8").read()
    m = re.search(r'--output-dir",\s*default="([^"]+)"', src)
    assert m, "canary-probe --output-dir default not found"
    assert camqual.DEVICE_OUTPUT_DIR == m.group(1), (
        f"round baselines {camqual.DEVICE_OUTPUT_DIR} but canary-probe defaults "
        f"to {m.group(1)}")


def test_wbs_04_6_constructs_its_file_checker(monkeypatch):
    """#305: WBS-04.6 had never executed, yet the suite was green.

    It passed ``expected_files=`` to a constructor that does not accept it and
    called the ``enabled`` property as a method. Both raise TypeError, so the case
    died before sending a shutter command -- and no test built the checker the way
    the round does, so nothing noticed.

    This stubs reachability true and the socket path false. Reaching the
    "9090 unreachable" BLOCKED verdict proves the checker was constructed and its
    ``enabled`` gate read without raising; before the fix this raised TypeError.
    """
    monkeypatch.setattr(camqual, "device_reachable", lambda host: (True, "stubbed"))

    def refuse(*_a, **_k):
        raise OSError("stub: no socket")

    monkeypatch.setattr(camqual, "connect", refuse)

    class NullRecorder:
        def line(self, *_a, **_k):
            pass

        def case(self, *_a, **_k):
            pass

    rec = camqual.case_wbs_04_6(NullRecorder(), "203.0.113.198", "root@203.0.113.198")
    assert rec["status"] == "BLOCKED", rec
    assert "9090 unreachable" in rec["reason"], (
        f"case never reached the socket step, so the checker gate was not exercised: {rec}")


# ── honest degradation ──────────────────────────────────────────────────────────────

def test_unreachable_device_yields_blocked_never_pass():
    """The single most important property: no camera must never read as a pass.

    Uses TEST-NET-3 (203.0.113.0/24), reserved for documentation, so nothing is
    contacted even if routing changes.
    """
    with tempfile.TemporaryDirectory() as tmp:
        proc = run("--host", "203.0.113.198", "--ssh-host", "root@203.0.113.198",
                   "--outdir", tmp)
    assert proc.returncode == 0, proc.stderr
    summary = re.search(r"SUMMARY (\{.*\})", proc.stdout)
    assert summary, f"no SUMMARY line in:\n{proc.stdout}"
    counts = json.loads(summary.group(1))
    assert set(counts) == {"BLOCKED"}, (
        f"unreachable device produced non-BLOCKED statuses: {counts}")
    assert sum(counts.values()) == 8, "every case must report, none may be dropped"
    for bad in ("DEVICE_VERIFIED", "OFFLINE_VERIFIED", "PASS"):
        assert bad not in counts


def test_bundle_is_written_even_when_everything_fails():
    """Evidence preservation is the point of the tool; a failed round must still bundle."""
    with tempfile.TemporaryDirectory() as tmp:
        proc = run("--host", "203.0.113.198", "--ssh-host", "root@203.0.113.198",
                   "--outdir", tmp)
        bundles = [n for n in os.listdir(tmp) if n.endswith(".tar.gz")]
    assert "BUNDLE" in proc.stdout, proc.stdout
    assert bundles, "no bundle written despite the round completing"


# ── marker correctness ──────────────────────────────────────────────────────────────

def test_aperture_marker_is_fnum_not_aperture():
    """pgphoto emits SP_SET_FNUM for aperture. There is no SP_SET_APERTURE.

    An earlier survey grepped SP_SET_APERTURE, got zero, and read that as "aperture was
    never exercised" when the archive in fact holds successful aperture writes. The
    harness must use the real marker or it will silently under-report again.
    """
    assert camqual.CONTROL_MARKERS["aperture"] == "SP_SET_FNUM"
    assert "SP_SET_APERTURE" not in json.dumps(camqual.CONTROL_MARKERS)


def test_control_markers_are_the_ones_in_real_logs():
    """Every marker the harness counts must actually occur in the committed archive."""
    if not os.path.isdir(EVIDENCE):
        raise AssertionError("docs/evidence missing; cannot validate markers")
    blob = []
    for dirpath, _dirs, files in os.walk(EVIDENCE):
        for name in files:
            if re.match(r"^(Mlog|Clog)", name):
                with open(os.path.join(dirpath, name), "r", encoding="utf-8",
                          errors="replace") as fh:
                    blob.append(fh.read())
    text = "\n".join(blob)
    assert text, "no Mlog/Clog bytes found to validate against"
    for control, marker in camqual.CONTROL_MARKERS.items():
        assert re.search(rf"{marker}\s+(OK|FAIL)", text), (
            f"{control}: marker {marker} never appears in real logs")


# ── non-vacuous analysis of real bytes ──────────────────────────────────────────────

def test_analyzer_finds_real_control_results():
    """A parser bug must not be able to report 'no evidence' when evidence exists."""
    target = None
    for dirpath, _dirs, files in os.walk(EVIDENCE):
        if any(re.match(r"^(Mlog|Clog)", n) for n in files) and \
                any("SP_SET_SHUTTER OK" in open(os.path.join(dirpath, n),
                                                encoding="utf-8", errors="replace")
                        .read() for n in files if re.match(r"^(Mlog|Clog)", n)):
            target = dirpath
            break
    assert target, "no archived log contains SP_SET_SHUTTER OK to validate against"

    proc = run("--analyze-only", target)
    assert proc.returncode == 0, proc.stderr
    ok = re.search(r"controls OK=(\d+)", proc.stdout)
    assert ok and int(ok.group(1)) > 0, (
        f"analyzer reported no successful writes in a directory that contains them:\n"
        f"{proc.stdout}")


def test_crash_and_control_success_coexist_in_archive():
    """#285 claims the segfault 'explains ALL the previously observed failures'.

    That is testable offline and is false: SP_SET_ISO OK and SP_SET_SHUTTER OK both exist
    in the archive, and each requires a pgphoto that was alive and completing writes. If
    this ever stops holding, the collapse assumption becomes worth re-testing -- so the
    assertion is pinned here rather than left as prose.
    """
    text = []
    for dirpath, _dirs, files in os.walk(EVIDENCE):
        for name in files:
            if re.match(r"^(Mlog|Clog)", name):
                with open(os.path.join(dirpath, name), "r", encoding="utf-8",
                          errors="replace") as fh:
                    text.append(fh.read())
    blob = "\n".join(text)
    assert re.search(r"SP_SET_ISO\s+OK", blob), "expected a successful ISO write"
    assert re.search(r"SP_SET_SHUTTER\s+OK", blob), "expected a successful shutter write"


def test_opcodes_come_from_observed_traffic():
    """Opcodes must match what the app actually sent, not a guess.

    These were read out of code[NNN],val[...] lines in docs/evidence. A wrong opcode would
    make every control case silently exercise nothing and report not-applied.
    """
    text = []
    for dirpath, _dirs, files in os.walk(EVIDENCE):
        for name in files:
            if re.match(r"^(Mlog|Clog)", name):
                with open(os.path.join(dirpath, name), "r", encoding="utf-8",
                          errors="replace") as fh:
                    text.append(fh.read())
    blob = "\n".join(text)
    for control, opcode in (("iso", 258), ("wb", 259), ("ev", 260), ("shutter", 261)):
        assert camqual.OPCODES[control] == opcode
        assert f"code[{opcode}],val[{control}" in blob or \
               f"code[{opcode}],val[s" in blob, (
            f"{control}: opcode {opcode} never observed in archived app traffic")


def test_keep_lv_ab_is_reported_not_faked():
    """#293 asks for a STAGE2_PENTAX_KEEP_LV=0 A/B. The tool must not pretend to run it.

    Performing that A/B means restarting pgphoto, which tears down the live camera session
    and invalidates every other case's evidence in the same round. The honest behaviour is
    to record what the running process actually has and hand back the manual procedure -- so
    a flag that implied an automated restart was removed rather than left as a no-op.
    """
    import inspect

    src = inspect.getsource(camqual.case_wbs_04_2)
    assert "next_action" in src, "case must state the A/B it did not perform"
    assert "--ab-keep-lv" not in src, (
        "a flag implying an automated pgphoto restart must not exist unless it does it")
    # The env read must target the real process environment, not a guess.
    env_src = inspect.getsource(camqual._pgphoto_env)
    assert "/proc/" in env_src and "environ" in env_src


def test_syntax_and_compilation():
    import py_compile
    with tempfile.NamedTemporaryFile(suffix=".pyc", delete=False) as tmp:
        py_compile.compile(SCRIPT, cfile=tmp.name, doraise=True)
