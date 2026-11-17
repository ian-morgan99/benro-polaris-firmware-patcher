from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "scripts" / "diagnostic" / "camera-layer-report.sh"


def test_camera_state_zero_is_not_classified_as_disconnected():
    source = REPORT.read_text(encoding="utf-8")

    assert "0=Idle; not a camera-presence signal" in source
    assert 'record "layer5-camera-state" PASS' in source
    assert 'record "layer5-published" FAIL "CameraState=Disconnected' not in source
    assert "code-286 published camera identity" in source


def test_report_uses_code_286_for_camera_identity():
    source = REPORT.read_text(encoding="utf-8")

    assert 'CAMINFO=$(printf' in source
    assert "model:[[:space:]]*(none|;|$)" in source
    assert "CameraState" in source
    assert "actual published camera identity is checked below from the code-286 snapshot" in source
