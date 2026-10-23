"""Tests for scripts/verify-shipped-artifacts.py (#214 D1, D2).

The real-artifact cases run against the shipped stage-2 tree of `.68` when it is present
in the checkout; they are skipped otherwise. The synthetic cases cover the failure modes,
because a gate that cannot fail is a rubber stamp.
"""

import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

REAL_STAGE2 = ROOT / "out" / "o-v17c-colortemp-formless" / "stage2-ondisk"


requires_real_artifacts = pytest.mark.skipif(
    not REAL_STAGE2.is_dir(),
    reason="archived .68 stage-2 tree not present in this checkout")


def load():
    path = ROOT / "scripts" / "verify-shipped-artifacts.py"
    spec = importlib.util.spec_from_file_location("verify_shipped", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


APP_LIB_FULL = """\
libc-2.24.so
libc.so.6
libdl.so.2
libexif.so.12
libgcc_s.so.1
libltdl.so.7
libm.so.6
libpthread.so.0
libusb-1.0.so.0
libz.so.1
ld-linux.so.3
"""


def test_device_listing_parser_extracts_sonames():
    mod = load()
    names = mod.parse_device_lib_listing(APP_LIB_FULL)
    assert "libc.so.6" in names
    assert "libexif.so.12" in names
    # Paths are reduced to basenames, and non-.so lines ignored.
    assert mod.parse_device_lib_listing("/app/lib/libz.so.1\nFwVer\nbin\n") == {"libz.so.1"}


@requires_real_artifacts
def test_real_shipped_tree_passes(tmp_path):
    mod = load()
    listing = tmp_path / "app-lib.txt"
    listing.write_text(APP_LIB_FULL)
    allowlist = mod.parse_device_lib_listing(listing.read_text())
    tool = shutil.which("readelf") or shutil.which("llvm-readelf")
    if not tool:
        pytest.skip("readelf not available")
    problems = mod.check_dependencies(str(REAL_STAGE2), tool, allowlist, True)
    assert problems == [], problems


@requires_real_artifacts
def test_unsatisfiable_dependency_is_reported(tmp_path):
    """A device missing libexif must fail, not silently pass."""
    mod = load()
    tool = shutil.which("readelf") or shutil.which("llvm-readelf")
    if not tool:
        pytest.skip("readelf not available")
    allowlist = mod.parse_device_lib_listing(APP_LIB_FULL) - {"libexif.so.12"}
    problems = mod.check_dependencies(str(REAL_STAGE2), tool, allowlist, True)
    assert any("libexif.so.12" in p for p in problems), problems


@requires_real_artifacts
def test_shipped_libraries_satisfy_each_other_without_the_allowlist(tmp_path):
    """libgphoto2_port is shipped, so it must not need to be on the device."""
    mod = load()
    tool = shutil.which("readelf") or shutil.which("llvm-readelf")
    if not tool:
        pytest.skip("readelf not available")
    allowlist = mod.parse_device_lib_listing(APP_LIB_FULL) - {"libgphoto2_port.so.12"}
    problems = mod.check_dependencies(str(REAL_STAGE2), tool, allowlist, True)
    assert not any("libgphoto2_port" in p for p in problems), problems


@requires_real_artifacts
def test_stale_loader_pin_is_caught(tmp_path):
    """D2: a loader compiled against a version the tree does not contain must fail."""
    mod = load()
    fake = tmp_path / "repo"
    (fake / "container").mkdir(parents=True)
    (fake / "scripts").mkdir(parents=True)
    loader = (ROOT / "container" / "stage2_loader.c").read_text(
        encoding="utf-8", errors="replace")
    (fake / "container" / "stage2_loader.c").write_text(
        loader.replace("/app/lib/stage2/libgphoto2/2.5.34",
                       "/app/lib/stage2/libgphoto2/2.5.99"))
    shutil.copy(ROOT / "scripts" / "generate-fwpkt-manifest.py",
                fake / "scripts")
    problems = mod.check_version_pins(str(REAL_STAGE2), str(fake), None)
    assert any("STAGE2_CAMLIBS_DIR" in p and "2.5.99" in p for p in problems), problems


@requires_real_artifacts
def test_matching_pins_produce_no_problems():
    mod = load()
    problems = mod.check_version_pins(str(REAL_STAGE2), str(ROOT), None)
    assert problems == [], problems


def test_missing_module_directories_are_reported(tmp_path):
    mod = load()
    empty = tmp_path / "stage2"
    empty.mkdir()
    problems = mod.check_version_pins(str(empty), str(ROOT), None)
    assert any("no libgphoto2/<version> directory" in p for p in problems), problems
    assert any("no libgphoto2_port/<version> directory" in p for p in problems), problems


@requires_real_artifacts
def test_core_libc_symlink_input_problem_warns_instead_of_failing(capsys):
    """A listing of real filenames without symlinks is an input problem, not a build one."""
    mod = load()
    tool = shutil.which("readelf") or shutil.which("llvm-readelf")
    if not tool:
        pytest.skip("readelf not available")
    # Only real file names, no libc.so.6 / libm.so.6 symlinks.
    allowlist = {"libc-2.24.so", "libm-2.24.so", "libpthread-2.24.so",
                 "libexif.so.12", "libltdl.so.7", "libusb-1.0.so.0",
                 "ld-linux.so.3"}
    problems = mod.check_dependencies(str(REAL_STAGE2), tool, allowlist, True)
    captured = capsys.readouterr().out
    assert "WARNING" in captured, captured
    # The core-libc noise is suppressed, but a genuine gap is still reported.
    assert not any("libc.so.6" in p for p in problems), problems


@requires_real_artifacts
def test_cli_passes_on_the_real_tree(tmp_path):
    listing = tmp_path / "app-lib.txt"
    listing.write_text(APP_LIB_FULL)
    result = subprocess.run(
        ["python3", str(ROOT / "scripts" / "verify-shipped-artifacts.py"),
         str(REAL_STAGE2), "--device-libs", str(listing)],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS" in result.stdout
