from pathlib import Path
import importlib.util


SCRIPT = Path(__file__).parents[1] / "scripts" / "verify_installed_build.py"
SPEC = importlib.util.spec_from_file_location("verify_installed_build", SCRIPT)
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MOD)


PROVENANCE = """\
source_kind=git-directory
actual_version=2.5.34
git_commit=abc123
patcher_commit=def456
build_id=6.0.0.54.53-o-v15o
display_fwver=6.0.0.54.53
"""


def files(tmp_path: Path):
    candidate = tmp_path / "candidate.txt"
    device = tmp_path / "device.txt"
    candidate_fw = tmp_path / "candidate-fwver"
    device_fw = tmp_path / "device-fwver"
    candidate.write_text(PROVENANCE)
    device.write_text(PROVENANCE)
    candidate_fw.write_text("FwVer:6.0.0.54.53;date:2026.10.03;\n")
    device_fw.write_text("FwVer:6.0.0.54.53;date:2026.10.03;\n")
    return candidate, device, candidate_fw, device_fw


def test_exact_identity_passes(tmp_path):
    assert MOD.compare(*files(tmp_path)) == []


def test_wrong_source_build_fails_closed(tmp_path):
    candidate, device, candidate_fw, device_fw = files(tmp_path)
    device.write_text(PROVENANCE.replace("git_commit=abc123", "git_commit=old999"))
    errors = MOD.compare(candidate, device, candidate_fw, device_fw)
    assert any("git_commit" in error for error in errors)


def test_wrong_display_version_fails_closed(tmp_path):
    candidate, device, candidate_fw, device_fw = files(tmp_path)
    device_fw.write_text("FwVer:6.0.0.54.52;date:2026.10.03;\n")
    errors = MOD.compare(candidate, device, candidate_fw, device_fw)
    assert any("display_fwver" in error for error in errors)


def test_missing_device_provenance_fails_closed(tmp_path):
    candidate, device, candidate_fw, device_fw = files(tmp_path)
    device.write_text("build_id=6.0.0.54.53-o-v15o\n")
    errors = MOD.compare(candidate, device, candidate_fw, device_fw)
    assert any("device missing patcher_commit" in error for error in errors)
