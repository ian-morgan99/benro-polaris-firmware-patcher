from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "create-release-change-manifest.py"


def run(*args: str, cwd: Path | None = None) -> str:
    return subprocess.check_output(
        list(args), cwd=cwd, text=True, stderr=subprocess.STDOUT
    ).strip()


def make_git_repo(path: Path, name: str) -> tuple[Path, str, str]:
    repo = path / name
    repo.mkdir()
    run("git", "init", "-b", "main", str(repo))
    run("git", "-C", str(repo), "config", "user.email", "test@example.invalid")
    run("git", "-C", str(repo), "config", "user.name", "Test")
    (repo / "file.txt").write_text("baseline\n", encoding="utf-8")
    run("git", "-C", str(repo), "add", "file.txt")
    run("git", "-C", str(repo), "commit", "-m", "baseline")
    baseline = run("git", "-C", str(repo), "rev-parse", "HEAD")
    (repo / "file.txt").write_text("candidate\n", encoding="utf-8")
    run("git", "-C", str(repo), "commit", "-am", "candidate change")
    head = run("git", "-C", str(repo), "rev-parse", "HEAD")
    return repo, baseline, head


def test_manifest_records_exact_commit_ranges_and_artifact_hashes(tmp_path: Path):
    lib, lib_base, lib_head = make_git_repo(tmp_path, "libgphoto2")
    patcher, patcher_base, patcher_head = make_git_repo(tmp_path, "patcher")
    stock = tmp_path / "stock.zip"
    stock.write_bytes(b"stock input\n")

    candidate = tmp_path / "candidate"
    fwpkt = candidate / "FwPkt"
    fwpkt.mkdir(parents=True)
    (fwpkt / "FwVer").write_text("FwVer:6.0.0.54.99;date:2026.10.28;\n", encoding="utf-8")
    (fwpkt / "firmwareInfo").write_text(
        "appfs size:1;appfs MD5:0123456789abcdef0123456789abcdef;\n",
        encoding="utf-8",
    )
    candidate_zip = candidate / "FwPkt.zip"
    with zipfile.ZipFile(candidate_zip, "w") as archive:
        for path in fwpkt.rglob("*"):
            archive.write(path, Path("FwPkt") / path.relative_to(fwpkt))
    (candidate / "build-source-provenance.txt").write_text("build\n", encoding="utf-8")

    summary = tmp_path / "summary.json"
    summary.write_text(
        json.dumps(
            {
                "baseline": {
                    "candidate_id": "previous",
                    "libgphoto2_commit": lib_base,
                    "patcher_commit": patcher_base,
                },
                "purpose": "test exact identity",
                "changes": [
                    {"component": "libgphoto2", "summary": "candidate change", "issues": ["#1"]}
                ],
                "validation_focus": ["identity"],
                "known_limits": ["not hardware qualified"],
            }
        ),
        encoding="utf-8",
    )

    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--summary",
            str(summary),
            "--candidate-id",
            candidate.name,
            "--display-fwver",
            "6.0.0.54.99",
            "--build-id",
            "6.0.0.54.99-test",
            "--libgphoto2",
            str(lib),
            "--patcher",
            str(patcher),
            "--stock",
            str(stock),
            "--candidate-dir",
            str(candidate),
        ],
        check=True,
        text=True,
    )
    manifest = json.loads((candidate / "release-change-manifest.json").read_text())
    assert manifest["source"]["head_commit"] == lib_head
    assert [item["sha"] for item in manifest["source"]["commits_since_baseline"]] == [lib_head]
    assert manifest["patcher"]["head_commit"] == patcher_head
    assert [item["sha"] for item in manifest["patcher"]["commits_since_baseline"]] == [patcher_head]
    assert manifest["artifact"]["stock_fwpkt_sha256"]
    assert (candidate / "RELEASE-IDENTITY.md").is_file()

