import importlib.util
import hashlib
import json
import zipfile
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "verify-candidate-identity.py"
SPEC = importlib.util.spec_from_file_location("verify_candidate_identity", SCRIPT)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def make_candidate(tmp_path: Path, with_manifest: bool = True) -> Path:
    candidate = tmp_path / "o-test-candidate"
    fwpkt = candidate / "FwPkt"
    for relative in MOD.REQUIRED_PAYLOAD:
        path = fwpkt / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"payload\n")
    (fwpkt / "FwVer").write_text(
        "FwVer:6.0.0.54.99;date:2026.10.28;\n", encoding="utf-8"
    )
    (fwpkt / "firmwareInfo").write_text("config size:8;config MD5:deadbeef;\n", encoding="utf-8")
    candidate.mkdir(exist_ok=True)
    (candidate / "build-source-provenance.txt").write_text(
        "\n".join(
            [
                "source_kind=git-directory",
                "actual_version=2.5.34",
                "git_commit=" + "a" * 40,
                "dirty_diff_hash=",
                "input_sha256=",
                "vanilla_source_explicit=0",
                "patcher_commit=" + "b" * 40,
                "patcher_dirty_diff_hash=",
                "selected_camlibs=ptp2,pentax",
                "build_id=6.0.0.54.99-o-test-candidate",
                "display_fwver=6.0.0.54.99",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    with zipfile.ZipFile(candidate / "FwPkt.zip", "w") as archive:
        for path in sorted(fwpkt.rglob("*")):
            if path.is_file():
                archive.write(path, Path("FwPkt") / path.relative_to(fwpkt))
    zip_path = candidate / "FwPkt.zip"
    change_manifest = {
        "schema": 1,
        "candidate_id": candidate.name,
        "display_fwver": "6.0.0.54.99",
        "build_id": "6.0.0.54.99-o-test-candidate",
        "purpose": "identity verifier fixture",
        "declared_changes": [{"component": "tests", "summary": "fixture"}],
        "known_limits": [],
        "validation_focus": [],
        "baseline": {
            "candidate_id": "fixture-base",
            "libgphoto2_commit": "a" * 40,
            "patcher_commit": "b" * 40,
        },
        "source": {
            "repository": "libgphoto2",
            "branch": "main",
            "head_commit": "a" * 40,
            "commits_since_baseline": [],
        },
        "patcher": {
            "repository": "benro-polaris-firmware-patcher",
            "branch": "main",
            "head_commit": "b" * 40,
            "commits_since_baseline": [],
        },
        "artifact": {
            "stock_fwpkt_sha256": "0" * 64,
            "fwpkt_zip_path": str(zip_path),
            "fwpkt_zip_sha256": MOD.sha256_file(zip_path),
            "fwpkt_zip_md5": hashlib.md5(zip_path.read_bytes()).hexdigest(),
            "appfs_md5": "0" * 32,
            "change_summary_path": "fixture.json",
        },
        "lifecycle": {
            "built": True,
            "offline_gated": False,
            "published": False,
            "installed_verified": False,
            "physically_qualified": False,
        },
    }
    change_path = candidate / "release-change-manifest.json"
    change_path.write_text(json.dumps(change_manifest) + "\n", encoding="utf-8")
    with (candidate / "build-source-provenance.txt").open("a", encoding="utf-8") as stream:
        stream.write(
            "candidate_id=" + candidate.name + "\n"
            "release_change_manifest=release-change-manifest.json\n"
            "release_change_manifest_sha256=" + MOD.sha256_file(change_path) + "\n"
        )
    if with_manifest:
        zip_path = candidate / "FwPkt.zip"
        manifest = {
            "schema": 1,
            "candidate": candidate.name,
            "zip": {
                "sha256": MOD.sha256_file(zip_path),
                "size": zip_path.stat().st_size,
            },
            "files": [{"path": "/app/FwVer", "sha256": "0" * 64, "size": 1}],
        }
        (candidate / "install-manifest.json").write_text(
            json.dumps(manifest) + "\n", encoding="utf-8"
        )
    return candidate


def test_complete_candidate_is_deployable(tmp_path):
    candidate = make_candidate(tmp_path)
    assert MOD.validate_candidate(candidate, require_deployable=True) == []


def test_missing_manifest_is_coherent_smoke_but_not_deployable(tmp_path):
    candidate = make_candidate(tmp_path, with_manifest=False)
    assert MOD.validate_candidate(candidate, require_deployable=False) == []
    errors = MOD.validate_candidate(candidate, require_deployable=True)
    assert any("install-manifest.json missing" in error for error in errors)


def test_manifest_cannot_describe_different_zip(tmp_path):
    candidate = make_candidate(tmp_path)
    manifest = json.loads((candidate / "install-manifest.json").read_text())
    manifest["zip"]["sha256"] = "f" * 64
    (candidate / "install-manifest.json").write_text(json.dumps(manifest) + "\n")
    errors = MOD.validate_candidate(candidate, require_deployable=True)
    assert any("ZIP SHA-256 mismatch" in error for error in errors)

