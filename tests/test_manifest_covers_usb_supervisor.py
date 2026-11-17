"""Issue #349: install-manifest.json must cover every changed runtime file.

v110 shipped exactly two changed files, one of which was
/app/lib/stage2/camera_usb_supervisor.sh. It was not in MANDATORY_FILES, so step 6
of release-fwpkt.sh -- "verify every mandatory installed file's SHA-256" -- never
looked at the one file the release existed to deliver. A build that silently
shipped the previous supervisor would still have reported `installed-verified`.

The issue also asks whether /app/bin/pgphoto should be added. It must not be:
appfs carries the stock ELF at that path, but install_stage2.sh overwrites it at
runtime with the generated pgphoto.wrapper. Confirmed on device 2026-11-17:
/app/bin/pgphoto is a 10794-byte `#!/bin/sh` script while appfs holds an
8922-byte ELF. Hashing appfs against that path would always mismatch and fail a
good install, so the payload that matters is verified via
lib/stage2/pgphoto.stage2ondisk instead.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
GEN = REPO / "scripts" / "generate-fwpkt-manifest.py"


def _mandatory_entries() -> list[tuple[str, str]]:
    """Read MANDATORY_FILES statically -- no appfs extraction needed."""
    if not GEN.exists():
        pytest.skip(f"{GEN} is missing")
    tree = ast.parse(GEN.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "MANDATORY_FILES":
                    # Unwrap ast.Constant -> str. Returning the nodes themselves
                    # makes every membership test silently false, so the suite
                    # would pass while asserting nothing.
                    return [tuple(c.value for c in e.elts)
                            for e in node.value.elts]
    pytest.fail("MANDATORY_FILES not found in generate-fwpkt-manifest.py")


def test_usb_supervisor_is_mandatory():
    """The file v110 exists to deliver must be verified after install."""
    device_paths = [d for d, _ in _mandatory_entries()]
    assert "lib/stage2/camera_usb_supervisor.sh" in device_paths, (
        "camera_usb_supervisor.sh is not mandatory, so post-install SHA-256 "
        "verification never checks it -- a build shipping the old supervisor "
        "would still report installed-verified (#349)")


def test_usb_supervisor_source_exists():
    """It must actually be baked into appfs, or the gate would fail every build."""
    src = REPO / "container" / "ondisk" / "camera_usb_supervisor.sh"
    assert src.is_file(), (
        f"{src} missing; install_stage2.sh copies it into lib/stage2 and the "
        f"manifest now requires it")


def test_pgphoto_wrapper_path_is_not_mandatory():
    """/app/bin/pgphoto is replaced at runtime, so appfs hashing it always fails.

    This is the trap the issue's 'worth checking' note would have walked into.
    """
    device_paths = [d for d, _ in _mandatory_entries()]
    assert "bin/pgphoto" not in device_paths, (
        "bin/pgphoto must NOT be mandatory: install_stage2.sh replaces that path "
        "at runtime with a generated shell wrapper, so the appfs ELF hash can "
        "never match the installed file and every good install would fail")


def test_pgphoto_payload_is_still_verified():
    """Excluding the wrapper must not leave pgphoto unverified entirely."""
    device_paths = [d for d, _ in _mandatory_entries()]
    assert "lib/stage2/pgphoto.stage2ondisk" in device_paths, (
        "pgphoto's real payload is no longer verified")


def test_no_duplicate_device_paths():
    """A duplicate entry would double-count and mask a missing file."""
    device_paths = [d for d, _ in _mandatory_entries()]
    dupes = {p for p in device_paths if device_paths.count(p) > 1}
    assert not dupes, f"duplicate mandatory paths: {sorted(dupes)}"


def test_every_entry_is_a_self_pair():
    """Device path and appfs-relative path must agree (appfs root == /app)."""
    bad = [(d, a) for d, a in _mandatory_entries() if d != a]
    assert not bad, f"device/appfs path mismatch: {bad}"


def test_header_doc_lists_the_supervisor():
    """The module docstring is the human-facing list; keep it honest."""
    doc = ast.get_docstring(ast.parse(GEN.read_text())) or ""
    assert "/app/lib/stage2/camera_usb_supervisor.sh" in doc, (
        "MANDATORY_FILES gained an entry the header doc does not list")


def test_header_doc_explains_the_pgphoto_exclusion():
    doc = ast.get_docstring(ast.parse(GEN.read_text())) or ""
    assert "/app/bin/pgphoto" in doc and "runtime" in doc.lower(), (
        "the pgphoto exclusion needs to be documented, or the next reader will "
        "re-add it and break the gate")


def test_autonomous_install_fixture_mirrors_the_generator():
    """tests/test_autonomous_install.py mirrors this list by hand.

    If they drift, that suite verifies a manifest shape the generator no longer
    produces -- green tests describing a release format that does not exist.
    """
    fixture = REPO / "tests" / "test_autonomous_install.py"
    if not fixture.exists():
        pytest.skip("test_autonomous_install.py missing")
    tree = ast.parse(fixture.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "DEVICE_FILES"
                for t in node.targets):
            names = {k.value for k in node.value.keys}
    if not names:
        pytest.fail("DEVICE_FILES fixture not found in test_autonomous_install.py")

    gen_paths = {d for d, _ in _mandatory_entries()}
    # usbscsi is conditional (K-5 II profile only) and FwVer is written separately.
    optional = {"lib/stage2/libgphoto2_port/0.12.2/usbscsi.so"}
    missing = (gen_paths - optional) - names
    assert not missing, (
        f"test_autonomous_install.py DEVICE_FILES is missing {sorted(missing)}; "
        f"it must mirror MANDATORY_FILES")
