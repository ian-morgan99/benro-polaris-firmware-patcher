"""Static contracts for the separate Astro candidate path."""
from pathlib import Path
import os
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build-astro-candidate.sh"
MANIFEST = ROOT / "scripts" / "create-astro-candidate-manifest.py"


def test_candidate_builder_is_separate_and_build_only():
    text = SCRIPT.read_text()
    assert "patch-polaris.sh" in text
    assert "build-astro.sh" in text
    assert "run_prerelease_gate.sh" in text
    assert "deployment=not-performed" in text
    assert "firmware_flash=not-performed" in text
    assert "upload-fwpkt-to-pr.sh" not in text
    assert "release-fwpkt.sh" not in text


def test_candidate_builder_binds_shared_inputs():
    text = SCRIPT.read_text()
    assert "397320411a1355f06d21233435e144d24efc4207" in text
    assert "3fb26e536ac169e4970d69516a9d45daf62563f5" in text
    assert '[ "$BRANCH" = main ]' in text
    assert 'git -C "$LIBSRC" status --porcelain' in text
    assert 'merge-base --is-ancestor "$CAMERA_BASELINE" HEAD' in text
    assert "create-release-change-manifest.py" in text
    assert "verify-candidate-identity.py" in text
    assert "release_change_manifest_sha256" in text


def test_candidate_manifest_records_packet_and_dependencies():
    text = MANIFEST.read_text()
    assert '"candidate_variant": "astro"' in text
    assert '"shared_camera_baseline"' in text
    assert '"libgphoto2_commit"' in text
    assert '"stock_sha256"' in text
    assert '"dependency_files"' in text
    assert '"install_manifest_sha256"' in text


def _shell(text, **env):
    return subprocess.run(
        ["bash", "-c", "set -euo pipefail\ndie() { echo \"$*\" >&2; exit 1; }\n" + text],
        env={**os.environ, **{k: str(v) for k, v in env.items()}},
        text=True, capture_output=True, timeout=20,
    )


