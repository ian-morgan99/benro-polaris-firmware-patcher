"""Tests for scripts/verify-candidate-differential.py (#214 follow-up).

The fixtures are real: the `.68` and `.69` manifests are copied out of `out/` so the
gate is exercised against the exact bytes it must reason about in production. The
`.70`-style cases are synthesised by editing only the version string, which is precisely
the mistake the gate exists to catch.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify-candidate-differential.py"
OUT = ROOT / "out"


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, timeout=60, cwd=str(ROOT),
    )


def make_candidate(tmp_path: Path, name: str, fwver: str, digests: dict[str, str]) -> Path:
    d = tmp_path / name
    d.mkdir(parents=True)
    files = [{"path": p, "sha256": s, "size": 1} for p, s in sorted(digests.items())]
    (d / "install-manifest.json").write_text(
        json.dumps({
            "schema": 1,
            "candidate": name,
            "zip": {"sha256": "0" * 64, "size": 1},
            "fwver_content": f"FwVer:{fwver};date:2026.10.24;",
            "stage2_mandatory": True,
            "files": files,
        }, indent=1),
        encoding="utf-8",
    )
    return d


BASE = {
    "/app/FwVer": "a" * 64,
    "/app/bin/polestar_app": "b" * 64,
    "/app/lib/stage2/pgphoto.stage2ondisk": "c" * 64,
    "/app/lib/stage2/libpolaris_stage2.so": "d" * 64,
    "/app/lib/stage2/libgphoto2.so.6": "e" * 64,
    "/app/lib/stage2/libgphoto2_port.so.12": "f" * 64,
    "/app/lib/stage2/libgphoto2/2.5.34/ptp2.so": "1" * 64,
    "/app/lib/stage2/libgphoto2/2.5.34/pentax.so": "2" * 64,
    "/app/lib/stage2/libgphoto2_port/0.12.2/usb1.so": "3" * 64,
    "/app/openpolaris-libgphoto2-provenance.txt": "4" * 64,
}


def test_identical_shipped_bytes_with_new_version_fails(tmp_path):
    """The `.70` trap: version advances, every shipped file is unchanged."""
    prev = make_candidate(tmp_path, "o-v17d", "6.0.0.54.69", BASE)
    cur = make_candidate(tmp_path, "o-v18a", "6.0.0.54.70", dict(BASE))
    proc = run("--previous", str(prev), "--current", str(cur))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "byte-identical" in proc.stdout


def test_same_version_on_two_candidates_fails(tmp_path):
    prev = make_candidate(tmp_path, "o-v17d", "6.0.0.54.69", BASE)
    cur = make_candidate(tmp_path, "o-v17e", "6.0.0.54.69", dict(BASE))
    proc = run("--previous", str(prev), "--current", str(cur))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "same display version" in proc.stdout


def test_single_component_change_passes(tmp_path):
    cur_digests = dict(BASE)
    cur_digests["/app/lib/stage2/libgphoto2/2.5.34/ptp2.so"] = "9" * 64
    prev = make_candidate(tmp_path, "o-v17d", "6.0.0.54.69", BASE)
    cur = make_candidate(tmp_path, "o-v18a", "6.0.0.54.70", cur_digests)
    proc = run("--previous", str(prev), "--current", str(cur))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "WARN" not in proc.stdout


def test_two_components_warn_and_name_them(tmp_path):
    """What `.69` actually did: `ptp2.so` and the loader both moved under one version."""
    cur_digests = dict(BASE)
    cur_digests["/app/lib/stage2/libgphoto2/2.5.34/ptp2.so"] = "9" * 64
    cur_digests["/app/lib/stage2/libpolaris_stage2.so"] = "8" * 64
    prev = make_candidate(tmp_path, "o-v17c", "6.0.0.54.68", BASE)
    cur = make_candidate(tmp_path, "o-v17d", "6.0.0.54.69", cur_digests)
    proc = run("--previous", str(prev), "--current", str(cur))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "WARN" in proc.stdout
    assert "ptp2.so" in proc.stdout and "libpolaris_stage2.so" in proc.stdout


def test_strict_mode_turns_the_warning_into_a_failure(tmp_path):
    cur_digests = dict(BASE)
    cur_digests["/app/lib/stage2/libgphoto2/2.5.34/ptp2.so"] = "9" * 64
    cur_digests["/app/lib/stage2/libpolaris_stage2.so"] = "8" * 64
    prev = make_candidate(tmp_path, "o-v17c", "6.0.0.54.68", BASE)
    cur = make_candidate(tmp_path, "o-v17d", "6.0.0.54.69", cur_digests)
    proc = run("--strict", "--previous", str(prev), "--current", str(cur))
    assert proc.returncode == 1, proc.stdout + proc.stderr


def test_missing_mandatory_file_fails(tmp_path):
    shrunk = {k: v for k, v in BASE.items() if not k.endswith("usb1.so")}
    prev = make_candidate(tmp_path, "o-v17d", "6.0.0.54.69", BASE)
    cur = make_candidate(tmp_path, "o-v18a", "6.0.0.54.70", shrunk)
    proc = run("--previous", str(prev), "--current", str(cur))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "mandatory file set differs" in proc.stdout


def test_missing_manifest_is_a_failure_not_a_skip(tmp_path):
    empty = tmp_path / "o-v18a"
    empty.mkdir()
    prev = make_candidate(tmp_path, "o-v17d", "6.0.0.54.69", BASE)
    proc = run("--previous", str(prev), "--current", str(empty))
    assert proc.returncode == 1
    assert "no install-manifest.json" in proc.stderr


def test_auto_detect_ignores_rejected_directories(tmp_path, monkeypatch):
    """A REJECTED_* directory must never be chosen as the comparison baseline."""
    good = make_candidate(tmp_path, "o-v17d", "6.0.0.54.69", BASE)
    bad = make_candidate(tmp_path, "REJECTED-o-v17e", "6.0.0.54.70", dict(BASE))
    # touch the rejected one last so mtime ordering would otherwise prefer it
    os.utime(bad / "install-manifest.json", (9_999_999_999, 9_999_999_999))
    cur = make_candidate(tmp_path, "o-v18a", "6.0.0.54.70",
                         {**BASE, "/app/lib/stage2/libgphoto2/2.5.34/ptp2.so": "7" * 64})
    import importlib.util

    spec = importlib.util.spec_from_file_location("vcd", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    picked = mod.auto_previous(str(tmp_path), str(cur))
    assert os.path.basename(picked) == "o-v17d"


@pytest.mark.skipif(
    not (OUT / "o-v17c-colortemp-formless" / "install-manifest.json").is_file()
    or not (OUT / "o-v17d-darkframe-budget-20261023" / "install-manifest.json").is_file(),
    reason="real .68/.69 candidate manifests not present in out/",
)
def test_real_68_to_69_history_is_detected():
    """Ground truth: `.69` moved both `ptp2.so` and the loader under one version."""
    proc = run(
        "--previous", str(OUT / "o-v17c-colortemp-formless"),
        "--current", str(OUT / "o-v17d-darkframe-budget-20261023"),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "WARN" in proc.stdout
    for needle in ("ptp2.so", "libpolaris_stage2.so"):
        assert needle in proc.stdout
