import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ONDISK = ROOT / "astro" / "ondisk"


def test_guide_has_a_complete_native_solver_path():
    text = (ONDISK / "polaris-guide.sh").read_text()
    assert '"$ASTRO/$SOLVER_BIN" --catalog "$INDEPENDENT_CATALOG"' in text
    assert '"scale_arcsec_per_px"' in text
    assert 'polaris-skysim-independent' in text
    assert '--radius "$GUIDE_HINT_RADIUS"' in text
    assert '--catalog-dir "$INDEPENDENT_CATALOG_DIR"' in text
    assert '--triangle-index "$INDEPENDENT_TRIANGLE_INDEX"' in text
    assert 'INDEPENDENT_ATTEMPTS' in text


def test_autosolve_quality_gate_understands_native_result_shape():
    text = (ONDISK / "polaris-autosolve.sh").read_text()
    assert '"matched_count"' in text
    assert '"rms_px"' in text
    assert 'solve_frame "$STUB_FRAME" "$_hra" "$_hdec"' in text
    assert 'solve_frame "$_f" "$_ra" "$_dec"' in text
    assert 'polaris-pointing-model.sh" reset' in text
    assert 'SESSION_FILE=${SESSION_FILE:-/app/sd/polaris-astro/session-id}' in text
    assert '"session_id":"%s"' in text


def test_boot_exports_solver_configuration_to_daemons():
    text = (ONDISK / "polaris-astro-boot.sh").read_text()
    assert "export SOLVER_BIN INDEPENDENT_CATALOG INDEPENDENT_CATALOG_DIR" in text
    assert 'SOLVER_BIN="${SOLVER_BIN:-polaris-solve}"' in text
    assert 'INDEPENDENT_CATALOG="${INDEPENDENT_CATALOG:-/app/sd/polaris-astro/catalogue.polcat}"' in text
    assert 'INDEPENDENT_CATALOG_MANIFEST="${INDEPENDENT_CATALOG_MANIFEST:-/app/sd/polaris-astro/catalogue-tiles.manifest.json}"' in text
    assert 'INDEPENDENT_TRIANGLE_INDEX="${INDEPENDENT_TRIANGLE_INDEX:-/app/sd/polaris-astro/catalogue-tiles.ptri}"' in text


def test_catalogue_is_optional_for_reference_bundle_but_installable():
    install = (ONDISK / "install_astro.sh").read_text()
    config = (ONDISK / "site.conf.example").read_text()
    assert 'catalogue.polcat' in install
    assert 'polaris-solve-independent-search' in install
    assert 'catalogue-tiles' in install
    assert 'INDEPENDENT_CATALOG=/app/sd/polaris-astro/catalogue.polcat' in config
    assert 'INDEPENDENT_CATALOG_DIR=/app/sd/polaris-astro/catalogue-tiles' in config
    assert 'INDEPENDENT_TRIANGLE_INDEX=/app/sd/polaris-astro/catalogue-tiles.ptri' in config
    assert 'SENSOR_PROFILE_FILE=/app/sd/polaris-astro/camera-sensors.tsv' in config
    assert 'ALLOW_DEFAULT_SENSOR=1' in config


def test_bundle_builder_carries_native_search_and_tile_package():
    build = (ROOT.parent / "build-astro.sh").read_text()
    assert "polaris-solve-independent-search" in build
    assert "--catalog-package" in build
    assert "catalogue-tiles.manifest.json" in build
    assert "catalogue-tiles.ptri.json" in build
    assert "camera-sensors.tsv" in build


def test_exif_writer_flushes_and_validates_atomic_temp_input():
    writer = (ROOT / "astro" / "polaris-exif-solve.c").read_text()
    assert "fsync(fileno(file))" in writer
    assert "write_all" in writer
    assert "if (segment_length > 65535U)" in writer
    assert "sync_parent_directory" in writer
    assert "rename(temp_path, output)" in writer
    assert "unlink(output)" not in writer


def test_exif_focal_parser_fails_closed_on_wrapped_offsets():
    extractor = (ROOT / "astro" / "polaris-extract.c").read_text()
    assert "exif_span_ok" in extractor
    assert "rel > len - tiff" in extractor
    assert "size <= len - off" in extractor
    assert "exif_focal35_mm" in extractor
    assert "exif camera-model" in extractor


