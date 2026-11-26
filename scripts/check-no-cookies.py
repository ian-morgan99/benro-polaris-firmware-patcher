#!/usr/bin/env python3
"""Fail if any tracked file contains account credentials (issue N1).

Scans the git index, not the working tree, so gitignored files (which is where
device logs live, via docs/evidence/**/*.log) are correctly out of scope: they
never reach the repository. The patterns cover the vendor account-flow fields
seen in Mlog dumps plus the two known plaintext base64 values.

Note this deliberately covers EVERY file type. An earlier proposal scoped the
guard to *.log, which would have missed all eight credential-bearing files that
were actually committed -- they are .txt and .json.
"""
import re
import subprocess
import sys

# Anchored on the vendor account-flow field names only. Deliberately does NOT
# match a bare `pwd` (that is a shell environment variable in captured process
# dumps, e.g. PWD=/home/ian) and does NOT match SSIDs, which are public device
# names such as polaris_d13e86 and carry no secret.
PATTERNS = [
    (r"(?i)\b(password|securityA|passwd)\s*[:=]\s*[A-Za-z0-9+/]{4,}={0,2}",
     "keyed credential value"),
    (r"\bMTIzNA==\b", "base64 of a known test password"),
    (r"\bQ2hyaXN0b3BoZXI=\b", "base64 of a known account name"),
    (r"(?i)\b(wps_psk|wpa_psk|psk)\s*[:=]\s*[A-Za-z0-9]{8,}", "WiFi pre-shared key"),
]

# Redaction marker we emit ourselves; never a finding.
ALLOW = re.compile(r"\[REDACTED")

# Paths that must not be scanned:
#  * this guard and the redactor, which necessarily contain the credential
#    patterns as literal regex definitions -- scanning them is self-referential;
#  * test files, which legitimately hold fixture secrets (psk=testpass123 and
#    the EXPECTED_PSK hash derived from PSK="hunter2hunter2" in
#    tests/test_setup_wifi_psk_not_in_argv.py). Those are behavioural-test inputs,
#    not leaked material, and failing on them would only train people to ignore
#    the guard. Evidence logs and operational scripts are still checked.
SKIP_PATH = re.compile(
    r"(scripts/check-no-cookies\.py$|scripts/redact-evidence-credentials\.py$"
    r"|(^|/)(tests?/|test_[^/]*\.py$|[^/]*_test\.py$))"
)


def tracked_files():
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True)
    return [f for f in out.stdout.split("\n") if f and not SKIP_PATH.search(f)]


def main():
    findings = []
    for path in tracked_files():
        try:
            with open(path, "r", errors="replace") as fh:
                for lineno, line in enumerate(fh, 1):
                    if ALLOW.search(line):
                        continue
                    for pat, label in PATTERNS:
                        if re.search(pat, line):
                            findings.append((path, lineno, label))
                            break
        except (OSError, UnicodeDecodeError):
            continue

    if not findings:
        print(f"CREDENTIAL GUARD: PASS ({len(tracked_files())} tracked files clean)")
        return 0

    print(f"CREDENTIAL GUARD: FAIL ({len(findings)} finding(s))")
    for path, lineno, label in findings[:40]:
        print(f"  {path}:{lineno}: {label}")
    print("\nRedact with: python3 scripts/redact-evidence-credentials.py")
    return 1


if __name__ == "__main__":
    sys.exit(main())
