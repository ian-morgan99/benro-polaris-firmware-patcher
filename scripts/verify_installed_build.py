#!/usr/bin/env python3
"""Fail-closed comparison of a candidate and installed Polaris identity."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REQUIRED_PROVENANCE = ("build_id", "patcher_commit", "git_commit", "display_fwver")
FWVER_RE = re.compile(r"(?:^|;)FwVer:([^;\r\n]+)")


def read_key_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"{path}:{number}: expected key=value")
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"{path}:{number}: empty key")
        values[key] = value.strip()
    return values


def read_fwver(path: Path) -> str:
    raw = path.read_text(encoding="utf-8").strip()
    match = FWVER_RE.search(raw)
    if not match:
        raise ValueError(f"{path}: no FwVer:<version>; field")
    return match.group(1)


def compare(candidate_provenance: Path, device_provenance: Path,
            candidate_fwver: Path, device_fwver: Path) -> list[str]:
    """Return mismatch/error strings; an empty list means identity matches."""
    errors: list[str] = []
    try:
        expected = read_key_values(candidate_provenance)
    except (OSError, ValueError) as exc:
        return [f"candidate provenance unreadable: {exc}"]
    try:
        actual = read_key_values(device_provenance)
    except (OSError, ValueError) as exc:
        return [f"device provenance unreadable: {exc}"]

    for key in REQUIRED_PROVENANCE:
        if not expected.get(key):
            errors.append(f"candidate missing {key}")
        if not actual.get(key):
            errors.append(f"device missing {key}")
        if expected.get(key) and actual.get(key) and expected[key] != actual[key]:
            errors.append(f"{key}: expected={expected[key]!r} actual={actual[key]!r}")

    try:
        expected_fwver = expected.get("display_fwver", "")
        candidate_fwver_value = read_fwver(candidate_fwver)
        actual_fwver = read_fwver(device_fwver)
    except (OSError, ValueError) as exc:
        errors.append(f"FwVer unreadable: {exc}")
    else:
        if not expected_fwver:
            errors.append("candidate missing display_fwver")
        if expected_fwver != candidate_fwver_value:
            errors.append(
                f"candidate FwVer: provenance={expected_fwver!r} package={candidate_fwver_value!r}"
            )
        if expected_fwver != actual_fwver:
            errors.append(f"display_fwver: expected={expected_fwver!r} actual={actual_fwver!r}")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-provenance", type=Path, required=True)
    parser.add_argument("--device-provenance", type=Path, required=True)
    parser.add_argument("--candidate-fwver", type=Path, required=True)
    parser.add_argument("--device-fwver", type=Path, required=True)
    args = parser.parse_args(argv)

    errors = compare(args.candidate_provenance, args.device_provenance,
                     args.candidate_fwver, args.device_fwver)
    if errors:
        print("INSTALLED BUILD IDENTITY: FAIL")
        for error in errors:
            print(f"  {error}")
        return 1
    candidate = read_key_values(args.candidate_provenance)
    print("INSTALLED BUILD IDENTITY: PASS")
    print(f"  build_id={candidate['build_id']}")
    print(f"  display_fwver={candidate['display_fwver']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
