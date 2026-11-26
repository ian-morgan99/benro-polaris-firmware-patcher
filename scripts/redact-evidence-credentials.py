#!/usr/bin/env python3
"""Redact account credentials from tracked evidence logs (issue N1).

Targets the vendor account-flow fields seen in Mlog dumps:
  password:<base64>   securityA:<base64>   and the two known plaintext base64 values.
Replaces only the value, never the key, so log structure stays analysable.
"""
import re
import sys
from pathlib import Path

FILES = [
    "docs/evidence/benro-connect-crash-20261010/raw/Mlog_000276.txt",
    "docs/evidence/issue-297-k3iii-stale-restart-lock/api-link-opcodes.json",
    "docs/evidence/liveview-crash-camera-offbus-20261103/raw/Mlog_000356.clean.txt",
    "docs/evidence/o-v13t-preinstall-state-20260929-132320/Mlog_000169.txt",
    "docs/evidence/o-v13t-preinstall-state-20260929-132320/Mlog_000170.txt",
    "docs/evidence/o-v13t-preinstall-state-20260929-132320/Mlog_000171.txt",
    "docs/evidence/v104-k1ii-android-20261110/Mlog-android-baseline.txt",
    "docs/evidence/v104-k1ii-liveview-garbled-20261110/Mlog-post-reboot-camera-not-detected.txt",
]

# key:value where value is base64-ish; keep the key for analysis.
KEYED = re.compile(r"(password|securityA|passwd|pwd)(\s*[:=]\s*)([A-Za-z0-9+/]{4,}={0,2})", re.I)
# bare known values (base64 of "1234" and "Christopher")
BARE = re.compile(r"\b(MTIzNA==|Q2hyaXN0b3BoZXI=)\b")

TOTAL = 0
for rel in FILES:
    p = Path(rel)
    if not p.exists():
        print(f"MISSING {rel}")
        continue
    text = p.read_text(errors="replace")
    n1 = len(KEYED.findall(text))
    n2 = len(BARE.findall(text))
    new = KEYED.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED-B64]", text)
    new = BARE.sub("[REDACTED-B64]", new)
    if new != text:
        p.write_text(new)
    TOTAL += n1 + n2
    print(f"{rel}: keyed={n1} bare={n2}")

print(f"TOTAL redactions: {TOTAL}")
sys.exit(0)
