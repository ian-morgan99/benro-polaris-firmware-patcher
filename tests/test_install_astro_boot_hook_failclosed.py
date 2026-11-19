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

    # The manifest must be built the way build-astro-candidate.sh builds it: over
    # the finished kit tree, not over the installer's hardcoded binary list. The
    # fixture used to list only the required binaries and claimed that "matched how
    # it is generated" -- it did not, and that is exactly how the VERSION bug stayed
    # green. build-astro-candidate.sh writes VERSION into the kit before generating
    # the manifest, so a real bundle lists VERSION plus every *.sh alongside the
    # binaries; a fixture listing only binaries lets the installer pass here while
    # failing on every device, because verification compares each listed entry
    # against $DEST and nothing copied VERSION there.
    entries = [f"{_sha256(src / n)}  {n}" for n in names]
    (src / "VERSION").write_text(
        "build_id=test-build\nfirmware_version=6.0.0.54.114\n"
        "firmware_version_source=explicit\n")
    entries.append(f"{_sha256(src / 'VERSION')}  VERSION")
    for sh in sorted(src.glob("*.sh")):
        if sh.name == "polaris-astro-boot.sh":
            continue  # installed as $HOOK, not into $DEST
        entries.append(f"{_sha256(sh)}  {sh.name}")
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


def test_manifest_listed_data_file_lands_in_dest(bundle):
    """Every manifest entry must actually be copied, not just checked.

    This is the v114 field failure. build-astro-candidate.sh writes VERSION into
    the kit and generates polaris-astro.manifest from the finished tree, so the
    manifest lists VERSION -- but install_astro.sh copied a hardcoded list of
    binaries plus *.sh and never copied VERSION. Verification then compared
    /app/astro/VERSION against a hash of a file that was never placed there,
    printed "VERIFY FAILED: VERSION", and exited 1.

    The exit is what made it catastrophic rather than merely noisy: the boot hook
    is installed further down the script, so the early exit meant no hook was
    written. The device came back with firmware flashed and /app/astro populated
    but nothing starting at boot -- "the astro module is not recognised" -- while
    the installer's output blamed the copy step instead of naming the missing hook.

    polaris-astro-sync.sh already derives its file list from the manifest so a
    bundle can add a file without editing it; install_astro.sh was the exception,
    and that asymmetry is how VERSION slipped through.
    """
    r = _run(bundle)
    assert r.returncode == 0, (
        "install must not fail on a manifest-listed data file:\n"
        f"{r.stdout}\n{r.stderr}")
    assert "VERIFY FAILED" not in r.stderr, (
        f"a manifest entry was verified but never copied: {r.stderr}")

    landed = bundle["dest"] / "VERSION"
    assert landed.is_file(), (
        "VERSION is listed in polaris-astro.manifest but did not reach $DEST -- "
        "/api/version would answer 'unknown' and the header chip stays hidden")
    assert _sha256(landed) == _sha256(bundle["src"] / "VERSION"), (
        "VERSION in $DEST does not match the bundle")

    # A data file must not be made executable just because it was installed.
    assert not landed.stat().st_mode & 0o111, "VERSION should not be executable"


def test_manifest_entry_missing_from_bundle_is_not_silently_ignored(bundle):
    """A manifest that promises a file the bundle lacks must still fail closed.

    The copy-by-manifest loop skips entries it cannot find in $SRC. If that skip
    also silenced verification, an incomplete bundle would install and report
    success -- the same silent no-op class this whole path exists to prevent.
    """
    (bundle["src"] / "VERSION").write_text("build_id=other\n")  # hash now stale
    r = _run(bundle)
    assert r.returncode != 0, (
        "a bundle whose VERSION does not match its manifest must not report success")
    assert "VERIFY FAILED" in r.stderr


