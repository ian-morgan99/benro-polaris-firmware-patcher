"""setup-wifi.sh must never put the Wi-Fi passphrase in a process argument.

Issue #290: the script's own header promised the password was "never passed as a
command-line argument (which would show in `ps`)", while the code did exactly that:

    "$WDIR/wpa_passphrase" "$SSID" "$PSK"

/proc is mounted on the Polaris, so any process could read the plaintext PSK out of
/proc/<pid>/cmdline for as long as wpa_passphrase ran -- and it would also appear in
`ps` output. The promise in the header was the only thing asserting otherwise, which is
why this survived review: the claim and the code were read as one document rather than
the claim being checked against the code.

wpa_passphrase reads the passphrase from stdin when given only the SSID, and produces a
byte-identical psk= line -- confirmed on the device's own build (both forms yielded
psk=0dbc7b0941498453168217919aa3706b8b4fe1e15c9159fc1094c6dd17559125 for the same
inputs). The stdin form additionally prints a "# reading passphrase from stdin" banner,
which must be stripped alongside the existing "#psk=" plaintext comment or the password
lands in the config file.

The behavioural test runs the real script against a stub that reproduces the device's
observed output, and asserts on what the child process actually received rather than on
the script's text.
"""

import os
import re
import stat
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "container" / "astro" / "ondisk" / "setup-wifi.sh"

SSID = "TestNetwork"
PSK = "hunter2hunter2"
# The hash the device's wpa_passphrase returns for SSID/PSK above, captured from it.
EXPECTED_PSK = "0dbc7b0941498453168217919aa3706b8b4fe1e15c9159fc1094c6dd17559125"

# Stub that mirrors the device build's observed behaviour, including the banner that
# only appears when the passphrase arrives on stdin. The printf %s specifiers belong to
# the shell, so the hash is injected via a literal token rather than Python %-formatting.
STUB = """#!/bin/sh
printf '%s\\n' "ARGV|$1|$2" >> "$ARGV_LOG"
if [ -n "$2" ]; then
  printf 'network={\\n\\tssid="%s"\\n\\t#psk="%s"\\n\\tpsk=__HASH__\\n}\\n' "$1" "$2"
else
  read P
  printf '# reading passphrase from stdin\\nnetwork={\\n\\tssid="%s"\\n\\t#psk="%s"\\n\\tpsk=__HASH__\\n}\\n' "$1" "$P"
fi
"""


def _run_script(tmp_path: Path) -> tuple[subprocess.CompletedProcess, Path, Path]:
    """Run the real setup-wifi.sh against a stub wpa_passphrase that logs its argv."""
    kit = tmp_path / "polaris-wifi"
    kit.mkdir()

    argv_log = tmp_path / "argv.log"
    stub = kit / "wpa_passphrase"
    stub.write_text(STUB.replace("__HASH__", EXPECTED_PSK))
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    env = dict(os.environ, WIFI_DIR=str(kit), ARGV_LOG=str(argv_log))
    proc = subprocess.run(
        ["sh", str(SCRIPT)],
        input=f"{SSID}\n{PSK}\n",
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    return proc, kit / "wpa.conf", argv_log


# ── the promise in the header, checked against the code ───────────────────────────

def test_passphrase_is_not_passed_as_an_argument():
    text = SCRIPT.read_text()
    assert re.search(r'wpa_passphrase"\s+"\$SSID"\s+"\$PSK"', text) is None, (
        "setup-wifi.sh passes $PSK as a command-line argument to wpa_passphrase; "
        "/proc is mounted on the device so any process can read it from cmdline"
    )
    assert re.search(r'printf\s+\'%s\\n\'\s+"\$PSK"\s*\|\s*"\$WDIR/wpa_passphrase"\s+"\$SSID"', text), (
        'setup-wifi.sh must pipe the passphrase into wpa_passphrase on stdin, e.g. '
        'printf \'%s\\n\' "$PSK" | "$WDIR/wpa_passphrase" "$SSID"'
    )


def test_both_plaintext_output_forms_are_stripped():
    """wpa_passphrase emits two plaintext lines; both must be filtered out.

    The #psk= comment was already handled. The stdin form adds a banner, and filtering
    only the comment would write the passphrase into wpa.conf -- a worse leak than the
    one being fixed.
    """
    text = SCRIPT.read_text()
    assert "#psk=" in text or re.search(r"#psk=", text), "the #psk= filter was removed"
    assert "reading passphrase" in text, (
        "the '# reading passphrase from stdin' banner must be stripped too, or the "
        "plaintext password is written into wpa.conf"
    )


def test_header_claim_matches_the_code():
    """The header must not claim something the code does not do.

    This is how #290 survived: the comment asserted argv-free handling and reviewers read
    it as fact instead of checking the invocation below it.
    """
    text = SCRIPT.read_text()
    header = text.split("WDIR=")[0]
    assert "command-line" in header, "header should state how the passphrase is passed"
    # Whatever the header promises, argv must not carry the secret -- asserted behaviourally
    # below; here just ensure the header describes stdin rather than denying a mechanism.
    assert re.search(r"stdin|standard input", header), (
        "the header should say the passphrase is handed to wpa_passphrase on stdin"
    )


# ── behavioural: what the child process actually received ─────────────────────────

def test_child_process_receives_no_passphrase_in_argv(tmp_path):
    proc, conf, argv_log = _run_script(tmp_path)
    assert proc.returncode == 0, f"setup-wifi.sh failed: {proc.stderr}"

    recorded = argv_log.read_text().strip().splitlines()
    assert recorded, "stub wpa_passphrase never ran"
    for line in recorded:
        _, ssid_arg, psk_arg = line.split("|", 2)
        assert ssid_arg == SSID, f"SSID argument wrong: {ssid_arg!r}"
        assert psk_arg == "", (
            f"wpa_passphrase received a passphrase in argv ({psk_arg!r}); "
            "it must arrive on stdin"
        )
        assert PSK not in line, "the plaintext passphrase reached the child's argv"


def test_resulting_config_has_hash_and_no_plaintext(tmp_path):
    proc, conf, _ = _run_script(tmp_path)
    assert proc.returncode == 0, f"setup-wifi.sh failed: {proc.stderr}"

    body = conf.read_text()
    assert EXPECTED_PSK in body, (
        "wpa.conf does not carry the expected psk hash -- the stdin form must produce "
        "the same hash as the argv form"
    )
    assert PSK not in body, "plaintext password present in wpa.conf"
    assert "#psk=" not in body, "wpa_passphrase's plaintext #psk= comment was not stripped"
    assert "reading passphrase" not in body, "the stdin banner was not stripped"


def test_config_written_with_private_mode(tmp_path):
    """The hash alone is enough to join the network, so the file is a credential."""
    proc, conf, _ = _run_script(tmp_path)
    assert proc.returncode == 0, f"setup-wifi.sh failed: {proc.stderr}"
    mode = stat.S_IMODE(conf.stat().st_mode)
    assert mode == 0o600, f"wpa.conf mode is {oct(mode)}, expected 0o600"


def test_no_temp_file_left_behind(tmp_path):
    """The config is built in .wpa.tmp; a leftover would hold the same credential."""
    proc, conf, _ = _run_script(tmp_path)
    assert proc.returncode == 0, f"setup-wifi.sh failed: {proc.stderr}"
    leftovers = [p.name for p in conf.parent.iterdir() if p.name.startswith(".wpa")]
    assert not leftovers, f"temporary credential file left behind: {leftovers}"