def _version_fixture(tmp_path, branch="main"):
    (tmp_path / "docs").mkdir()
    (tmp_path / "scripts").mkdir()
    state = tmp_path / "docs/RELEASE-VERSION-STATE.md"
    state.write_text("last_display_fwver=6.0.0.54.108\n"
                     "consumed_display_fwver=6.0.0.54.108\n")
    shutil.copy(ROOT / "scripts/verify_display_fwver_monotonic.py", tmp_path / "scripts")
    for args in (["init", "-q", "-b", branch], ["add", "."],
                 ["-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                  "commit", "-qm", "fixture"]):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True,
                       capture_output=True)
    return state


def _preflight():
    text = SCRIPT.read_text()
    return text[text.index('BRANCH="$(git'):text.index('TREE_STATUS=')]


def _claim():
    text = SCRIPT.read_text()
    return text[text.index('echo "Claiming the gated'):text.index('echo "[9/9]')]


def test_main_preflight_does_not_consume_version(tmp_path):
    state = _version_fixture(tmp_path)
    before = state.read_text()
    result = _shell(_preflight(), ROOT=tmp_path, DISPLAY_FWVER="6.0.0.54.109",
                    LIB_BASELINE="a" * 40)
    assert result.returncode == 0, result.stderr
    assert state.read_text() == before


def test_retired_feature_branch_cannot_build(tmp_path):
    _version_fixture(tmp_path, "feature/astro-native-platesolve")
    result = _shell(_preflight(), ROOT=tmp_path, DISPLAY_FWVER="6.0.0.54.109",
                    LIB_BASELINE="a" * 40)
    assert result.returncode != 0
    assert "must be built from main" in result.stderr


def test_claim_binds_exact_commits_and_blocks_reuse(tmp_path):
    state = _version_fixture(tmp_path)
    env = dict(ROOT=tmp_path, DISPLAY_FWVER="6.0.0.54.109", LIB_BASELINE="a" * 40)
    result = _shell(_preflight() + _claim(), **env)
    assert result.returncode == 0, result.stderr
    head = subprocess.check_output(["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
                                   text=True).strip()
    assert f"version_commit_binding=6.0.0.54.109|libgphoto2={'a' * 40}|patcher={head}" in state.read_text()
    assert _shell(_preflight(), **env).returncode != 0
    result = _shell(_preflight(), **{**env, "DISPLAY_FWVER": "6.0.0.54.110"})
    assert result.returncode != 0
    assert "already issued as" in result.stderr


def test_failed_gate_cannot_claim_version(tmp_path):
    state = _version_fixture(tmp_path)
    before = state.read_text()
    text = SCRIPT.read_text()
    gate = text[text.index('[ "$GATE_RC" -eq 0 ]'):text.index('echo "[6/9]')]
    result = _shell(gate + _claim(), GATE_RC=1, ROOT=tmp_path)
    assert result.returncode != 0
    assert state.read_text() == before
    assert text.index('--require-deployable') < text.index('echo "Claiming the gated')
    assert text.index('VERSION_STATE=') < text.index('bash "$ROOT/patch-polaris.sh"')


def test_wrapper_requires_an_explicit_full_pin_before_provisioning():
    wrapper = ROOT / "scripts/build-astro.sh"
    for extra in ([], ["--pin", "abc123"], ["--pin", "z" * 40]):
        result = subprocess.run(["bash", str(wrapper), "--version", "109", *extra],
                                text=True, capture_output=True, timeout=20)
        assert result.returncode != 0
        assert "--pin" in result.stderr
        assert "cloning" not in result.stdout
    result = subprocess.run(["bash", str(SCRIPT)], text=True,
                            capture_output=True, timeout=20)
    assert result.returncode != 0
    assert "explicit --libgphoto2-commit" in result.stderr


def test_explicit_pin_cannot_be_overridden_by_supplied_source(tmp_path):
    _version_fixture(tmp_path)
    text = (ROOT / "scripts/build-astro.sh").read_text()
    check = text[text.index('ACTUAL_PIN='):text.index('if [ -n "$(git -C "$LIBSRC" status')]
    result = _shell(check, LIBSRC=tmp_path, PIN="a" * 40)
    assert result.returncode != 0
    assert "does not match" in result.stderr
    assert '--libgphoto2-commit "$ACTUAL_PIN"' in text


def test_zero_child_exit_with_missing_artifacts_is_failure(tmp_path):
    text = (ROOT / "scripts/build-astro.sh").read_text()
    result_check = text[text.index('if [ "$rc" -eq 0 ] &&'): ]
    result = _shell(result_check, rc=0, OUT=tmp_path, ROOT=tmp_path, LOG=tmp_path / "missing",
                    CANDIDATE_ID="fixture", FWVER="6.0.0.54.109")
    assert result.returncode != 0
    assert "BUILD FAILED" in result.stdout


def test_stale_generated_docker_cannot_shadow_working_route(tmp_path):
    tools = tmp_path / "tools"
    tools.mkdir()
    shutil.copy(ROOT / "tools/host-docker.sh", tools)
    native = tmp_path / "native"
    native.mkdir()
    docker = native / "docker"
    docker.write_text("#!/bin/sh\nexit 0\n")
    docker.chmod(0o755)
    envbin = tmp_path / "build-bin"
    envbin.mkdir()
    stale = envbin / "docker"
    stale.write_text("#!/bin/sh\nexit 127\n")
    stale.chmod(0o755)
    text = (ROOT / "scripts/build-astro.sh").read_text()
    setup = text[text.index('. "$ROOT/tools/host-docker.sh"'):text.index('# ubireader:')]
    result = _shell(setup, ROOT=tmp_path, ENVBIN=envbin,
                    PATH=f"{native}:{os.environ['PATH']}")
    assert result.returncode == 0, result.stderr
    assert subprocess.run([str(stale), "info"]).returncode == 0
    assert str(docker) in stale.read_text()
