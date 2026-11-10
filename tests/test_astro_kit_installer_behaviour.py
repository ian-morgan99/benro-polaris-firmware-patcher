"""Drive install-astro-kit.sh end-to-end against a stub ssh, no device needed.

The kit installer exists because the step was hand-rolled every release and drifted:
scp cannot work here (sshd has no sftp-server subsystem), staging tended to skip
polaris-wifi/, and nothing checked that install_astro.sh had actually run -- so a
device came back with the right FwVer, an empty /app/astro, no boot hook and port 8090
closed, and looked installed.

The stub ssh runs the remote command strings LOCALLY against a fake root, using the
host's real tar and real sha256sum. That fidelity matters: an earlier version of this
harness canned the verification output, which hid a bug where the manifest scoping
pattern anchored on the line start of sha256sum's "<hash>  ./path" output and matched
zero files -- the same two-space separator that broke install_astro.sh in #312. With
real tar and real hashes, a verification step that silently checks nothing fails here.
"""

from pathlib import Path
import hashlib
import os
import subprocess

ROOT = Path(__file__).resolve().parents[1]
KIT_SCRIPT = ROOT / "scripts/release/install-astro-kit.sh"


def sha256_of(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_candidate(tmp_path, *, corrupt=None):
    """A candidate tree with a realistic ASTRO-MANIFEST.sha256.

    Lines are sha256sum's own format, "<hash>  ./<path>" with TWO spaces, and the
    hashes are real so `sha256sum -c` genuinely passes or fails.
    """
    root = tmp_path / "candidate"
    sd_root = root / "astro-bundle" / "COPY-TO-SD-CARD-ROOT"
    kit = sd_root / "polaris-astro"
    kit.mkdir(parents=True)
    (kit / "install_astro.sh").write_text("#!/bin/sh\nexit 0\n")
    (kit / "polaris-httpd").write_text("httpd-bytes\n")
    (sd_root / "polaris-wifi").mkdir()
    (sd_root / "polaris-wifi" / "setup-wifi.sh").write_text("#!/bin/sh\nexit 0\n")
    (sd_root / "astrometry").mkdir()
    (sd_root / "astrometry" / "index-4110.fits").write_text("index-bytes\n")

    lines = []
    for path in sorted(sd_root.rglob("*")):
        if not path.is_file():
            continue
        rel = "./" + str(path.relative_to(sd_root))
        digest = sha256_of(path)
        if corrupt and path.name == corrupt:
            digest = "0" * 64
        lines.append(f"{digest}  {rel}")
    (root / "astro-bundle" / "ASTRO-MANIFEST.sha256").write_text("\n".join(lines) + "\n")
    (root / "build-source-provenance.txt").write_text("build_id=astro-v99-test\n")
    return root


STUB = r"""#!/usr/bin/env bash
# Fake ssh: runs the remote command locally against $FAKE_ROOT, with real tar and
# real sha256sum, so the script's own pipelines are exercised verbatim.
echo "$*" >> "$SSH_TRACE"
cmd="${*: -1}"

# /app/sd on the device is $FAKE_ROOT/app/sd here.
rewritten=${cmd//\/app\/sd/$FAKE_ROOT/app/sd}

case "$cmd" in
  *'echo ok'*) echo ok; exit 0;;
  *'df -k /app'*) echo "$FAKE_APP_FREE_KB"; exit 0;;
  *'tar xzf - -C /app/sd'*)
    mkdir -p "$FAKE_ROOT/app/sd"
    eval "${rewritten/&& sync/}"
    exit $?;;
  *'sha256sum -c'*)
    eval "$rewritten"
    exit 0;;
  *install_astro.sh*)
    echo "[astro] boot hook installed -> /app/network_telnetd.sh"
    exit 0;;
  *'sh -s'*) echo "httpd=$FAKE_HTTPD hook=$FAKE_HOOK port8090=$FAKE_PORT"; exit 0;;
esac
exit 0
"""

NO_HOOK_STUB = STUB.replace(
    'echo "[astro] boot hook installed -> /app/network_telnetd.sh"',
    'echo "[astro] WARNING: no polaris-astro-boot.sh in the bundle; nothing will start at boot."',
)


def stub_bin(tmp_path, *, no_hook=False):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "ssh"
    stub.write_text(NO_HOOK_STUB if no_hook else STUB)
    stub.chmod(0o755)
    return bin_dir


def run_kit(candidate, bin_dir, tmp_path, *args, **overrides):
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    env["FAKE_ROOT"] = str(tmp_path / "device")
    env["FAKE_APP_FREE_KB"] = str(overrides.pop("app_free_kb", 13000))
    env["FAKE_HTTPD"] = str(overrides.pop("httpd", 1))
    env["FAKE_HOOK"] = str(overrides.pop("hook", 1))
    env["FAKE_PORT"] = str(overrides.pop("port", 1))
    env["SSH_TRACE"] = str(tmp_path / "ssh-calls.log")
    return subprocess.run(
        ["bash", str(KIT_SCRIPT), str(candidate), *args],
        text=True, capture_output=True, timeout=60, env=env, cwd=ROOT,
    )


def test_happy_path_stages_verifies_installs_and_confirms(tmp_path):
    candidate = make_candidate(tmp_path)
    result = run_kit(candidate, stub_bin(tmp_path), tmp_path, "--no-indexes")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "3 staged files verified byte-for-byte" in result.stdout
    assert "http://192.168.0.1:8090/ is serving" in result.stdout

    device_sd = tmp_path / "device" / "app" / "sd"
    assert (device_sd / "polaris-astro" / "polaris-httpd").is_file()
    # Both kits travel, not just polaris-astro: a stale polaris-wifi on the card has
    # been a real hand-staging fault.
    assert (device_sd / "polaris-wifi" / "setup-wifi.sh").is_file()
    calls = (tmp_path / "ssh-calls.log").read_text()
    assert "scp" not in calls, "must never use scp; sshd has no sftp-server"


def test_indexes_excluded_by_default(tmp_path):
    candidate = make_candidate(tmp_path)
    result = run_kit(candidate, stub_bin(tmp_path), tmp_path, "--no-indexes")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "staging: polaris-astro polaris-wifi" in result.stdout
    assert not (tmp_path / "device" / "app" / "sd" / "astrometry").exists()


def test_indexes_staged_when_requested(tmp_path):
    candidate = make_candidate(tmp_path)
    result = run_kit(candidate, stub_bin(tmp_path), tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "staging: polaris-astro polaris-wifi astrometry" in result.stdout
    assert (tmp_path / "device" / "app" / "sd" / "astrometry" / "index-4110.fits").is_file()


def test_verification_checks_a_real_number_of_files(tmp_path):
    """Guards the scoping regex against matching nothing.

    sha256sum emits "<hash>  ./path", so a caret-slash-dot pattern matches zero
    lines. Aborting on zero is the safe half; the dangerous half is verifying
    nothing and reporting success, which is what a relaxed version of that check
    would have done.
    """
    candidate = make_candidate(tmp_path)
    result = run_kit(candidate, stub_bin(tmp_path), tmp_path, "--no-indexes")
    assert "0 staged files verified" not in result.stdout
    assert "manifest has no entries" not in result.stderr


def test_fails_closed_when_a_staged_file_does_not_match(tmp_path):
    # A truncated or swapped transfer must not read as a successful install.
    candidate = make_candidate(tmp_path, corrupt="polaris-httpd")
    result = run_kit(candidate, stub_bin(tmp_path), tmp_path, "--no-indexes")
    assert result.returncode == 4
    assert "does not match the candidate manifest" in result.stderr
    assert "polaris-httpd" in result.stderr


def test_fails_closed_when_the_boot_hook_is_not_installed(tmp_path):
    candidate = make_candidate(tmp_path)
    result = run_kit(candidate, stub_bin(tmp_path, no_hook=True), tmp_path, "--no-indexes")
    assert result.returncode == 5
    assert "boot hook" in result.stderr


def test_fails_closed_when_port_8090_is_not_serving(tmp_path):
    candidate = make_candidate(tmp_path)
    result = run_kit(candidate, stub_bin(tmp_path), tmp_path, "--no-indexes", port=0)
    assert result.returncode == 5
    assert "8090" in result.stderr


def test_fails_closed_when_httpd_is_absent(tmp_path):
    candidate = make_candidate(tmp_path)
    result = run_kit(candidate, stub_bin(tmp_path), tmp_path, "--no-indexes", httpd=0)
    assert result.returncode == 5
    assert "polaris-httpd" in result.stderr


def test_fails_closed_when_app_has_no_room(tmp_path):
    # #312: ENOSPC on /app killed install_astro.sh between the binaries and the boot
    # hook, so the device booted with the solver present and nothing starting it.
    candidate = make_candidate(tmp_path)
    result = run_kit(candidate, stub_bin(tmp_path), tmp_path, "--no-indexes", app_free_kb=500)
    assert result.returncode == 3
    assert "#312" in result.stderr


def test_receipt_records_the_install(tmp_path):
    candidate = make_candidate(tmp_path)
    result = run_kit(candidate, stub_bin(tmp_path), tmp_path, "--no-indexes")
    assert result.returncode == 0, result.stdout + result.stderr
    receipt = (candidate / "install-receipt.txt").read_text()
    assert "kit_status=installed-verified" in receipt
    assert "build_id=astro-v99-test" in receipt


def test_no_receipt_written_when_verification_fails(tmp_path):
    candidate = make_candidate(tmp_path, corrupt="polaris-httpd")
    result = run_kit(candidate, stub_bin(tmp_path), tmp_path, "--no-indexes")
    assert result.returncode == 4
    assert not (candidate / "install-receipt.txt").exists(), (
        "a failed install must never be recorded as installed-verified"
    )
