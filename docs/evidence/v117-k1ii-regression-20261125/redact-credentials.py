#!/usr/bin/env python3
"""Strip Benro account credentials from pulled device logs before they are committed.

The head logs its own auth handshake verbatim, including base64-encoded account
material (`password:...`, `securityA:...`). Those are the operator's real
credentials and must never reach git. Redacted in place, and the log tarball is
rebuilt from redacted contents so no copy survives inside it either.
"""
import os
import re
import sys
import tarfile
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
PATTERNS = [
    (re.compile(rb"(password:)[A-Za-z0-9+/=]+"), rb"\1[REDACTED]"),
    (re.compile(rb"(securityA:)[A-Za-z0-9+/=]+"), rb"\1[REDACTED]"),
    (re.compile(rb"(username:[REDACTED];\"'\s]+"), rb"\1[REDACTED]"),
]


def scrub(data: bytes) -> bytes:
    for pat, repl in PATTERNS:
        data = pat.sub(repl, data)
    return data


def main() -> int:
    changed_files = 0
    hits = 0

    for dirpath, _, files in os.walk(ROOT):
        for name in files:
            path = os.path.join(dirpath, name)
            if name.endswith(".tar.gz"):
                continue
            with open(path, "rb") as fh:
                raw = fh.read()
            clean = scrub(raw)
            if clean != raw:
                hits += sum(len(p.findall(raw)) for p, _ in PATTERNS)
                with open(path, "wb") as fh:
                    fh.write(clean)
                changed_files += 1

    # Rebuild any tarball so no credential survives inside an archive member.
    for dirpath, _, files in os.walk(ROOT):
        for name in files:
            if not name.endswith(".tar.gz"):
                continue
            arc = os.path.join(dirpath, name)
            with tempfile.TemporaryDirectory() as work:
                with tarfile.open(arc, "r:gz") as tf:
                    tf.extractall(work, filter="data")
                for sub_dir, _, sub_files in os.walk(work):
                    for sub in sub_files:
                        p = os.path.join(sub_dir, sub)
                        with open(p, "rb") as fh:
                            raw = fh.read()
                        clean = scrub(raw)
                        if clean != raw:
                            hits += sum(len(pat.findall(raw)) for pat, _ in PATTERNS)
                            changed_files += 1
                            with open(p, "wb") as fh:
                                fh.write(clean)
                os.remove(arc)
                with tarfile.open(arc, "w:gz") as tf:
                    tf.add(work, arcname=".")

    print(f"redacted {hits} credential occurrence(s) across {changed_files} file(s)")

    # Fail closed: nothing matching may remain anywhere under this directory.
    residual = 0
    for dirpath, _, files in os.walk(ROOT):
        for name in files:
            if name.endswith(".tar.gz"):
                continue
            with open(os.path.join(dirpath, name), "rb") as fh:
                if any(pat.search(fh.read()) for pat, _ in PATTERNS):
                    residual += 1
    if residual:
        print(f"FAIL: {residual} file(s) still contain credentials", file=sys.stderr)
        return 1
    print("verified clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
