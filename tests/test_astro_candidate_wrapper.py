"""Static contracts for the separate Astro candidate path."""
from pathlib import Path


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
    assert "8c015c0a73c8affea8fa723badcceb4070ef81b4" in text
    assert "051d224dbd33fda67ff65ce73a6d6bbd9c9a3aff" in text
    assert 'feature/astro-native-platesolve' in text
    assert 'git -C "$LIBSRC" status --porcelain' in text
    assert 'merge-base --is-ancestor "$CAMERA_BASELINE" HEAD' in text


def test_candidate_manifest_records_packet_and_dependencies():
    text = MANIFEST.read_text()
    assert '"candidate_variant": "astro"' in text
    assert '"shared_camera_baseline"' in text
    assert '"libgphoto2_commit"' in text
    assert '"stock_sha256"' in text
    assert '"dependency_files"' in text
    assert '"install_manifest_sha256"' in text
