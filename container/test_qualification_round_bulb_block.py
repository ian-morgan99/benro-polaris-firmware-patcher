"""The unsafe full round must stop before it can contact a device."""

import os
from pathlib import Path
import shutil
import subprocess


def test_qualification_round_blocks_before_device_access(tmp_path):
    source = Path(__file__).resolve().parents[1] / "scripts" / "run-qualification-round.sh"
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    runner = scripts / source.name
    shutil.copyfile(source, runner)

    # A caller-supplied flag must not accidentally override the safety block.
    env = dict(os.environ, OPENPOLARIS_ALLOW_BULB="1")
    result = subprocess.run(["bash", str(runner)], cwd=tmp_path, env=env,
                            capture_output=True, text=True, timeout=5)

    assert result.returncode == 2
    assert "BLOCKED" in result.stderr
    assert "#251" in result.stderr
    assert not (tmp_path / "out").exists()
