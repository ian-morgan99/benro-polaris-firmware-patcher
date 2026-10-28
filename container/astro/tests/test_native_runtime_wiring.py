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


def test_end_to_end_session_hooks_are_mode_gated_and_separate():
    boot = (ONDISK / "polaris-astro-boot.sh").read_text()
    frame = (ONDISK / "polaris-frame-watch.sh").read_text()
    goto = (ONDISK / "polaris-goto-watch.sh").read_text()
    wrapper = (ONDISK / "polaris-goto-solve.sh").read_text()
    align = (ONDISK / "polaris-align.sh").read_text()
    httpd = (ROOT / "astro" / "polaris-httpd.c").read_text()
    assert 'AUTO_SOLVE_FRAMES' in boot and 'FRAME_CORRECT' in boot
    assert 'GOTO_SOLVE_WATCH' in boot and 'GOTO_SOLVE_APPLY' in boot
    assert 'MODE_FILE' in frame and '"8"' in frame
    assert 'MODE_FILE' in goto and '"8"' in goto
    assert 'track:1' in goto and 'track:0' in goto
    assert '--already-there' in wrapper and 'polaris-align.sh' in wrapper
    assert 'target_ra_deg' in wrapper and 'TARGET_FILE}.tmp.$$' in wrapper
    assert 'target_ra_deg' in frame and 'TARGET_FILE' in frame
    assert 'FALLBACK_RADIUS' in frame and 'run_align' in frame
    assert 'focal from config' in align and 'emit_solution "$OUT"; exit 0' in align
    assert 'GOTO_PLATESOLVE' in httpd and 'polaris-goto-solve.sh' in httpd
    assert '/api/astro/solve' in httpd and 'last-frame-solution.json' in httpd
