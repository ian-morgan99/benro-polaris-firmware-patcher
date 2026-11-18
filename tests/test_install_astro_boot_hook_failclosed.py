"""Execute install_astro.sh's boot-hook step for real, in a sandbox.

The existing installer suite (test_astro_kit_installer_behaviour.py) drives the
*kit* script through a hand-written ssh stub that re-implements the remote steps
in prose. Nothing there runs install_astro.sh itself, so the claim "boot hook
installed" was never executed off-device -- it was only ever grepped for. That is
how the v104 symptom (#312: polaris-httpd present, port closed, nothing at boot)
survived a green suite: the check that would have caught it asserted about the
script instead of running it.

These tests run the real script with SRC/DEST/HOOK/CONF redirected into tmp_path.
HOOK and CONF were hardcoded until this round, which is precisely why no test
could reach the hook path; the defaults are unchanged on device.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "container" / "astro" / "ondisk" / "install_astro.sh"
BOOT_SCRIPT = ROOT / "container" / "astro" / "ondisk" / "polaris-astro-boot.sh"


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _required_binaries() -> list[str]:
    """Parse the installer's own required-binary loop.

    Hardcoding this list in the test would mean a new load-bearing binary silently
    breaks real installs while this suite stays green -- the fixture would keep
    shipping an outdated bundle and the check would pass for the wrong reason.
    """
    text = INSTALLER.read_text(encoding="utf-8", errors="replace")
    # The loop spans two lines with a backslash continuation and ends "; do".
    m = re.search(r"for b in (.*?);\s*do\b", text, re.S)
    if not m:
        pytest.fail("could not find the required-binary loop in install_astro.sh")
    return [b for b in m.group(1).replace("\\\n", " ").split() if b.strip()]


@pytest.fixture()
def bundle(tmp_path: Path) -> dict[str, Path]:
    """A minimal but honest bundle: real boot script, every required binary."""
    if not INSTALLER.is_file():
        pytest.skip(f"{INSTALLER} is missing")

    src = tmp_path / "src"
    src.mkdir()
    shutil.copy(BOOT_SCRIPT, src / "polaris-astro-boot.sh")

    names = _required_binaries()
    assert names, "installer requires no binaries -- check the parser"
    for name in names:
        p = src / name
        p.write_text("#!/bin/sh\nexit 0\n")
        p.chmod(0o755)

    # Manifest covers $DEST contents only, matching how it is generated.
    entries = [f"{_sha256(src / n)}  {n}" for n in names]
    (src / "polaris-astro.manifest").write_text("\n".join(entries) + "\n")

    app = tmp_path / "app"
    (app / "sd" / "polaris-astro").mkdir(parents=True)
    return {
        "src": src,
        "dest": app / "astro",
        "hook": app / "network_telnetd.sh",
        "conf": app / "sd" / "polaris-astro" / "site.conf",
        "indexes": app / "sd" / "astrometry",
        "app": app,
    }


def _run(bundle: dict[str, Path], extra_env: dict[str, str] | None = None):
    env = dict(os.environ)
    env.update({
        "SRC": str(bundle["src"]),
        "DEST": str(bundle["dest"]),
        "HOOK": str(bundle["hook"]),
        "CONF": str(bundle["conf"]),
        "INDEXES": str(bundle["indexes"]),
        "PROFILE_DIR": str(bundle["app"] / "sd" / "polaris-astro"),
    })
    env.update(extra_env or {})
    return subprocess.run(
        ["sh", str(INSTALLER)],
        text=True, capture_output=True, timeout=120, env=env, cwd=str(ROOT))


def test_boot_hook_is_written_and_matches_bundle(bundle):
    """The hook must exist and be byte-identical to the bundle's copy."""
    r = _run(bundle)
    assert r.returncode == 0, f"installer failed: {r.stdout}\n{r.stderr}"
    assert bundle["hook"].is_file(), "boot hook not written"
    want = _sha256(bundle["src"] / "polaris-astro-boot.sh")
    got = _sha256(bundle["hook"])
    assert got == want, (
        f"boot hook differs from bundle after install\n  want {want}\n  got {got}")
    assert bundle["hook"].stat().st_mode & 0o111, "boot hook is not executable"


def test_reports_verification_not_just_install(bundle):
    """The success line must say the hook was verified, not merely copied.

    'installed' is what the old script printed right before shipping a device
    with nothing at boot; the wording is part of the evidence operators read.
    """
    r = _run(bundle)
    assert "boot hook installed and verified" in r.stdout, (
        f"installer did not confirm verification: {r.stdout}")


def test_missing_boot_script_is_fatal_not_a_warning(bundle):
    """A bundle with no boot script cannot autostart; claiming success is a lie.

    This used to print WARNING and exit 0, so an install that could never start
    Astro at boot reported the same status as a working one.
    """
    (bundle["src"] / "polaris-astro-boot.sh").unlink()
    r = _run(bundle)
    assert r.returncode != 0, (
        "installer exited 0 with no boot script present; nothing will start at "
        "boot and the operator has no way to know")
    assert "FATAL" in r.stderr, f"expected a fatal message, got: {r.stderr}"


def test_corrupt_hook_fails_closed(bundle, monkeypatch):
    """If the hook copy ends up wrong, the installer must fail rather than pass.

    Simulated by making the source unreadable mid-copy is fragile; instead we
    pre-place a hook that cannot be overwritten by pointing HOOK at a directory,
    which reproduces the "cp succeeded but the file is not what we wanted" shape.
    """
    bundle["hook"].mkdir(parents=True)  # cp onto a directory cannot produce a file
    r = _run(bundle)
    assert r.returncode != 0, (
        "installer reported success while the boot hook is a directory")


def test_existing_hook_is_preserved_and_chained(bundle):
    """Overwriting the SSH hook blindly would lock the operator out.

    The firmware patcher's SSH option uses the same file, so anything already
    there must be kept and run first.
    """
    bundle["hook"].write_text("#!/bin/sh\necho start_sshd\n")
    bundle["hook"].chmod(0o755)
    r = _run(bundle)
    assert r.returncode == 0, f"installer failed: {r.stderr}"

    backup = bundle["app"] / "network_telnetd.pre-astro.sh"
    assert backup.is_file(), "existing hook was not preserved"
    assert "start_sshd" in backup.read_text(), (
        "preserved backup does not contain the original ssh starter")

    # The new hook must still chain to it, or ssh silently stops working.
    assert "network_telnetd.pre-astro.sh" in bundle["hook"].read_text(), (
        "new boot hook does not chain to the preserved ssh hook")


def test_no_boot_flag_skips_hook_without_failing(bundle):
    """NO_BOOT=1 is a documented opt-out and must not trip the new fatal path."""
    r = _run(bundle, {"NO_BOOT": "1"})
    assert r.returncode == 0, f"NO_BOOT=1 should succeed: {r.stderr}"
    assert not bundle["hook"].exists(), "NO_BOOT=1 still wrote a boot hook"


def test_default_hook_path_is_unchanged():
    """On-device behaviour must be identical to before the refactor.

    Making HOOK overridable is only safe if the default is exactly what it was;
    a changed default would silently move the file bootapp looks for and break
    autostart on every real install.
    """
    text = INSTALLER.read_text(encoding="utf-8", errors="replace")
    assert 'HOOK=${HOOK:-/app/network_telnetd.sh}' in text, (
        "default HOOK path changed; /app/bootapp looks for exactly this file")
    assert '${HOOK%.sh}.pre-astro.sh' in text, (
        "backup must still resolve to /app/network_telnetd.pre-astro.sh on device")
