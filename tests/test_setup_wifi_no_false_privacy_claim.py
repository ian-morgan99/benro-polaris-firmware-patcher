"""setup-wifi.sh must not claim the PSK file is private when it cannot be (#302).

Issue #302: /app/sd is vfat mounted fmask=0022. vfat has no per-file permission
model, so `chmod 600` returns success and changes nothing -- proved on the device
by the reporter with a throwaway probe (touch, chmod 600, ls -l -> still 755). The
result is that wpa.conf, which holds a WPA2 PSK hash sufficient to join the network
without the passphrase, sits world-readable at 755.

This is not a bug in the script's logic and no chmod can fix it; the reporter is
right that the fix is either to move the config to UBIFS (/var/lib/polaris, where
chmod works) or to stop claiming protection. Moving it is a distribution decision
with a compatibility fallback to design, so it is not made here. What IS fixed here
is the lie: the header said "the file is chmod 600 -- treat it as a credential", and
the comment written into wpa.conf itself said "keep it private". Both asserted a
property the filesystem cannot provide. A false security claim is worse than none,
because someone reading it will reasonably conclude the secret is protected and stop
thinking about it.

These tests assert on the CLAIMS rather than on the mode, because the mode is the
thing we cannot change without the relocation decision. Note that
test_setup_wifi_psk_not_in_argv.py::test_config_written_with_private_mode asserts
0o600 -- that passes on ext4 where chmod works, and it is precisely why this survived
review: the test validated the behaviour on a filesystem that honours chmod, not the
one the file actually lives on. That test stays, because the chmod is still correct
for a filesystem that honours it; what was wrong was relying on it as protection.

The stub mirrors the device's wpa_passphrase, including both plaintext lines the
script must strip: the #psk="..." comment and the stdin banner.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "container" / "astro" / "ondisk" / "setup-wifi.sh"

SSID = "TestNetwork"
PSK = "hunter2hunter2"
# Hash the device's own wpa_passphrase produces for SSID/PSK above.
EXPECTED_PSK = "0dbc7b0941498453168217919aa3706b8b4fe1e15c9159fc1094c6dd17559125"

# Reads the passphrase from stdin when given only the SSID, exactly like the device
# build, and emits both plaintext lines the script is required to strip. The hash is
# injected as a literal token because the printf %s specifiers belong to the shell.
STUB = """#!/bin/sh
if [ -n "$2" ]; then
  printf 'network={\\n\\tssid="%s"\\n\\t#psk="%s"\\n\\tpsk=__HASH__\\n}\\n' "$1" "$2"
else
  read P
  printf '# reading passphrase from stdin\\nnetwork={\\n\\tssid="%s"\\n\\t#psk="%s"\\n\\tpsk=__HASH__\\n}\\n' "$1" "$P"
fi
"""


def _run(wdir: Path):
    """Run the real script against the stub in a throwaway WIFI_DIR."""
    (wdir / "wpa_passphrase").write_text(STUB.replace("__HASH__", EXPECTED_PSK))
    (wdir / "wpa_passphrase").chmod(0o755)
    proc = subprocess.run(
        ["sh", str(SCRIPT)], input=f"{SSID}\n{PSK}\n",
        capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "WIFI_DIR": str(wdir)},
    )
    return proc, wdir / "wpa.conf"


def test_header_no_longer_presents_chmod_as_protection():
    """The old wording was 'the file is chmod 600 -- treat it as a credential'.

    The second clause is still true; the first implies the permissions hold, and on
    vfat they do not.
    """
    text = SCRIPT.read_text(encoding="utf-8")
    assert re.search(r"chmod 600\s*--\s*treat it as a credential", text) is None, (
        "the header again presents `chmod 600` as if it protects the file; on vfat "
        "(fmask=0022) chmod is a no-op and wpa.conf is world-readable (#302)"
    )


def test_header_states_the_real_exposure():
    """A reader must learn who can actually read the secret, not just that it is sensitive."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "vfat" in text.lower(), "header should name the filesystem that defeats chmod"
    assert "fmask" in text, "header should cite fmask=0022 as the cause"
    assert re.search(
        r"world-readable|readable by every process|anyone who puts the card", text, re.I
    ), "header must state the actual audience for the credential (#302)"


def test_generated_config_does_not_tell_the_reader_to_keep_it_private():
    """The comment written INTO wpa.conf is what a user sees with `cat`.

    It used to say 'keep it private'. That instruction cannot be carried out on the
    card the file lives on, and it reassures exactly the person who should be worried.
    """
    with tempfile.TemporaryDirectory() as td:
        proc, conf = _run(Path(td))
        assert proc.returncode == 0, f"setup-wifi.sh failed: {proc.stderr}"
        body = conf.read_text(encoding="utf-8")

    assert "keep it private" not in body.lower(), (
        "wpa.conf still tells the reader to keep it private; vfat cannot enforce that, "
        "so the line is false reassurance (#302)"
    )
    assert re.search(r"vfat|cannot be made private", body, re.I), (
        "wpa.conf should state plainly that permissions do not protect it"
    )
    # Honesty must not break the file's actual purpose.
    assert EXPECTED_PSK in body, "PSK hash missing: the honesty edit broke the output"
    assert PSK not in body, "plaintext password leaked into wpa.conf"
    assert "#psk=" not in body, "wpa_passphrase's plaintext #psk= comment was not stripped"
    assert "reading passphrase" not in body, "the stdin banner was not stripped"


def test_summary_reports_the_mode_that_was_actually_stored():
    """Report real permissions rather than the ones we asked for.

    Asking for 600 and printing nothing lets the operator believe it took effect --
    which is how the claim stayed believed for so long.
    """
    with tempfile.TemporaryDirectory() as td:
        proc, _ = _run(Path(td))
        assert proc.returncode == 0, f"setup-wifi.sh failed: {proc.stderr}"

    assert re.search(r"file mode as stored", proc.stdout), (
        "the summary should print the mode the file actually ended up with"
    )
    # On ext4 chmod genuinely works, so no warning is due here. Asserting absence
    # proves the check keys on the real mode instead of firing unconditionally --
    # a diagnostic that always warns is one people learn to ignore.
    assert "world-readable" not in proc.stdout, (
        "warned about world-readable on a filesystem where chmod worked; the warning "
        "must be conditional on the stored mode"
    )


def test_no_temporary_credential_file_left_behind():
    """The honesty edits must not disturb cleanup."""
    with tempfile.TemporaryDirectory() as td:
        wdir = Path(td)
        proc, _ = _run(wdir)
        assert proc.returncode == 0, f"setup-wifi.sh failed: {proc.stderr}"
        leftovers = [p.name for p in wdir.iterdir()
                     if p.name not in ("wpa.conf", "wpa_passphrase")]
    assert not leftovers, f"temporary credential file left behind: {leftovers}"
