from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "canary_file_check", ROOT / "scripts" / "canary-probe.py"
)
assert SPEC and SPEC.loader
CANARY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CANARY)


def completed(returncode: int = 0, stdout: str = "", stderr: str = ""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def test_file_check_snapshots_then_returns_only_new_paths(monkeypatch):
    replies = iter([
        completed(stdout="/app/sd/normal/SP_0001.dng\n"),
        completed(stdout=("/app/sd/normal/SP_0001.dng\n"
                          "/app/sd/normal/SP_0002.dng\n"
                          "/app/sd/normal/SP_0002.jpg\n")),
    ])
    monkeypatch.setattr(CANARY.subprocess, "run", lambda *a, **k: next(replies))
    check = CANARY.DeviceFileCheck("root@polaris", "/app/sd/normal")

    check.arm()
    assert check.new_files() == [
        "/app/sd/normal/SP_0002.dng",
        "/app/sd/normal/SP_0002.jpg",
    ]
    check.disarm()
    assert check.before_files is None


def test_failed_baseline_keeps_verdict_unknown(monkeypatch):
    calls = []

    def run(*args, **kwargs):
        calls.append(args)
        return completed(returncode=1, stderr="permission denied")

    monkeypatch.setattr(CANARY.subprocess, "run", run)
    check = CANARY.DeviceFileCheck("root@polaris", "/app/sd/normal")
    check.arm()

    assert check.before_files is None
    assert check.new_files() is None
    assert len(calls) == 1


def test_failed_query_is_unknown_even_with_partial_stdout(monkeypatch):
    replies = iter([
        completed(stdout="/app/sd/normal/SP_old.dng\n"),
        completed(returncode=1, stdout="/app/sd/normal/SP_new.dng\n",
                  stderr="find failed"),
    ])
    monkeypatch.setattr(CANARY.subprocess, "run", lambda *a, **k: next(replies))
    check = CANARY.DeviceFileCheck("root@polaris", "/app/sd/normal")
    check.arm()

    assert check.new_files() is None


def test_output_directory_is_shell_quoted_for_remote_find(monkeypatch):
    calls = []
    monkeypatch.setattr(
        CANARY.subprocess,
        "run",
        lambda args, **kwargs: calls.append(args) or completed(),
    )
    check = CANARY.DeviceFileCheck(
        "root@polaris", "/app/sd/normal; touch /tmp/should-not-run",
        ssh_options=["ssh"],
    )
    check.arm()

    assert calls[0][-1] == (
        "find '/app/sd/normal; touch /tmp/should-not-run' -type f 2>/dev/null"
    )


def test_only_complete_same_stem_sp_file_sets_satisfy_contract():
    raw_jpeg = [
        "/app/sd/normal/SP_0042.dng",
        "/app/sd/normal/SP_0042.jpg",
        "/app/sd/normal/other.log",
    ]
    assert CANARY.expected_output_files(raw_jpeg, 2) == raw_jpeg[:2]
    assert CANARY.expected_output_files([raw_jpeg[0]], 1) == [raw_jpeg[0]]
    assert CANARY.expected_output_files([raw_jpeg[1]], 1) == [raw_jpeg[1]]
    assert CANARY.expected_output_files(raw_jpeg[:1], 2) is None
    assert CANARY.expected_output_files(
        ["/app/sd/normal/SP_0042.dng", "/app/sd/normal/SP_0043.jpg"], 2
    ) is None
    assert CANARY.expected_output_files(
        ["/app/sd/normal/other.log"], 1
    ) is None


def test_timeout_inventory_requires_complete_expected_output_set():
    class FakeInventory:
        before_files = {"/app/sd/normal/existing.dng"}

        def __init__(self, replies):
            self.replies = iter(replies)

        def new_files(self, timeout=30.0):
            return next(self.replies)

    raw_jpeg = ["/app/sd/normal/SP_0042.dng", "/app/sd/normal/SP_0042.jpg"]
    observed, new_paths, complete = CANARY.wait_for_expected_output_set(
        FakeInventory([raw_jpeg]), 2, 0
    )
    assert observed and new_paths == raw_jpeg and complete == raw_jpeg

    observed, new_paths, complete = CANARY.wait_for_expected_output_set(
        FakeInventory([raw_jpeg[:1]]), 2, 0
    )
    assert observed and new_paths == raw_jpeg[:1] and complete is None


def test_poll_commands_are_bounded_by_the_remaining_wait_budget(monkeypatch):
    clock = [0.0]
    query_timeouts = []

    class EmptyInventory:
        before_files = set()

        def new_files(self, timeout=30.0):
            query_timeouts.append(timeout)
            return []

    monkeypatch.setattr(CANARY.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        CANARY.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds)
    )
    observed, new_paths, complete = CANARY.wait_for_expected_output_set(
        EmptyInventory(), 2, 2.5
    )

    assert observed and new_paths == [] and complete is None
    assert query_timeouts == [2.5, 0.5]
    assert clock[0] == 2.5


def test_unknown_inventory_is_not_reported_as_no_file():
    class NoBaseline:
        before_files = None

        def new_files(self):
            raise AssertionError("unknown baseline must not be queried")

    assert CANARY.wait_for_expected_output_set(NoBaseline(), 1, 20) == (
        False, [], None
    )


def test_disabled_file_check_never_runs_ssh(monkeypatch):
    def unexpected_run(*_args, **_kwargs):
        raise AssertionError("disabled file check must not invoke SSH")

    monkeypatch.setattr(CANARY.subprocess, "run", unexpected_run)
    check = CANARY.DeviceFileCheck(None, "/app/sd/normal")
    check.arm()

    assert check.new_files() is None


def test_non_finite_file_check_wait_is_rejected_before_connecting():
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "canary-probe.py"),
            "--probe",
            "--file-check-wait",
            "nan",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )

    assert result.returncode == 2
    assert "file-check-wait must be finite and non-negative" in result.stderr
