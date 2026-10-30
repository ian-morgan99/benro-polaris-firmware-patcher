"""Exercise the desktop build wrapper without Docker, network, or hardware."""

import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def run_wrapper(tmp_path, overrides=None):
    scripts = tmp_path / "scripts"
    release = scripts / "release"
    release.mkdir(parents=True)
    wrapper = release / "build-and-install.sh"
    shutil.copyfile(ROOT / "scripts/release/build-and-install.sh", wrapper)
    builder = scripts / "build-release-candidate.sh"
    builder.write_text('#!/bin/bash\nprintf "%s\\n" "$@" > "$CAPTURE_ARGS"\n')
    builder.chmod(0o755)
    stock = tmp_path / "stock" / "FwPkt"
    stock.mkdir(parents=True)
    (stock / "firmwareInfo").write_text("test fixture\n")
    (tmp_path / "summary.json").write_text("{}\n")
    captured = tmp_path / "builder-args.txt"
    env = dict(os.environ)
    for key in ("BUILD_ID", "DISPLAY_FWVER", "CANDIDATE_ID", "CHANGE_SUMMARY",
                "LIBGPHOTO_REPO", "BASH_ENV"):
        env.pop(key, None)
    env.update(CANDIDATE_ID="offline-wrapper-test", CHANGE_SUMMARY="summary.json",
               STOCK_FWPKT=str(stock.parent), CAPTURE_ARGS=str(captured))
    env.update(overrides or {})
    # Exported functions take precedence over the wrapper's system-tool PATH.
    # No actual Docker daemon, clone, release builder, or device is contacted.
    bootstrap = '''
docker() { test "$1" = info; }
git() {
    if [ "$1" = clone ]; then
        mkdir -p "${@: -1}/.git"
    elif [ "$1" = -C ] && [ "$3" = branch ]; then
        printf 'main\\n'
    elif [ "$1" = -C ] && [ "$3" = status ]; then
        return 0
    else
        return 91
    fi
}
export -f docker git
exec bash "$1"
'''
    result = subprocess.run(["bash", "-c", bootstrap, "test", str(wrapper)],
                            cwd=tmp_path, env=env, text=True,
                            capture_output=True, timeout=15)
    args = captured.read_text().splitlines() if captured.exists() else None
    return result, args


def test_desktop_defaults_delegate_version_and_build_id_to_release_builder(tmp_path):
    result, args = run_wrapper(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert args[3:5] == ["auto", "auto"]
    assert args[5:] == ["--change-summary", str(tmp_path / "summary.json")]
    assert not Path(args[2]).exists(), "temporary source clone must be cleaned up"


@pytest.mark.parametrize("overrides, expected", [
    ({"DISPLAY_FWVER": "6.0.0.54.91"}, ["auto", "6.0.0.54.91"]),
    ({"DISPLAY_FWVER": "6.0.0.54.91", "BUILD_ID": "6.0.0.54.91-reviewed"},
     ["6.0.0.54.91-reviewed", "6.0.0.54.91"]),
])
def test_explicit_reviewed_identity_is_forwarded(tmp_path, overrides, expected):
    result, args = run_wrapper(tmp_path, overrides)
    assert result.returncode == 0, result.stdout + result.stderr
    assert args[3:5] == expected


def test_missing_change_summary_stops_before_source_clone_or_build(tmp_path):
    result, args = run_wrapper(tmp_path, {"CHANGE_SUMMARY": ""})
    assert result.returncode == 2
    assert "CHANGE_SUMMARY is required" in result.stdout
    assert "== clean libgphoto2 source ==" not in result.stdout
    assert args is None
