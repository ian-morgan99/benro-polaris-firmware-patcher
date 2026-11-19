"""Protect shared checkout state and immutable camera-packet publication."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile


REPO = Path(__file__).resolve().parents[1]
UPLOADER = Path(".github/skills/fwpkt-private-upload/scripts/upload-fwpkt-to-pr.sh")
CANDIDATE = "camera-test"
VERSION = "6.0.0.54.1"
DESTINATION = Path(f"firmware-packets/{VERSION}--{CANDIDATE}/FwPkt.zip")


def git(*args, cwd, env):
    return subprocess.check_output(
        ["git", *args], cwd=cwd, env=env, text=True, stderr=subprocess.PIPE,
    ).strip()


def write_packet(build, contents):
    checksum = hashlib.md5(contents).hexdigest()
    with zipfile.ZipFile(build / "FwPkt.zip", "w") as packet:
        packet.writestr("FwPkt/camera/appfs.ubifs", contents)
        packet.writestr(
            "FwPkt/firmwareInfo", f"appfs size:{len(contents)};appfs MD5:{checksum};\n"
        )


def test_uploader_preserves_local_work_and_published_bytes(tmp_path):
    env = dict(os.environ, GIT_AUTHOR_NAME="Release test", GIT_AUTHOR_EMAIL="test@example.invalid",
               GIT_COMMITTER_NAME="Release test", GIT_COMMITTER_EMAIL="test@example.invalid")
    for name in ("GH_TOKEN", "PR_CHECKOUT"):
        env.pop(name, None)
    remote = tmp_path / "remote"
    remote.mkdir()
    git("init", "--bare", "--initial-branch=main", cwd=remote, env=env)
    env["PR_REPO"] = remote.as_uri()

    shared = tmp_path / "shared"
    git("clone", env["PR_REPO"], str(shared), cwd=tmp_path, env=env)
    notes = shared / "notes"
    notes.write_text("published\n")
    git("add", "notes", cwd=shared, env=env)
    git("commit", "-m", "initial", cwd=shared, env=env)
    git("push", "origin", "main", cwd=shared, env=env)

    patcher = tmp_path / "patcher"
    uploader = patcher / UPLOADER
    uploader.parent.mkdir(parents=True)
    shutil.copyfile(REPO / UPLOADER, uploader)
    # Isolate the publication logic. The release suite covers package validation.
    for gate in ("scripts/verify-candidate-identity.py", "container/validate_fw_package.py"):
        path = patcher / gate
        path.parent.mkdir()
        path.write_text("raise SystemExit(0)\n")

    build = tmp_path / CANDIDATE
    build.mkdir()
    write_packet(build, b"first appfs")
    manifest = {
        "candidate_id": CANDIDATE,
        "display_fwver": VERSION,
        "source": {"head_commit": "a" * 40},
        "patcher": {"head_commit": "b" * 40},
    }
    (build / "release-change-manifest.json").write_text(json.dumps(manifest))
    (build / "RELEASE-IDENTITY.md").write_text("exact build identity\n")

    def upload(**overrides):
        return subprocess.run(
            ["bash", str(uploader), "--build", str(build), "--id", CANDIDATE],
            env=dict(env, **overrides), capture_output=True, text=True, check=False,
        )

    notes.write_text("uncommitted edit\n")
    dirty = upload(PR_CHECKOUT=str(shared))
    assert dirty.returncode != 0 and "contains local changes" in dirty.stderr
    assert notes.read_text() == "uncommitted edit\n"

    git("add", "notes", cwd=shared, env=env)
    git("commit", "-m", "local work", cwd=shared, env=env)
    unpublished = git("rev-parse", "HEAD", cwd=shared, env=env)
    ahead = upload(PR_CHECKOUT=str(shared))
    assert ahead.returncode != 0 and "has unpublished commits" in ahead.stderr
    assert git("rev-parse", "HEAD", cwd=shared, env=env) == unpublished

    published = upload()
    assert published.returncode == 0, published.stderr
    remote_head = git("rev-parse", "main", cwd=remote, env=env)
    original = git("rev-parse", f"main:{DESTINATION.as_posix()}", cwd=remote, env=env)

    repeated = upload()
    assert repeated.returncode == 0 and "already published" in repeated.stdout

    write_packet(build, b"different appfs")
    conflict = upload()
    assert conflict.returncode != 0 and "refusing to replace published bytes" in conflict.stderr
    assert git("rev-parse", "main", cwd=remote, env=env) == remote_head
    assert git("rev-parse", f"main:{DESTINATION.as_posix()}", cwd=remote, env=env) == original
    assert git("rev-parse", "HEAD", cwd=shared, env=env) == unpublished
