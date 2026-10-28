from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ONDISK = ROOT / "astro" / "ondisk"


def test_guide_has_a_complete_native_solver_path():
    text = (ONDISK / "polaris-guide.sh").read_text()
    assert '"$ASTRO/$SOLVER_BIN" --catalog "$INDEPENDENT_CATALOG"' in text
    assert '"scale_arcsec_per_px"' in text
    assert 'polaris-skysim-independent' in text
    assert '--radius "$GUIDE_HINT_RADIUS"' in text


def test_autosolve_quality_gate_understands_native_result_shape():
    text = (ONDISK / "polaris-autosolve.sh").read_text()
    assert '"matched_count"' in text
    assert '"rms_px"' in text
    assert 'solve_frame "$STUB_FRAME" "$_hra" "$_hdec"' in text
    assert 'solve_frame "$_f" "$_ra" "$_dec"' in text


def test_boot_exports_solver_configuration_to_daemons():
    text = (ONDISK / "polaris-astro-boot.sh").read_text()
    assert "export SOLVER_BIN INDEPENDENT_CATALOG CAMERA_MODEL SENSOR_MM" in text
    assert 'SOLVER_BIN="${SOLVER_BIN:-polaris-solve}"' in text
    assert 'INDEPENDENT_CATALOG="${INDEPENDENT_CATALOG:-/app/sd/polaris-astro/catalogue.polcat}"' in text


def test_catalogue_is_optional_for_reference_bundle_but_installable():
    install = (ONDISK / "install_astro.sh").read_text()
    config = (ONDISK / "site.conf.example").read_text()
    assert 'catalogue.polcat' in install
    assert 'INDEPENDENT_CATALOG=/app/sd/polaris-astro/catalogue.polcat' in config
