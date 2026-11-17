"""camera-death-watch.sh must detect every supported body, not just Canon.

The flight recorder for "the camera died and the mount drove itself somewhere
bad" decided camera presence with an exact match on vendor 04a9 -- Canon EOS.
Every Pentax body therefore looked like "no camera attached" from boot onward,
so the watcher never armed and wrote no dossier for any drop. That includes the
K-3 III loss in #347 and the K-1 II drops observed on v110/v111: the tool built
to capture this evidence was silently discarding it, and its startup line read
"camera present=0", which is indistinguishable from a healthy watcher with no
camera plugged in.

This is the failure mode this repo keeps hitting -- a guard that only ever tests
the happy path -- so the test drives the real shell function against a fake
/sys tree rather than grepping for a magic string.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "container" / "astro" / "ondisk" / "camera-death-watch.sh"

# Bodies we actually support, taken from the vendor list in
# camera_usb_supervisor.sh. 25fb is Ricoh: both the K-1 II and the K-3 III.
CAMERAS = {
    "04a9": "Canon EOS",
    "25fb": "Ricoh (Pentax K-1 II / K-3 III)",
    "04b0": "Nikon",
    "04da": "Panasonic",
    "054c": "Sony",
}

NON_CAMERAS = {
    "1a40": "USB2.0 hub",
    "1d6b": "Linux xHCI controller",
    "0951": "USB stick",
}


@pytest.fixture(scope="module")
def source() -> str:
    if not SCRIPT.exists():
        pytest.skip(f"{SCRIPT} is missing; nothing to check")
    return SCRIPT.read_text()


def _extract(source: str, name: str) -> str:
    """Pull one shell function out of the script so we execute the real body."""
    m = re.search(rf"^{name}\(\)\s*\{{\n(.*?)^\}}", source, re.M | re.S)
    if not m:
        # A missing detector is itself the bug this file guards against: with no
        # camera_present() there is no arming logic at all, so fail rather than
        # skip -- a skip here would let a deleted function look green.
        pytest.fail(f"{name}() not found in {SCRIPT.name}: nothing can detect "
                    f"a camera, so the flight recorder cannot arm")
    return m.group(1)


def _run(body: str, devices: dict[str, str], extra_env: str = "") -> int:
    """Run `body` against a fake /sys tree; exit 0 means 'camera present'."""
    if shutil.which("sh") is None:
        pytest.skip("no sh available to execute the watcher logic")

    lines = ["set -u"]
    if extra_env:
        lines.append(extra_env)
    lines.append(body)
    lines.append("camera_present")
    script = "\n".join(lines)

    r = subprocess.run(["sh", "-c", script], capture_output=True, text=True)
    if r.returncode == 127 or r.stderr.strip():
        pytest.fail(f"watcher logic failed to execute: {r.stderr.strip()[:200]}")
    return r.returncode


@pytest.fixture()
def fake_sys(tmp_path):
    """Build a /sys/bus/usb/devices tree containing the given vendor IDs."""
    def build(vendors: list[str]) -> dict[str, str]:
        root = tmp_path / "devices"
        for i, v in enumerate(vendors):
            d = root / f"1-1.{i}"
            d.mkdir(parents=True, exist_ok=True)
            (d / "idVendor").write_text(v + "\n")
            (d / "idProduct").write_text("0189\n")
            (d / "product").write_text("FAKE\n")
        return {"root": str(root)}
    return build


def _patched_scan(source: str, fake_root: str) -> str:
    """Rebuild camera_present() so it reads our fake tree.

    The CAMERA_VENDORS default is pulled in when present, so the test exercises
    the real list rather than one invented here -- otherwise a broken default
    would pass while the shipped script stayed blind. When it is absent (the
    pre-fix script) the original body runs verbatim, so these tests FAIL on the
    old Canon-only code instead of skipping past it.

    The body is re-wrapped in its function header because _extract() returns
    only the interior, and a bare `return` at top level is not valid shell.
    """
    body = _extract(source, "camera_present")
    body = body.replace("/sys/bus/usb/devices", fake_root)
    m = re.search(r"^CAMERA_VENDORS=.*$", source, re.M)
    prelude = m.group(0) if m else 'CAMERA_VENDORS=""'
    return f'{prelude}\ncamera_present() {{\n{body}}}'


def _patched_identity(source: str, fake_root: str) -> str:
    """Same treatment for camera_identity()."""
    body = _extract(source, "camera_identity")
    body = body.replace("/sys/bus/usb/devices", fake_root)
    m = re.search(r"^CAMERA_VENDORS=.*$", source, re.M)
    prelude = m.group(0) if m else 'CAMERA_VENDORS=""'
    return f'{prelude}\ncamera_identity() {{\n{body}}}'


@pytest.mark.parametrize("vendor,label", sorted(CAMERAS.items()))
def test_supported_body_is_detected(source, fake_sys, vendor, label):
    """Every supported vendor must arm the watcher, not just Canon."""
    devs = fake_sys([vendor, "1d6b"])          # camera + a controller
    body = _patched_scan(source, devs["root"])
    assert _run(body, devs) == 0, (
        f"{label} ({vendor}) is not detected as a camera; the flight recorder "
        f"will never arm for it and will write no dossier on drop")


def test_pentax_specifically(source, fake_sys):
    """The regression: a Pentax K-1 II / K-3 III must be seen.

    Before the fix this returned 1 forever, because the match was exactly "04a9".
    """
    devs = fake_sys(["25fb", "1a40", "1d6b"])   # Pentax + hub + controller
    body = _patched_scan(source, devs["root"])
    assert _run(body, devs) == 0, (
        "Pentax (25fb) still invisible -- this is the #347 evidence gap")


def test_hub_alone_is_not_a_camera(source, fake_sys):
    """Must not over-correct into 'any device is a camera'.

    The hub (1a40) and the xHCI controller (1d6b) are always present. Treating
    them as a camera would arm the watcher permanently and fire a bogus dossier
    on every boot.
    """
    devs = fake_sys(list(NON_CAMERAS))
    body = _patched_scan(source, devs["root"])
    assert _run(body, devs) != 0, (
        "a hub/controller-only bus counts as a camera; the watcher would arm "
        "spuriously")


def test_no_devices_is_not_a_camera(source, fake_sys):
    devs = fake_sys([])
    body = _patched_scan(source, devs["root"])
    assert _run(body, devs) != 0


def test_vendor_list_matches_the_supervisor(source):
    """The two watchers must not drift apart.

    camera_usb_supervisor.sh already had the correct list. If these diverge, a
    body can be visible to one and invisible to the other -- which is precisely
    how this bug survived: the supervisor saw 25fb, the death-watch did not.
    """
    sup = REPO / "container" / "ondisk" / "camera_usb_supervisor.sh"
    if not sup.exists():
        sup = next((p for p in REPO.rglob("camera_usb_supervisor.sh")
                    if "builds" not in p.parts and "out" not in p.parts), None)
    if sup is None or not sup.exists():
        pytest.skip("camera_usb_supervisor.sh not found in this tree")

    sup_vendors = set(re.findall(r"\b[0-9a-f]{4}\b",
                                 _extract(sup.read_text(), "camera_vendor")))
    watch_vendors = set(re.findall(
        r"CAMERA_VENDORS=.*?:-([^\}]+)\}", source))
    if not watch_vendors:
        pytest.skip("CAMERA_VENDORS default not in the expected form")
    watch_set = set(watch_vendors.pop().split())

    missing = sup_vendors - watch_set
    assert not missing, (
        f"death-watch is missing vendors the supervisor supports: "
        f"{sorted(missing)} -- drift means a camera is invisible to one watcher")


def test_startup_line_names_the_body(source, fake_sys):
    """The log must say which body it armed for.

    "camera present=0" used to be indistinguishable from "unsupported camera",
    so the Canon-only bug produced a log that looked healthy.
    """
    assert "camera_identity" in source, (
        "startup line does not name the detected body")
    assert "vendors:" in source, (
        "startup line does not record which vendors it will accept")

    # And it must actually report the Pentax, not just contain the words.
    devs = fake_sys(["25fb", "1a40"])
    body = _patched_identity(source, devs["root"])
    if shutil.which("sh") is None:
        pytest.skip("no sh available")
    r = subprocess.run(
        ["sh", "-c", body + "\ncamera_identity"],
        capture_output=True, text=True)
    assert r.returncode == 0 and "25fb:0189" in r.stdout, (
        f"camera_identity() did not name the Pentax (rc={r.returncode}, "
        f"out={r.stdout!r})")


def test_canon_only_match_is_gone(source):
    """Guard against the exact regression reappearing."""
    body = _extract(source, "camera_present")
    assert '"04a9"' not in body and "'04a9'" not in body, (
        "camera_present() is matching Canon alone again")