def test_align_rejects_missing_image_before_solver_access():
    align = ONDISK / "polaris-align.sh"
    env = os.environ.copy()
    env.update({"CAMERA_MODEL": "", "SENSOR_MM": "", "ALLOW_DEFAULT_SENSOR": "0"})
    result = subprocess.run(
        ["sh", str(align), "/tmp/no-such-image.jpg"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "no such image" in result.stderr


def test_align_accepts_a_non_pentax_camera_via_generic_profile(tmp_path):
    astro = tmp_path / "astro"
    astro.mkdir()
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"not-a-real-jpeg-but-the-extractor-is-stubbed")
    profile = tmp_path / "camera-sensors.tsv"
    profile.write_text("Generic Camera 9000\t22.2\n")
    args = tmp_path / "solver.args"

    extractor = astro / "polaris-extract"
    extractor.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' '# full resolution 100 x 80' '10 10 100'\n"
    )
    solver = astro / "polaris-solve-independent"
    solver.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$*\" > {args}\n"
        "printf '%s\\n' '{\"solved\":true,\"ra_deg\":10,\"dec_deg\":20,\"matched_count\":12,\"rms_px\":1}'\n"
    )
    extractor.chmod(0o755)
    solver.chmod(0o755)
    catalogue = tmp_path / "catalogue.polcat"
    catalogue.write_text("placeholder\n")

    env = os.environ.copy()
    env.update(
        {
            "ASTRO": str(astro),
            "SOLVER_BIN": "polaris-solve-independent",
            "INDEPENDENT_CATALOG": str(catalogue),
            "SENSOR_PROFILE_FILE": str(profile),
            "CAMERA_MODEL": "Generic Camera 9000",
            "SENSOR_MM": "",
            "ALLOW_DEFAULT_SENSOR": "0",
            "FOCAL_MM": "50",
            "MOUNT_HINT": "0",
        }
    )
    result = subprocess.run(
        ["sh", str(ONDISK / "polaris-align.sh"), str(image), "50"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert '"solved":true' in result.stdout
    assert "--sensor-mm 22.2" in args.read_text()
    assert "--focal-mm 50" in args.read_text()


def test_align_uses_bounded_generic_geometry_for_unknown_camera(tmp_path):
    astro = tmp_path / "astro"
    indexes = tmp_path / "indexes"
    astro.mkdir()
    indexes.mkdir()
    (indexes / "index-unknown.fits").write_text("placeholder\n")
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"not-a-real-jpeg-but-the-extractor-is-stubbed")
    args = tmp_path / "solver.args"

    extractor = astro / "polaris-extract"
    extractor.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' '# full resolution 100 x 80' '10 10 100'\n"
    )
    solver = astro / "polaris-solve"
    solver.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$*\" > {args}\n"
        "printf '%s\\n' '{\"solved\":true,\"ra_deg\":10,\"dec_deg\":20}'\n"
    )
    extractor.chmod(0o755)
    solver.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "ASTRO": str(astro),
            "INDEXES": str(indexes),
            "SOLVER_BIN": "polaris-solve",
            "CAMERA_MODEL": "Some Other Camera",
            "SENSOR_MM": "",
            "SENSOR_PROFILE_FILE": str(tmp_path / "missing.tsv"),
            "ALLOW_DEFAULT_SENSOR": "1",
            "FOCAL_MM": "50",
            "MOUNT_HINT": "0",
        }
    )
    result = subprocess.run(
        ["sh", str(ONDISK / "polaris-align.sh"), str(image), "50"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert '"solved":true' in result.stdout
    solver_args = args.read_text()
    assert "--scale-low" in solver_args and "--scale-high" in solver_args
    assert "--sensor-mm" not in solver_args


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
    assert 'polaris-pointing-model.sh' in wrapper and 'GOTO_MODEL_APPLY' in wrapper
    assert 'GOTO_MODEL_RECORD=1' in (ONDISK / "site.conf.example").read_text()
    assert 'target_ra_deg' in frame and 'TARGET_FILE' in frame
    assert 'FRAME_TELEMETRY' in frame and 'rate_control":"unavailable' in frame
    assert 'FALLBACK_RADIUS' in frame and 'run_align' in frame
    assert 'withholding frame correction while field rotation is above threshold' in frame
    assert 'focal from config' in align and 'emit_solution "$OUT"; exit 0' in align
    assert 'retrying bounded blind search' in align and 'USE_HINT=0' in align
    assert 'mktemp "${IMG}.polaris-exif.tmp.XXXXXX"' in align
    assert 'tail -c 2' in align and 'original image preserved' in align
    assert 'sensor_geometry_required' in align
    assert 'ALLOW_DEFAULT_SENSOR' in align
    assert 'SENSOR_PROFILE_FILE' in align
    assert 'generic-default' in align
    assert '*K-3*' not in align and '*K3*' not in align
    assert 'EXIF_WRITEBACK:-0' in align
    assert 'SESSION_FILE' in frame and 'session_target_from_file' in frame
    assert 'FRAME_REQUIRE_CAPTURE_EVENT' in frame and 'capture_event_matches' in frame
    assert 'FRAME_REQUIRE_CAPTURE_EVENT="${FRAME_REQUIRE_CAPTURE_EVENT:-1}"' in boot
    assert 'MAX_TELEMETRY_BYTES' in frame and 'MAX_HISTORY_BYTES' in frame
    assert 'session_id' in wrapper
    assert 'SESSION_FILE=${SESSION_FILE:-/app/sd/polaris-astro/session-id}' in (ONDISK / "solve-now.sh").read_text()
    assert '"session_id":"%s"' in (ONDISK / "solve-now.sh").read_text()
    assert 'GOTO_PLATESOLVE' in httpd and 'polaris-goto-solve.sh' in httpd
    assert '/api/astro/solve' in httpd and 'last-frame-solution.json' in httpd