def test_hook_is_installed_even_when_a_copy_is_skipped(bundle):
    """Ordering guard: the hook step must be reachable after the copy loops.

    The v114 failure was an early exit *before* the hook block. If a future edit
    moves verification after the hook, or makes a copy failure non-fatal, this
    catches the drift: both outcomes are asserted together, so a script that
    installs files but not the hook cannot pass.
    """
    r = _run(bundle)
    assert r.returncode == 0, f"installer failed:\n{r.stdout}\n{r.stderr}"
    assert "verified every manifest entry" in r.stdout, (
        f"verification did not complete: {r.stdout}")
    assert "boot hook installed and verified" in r.stdout, (
        f"hook step never ran: {r.stdout}")


def test_truncated_manifest_does_not_claim_full_verification(bundle):
    """A damaged manifest must not report that everything was checked.

    Reproduced against the shipped v114 kit: with polaris-astro.manifest cut to
    5 of its 39 lines -- what bad sectors or a partial copy produce -- the loop
    parsed the surviving lines, found nothing wrong with them, printed "verified
    every manifest entry", installed the boot hook and exited 0. Thirty-four
    load-bearing files went unchecked, polaris-httpd among them. The word "every"
    made a partial check indistinguishable from a complete one, which is exactly
    the class of silent no-op this block exists to prevent.

    The manifest is read as a stream, so truncation is invisible without counting:
    the file is still valid text up to the point where it stops.
    """
    manifest = bundle["src"] / "polaris-astro.manifest"
    lines = manifest.read_text().splitlines()
    assert len(lines) > 5, "fixture manifest too short to test truncation"
    manifest.write_text("\n".join(lines[:5]) + "\n")

    r = _run(bundle)
    assert r.returncode != 0, (
        "a truncated manifest must not pass silently:\n"
        f"rc={r.returncode}\n{r.stdout}\n{r.stderr}")
    assert "not listed" in r.stderr and "never compared" in r.stderr, (
        f"the failure must name the manifest as the fault: {r.stderr}")
    assert not bundle["hook"].is_file(), (
        "a truncated manifest must fail before the boot hook is installed")


def test_empty_manifest_fails_closed(bundle):
    """A zero-length manifest is a damaged bundle, not "nothing to verify".

    Without the guard this reports success and installs the boot hook while
    comparing nothing, reintroducing the #292 silent no-op by packaging rather
    than by code.
    """
    (bundle["src"] / "polaris-astro.manifest").write_text("")
    r = _run(bundle)
    assert r.returncode != 0, (
        f"an empty manifest must not report success:\n{r.stdout}\n{r.stderr}")


def test_malformed_hash_is_reported_as_manifest_damage(bundle):
    """A corrupt hash must say the manifest is damaged, not that a file differs.

    "VERIFY FAILED: x" sends the operator to re-copy the payload; the real fault
    is the manifest itself, so re-extracting the wrong thing wastes the attempt.
    Bad sectors mid-file and CRLF text from Windows both land here.
    """
    manifest = bundle["src"] / "polaris-astro.manifest"
    lines = manifest.read_text().splitlines()
    name = lines[3].split()[1]
    manifest.write_text("\n".join(
        [("z" * 64) + "  " + name if i == 3 else l for i, l in enumerate(lines)
    ]) + "\n")

    r = _run(bundle)
    assert r.returncode != 0, "a malformed hash must fail the install"
    assert "MANIFEST CORRUPT" in r.stderr, (
        f"a non-hex hash should be attributed to the manifest: {r.stderr}")


def test_success_line_reports_the_count_it_actually_checked(bundle):
    """The count must match the fixture's entry count, not merely be present.

    Guards the falsifiability itself: if the counter were wired to the wrong
    variable the line would still print a number and still read as success.
    """
    r = _run(bundle)
    assert r.returncode == 0, f"installer failed:\n{r.stdout}\n{r.stderr}"
    n = len((bundle["src"] / "polaris-astro.manifest").read_text().splitlines())
    assert f"({n} of {n})" in r.stdout, (
        f"expected a verified count of {n}: {r.stdout}")


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
