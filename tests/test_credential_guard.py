"""Regression coverage for the credential guard (issue N1).

Why this exists: scripts/check-no-cookies.py was written to catch credential
material reaching the repository, but nothing invoked it and nothing tested it.
A leak-detection check that nobody runs is worse than none, because it advertises
protection that does not exist -- and a detector whose patterns can silently stop
matching is the same failure in a different shape.

Two distinct things are covered here:

1. The detection logic itself, exercised against synthetic strings. This never
   touches the git index, so it cannot be affected by what happens to be staged.
2. That the guard actually runs green on the committed tree, i.e. the wiring in
   tests/run_prerelease_gate.sh has a real subject and the eight files redacted
   for N1 have not regressed.

The synthetic values are deliberately the two base64 strings the guard already
knows about (a well-known default PIN and a test account name). They are fixture
input, not leaked material -- the same reasoning that makes the guard skip tests/
(see SKIP_PATH in check-no-cookies.py).
"""
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts" / "check-no-cookies.py"


def _load_guard():
    spec = importlib.util.spec_from_file_location("check_no_cookies", GUARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GUARD_MODULE = _load_guard()


def _hits(line):
    """True if any guard pattern matches `line` and the redaction marker does not."""
    if GUARD_MODULE.ALLOW.search(line):
        return False
    return any(GUARD_MODULE.re.search(pat, line) for pat, _ in GUARD_MODULE.PATTERNS)


# The exact shape found in Mlog dumps from the vendor account flow (code:790).
LEAKY = [
    "msgToApp success;type[2],code[790],val[step:1;password:MTIzNA==;securityQ:3;securityA:MTIzNA==]",
    "val[step:1;password:Q2hyaXN0b3BoZXI=;securityQ:3]",
    "password=MTIzNA==",
    "passwd: MTIzNA==",
    "wps_psk:supersecretkey123",
]

# Shapes that must NOT trip the guard. Each of these appears in real captured
# device output, so a false positive here means the guard gets disabled by
# whoever next runs it -- which is exactly how the original leak survived.
CLEAN = [
    # The redaction marker we emit ourselves. Note "REDACTED" is itself
    # alphanumeric, so an unanchored pattern matches it; ALLOW must win first.
    "val[step:1;password:[REDACTED];securityQ:3;securityA:[REDACTED]]",
    # PWD is a shell environment variable in process dumps, not a credential.
    "PWD=/home/ian/Documents/VSCodeProjects/BenroPolarisPatcher",
    # SSIDs are public device names and carry no secret.
    "ssid:polaris_d13e86",
    # A bare word, no key=value shape.
    "password prompt dismissed by user",
    # Field present but empty.
    "password:[]",
]


def test_guard_detects_known_leak_shapes():
    for line in LEAKY:
        assert _hits(line), f"guard failed to detect: {line[:60]}"


def test_guard_does_not_flag_benign_shapes():
    for line in CLEAN:
        assert not _hits(line), f"guard false-positive on: {line[:60]}"


def test_redaction_marker_is_never_a_finding():
    # The real contract between the two tools: whatever the redactor emits must
    # read as clean to the guard. If this breaks, every redacted file reports as
    # still leaking -- which is exactly how a guard gets switched off by whoever
    # next runs it.
    #
    # scripts/redact-evidence-credentials.py substitutes `[REDACTED-B64]` for both
    # the keyed and bare forms, and the guard's ALLOW requires a literal '[REDACTED',
    # so the two agree. The marker is asserted here as a literal rather than by
    # importing the redactor: that script has no import guard and runs its main()
    # on import, which would rewrite files during a test run.
    #
    # If either tool's marker changes, this test must change with it -- that is the
    # point, not an inconvenience.
    marker = "[REDACTED-B64]"
    # Only the shapes the redactor actually rewrites: KEYED covers
    # password|securityA|passwd|pwd and BARE covers the two known base64 values.
    for line in [leaky for leaky in LEAKY if "psk" not in leaky]:
        redacted = re.sub(
            r"(password|securityA|passwd)(\s*[:=]\s*)\S+", rf"\g<1>\g<2>{marker}", line
        )
        redacted = re.sub(r"\b(MTIzNA==|Q2hyaXN0b3BoZXI=)\b", marker, redacted)
        assert not _hits(redacted), f"redactor output still flagged: {redacted[:70]}"


def test_psk_is_detected_but_not_auto_redactable():
    # Documents a real asymmetry found while wiring this up, rather than hiding it.
    # The guard flags wps_psk/wpa_psk/psk, but scripts/redact-evidence-credentials.py
    # only rewrites password|securityA|passwd|pwd and two bare base64 values -- so a
    # PSK finding has no automated remediation, and the guard's own advice
    # ("Redact with: python3 scripts/redact-evidence-credentials.py") would be a dead
    # end for it. The redactor is also hardcoded to eight specific paths, so it cannot
    # redact newly committed files at all.
    #
    # This test pins current behaviour so that if either tool changes, the other's
    # gap becomes visible instead of silently assumed fixed. PSK exposure in evidence
    # needs a real fix (extend the redactor, or drop the pattern); until then it is
    # caught at the gate and must be handled by hand.
    psk_line = "wps_psk:supersecretkey123"
    assert _hits(psk_line), "guard should still detect PSK material"

    redactor_text = (ROOT / "scripts" / "redact-evidence-credentials.py").read_text()
    assert "psk" not in redactor_text.lower(), (
        "the redactor now handles PSKs -- update this test and the guard's advice, "
        "since automated remediation is then available"
    )


def test_unbracketed_redaction_is_still_flagged():
    # Pins the deliberate boundary above: ALLOW only suppresses the bracketed form
    # the tools emit. An unbracketed marker is not one of our markers, so it must
    # still be reported rather than silently allowed through.
    assert _hits("password:REDACTED")


def test_guard_runs_and_passes_on_committed_tree():
    """The gate invokes this script; prove it is runnable and currently clean."""
    result = subprocess.run(
        [sys.executable, str(GUARD)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "credential guard is failing on the committed tree:\n" + result.stdout
    )
    assert "CREDENTIAL GUARD: PASS" in result.stdout


def test_guard_is_registered_in_the_prerelease_gate():
    """The whole point of the wiring: the gate must actually call the guard.

    Without this assertion the check can be deleted from run_prerelease_gate.sh
    and every other test here still passes -- which is precisely how the guard
    came to be unwired in the first place.
    """
    gate = (ROOT / "tests" / "run_prerelease_gate.sh").read_text()
    assert "check-no-cookies.py" in gate, "guard is not invoked by the pre-release gate"
    assert "check_credentials_not_in_tracked_files" in gate, (
        "guard check is defined but never invoked in the gate"
    )
