"""Static safety gates for the controlled Astro bundle builder."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build-astro-bundle.sh"


def test_controlled_astro_builder_is_present_and_separate_from_firmware_release():
    text = SCRIPT.read_text()
    assert SCRIPT.is_file()
    assert "build-release-candidate.sh" in text
    assert "build-astro.sh" in text
    assert "patch-polaris.sh" not in text
    assert "FwPkt" in text
    assert "firmware_release=not-produced" in text


def test_controlled_astro_builder_has_fail_closed_branch_and_tree_gates():
    text = SCRIPT.read_text()
    assert 'feature/astro-native-platesolve' in text
    assert 'git -C "$ROOT" status --porcelain=v1 --untracked-files=all' in text
    assert '--allow-main' in text
    assert '--allow-dirty' in text
    assert 'git -C "$ROOT" diff --check' in text


def test_controlled_astro_builder_records_manifest_and_provenance():
    text = SCRIPT.read_text()
    assert 'ASTRO-MANIFEST.sha256' in text
    assert 'build-source-provenance.txt' in text
    assert 'patcher_commit=' in text
    assert 'firmware_flash=not-performed' in text
