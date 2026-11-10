"""The astro kit must be installed by a script, never by hand after a flash.

A firmware flash replaces appfs, and /app/astro plus its boot hook live there, so
every flash deletes the plate solver. That step has to be repeated on every
release and was never scripted, so it got done by hand and drifted: scp cannot
work against this device at all (sshd has no sftp-server subsystem), hand staging
tended to copy polaris-astro/ only, and nothing verified install_astro.sh had
actually run. The result was a device with the right FwVer, an empty /app/astro,
no boot hook and port 8090 closed -- reported by testers as "8090 unreachable".

These tests pin the fix in place without touching Docker, the network or hardware.
"""

from pathlib import Path
import os
import re
import stat
import subprocess

ROOT = Path(__file__).resolve().parents[1]
KIT_SCRIPT = ROOT / "scripts/release/install-astro-kit.sh"
FLASH_SCRIPT = ROOT / "scripts/release/release-fwpkt.sh"


def test_kit_installer_exists_and_is_executable():
    assert KIT_SCRIPT.is_file(), f"{KIT_SCRIPT} is missing"
    mode = KIT_SCRIPT.stat().st_mode
    assert mode & stat.S_IXUSR, f"{KIT_SCRIPT} is not executable in the working tree"
    # Shipped scripts have been committed non-executable before (#308), which
    # makes them unrunnable straight out of a fresh clone.
    listed = subprocess.run(
        ["git", "ls-files", "-s", str(KIT_SCRIPT.relative_to(ROOT))],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    if listed.stdout.strip():
        assert listed.stdout.split()[0] == "100755", (
            f"{KIT_SCRIPT.name} must be mode 100755 in git, got {listed.stdout.split()[0]}"
        )


def _code_lines(path):
    """Script body with comments and the header docstring removed.

    The header deliberately says the word scp to explain why it cannot be used,
    so a naive search over the whole file matches prose and fails.
    """
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines)


def test_kit_installer_is_bash_clean_and_posix_remote():
    subprocess.run(["bash", "-n", str(KIT_SCRIPT)], check=True)
    text = KIT_SCRIPT.read_text(encoding="utf-8")
    code = _code_lines(KIT_SCRIPT)
    # scp cannot work here: sshd has no sftp-server subsystem, so it dies with
    # "Connection closed", and legacy `scp -O` hangs. Only tar over ssh works.
    assert not re.search(r"(?<![\w/-])scp\s", code), "kit staging must not use scp"
    assert "tar czf -" in text and "tar xzf - -C /app/sd" in text, (
        "kit staging must stream one tar archive over ssh into /app/sd"
    )


def test_kit_installer_fails_closed_on_the_three_known_faults():
    text = KIT_SCRIPT.read_text(encoding="utf-8")
    # 1. A kit that installed nothing but looked fine (#312 / the .104 report).
    assert "boot hook installed ->" in text, "must require install_astro.sh to confirm the hook"
    assert "port8090=1" in text, "must require port 8090 to be listening"
    assert "/app/astro/polaris-httpd" in text, "must require polaris-httpd on disk"
    # 2. A truncated transfer read as a successful install.
    assert "ASTRO-MANIFEST.sha256" in text and "sha256sum -c" in text, (
        "staged bytes must be verified against the candidate manifest"
    )
    # 3. ENOSPC on /app killing the installer before the hook was written (#312).
    assert re.search(r"df -k /app", text), "must check free space on /app first"


def test_flash_installer_runs_the_kit_step_by_default():
    text = FLASH_SCRIPT.read_text(encoding="utf-8")
    assert "INSTALL_KIT=1" in text, (
        "the astro kit must be installed by default after a flash; making it "
        "opt-in is how 8090 came back closed on .104"
    )
    assert "install-astro-kit.sh" in text, "release-fwpkt.sh must invoke the kit installer"
    # Staged-only runs never flashed anything, so there is nothing to restore.
    assert 'SKIP_TRIGGER" = "1"' in text.split("7. Astro kit")[1], (
        "phase 7 must be skipped when no flash was triggered"
    )


def test_kit_installer_refuses_a_candidate_without_a_kit(tmp_path):
    empty = tmp_path / "candidate"
    (empty / "astro-bundle" / "COPY-TO-SD-CARD-ROOT").mkdir(parents=True)
    result = subprocess.run(
        ["bash", str(KIT_SCRIPT), str(empty)],
        text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 2
    assert "carries no astro kit" in result.stderr


def test_kit_installer_refuses_a_kit_with_no_manifest(tmp_path):
    # A shipped kit with no manifest cannot be verified, and one did install
    # nothing while reporting success.
    candidate = tmp_path / "candidate"
    kit = candidate / "astro-bundle" / "COPY-TO-SD-CARD-ROOT" / "polaris-astro"
    kit.mkdir(parents=True)
    (kit / "install_astro.sh").write_text("#!/bin/sh\nexit 0\n")
    result = subprocess.run(
        ["bash", str(KIT_SCRIPT), str(candidate)],
        text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 2
    assert "cannot be verified" in result.stderr


def test_kit_installer_usage_lists_every_flag():
    result = subprocess.run(
        ["bash", str(KIT_SCRIPT), "--help"], text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0
    for flag in ("--no-indexes", "--no-wifi", "--no-boot", "--reboot", "--skip-verify"):
        assert flag in result.stdout, f"--help does not document {flag}"


def test_kit_installer_help_and_usage_are_reachable():
    # --help prints a header range; if the header grows past it the operator
    # gets a truncated usage message exactly when they need it.
    result = subprocess.run(
        ["bash", str(KIT_SCRIPT), "--help"], text=True, capture_output=True, timeout=30,
    )
    assert "install-astro-kit.sh" in result.stdout
    assert "never scp" in result.stdout.lower() or "Never scp" in result.stdout


def test_no_hand_staging_instructions_left_in_the_release_docs():
    # The docs must point at the script rather than describing a manual copy.
    doc = ROOT / "docs/FIRMWARE-INSTALL-PROCESS.md"
    text = doc.read_text(encoding="utf-8")
    assert "install-astro-kit.sh" in text, (
        "FIRMWARE-INSTALL-PROCESS.md must name the supported kit installer"
    )
